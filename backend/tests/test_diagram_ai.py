"""Offline (LLM_PROVIDER=mock) tests for AI diagram generation and editing."""

from __future__ import annotations

import pytest

from backend.config import get_settings
from backend.llm.factory import get_llm
from backend.planning import diagram_ai


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


def test_sanitize_strips_fences_and_ensures_header():
    fenced = "```mermaid\nWeb --> API\n```"
    cleaned = diagram_ai._sanitize_mermaid(fenced, "architecture")
    assert cleaned.startswith("flowchart LR")
    assert "Web --> API" in cleaned
    assert "```" not in cleaned


def test_sanitize_keeps_an_existing_header():
    text = diagram_ai._sanitize_mermaid("flowchart TB\n  A --> B", "infrastructure")
    assert text.splitlines()[0] == "flowchart TB"


def test_sanitize_uses_default_header_for_new_diagram_types():
    text = diagram_ai._sanitize_mermaid("  todo[Todo]\n    task[Clarify scope]", "kanban")
    assert text.splitlines()[0] == "kanban"


@pytest.mark.asyncio
async def test_generate_from_prompt_offline(mock_llm):
    result = await diagram_ai.assist_diagram(prompt="Payment service talks to a ledger and a fraud engine")
    assert result["mermaid"].startswith("flowchart")
    assert "-->" in result["mermaid"]
    assert result["message"]


@pytest.mark.asyncio
async def test_generate_new_mermaid_type_offline(mock_llm):
    result = await diagram_ai.assist_diagram(prompt="Show delivery stages", diagram_type="kanban")
    assert result["mermaid"].startswith("kanban")
    assert "backlog" in result["mermaid"]
    assert result["message"]


@pytest.mark.asyncio
async def test_assist_edit_extends_current_diagram_offline(mock_llm):
    current = 'flowchart LR\n  Web["Web application"] --> Api["Experience API"]'
    result = await diagram_ai.assist_diagram(
        prompt="add a notifications service",
        current_source=current,
        history=[{"role": "user", "content": "start"}],
    )
    # The original nodes are preserved and a new node is appended.
    assert 'Web["Web application"]' in result["mermaid"]
    assert result["mermaid"].count("-->") >= 2
    assert result["message"]


def test_title_from_prompt():
    assert diagram_ai.title_from_prompt("Design the payments platform with a ledger and fraud checks") \
        .startswith("Design the payments platform")
