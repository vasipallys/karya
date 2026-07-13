"""Lazy, in-process Hugging Face chat model for ``LLM_PROVIDER=local``."""

from __future__ import annotations

import os
import threading
import time
import logging
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

# Reuse Uvicorn's configured handler so lifecycle messages are visible at the
# normal INFO level in `npm run dev:all` and packaged API logs.
logger = logging.getLogger("uvicorn.error")


class LocalModelLoadingError(RuntimeError):
    """Raised while the background loader is still preparing the model."""


class LocalModelInferenceError(RuntimeError):
    """A user-facing local inference failure without provider internals."""


_load_lock = threading.Lock()
_load_state: dict[str, Any] = {"status": "not_started", "started_at": None, "loaded_at": None, "error": None}


class LocalHuggingFaceChatModel(BaseChatModel):
    """A production-oriented Transformers adapter with background model loading.

    Loading always runs on a background daemon thread so health/config endpoints
    stay responsive and neither startup nor the request path blocks on multi-GB
    weights. It is kicked off at API startup when ``LLM_LOCAL_PRELOAD`` is on (the
    default) so the first call is fast, otherwise lazily on the first inference.
    Generation is serialized because a single Transformers model instance is not
    safe to mutate concurrently.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model_name: str
    token: str | None = Field(default=None, repr=False)
    temperature: float = 0.2
    max_new_tokens: int = 3000
    device: str = "auto"
    dtype: str = "auto"
    revision: str = "main"
    cache_dir: str | None = None
    context_window: int = 8192
    trust_remote_code: bool = False
    local_files_only: bool = False

    @property
    def _llm_type(self) -> str:
        return "local-huggingface"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model_name, "device": self.device, "dtype": self.dtype}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        runtime = _runtime(
            self.model_name,
            self.token,
            self.device,
            self.dtype,
            self.revision,
            self.cache_dir,
            self.trust_remote_code,
            self.local_files_only,
        )
        try:
            text = runtime.generate(
                _normalize_messages(messages),
                temperature=self.temperature,
                max_new_tokens=int(kwargs.get("max_new_tokens", self.max_new_tokens)),
                context_window=self.context_window,
                stop=stop or [],
            )
        except LocalModelLoadingError:
            raise
        except Exception as exc:
            raise LocalModelInferenceError(
                "Local model inference failed. Check /health and the API log for the underlying model error."
            ) from exc
        from langchain_core.messages import AIMessage

        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def _message_dict(message: BaseMessage) -> dict[str, str]:
    role = {"human": "user", "ai": "assistant", "system": "system"}.get(message.type, message.type)
    content = message.content
    if not isinstance(content, str):
        content = "\n".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
    return {"role": role, "content": content}


def _normalize_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    """Produce a Gemma-compatible alternating chat sequence.

    Karya's structured wrapper adds schema instructions as a system message while
    each feature already supplies its own system prompt. Most hosted providers
    accept consecutive system messages; Gemma's template deliberately rejects
    them. Merge all leading system instructions, then merge any adjacent equal
    roles without discarding content.
    """
    converted = [_message_dict(message) for message in messages]
    leading_system: list[str] = []
    while converted and converted[0]["role"] == "system":
        leading_system.append(converted.pop(0)["content"])
    if leading_system:
        converted.insert(0, {"role": "system", "content": "\n\n".join(leading_system)})

    normalized: list[dict[str, str]] = []
    for message in converted:
        if normalized and normalized[-1]["role"] == message["role"]:
            normalized[-1]["content"] += "\n\n" + message["content"]
        else:
            normalized.append(dict(message))
    return normalized


def _reject_unsupported_model_dir(model_name: str) -> None:
    """Fail fast with actionable guidance for a physical folder the Transformers
    runtime can't load — most commonly a GGUF (llama.cpp / LM Studio) export."""
    if not os.path.isdir(model_name):
        return
    try:
        entries = os.listdir(model_name)
    except OSError:
        return
    has_gguf = any(name.lower().endswith(".gguf") for name in entries)
    has_config = "config.json" in entries
    if has_gguf and not has_config:
        raise RuntimeError(
            f"'{model_name}' looks like a GGUF model (the llama.cpp / LM Studio format), which the in-process "
            "Transformers runtime cannot load. Either point LLM_MODEL at a standard Hugging Face checkpoint "
            "folder (config.json + *.safetensors + tokenizer files), or serve the GGUF from LM Studio / "
            "Ollama / llama.cpp and use LLM_PROVIDER=compatible with LLM_BASE_URL (e.g. "
            "http://localhost:1234/v1) instead."
        )
    if not has_config:
        raise RuntimeError(
            f"'{model_name}' is not a loadable Transformers checkpoint — no config.json was found. Point "
            "LLM_MODEL at a folder containing config.json, the model weights (*.safetensors), and the "
            "tokenizer files."
        )


