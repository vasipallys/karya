"""L4 implementation-detail: CRUD, readiness, summary, checklist toggle, traceability, AI."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.l4arch import service, store
from backend.l4arch.models import ChecklistCreate, ChecklistUpdate, CodeUnitCreate, L4Update, TestCaseCreate
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-l4arch-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _scope():
    project = create_project(ProjectCreate(name="L4"))
    l1 = c4_store.create_element(project["id"], C4ElementCreate(level="L1", name="Banking"))
    l2 = c4_store.create_element(project["id"], C4ElementCreate(level="L2", name="Onboarding", parent_id=l1["id"]))
    l3 = c4_store.create_element(project["id"], C4ElementCreate(level="L3", name="pay-api", parent_id=l2["id"]))
    l4 = c4_store.create_element(project["id"], C4ElementCreate(level="L4", name="PayController.create", parent_id=l3["id"]))
    return project["id"], l3["id"], l4["id"]


def test_arch_attaches_only_to_l4():
    project_id, l3, l4 = _scope()
    with pytest.raises(store.L4ArchValidationError):
        store.create_code_unit(project_id, l3, CodeUnitCreate(name="X"))
    store.create_code_unit(project_id, l4, CodeUnitCreate(name="OK"))


def test_artifact_crud_and_checklist_bool():
    project_id, _, l4 = _scope()
    store.create_code_unit(project_id, l4, CodeUnitCreate(name="Controller", responsibility="handle"))
    store.create_test_case(project_id, l4, TestCaseCreate(name="rejects invalid", test_type="unit"))
    item = store.create_checklist_item(project_id, l4, ChecklistCreate(item="Code written", category="code", done=True))
    assert item["done"] is True
    assert len(store.list_code_units(l4)) == 1
    assert len(store.list_test_cases(l4)) == 1
    toggled = store.update_checklist_item(project_id, item["id"], ChecklistUpdate(done=False))
    assert toggled["done"] is False


def test_readiness_progression_and_weights():
    project_id, _, l4 = _scope()
    assert service.readiness(project_id, l4)["score"] <= 20
    store.update_l4(project_id, l4, L4Update(code_diagram="classDiagram\n class A", status="approved"))
    store.create_code_unit(project_id, l4, CodeUnitCreate(name="Controller", responsibility="handle"))
    store.create_test_case(project_id, l4, TestCaseCreate(name="t", test_type="unit"))
    store.create_checklist_item(project_id, l4, ChecklistCreate(item="done", category="code", done=True))
    result = service.readiness(project_id, l4)
    assert result["score"] >= 80
    assert len(result["areas"]) == 5
    assert sum(a["weight"] for a in result["areas"]) == 100


def test_implementation_summary_markdown_mermaid():
    project_id, _, l4 = _scope()
    store.create_code_unit(project_id, l4, CodeUnitCreate(name="Controller", unit_type="class"))
    store.create_checklist_item(project_id, l4, ChecklistCreate(item="Tests pass", category="tests", done=True))
    es = service.implementation_summary(project_id, l4)
    assert es["markdown"].startswith("# PayController.create")
    assert "```mermaid" in es["markdown"]
    assert "## Definition of Done" in es["markdown"]
    assert "- [x]" in es["markdown"]


def test_traceability_l2_l3_l4_chain():
    project_id, _, l4 = _scope()
    trace = service.traceability(project_id, l4)
    assert trace["l3"]["name"] == "pay-api"
    assert trace["l2"]["name"] == "Onboarding"
    assert "L2 --> L3" in trace["mermaid"]
    assert "L3 --> L4" in trace["mermaid"]


@pytest.mark.asyncio
async def test_ai_generate_and_apply_l4():
    from backend.ai import agents

    project_id, _, l4 = _scope()
    draft = await agents.generate_l4_baseline(project_id, l4, "Implement the create endpoint.")
    assert draft.code_diagram and draft.code_units and draft.test_cases and draft.checklist
    result = agents.apply_l4_baseline(project_id, l4, draft.model_dump())
    assert result["code_units"] == len(draft.code_units)
    assert store.get_l4(project_id, l4)["code_diagram"] == draft.code_diagram
    assert len(store.list_checklist(l4)) == len(draft.checklist)
