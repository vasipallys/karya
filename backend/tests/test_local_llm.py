"""Factory and parsing tests for the optional local Hugging Face provider."""

from __future__ import annotations

import threading
import time
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.config import ConfigurationError, get_settings
from backend.graph.nodes import _parse_structured_result
from backend.llm import factory
from backend.llm import local
from backend.api.main import app
from backend.ai import agents
from backend.storage import db


class ExampleOutput(BaseModel):
    answer: str


@pytest.fixture
def local_config(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_MODEL", "google/gemma-3-1b-it")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    factory.get_llm.cache_clear()
    yield
    get_settings.cache_clear()
    if hasattr(factory.get_llm, "cache_clear"):
        factory.get_llm.cache_clear()


def test_local_provider_needs_no_api_key(local_config):
    factory.validate_factory_config()
    assert get_settings().llm.model == "google/gemma-3-1b-it"


def test_local_config_rejects_unsafe_shape(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_MODEL", "google/gemma-3-1b-it")
    monkeypatch.setenv("LLM_LOCAL_DTYPE", "int4")
    get_settings.cache_clear()
    with pytest.raises(ConfigurationError, match="LLM_LOCAL_DTYPE"):
        get_settings().llm
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_structured_local_wrapper_adds_schema_and_parses(local_config, monkeypatch):
    class FakeModel:
        messages = None

        async def ainvoke(self, messages):
            self.messages = messages
            return AIMessage(content='Result: {"answer":"ready"}')

    fake = FakeModel()
    monkeypatch.setattr(factory, "get_llm", lambda: fake)
    result = await factory.get_structured_llm(ExampleOutput).ainvoke([])
    assert "JSON Schema" in fake.messages[0].content
    assert _parse_structured_result(ExampleOutput, result).answer == "ready"


def test_background_load_never_blocks_inference_request(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(local, "_runtime_cached", lambda *args: release.wait(2) or object())
    local._load_state.update(status="not_started", started_at=None, loaded_at=None, error=None)
    model = SimpleNamespace(model_name="test", token=None, device="cpu", dtype="float32", revision="main",
                            cache_dir=None, trust_remote_code=False, local_files_only=True)

    local.start_background_load(model)
    assert local.runtime_status()["status"] == "loading"
    with pytest.raises(local.LocalModelLoadingError, match="loading is in progress"):
        local._runtime("test", None, "cpu", "float32", "main", None, False, True)

    release.set()
    deadline = time.time() + 2
    while local.runtime_status()["status"] == "loading" and time.time() < deadline:
        time.sleep(0.01)
    assert local.runtime_status()["status"] == "ready"
    local._load_state.update(status="not_started", started_at=None, loaded_at=None, error=None)


def test_local_provider_does_not_load_model_during_api_startup(local_config, monkeypatch):
    directory = Path(tempfile.mkdtemp(prefix="karya-local-startup-"))
    try:
        monkeypatch.setenv("KARYA_DB", str(directory / "startup.db"))
        db._initialized.clear()
        local._load_state.update(status="not_started", started_at=None, loaded_at=None, error=None)
        monkeypatch.setattr(local, "_runtime_cached", lambda *args: pytest.fail("startup must not load model weights"))

        with TestClient(app) as client:
            assert client.get("/projects", headers={"X-User-Role": "admin"}).status_code == 200
            health = client.get("/health").json()
            assert health["llm"]["status"] == "not_started"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_gemma_messages_merge_structured_and_feature_system_prompts():
    messages = local._normalize_messages([
        SystemMessage(content="Return schema-valid JSON."),
        SystemMessage(content="You are the Karya assistant."),
        HumanMessage(content="List the containers."),
    ])
    assert [message["role"] for message in messages] == ["system", "user"]
    assert "schema-valid JSON" in messages[0]["content"]
    assert "Karya assistant" in messages[0]["content"]


def test_local_generation_wraps_chat_template_errors(monkeypatch):
    class BrokenRuntime:
        def generate(self, *args, **kwargs):
            raise ValueError("Conversation roles must alternate")

    monkeypatch.setattr(local, "_runtime", lambda *args: BrokenRuntime())
    model = local.LocalHuggingFaceChatModel(model_name="test")
    with pytest.raises(local.LocalModelInferenceError, match="Local model inference failed"):
        model._generate([SystemMessage(content="system"), HumanMessage(content="hello")])


@pytest.mark.asyncio
async def test_local_chat_uses_deterministic_routing_without_json_generation(monkeypatch):
    class FakeTextModel:
        async def ainvoke(self, messages, **kwargs):
            assert kwargs["max_new_tokens"] == 256
            return AIMessage(content="A normal Markdown answer, not JSON.")

    monkeypatch.setattr(agents, "get_llm", lambda: FakeTextModel())
    elements = [{"name": "payments-api", "level": "L2", "status": "active"}]

    overview = await agents._interpret_local_chat("what is the project status?", "auto", elements, "USER MESSAGE:\nstatus")
    answer = await agents._interpret_local_chat("explain this platform", "chat", elements, "USER MESSAGE:\nexplain")
    rename = await agents._interpret_local_chat("rename payments-api to payments-v2", "auto", elements, "USER MESSAGE:\nrename")

    assert overview.action == "overview"
    assert answer.action == "answer" and answer.reply == "A normal Markdown answer, not JSON."
    assert rename.action == "update_element" and rename.new_name == "payments-v2"
