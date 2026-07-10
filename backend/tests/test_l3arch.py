"""L3 component-architecture: CRUD, readiness, summary, RACI, approvals, traceability, AI."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.l3arch import service, store
from backend.l3arch.models import ComponentCreate, ConcernCreate, DependencyCreate, InterfaceCreate, L3Update
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-l3arch-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _scope():
    project = create_project(ProjectCreate(name="L3"))
    l1 = c4_store.create_element(project["id"], C4ElementCreate(level="L1", name="Banking"))
    l2 = c4_store.create_element(project["id"], C4ElementCreate(level="L2", name="Onboarding", parent_id=l1["id"]))
    l3 = c4_store.create_element(project["id"], C4ElementCreate(level="L3", name="pay-api", parent_id=l2["id"]))
    return project["id"], l2["id"], l3["id"]


def test_arch_attaches_only_to_l3():
    project_id, l2, l3 = _scope()
    with pytest.raises(store.L3ArchValidationError):
        store.create_component(project_id, l2, ComponentCreate(name="X"))
    store.create_component(project_id, l3, ComponentCreate(name="OK"))


def test_artifact_crud():
    project_id, _, l3 = _scope()
    c = store.create_component(project_id, l3, ComponentCreate(name="Svc", component_type="service", responsibilities="Core", owner="Ada"))
    store.create_interface(project_id, l3, InterfaceCreate(name="POST /x", authentication="OAuth2"))
    store.create_dependency(project_id, l3, DependencyCreate(name="Ledger", dependency_type="container"))
    store.create_concern(project_id, l3, ConcernCreate(name="Validation", category="validation"))
    assert len(store.list_components(l3)) == 1
    assert len(store.list_interfaces(l3)) == 1
    assert len(store.list_dependencies(l3)) == 1
    assert len(store.list_concerns(l3)) == 1
    store.delete_component(project_id, c["id"])
    assert store.list_components(l3) == []


def test_readiness_progression_and_weights():
    project_id, _, l3 = _scope()
    assert service.readiness(project_id, l3)["score"] <= 15
    store.update_l3(project_id, l3, L3Update(component_diagram="flowchart TB\n A-->B", status="approved"))
    store.create_component(project_id, l3, ComponentCreate(name="Svc", responsibilities="Core", owner="Ada"))
    store.create_interface(project_id, l3, InterfaceCreate(name="POST /x", authentication="OAuth2"))
    store.create_dependency(project_id, l3, DependencyCreate(name="Ledger"))
    store.create_concern(project_id, l3, ConcernCreate(name="Sec", category="security"))
    result = service.readiness(project_id, l3)
    assert result["score"] >= 80
    assert len(result["areas"]) == 9
    assert sum(a["weight"] for a in result["areas"]) == 100
    assert isinstance(result["gaps"], list)


def test_engineering_summary_markdown_mermaid():
    project_id, _, l3 = _scope()
    store.create_component(project_id, l3, ComponentCreate(name="Controller", component_type="controller"))
    es = service.engineering_summary(project_id, l3)
    assert es["markdown"].startswith("# pay-api")
    assert "```mermaid" in es["markdown"]
    assert "## Interfaces & Contracts" in es["markdown"]


def test_sequential_approval_baselines_l3():
    project_id, _, l3 = _scope()
    store.submit_for_review(project_id, l3)
    with pytest.raises(store.L3ArchValidationError):
        store.decide_approval(project_id, l3, "security", True, "x", "")  # out of order
    for stage in ("design", "interfaces", "security", "testing", "architecture", "tech_lead"):
        state = store.decide_approval(project_id, l3, stage, True, "Diana", "ok")
    assert state["complete"]
    assert store.get_l3(project_id, l3)["status"] == "baselined"


def test_raci_matrix_set_and_validate():
    project_id, _, l3 = _scope()
    matrix = store.set_raci(project_id, l3, "interfaces", "tech_lead", "A")
    assert matrix["interfaces:tech_lead"] == "A"
    store.set_raci(project_id, l3, "interfaces", "tech_lead", "")  # clear
    assert "interfaces:tech_lead" not in store.get_l3(project_id, l3)["raci"]
    with pytest.raises(store.L3ArchValidationError):
        store.set_raci(project_id, l3, "bad_artifact", "tech_lead", "R")
    with pytest.raises(store.L3ArchValidationError):
        store.set_raci(project_id, l3, "interfaces", "tech_lead", "X")


def test_traceability_l2_l3_l4():
    project_id, _, l3 = _scope()
    c4_store.create_element(project_id, C4ElementCreate(level="L4", name="PayController", parent_id=l3))
    trace = service.traceability(project_id, l3)
    assert trace["l2"]["name"] == "Onboarding"
    assert trace["l4_count"] == 1
    assert "flowchart" in trace["mermaid"]
    assert "L2 --> L3" in trace["mermaid"]


@pytest.mark.asyncio
async def test_ai_generate_and_apply_l3():
    from backend.ai import agents

    project_id, _, l3 = _scope()
    draft = await agents.generate_l3_baseline(project_id, l3, "A payments component.")
    assert draft.component_diagram and draft.components and draft.interfaces and draft.concerns
    result = agents.apply_l3_baseline(project_id, l3, draft.model_dump())
    assert result["components"] == len(draft.components)
    assert store.get_l3(project_id, l3)["component_diagram"] == draft.component_diagram
    assert len(store.list_interfaces(l3)) == len(draft.interfaces)


def test_ai_apply_bad_element_returns_4xx_not_500():
    """A stale/wrong-level element id must yield a clean 400/404, not a 500."""
    project_id, l2, _ = _scope()
    empty = {"summary": "x", "component_diagram": "", "components": [{"name": "C"}], "interfaces": [], "dependencies": [], "concerns": []}
    with TestClient(app) as client:
        headers = {"X-User-Role": "admin"}
        wrong_level = client.post(f"/projects/{project_id}/l3/{l2}/ai/l3/apply", json={"draft": empty}, headers=headers)
        assert wrong_level.status_code == 400
        assert wrong_level.json()["error"]["code"] == "invalid"
        missing = client.post(f"/projects/{project_id}/l3/does-not-exist/ai/l3/apply", json={"draft": empty}, headers=headers)
        assert missing.status_code == 404
