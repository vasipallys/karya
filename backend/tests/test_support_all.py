"""Approvals, exec-summary exports, integration catalog, orchestrator, masking, ABAC."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.ai.masking import mask_pii
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.integrations import catalog
from backend.l1arch import exports, store
from backend.l1arch.models import CapabilityCreate, VisionUpdate
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-supportall-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _scope(sensitivity="standard"):
    project = create_project(ProjectCreate(name="Gov", sensitivity=sensitivity))
    l1 = c4_store.create_element(project["id"], C4ElementCreate(level="L1", name="Payments"))
    return project["id"], l1["id"]


# ---- approvals ----

def test_sequential_approval_baselines_vision():
    project_id, l1 = _scope()
    store.submit_for_review(project_id, l1)
    with pytest.raises(store.L1ArchValidationError):
        store.decide_approval(project_id, l1, "security", True, "x", "")  # out of order
    for stage in ("product", "architecture", "security", "risk", "finance", "sponsor"):
        state = store.decide_approval(project_id, l1, stage, True, "Diana", "ok")
    assert state["complete"]
    assert store.get_vision(project_id, l1)["status"] == "baselined"


def test_rejection_reverts_baseline():
    project_id, l1 = _scope()
    store.update_vision(project_id, l1, VisionUpdate(status="baselined"))
    store.submit_for_review(project_id, l1)
    store.decide_approval(project_id, l1, "product", False, "Diana", "needs work")
    assert store.get_vision(project_id, l1)["status"] == "draft"


def test_decide_before_submit_rejected():
    project_id, l1 = _scope()
    with pytest.raises(store.L1ArchValidationError):
        store.decide_approval(project_id, l1, "product", True, "x", "")


# ---- exports ----

def test_exec_exports_produce_files():
    project_id, l1 = _scope()
    store.update_vision(project_id, l1, VisionUpdate(vision_statement="Deliver value"))
    store.create_capability(project_id, l1, CapabilityCreate(name="Payments"))

    md, md_name = exports.executive_markdown(project_id, l1)
    assert md_name.endswith(".md") and b"# Payments" in md

    pptx, pptx_name = exports.executive_pptx(project_id, l1)
    assert pptx_name.endswith(".pptx") and pptx[:2] == b"PK"  # zip/office container

    docx, docx_name = exports.executive_docx(project_id, l1)
    assert docx_name.endswith(".docx") and docx[:2] == b"PK"


# ---- integration catalog ----

def test_catalog_lists_all_tools_with_status():
    data = catalog.list_catalog()
    assert data["total"] >= 40
    keys = {tool["key"] for group in data["groups"] for tool in group["tools"]}
    assert {"jira", "confluence", "structurizr", "servicenow_grc", "document_import"} <= keys
    assert data["counts"]["adapter"] >= 1  # document_import etc.


# ---- masking ----

def test_mask_pii_redacts_contacts():
    masked = mask_pii("Reach ada@example.com or call +1 415 555 1234, SSN 123-45-6789")
    assert "ada@example.com" not in masked
    assert "[email]" in masked and "[phone]" in masked and "[id]" in masked


# ---- orchestrator ----

@pytest.mark.asyncio
async def test_orchestrator_routes_requests():
    from backend.ai import agents
    cases = {
        "assign engineers to the squads": "auto_staffing",
        "draft the vision and OKRs": "generate_l1_baseline",
        "build a C4 context diagram": "scaffold_c4",
        "break this epic into stories": "decompose_story",
    }
    for request, expected in cases.items():
        plan = await agents.orchestrate(request)
        assert plan.action == expected


# ---- ABAC (HTTP) ----

@pytest.fixture
def client():
    from backend.access import store as access
    from backend.access.models import AccessUpdate
    from backend.resources import store as resources
    from backend.resources.models import StaffCreate

    db.init_db()
    admin = resources.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="Admin"))
    viewer = resources.create_staff(StaffCreate(staff_first_name="Val", staff_last_name="Viewer"))
    access.set_access(admin["id"], AccessUpdate(role="admin"))
    access.set_access(viewer["id"], AccessUpdate(role="viewer"))
    from backend.api.main import app
    with TestClient(app) as test_client:
        test_client.ids = {"admin": admin["id"], "viewer": viewer["id"]}
        yield test_client


def test_restricted_workspace_blocks_low_roles(client):
    restricted = create_project(ProjectCreate(name="Secret", sensitivity="restricted"))["id"]
    standard = create_project(ProjectCreate(name="Open", sensitivity="standard"))["id"]
    # Viewer can read a standard workspace but not a restricted one.
    assert client.get(f"/projects/{standard}", headers={"X-User-Id": client.ids["viewer"]}).status_code == 200
    assert client.get(f"/projects/{restricted}", headers={"X-User-Id": client.ids["viewer"]}).status_code == 403
    # Admin can read the restricted workspace.
    assert client.get(f"/projects/{restricted}", headers={"X-User-Id": client.ids["admin"]}).status_code == 200


def test_integration_catalog_endpoint(client):
    response = client.get("/integrations/catalog", headers={"X-User-Id": client.ids["viewer"]})
    assert response.status_code == 200
    assert response.json()["total"] >= 40
