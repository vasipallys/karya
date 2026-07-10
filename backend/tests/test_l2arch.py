"""L2 container-architecture: CRUD, readiness, engineering summary, AI generate/apply."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.l2arch import service, store
from backend.l2arch.models import ApiCreate, ContainerCreate, IntegrationCreate, L2Update, NfrCreate
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-l2arch-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _scope():
    project = create_project(ProjectCreate(name="L2"))
    l1 = c4_store.create_element(project["id"], C4ElementCreate(level="L1", name="Banking"))
    l2 = c4_store.create_element(project["id"], C4ElementCreate(level="L2", name="Onboarding", parent_id=l1["id"]))
    return project["id"], l1["id"], l2["id"]


def test_arch_attaches_only_to_l2():
    project_id, l1, l2 = _scope()
    with pytest.raises(store.L2ArchValidationError):
        store.create_container(project_id, l1, ContainerCreate(name="X"))
    store.create_container(project_id, l2, ContainerCreate(name="OK"))


def test_arch_upsert_and_default():
    project_id, _, l2 = _scope()
    assert store.get_l2(project_id, l2)["summary"] == ""
    store.update_l2(project_id, l2, L2Update(summary="A platform", container_diagram="flowchart LR\n A-->B", status="reviewed"))
    arch = store.get_l2(project_id, l2)
    assert arch["summary"] == "A platform"
    assert arch["status"] == "reviewed"
    assert "flowchart" in arch["container_diagram"]


def test_artifact_crud():
    project_id, _, l2 = _scope()
    c = store.create_container(project_id, l2, ContainerCreate(name="Svc", owner_team="Squad A", responsibilities="Core"))
    store.create_api(project_id, l2, ApiCreate(name="GET /x", provider="Svc"))
    store.create_nfr(project_id, l2, NfrCreate(name="Latency", category="performance", target="300ms"))
    store.create_integration(project_id, l2, IntegrationCreate(name="Core", target_system="Core Banking"))
    assert len(store.list_containers(l2)) == 1
    assert len(store.list_apis(l2)) == 1
    assert len(store.list_nfrs(l2)) == 1
    assert len(store.list_integrations(l2)) == 1
    store.delete_container(project_id, c["id"])
    assert store.list_containers(l2) == []


def test_readiness_progression_and_weights():
    project_id, _, l2 = _scope()
    assert service.readiness(project_id, l2)["score"] <= 15  # only L1 alignment initially
    store.update_l2(project_id, l2, L2Update(container_diagram="flowchart LR\n A-->B", status="approved"))
    store.create_container(project_id, l2, ContainerCreate(name="Svc", owner_team="Squad", responsibilities="Core"))
    store.create_api(project_id, l2, ApiCreate(name="api", data_classification="confidential"))
    store.create_nfr(project_id, l2, NfrCreate(name="n", category="security"))
    store.create_integration(project_id, l2, IntegrationCreate(name="i"))
    result = service.readiness(project_id, l2)
    assert result["score"] >= 80
    assert len(result["areas"]) == 9
    assert sum(a["weight"] for a in result["areas"]) == 100
    assert isinstance(result["gaps"], list)


def test_engineering_summary_markdown_mermaid():
    project_id, _, l2 = _scope()
    store.create_container(project_id, l2, ContainerCreate(name="Web App"))
    es = service.engineering_summary(project_id, l2)
    assert es["markdown"].startswith("# Onboarding")
    assert "```mermaid" in es["markdown"]
    assert "## API & Data Contracts" in es["markdown"]


def test_sequential_approval_baselines_l2():
    project_id, _, l2 = _scope()
    store.submit_for_review(project_id, l2)
    with pytest.raises(store.L2ArchValidationError):
        store.decide_approval(project_id, l2, "security", True, "x", "")  # out of order
    for stage in ("engineering", "security", "nfr", "data", "architecture", "sponsor"):
        state = store.decide_approval(project_id, l2, stage, True, "Diana", "ok")
    assert state["complete"]
    assert store.get_l2(project_id, l2)["status"] == "baselined"


def test_raci_matrix_set_and_validate():
    project_id, _, l2 = _scope()
    matrix = store.set_raci(project_id, l2, "api_contracts", "engineering_lead", "R")
    assert matrix["api_contracts:engineering_lead"] == "R"
    store.set_raci(project_id, l2, "api_contracts", "engineering_lead", "")  # clear
    assert "api_contracts:engineering_lead" not in store.get_l2(project_id, l2)["raci"]
    with pytest.raises(store.L2ArchValidationError):
        store.set_raci(project_id, l2, "bad_artifact", "engineering_lead", "R")
    with pytest.raises(store.L2ArchValidationError):
        store.set_raci(project_id, l2, "api_contracts", "engineering_lead", "X")


def test_traceability_l1_l2_l3():
    project_id, l1, l2 = _scope()
    c4_store.create_element(project_id, C4ElementCreate(level="L3", name="pay-api", parent_id=l2))
    trace = service.traceability(project_id, l2)
    assert trace["l1"]["name"] == "Banking"
    assert trace["l3_count"] == 1
    assert "flowchart" in trace["mermaid"]
    assert "L1 --> L2" in trace["mermaid"]


def test_openapi_import():
    from backend.l2arch import imports

    project_id, _, l2 = _scope()
    spec = '{"info":{"title":"Pay","version":"1.2"},"paths":{"/pay":{"post":{}},"/status":{"get":{}}}}'
    result = imports.run_import(project_id, l2, "openapi", spec)
    assert result["created_apis"] == 2
    names = {a["name"] for a in store.list_apis(l2)}
    assert "POST /pay" in names and "GET /status" in names
    with pytest.raises(imports.ImportError_):
        imports.run_import(project_id, l2, "openapi", '{"not":"openapi"}')


def test_kubernetes_import():
    from backend.l2arch import imports

    project_id, _, l2 = _scope()
    manifest = "kind: Deployment\nmetadata:\n  name: pay-service\n  labels: {app: payments}\n---\nkind: Service\nmetadata: {name: pay-svc}\n"
    result = imports.run_import(project_id, l2, "kubernetes", manifest)
    assert result["created_containers"] == 2
    assert {c["name"] for c in store.list_containers(l2)} == {"pay-service", "pay-svc"}


@pytest.mark.asyncio
async def test_ai_generate_and_apply_l2():
    from backend.ai import agents

    project_id, _, l2 = _scope()
    draft = await agents.generate_l2_baseline(project_id, l2, "A customer onboarding platform.")
    assert draft.container_diagram and draft.containers and draft.apis and draft.nfrs
    result = agents.apply_l2_baseline(project_id, l2, draft.model_dump())
    assert result["containers"] == len(draft.containers)
    assert store.get_l2(project_id, l2)["container_diagram"] == draft.container_diagram
    assert len(store.list_apis(l2)) == len(draft.apis)
