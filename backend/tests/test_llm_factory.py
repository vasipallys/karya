"""Provider-neutral structured-output factory behavior."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from backend.config import get_settings
from backend.llm import factory


class ExampleOutput(BaseModel):
    value: str


def _groq_config(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_groq_json_mode_always_mentions_json(monkeypatch):
    seen = {}

    class Structured:
        async def ainvoke(self, messages, config=None):
            seen["messages"] = messages
            return {"parsed": ExampleOutput(value="ok"), "raw": None, "parsing_error": None}

    class Model:
        def with_structured_output(self, schema, **kwargs):
            assert schema is ExampleOutput
            assert kwargs == {"method": "json_mode", "include_raw": True}
            return Structured()

    _groq_config(monkeypatch)
    monkeypatch.setattr(factory, "get_llm", lambda: Model())
    try:
        result = await factory.get_structured_llm(ExampleOutput).ainvoke([HumanMessage(content="hello")])
        assert result["parsed"].value == "ok"
        assert any("json" in str(message.content).lower() for message in seen["messages"])
        assert any('"value"' in str(message.content) for message in seen["messages"])
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_hosted_provider_exception_is_normalized(monkeypatch):
    class Structured:
        async def ainvoke(self, messages, config=None):
            error = RuntimeError("upstream unavailable")
            error.status_code = 503
            raise error

    class Model:
        def with_structured_output(self, schema, **kwargs):
            return Structured()

    _groq_config(monkeypatch)
    monkeypatch.setattr(factory, "get_llm", lambda: Model())
    try:
        with pytest.raises(factory.LLMInvocationError, match="upstream unavailable") as raised:
            await factory.get_structured_llm(ExampleOutput).ainvoke([HumanMessage(content="hello")])
        assert raised.value.retryable is True
    finally:
        get_settings.cache_clear()
