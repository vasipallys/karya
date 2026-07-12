"""Download and validate the configured local Hugging Face model once.

The resulting Hugging Face cache is reused across API restarts. Passing
``--verify-load`` additionally loads the weights into the selected device as a
one-off hardware/memory test; it does not keep them resident after this script exits.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Karya's configured local Hugging Face model")
    parser.add_argument("--verify-load", action="store_true", help="also load all weights to validate RAM/VRAM")
    args = parser.parse_args()
    config = get_settings().llm
    if config.provider.lower() != "local":
        print("Set LLM_PROVIDER=local in backend/.env before running this command.", file=sys.stderr)
        return 2

    try:
        from huggingface_hub import snapshot_download
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        print("Install local dependencies first: python -m pip install -r requirements-local.txt", file=sys.stderr)
        return 2

    token = config.api_key.get_secret_value() or None
    print(f"Preparing {config.model} (revision {config.local_revision})")
    print(f"Cache: {config.local_cache_dir or 'Hugging Face default'}")
    snapshot = snapshot_download(
        repo_id=config.model,
        revision=config.local_revision,
        cache_dir=config.local_cache_dir,
        token=token,
        local_files_only=config.local_files_only,
    )
    AutoConfig.from_pretrained(snapshot, trust_remote_code=config.local_trust_remote_code)
    tokenizer = AutoTokenizer.from_pretrained(snapshot, trust_remote_code=config.local_trust_remote_code)
    tokenizer.apply_chat_template(
        [{"role": "system", "content": "You are Karya."}, {"role": "user", "content": "Health check."}],
        add_generation_prompt=True,
        return_tensors="pt",
    )
    print(f"Download and tokenizer validation complete: {snapshot}")

    if args.verify_load:
        print("Loading model weights for hardware verification (progress follows)...")
        from backend.llm.local import _resolve_device, _resolve_dtype
        import torch

        device = _resolve_device(torch, config.local_device)
        dtype = _resolve_dtype(torch, config.local_dtype, device)
        model = AutoModelForCausalLM.from_pretrained(
            snapshot, torch_dtype=dtype, low_cpu_mem_usage=True,
            trust_remote_code=config.local_trust_remote_code,
        )
        if device != "auto":
            model.to(device)
        print(f"Weight-load verification complete on {device} ({dtype}).")
    print("Setup complete. Start Karya with: npm run dev:all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
