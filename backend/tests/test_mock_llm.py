"""Full-pipeline integration test using LLM_PROVIDER=mock (offline, no key)."""

from __future__ import annotations

import pytest

from backend.anchors import ANCHORS
from backend.config import get_settings
from backend.graph.build import get_estimation_graph
from backend.graph.state import PARAMETERS
from backend.llm.factory import get_llm, validate_factory_config
from backend.llm.mock import _points


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    get_llm.cache_clear()
    yield
    get_settings.cache_clear()
    get_llm.cache_clear()


def test_mock_mode_needs_no_api_key(mock_llm):
    validate_factory_config()
    get_settings().validate_startup()


@pytest.mark.asyncio
async def test_full_graph_runs_offline(mock_llm):
    graph = get_estimation_graph()
    story = {"title": "Payment initiation API", "user_story": "Submit a payment instruction.", "acceptance_criteria": ["Returns a payment id"]}
    result = await graph.ainvoke(
        {"story": story, "anchors": ANCHORS, "refinement": None, "messages": []},
        config={"configurable": {"thread_id": "mock-test"}},
    )
    assert result["points"] in {2, 3, 5, 8, 13}
    assert result["tldr"].startswith(str(result["points"]))
    assert result["plain_language_why"]
    assert {item["parameter"] for item in result["scorecard"]} == set(PARAMETERS)
    assert result["hidden_tasks"]
    assert result["risks"]


@pytest.mark.asyncio
async def test_mock_thirteen_exercises_spike_and_split(mock_llm):
    title = next(f"Story variant {index}" for index in range(200) if _points(f"Story variant {index}") == 13)
    graph = get_estimation_graph()
    result = await graph.ainvoke(
        {"story": {"title": title}, "anchors": ANCHORS, "refinement": None, "messages": []},
        config={"configurable": {"thread_id": "mock-13"}},
    )
    assert result["points"] == 13
    assert result["spike_recommended"] is True
    assert result["split_recommendation"]["split_recommended"] is True
    assert result["split_recommendation"]["proposed_stories"]
