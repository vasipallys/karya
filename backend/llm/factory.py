"""The only module that knows how provider names become chat models."""

from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from backend.config import ConfigurationError, get_settings

OPENAI_COMPATIBLE = {"moonshot", "deepseek", "openrouter", "ollama", "vllm", "compatible"}
NATIVE_PROVIDERS = {"anthropic", "google_genai", "openai", "groq", "mistral"}
OFFLINE_PROVIDERS = {"mock"}
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def validate_factory_config() -> None:
    """Validate provider-specific settings without leaking conditionals elsewhere."""
    config = get_settings().llm
    provider = config.provider.lower()
    errors = []
    if provider not in OPENAI_COMPATIBLE | NATIVE_PROVIDERS | OFFLINE_PROVIDERS:
        errors.append(f"Unsupported LLM_PROVIDER '{config.provider}'")
    if provider in OPENAI_COMPATIBLE and not config.base_url:
        errors.append(f"LLM_BASE_URL is required for provider '{config.provider}'")
    if provider not in OFFLINE_PROVIDERS and not config.api_key.get_secret_value():
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
    if config.provider.lower() == "groq":
        # Groq JSON mode avoids tool_use_failed errors from otherwise-valid tool args.
        return model.with_structured_output(schema, method="json_mode", include_raw=True)
    return model.with_structured_output(schema, include_raw=True)
