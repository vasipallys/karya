# Local Hugging Face LLM

Karya can run an instruction-tuned Hugging Face model in the FastAPI process. The
recommended small default is `google/gemma-3-1b-it`; any causal chat model with a
Transformers chat template can be selected with `LLM_MODEL`.

## Install and configure

Gemma is license-gated. Sign in to Hugging Face, accept the model license on the
[`google/gemma-3-1b-it` model page](https://huggingface.co/google/gemma-3-1b-it),
and create a read token if the model is not already cached.

```powershell
python -m pip install -r requirements-local.txt
Copy-Item backend\.env.example backend\.env
```

Set these values in `backend/.env`:

```dotenv
LLM_PROVIDER=local
LLM_MODEL=google/gemma-3-1b-it
LLM_API_KEY=hf_your_read_token
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=1024
LLM_LOCAL_DEVICE=auto
LLM_LOCAL_DTYPE=auto
LLM_LOCAL_REVISION=main
LLM_LOCAL_CONTEXT_WINDOW=4096
LLM_LOCAL_CACHE_DIR=
LLM_LOCAL_FILES_ONLY=false
LLM_LOCAL_TRUST_REMOTE_CODE=false
```

After saving `backend/.env`, perform the one-time download and validation:

```powershell
npm run api:setup:local-llm

# Optional: also prove that all weights fit in RAM/VRAM.
npm run api:setup:local-llm -- --verify-load
```

The Hugging Face cache is reused on every later run, so model files are not
downloaded again. Loading cached weights into RAM/VRAM is still required once per
API process. Karya prints download/tensor progress and explicit start/ready timing
messages in the API terminal.

The token is optional after the gated model has been cached. For an air-gapped
deployment, pre-populate `LLM_LOCAL_CACHE_DIR`, pin `LLM_LOCAL_REVISION` to a model
commit hash, then set `LLM_LOCAL_FILES_ONLY=true`. Keep
`LLM_LOCAL_TRUST_REMOTE_CODE=false` unless the selected model has been reviewed and
requires custom repository code.

## Runtime behavior

- Model loading runs on a background daemon thread and never blocks startup or the
  request path. With `LLM_LOCAL_PRELOAD=true` (the default) the loader starts at API
  startup — plus a one-token warmup so the first real call skips kernel init — so the
  model is usually `ready` by the time you interact. Set `LLM_LOCAL_PRELOAD=false` to
  defer loading to the first AI request (for packaged/CI startups that must not touch
  multi-GB weights). `/health` reports `llm.status` as `not_started`, `loading`,
  `ready`, or `error`; chat returns a retryable response while loading instead of
  holding the request open and appearing frozen.
- During `loading`, watch the API terminal for Hugging Face/Transformers progress.
  A subsequent AI request reports elapsed loading seconds; retry after health is
  `ready`.
- `auto` selects CUDA, then Apple MPS, then CPU. Override it with `cpu`, `mps`,
  `cuda`, or `cuda:0`.
- `auto` dtype uses FP16 on GPU/MPS and FP32 on CPU. CPU inference works but is
  substantially slower and needs enough RAM for model weights and generation.
- One process holds one cached model and serializes generation. Use one API worker
  per GPU; multiple workers each load their own full copy of the model.
- Prompts are left-truncated to `LLM_LOCAL_CONTEXT_WINDOW`. Generated output is
  bounded by `LLM_MAX_TOKENS`.

For higher throughput, serve the model using vLLM or Ollama and use Karya's existing
`vllm` or `ollama` OpenAI-compatible provider instead of the in-process `local`
provider.

For a self-contained desktop build, install `requirements-local.txt` in the build
environment and set `KARYA_BUNDLE_LOCAL_LLM=true` before running the desktop build.
This is opt-in because bundling PyTorch and Transformers substantially increases the
installer size. Model weights are still stored in the user's Hugging Face cache and
are not embedded in the installer.

## Production checklist

Pin Python dependencies and `LLM_LOCAL_REVISION`, warm the model with a smoke request
before admitting traffic, persist the Hugging Face cache outside ephemeral storage,
monitor RAM/VRAM and request latency, and avoid logging `LLM_API_KEY`. The `/health`
endpoint validates configuration; actual model availability is established on first
inference so startup remains recoverable when a download or accelerator is unavailable.