class _TransformersRuntime:
    def __init__(self, model_name: str, token: str | None, device: str, dtype: str, revision: str,
                 cache_dir: str | None, trust_remote_code: bool, local_files_only: bool) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Local LLM dependencies are missing. Install them with "
                "`python -m pip install -r requirements-local.txt`."
            ) from exc

        _reject_unsupported_model_dir(model_name)

        from transformers.utils import logging as transformers_logging
        # Loading runs outside the request path; keep Transformers/tqdm progress
        # visible in the API terminal so operators can distinguish work from a hang.
        transformers_logging.enable_progress_bar()
        self.torch = torch
        self.lock = threading.Lock()
        auth = token or None
        common = dict(revision=revision, cache_dir=cache_dir, token=auth,
                      trust_remote_code=trust_remote_code, local_files_only=local_files_only)
        # Prefer the fast tokenizer, but fall back to the slow one — some on-disk
        # models (e.g. Qwen checkpoints) ship without a fast tokenizer.json. If both
        # fail for a missing backend, point at the extras that provide it.
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, **common)
        except Exception:  # noqa: BLE001 - the slow path below surfaces any real error
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False, **common)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Failed to build the tokenizer for this model. If the underlying error mentions "
                    "'sentencepiece' or 'tiktoken', install the local extras with "
                    "`python -m pip install -r requirements-local.txt` (they now include both)."
                ) from exc
        resolved_device = _resolve_device(torch, device)
        torch_dtype = _resolve_dtype(torch, dtype, resolved_device)
        # ``torch_dtype`` remains compatible with the minimum supported
        # Transformers 4.50; newer releases only emit a harmless rename warning.
        model_kwargs: dict[str, Any] = {**common, "torch_dtype": torch_dtype, "low_cpu_mem_usage": True}
        if resolved_device == "auto":
            model_kwargs["device_map"] = "auto"
        self.model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
        if resolved_device != "auto":
            self.model.to(resolved_device)
        self.model.eval()
        self.input_device = next(self.model.parameters()).device

    def warmup(self) -> None:
        """Run one throwaway token so kernel/graph init happens off the request
        path. Best-effort — a warmup failure must not fail the load."""
        try:
            self.generate([{"role": "user", "content": "ok"}], temperature=0.0,
                          max_new_tokens=1, context_window=32, stop=[])
        except Exception:  # noqa: BLE001 - warmup is advisory only
            logger.debug("Local LLM warmup pass skipped", exc_info=True)

    def generate(self, messages: list[dict[str, str]], *, temperature: float, max_new_tokens: int,
                 context_window: int, stop: list[str]) -> str:
        with self.lock, self.torch.inference_mode():
            encoded = self.tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
            )
            input_ids = encoded["input_ids"][:, -context_window:].to(self.input_device)
            attention_mask = encoded.get("attention_mask")
            if attention_mask is not None:
                attention_mask = attention_mask[:, -context_window:].to(self.input_device)
            sampling = temperature > 0
            generation = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "max_new_tokens": max_new_tokens,
                "do_sample": sampling,
                "pad_token_id": self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
                "eos_token_id": self.tokenizer.eos_token_id,
            }
            if sampling:
                generation["temperature"] = temperature
            output = self.model.generate(**generation)
            text = self.tokenizer.decode(output[0, input_ids.shape[1]:], skip_special_tokens=True).strip()
            for marker in stop:
                if marker and marker in text:
                    text = text.split(marker, 1)[0]
            return text.strip()


