"""The only module that knows how provider names become chat models."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from backend.config import ConfigurationError, get_settings

OPENAI_COMPATIBLE = {"moonshot", "deepseek", "openrouter", "ollama", "vllm", "compatible"}
NATIVE_PROVIDERS = {"anthropic", "google_genai", "openai", "groq", "mistral"}
OFFLINE_PROVIDERS = {"mock"}
LOCAL_PROVIDERS = {"local"}
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def validate_factory_config() -> None:
    """Validate provider-specific settings without leaking conditionals elsewhere."""
    config = get_settings().llm
    provider = config.provider.lower()
    errors = []
    if provider not in OPENAI_COMPATIBLE | NATIVE_PROVIDERS | OFFLINE_PROVIDERS | LOCAL_PROVIDERS:
        errors.append(f"Unsupported LLM_PROVIDER '{config.provider}'")
    if provider in OPENAI_COMPATIBLE and not config.base_url:
        errors.append(f"LLM_BASE_URL is required for provider '{config.provider}'")
    if provider not in OFFLINE_PROVIDERS | LOCAL_PROVIDERS and not config.api_key.get_secret_value():
        errors.append("LLM_API_KEY is required")
    if errors:
        raise ConfigurationError(errors)


@lru_cache
def get_llm() -> BaseChatModel:
    """Build the configured chat model. No caller needs provider conditionals."""
    config = get_settings().llm
    provider = config.provider.lower()
    validate_factory_config()
    if provider in OFFLINE_PROVIDERS:
        from langchain_core.language_models import FakeListChatModel

        return FakeListChatModel(responses=["Mock mode is active; structured estimation uses the offline mock."])
    if provider in LOCAL_PROVIDERS:
        from backend.llm.local import LocalHuggingFaceChatModel

        return LocalHuggingFaceChatModel(
            model_name=config.model,
            token=config.api_key.get_secret_value() or None,
            temperature=config.temperature,
            max_new_tokens=config.max_tokens,
            device=config.local_device,
            dtype=config.local_dtype,
            revision=config.local_revision,
            cache_dir=config.local_cache_dir,
            context_window=config.local_context_window,
            trust_remote_code=config.local_trust_remote_code,
            local_files_only=config.local_files_only,
        )
    common = {
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "api_key": config.api_key.get_secret_value(),
        "max_retries": 1,
    }
    if provider in OPENAI_COMPATIBLE:
        return ChatOpenAI(**common, base_url=config.base_url)
    return init_chat_model(model_provider=provider, **common)


def get_structured_llm(schema: type[SchemaT]) -> Runnable:
    """Return a schema-constrained model using the provider's reliable mode."""
    config = get_settings().llm
    if config.provider.lower() in OFFLINE_PROVIDERS:
        from backend.llm.mock import MockStructuredLLM

        return MockStructuredLLM(schema)
    model = get_llm()
    if config.provider.lower() in LOCAL_PROVIDERS:
        schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        instruction = (
            f"Return only one valid JSON object matching this JSON Schema. No markdown or commentary.\n{schema_json}"
        )

        async def invoke(messages):
            raw = await model.ainvoke([SystemMessage(content=instruction), *messages])
            return {"raw": raw, "parsed": None, "parsing_error": None}

        return RunnableLambda(invoke)
    if config.provider.lower() == "groq":
        # Groq JSON mode avoids tool_use_failed errors from otherwise-valid tool args.
        return model.with_structured_output(schema, method="json_mode", include_raw=True)
    return model.with_structured_output(schema, include_raw=True)


def preload_llm() -> None:
    """Warm the model at startup so the first user request isn't a cold miss.

    Only the local in-process runtime pays a real load cost (multi-second weight
    load + first-call kernel warmup); hosted providers are no-ops. Loading runs on
    a background daemon thread, so this returns immediately and never blocks the
    API's startup or health checks.
    """
    config = get_settings().llm
    if config.provider.lower() not in LOCAL_PROVIDERS or not config.local_preload:
        return
    from backend.llm.local import start_background_load

    start_background_load(get_llm())


def llm_runtime_status() -> dict:
    if get_settings().llm.provider.lower() not in LOCAL_PROVIDERS:
        return {"status": "ready"}
    from backend.llm.local import runtime_status
    return runtime_status()


def prefers_text_routing() -> bool:
    """Whether the configured model is more reliable with deterministic routing.

    Small local instruction models are good response generators but unreliable
    emitters of Karya's large ChatCommand JSON schema. Keep the provider name in
    this factory while allowing the chat agent to select the suitable strategy.
    """
    return get_settings().llm.provider.lower() in LOCAL_PROVIDERS