def _resolve_device(torch: Any, requested: str) -> str:
    requested = requested.strip().lower()
    if requested != "auto":
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(f"LLM_LOCAL_DEVICE={requested} requested but CUDA is unavailable")
        if requested == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("LLM_LOCAL_DEVICE=mps requested but MPS is unavailable")
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_dtype(torch: Any, requested: str, device: str) -> Any:
    requested = requested.strip().lower()
    if requested == "auto":
        return torch.float16 if device in {"cuda", "mps"} else torch.float32
    allowed = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}
    if requested not in allowed:
        raise RuntimeError("LLM_LOCAL_DTYPE must be auto, float32, float16, or bfloat16")
    return allowed[requested]


@lru_cache(maxsize=2)
def _runtime_cached(model_name: str, token: str | None, device: str, dtype: str, revision: str,
                    cache_dir: str | None, trust_remote_code: bool, local_files_only: bool) -> _TransformersRuntime:
    return _TransformersRuntime(model_name, token, device, dtype, revision, cache_dir,
                                trust_remote_code, local_files_only)


def _runtime(model_name: str, token: str | None, device: str, dtype: str, revision: str,
             cache_dir: str | None, trust_remote_code: bool, local_files_only: bool) -> _TransformersRuntime:
    with _load_lock:
        status = _load_state["status"]
        error = _load_state["error"]
    if status == "loading":
        elapsed = runtime_status()["load_seconds"]
        raise LocalModelLoadingError(
            f"Local model loading is in progress ({elapsed or 0:.0f}s). Progress is shown in the API terminal; "
            "retry when /health reports ready."
        )
    if status == "error":
        raise RuntimeError(f"The local model failed to load: {error}")
    if status == "not_started":
        start_background_load(LocalHuggingFaceChatModel(
            model_name=model_name, token=token, device=device, dtype=dtype, revision=revision,
            cache_dir=cache_dir, trust_remote_code=trust_remote_code, local_files_only=local_files_only,
        ))
        raise LocalModelLoadingError(
            "Local model loading started. Progress is shown in the API terminal; retry when /health reports ready."
        )
    return _runtime_cached(model_name, token, device, dtype, revision, cache_dir,
                           trust_remote_code, local_files_only)


def start_background_load(model: LocalHuggingFaceChatModel) -> None:
    """Start one daemon loader without delaying FastAPI startup or requests."""
    with _load_lock:
        if _load_state["status"] in {"loading", "ready"}:
            return
        _load_state.update(status="loading", started_at=time.time(), loaded_at=None, error=None)

    def load() -> None:
        started = time.perf_counter()
        logger.info("Local LLM loading started: model=%s device=%s dtype=%s cache=%s",
                    model.model_name, model.device, model.dtype, model.cache_dir or "Hugging Face default")
        try:
            runtime = _runtime_cached(model.model_name, model.token, model.device, model.dtype, model.revision,
                                      model.cache_dir, model.trust_remote_code, model.local_files_only)
            warmup = getattr(runtime, "warmup", None)
            if callable(warmup):
                warmup()  # first-token kernel init off the request path
            with _load_lock:
                _load_state.update(status="ready", loaded_at=time.time(), error=None)
            logger.info("Local LLM ready: model=%s load_seconds=%.1f", model.model_name, time.perf_counter() - started)
        except Exception as exc:
            with _load_lock:
                _load_state.update(status="error", error=str(exc)[:500])
            logger.exception("Local LLM failed to load: model=%s", model.model_name)

    threading.Thread(target=load, name="karya-local-llm-loader", daemon=True).start()


def runtime_status() -> dict[str, Any]:
    with _load_lock:
        state = dict(_load_state)
    now = state["loaded_at"] or time.time()
    started = state["started_at"]
    return {
        "status": state["status"],
        "load_seconds": round(now - started, 1) if started else None,
        "error": state["error"],
    }
