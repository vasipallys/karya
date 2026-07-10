"""L1 architecture baseline: CRUD, readiness score, executive summary, AI generate/apply."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.l1arch import service, store
from backend.l1arch.models import (
    CapabilityCreate,
    CommentCreate,
    OkrCreate,
    OkrUpdate,
    RiskCreate,
    StakeholderCreate,
    VisionUpdate,
)
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-l1arch-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _scope():
    project = create_project(ProjectCreate(name="Arch"))
    l1 = c4_store.create_element(project["id"], C4ElementCreate(level="L1", name="Digital banking"))
    return project["id"], l1["id"]


def test_baseline_attaches_only_to_l1():
    project_id, l1 = _scope()
    l2 = c4_store.create_element(project_id, C4ElementCreate(level="L2", name="svc", parent_id=l1))
    with pytest.raises(store.L1ArchValidationError):
        store.create_okr(project_id, l2["id"], OkrCreate(objective="X"))


def test_vision_upsert_and_default():
    project_id, l1 = _scope()
    assert store.get_vision(project_id, l1)["vision_statement"] == ""
    store.update_vision(project_id, l1, VisionUpdate(vision_statement="Be the best", status="approved"))
    v = store.get_vision(project_id, l1)
    assert v["vision_statement"] == "Be the best"
    assert v["status"] == "approved"


def test_vision_detail_fields_persist():
    project_id, l1 = _scope()
    store.update_vision(project_id, l1, VisionUpdate(
        vision_statement="CRM", vision_statement_details="## Notes\nUnified customer workspace.",
    ))
    v = store.get_vision(project_id, l1)
    assert "Unified customer workspace" in v["vision_statement_details"]


@pytest.mark.asyncio
async def test_ai_summarize_field():
    from backend.ai import agents

    result = await agents.summarize_field(
        "## Notes\nWe want a unified customer engagement workspace. It improves productivity.", "vision"
    )
    assert result.summary
    assert "#" not in result.summary  # markdown stripped


def test_okr_stakeholder_capability_risk_crud():
    project_id, l1 = _scope()
    okr = store.create_okr(project_id, l1, OkrCreate(objective="Grow", key_result="10% up", target_value="10%"))
    store.update_okr(project_id, okr["id"], OkrUpdate(status="at_risk"))
    assert store.list_okrs(l1)[0]["status"] == "at_risk"

    person = store.create_stakeholder(project_id, l1, StakeholderCreate(name="Ada", role="Product Owner", raci="Accountable"))
    assert store.list_stakeholders(l1)[0]["name"] == "Ada"
    store.delete_stakeholder(project_id, person["id"])
    assert store.list_stakeholders(l1) == []

    cap = store.create_capability(project_id, l1, CapabilityCreate(name="Payments", criticality="high"))
    child = store.create_capability(project_id, l1, CapabilityCreate(name="Cards", parent_id=cap["id"], cap_level="L2"))
    assert child["parent_id"] == cap["id"]

    risk = store.create_risk(project_id, l1, RiskCreate(title="Vendor lock-in", category="architecture", funding_source="Change"))
    assert store.list_risks(l1)[0]["title"] == "Vendor lock-in"
    store.delete_risk(project_id, risk["id"])
    assert store.list_risks(l1) == []


def test_parent_capability_must_share_l1():
    project_id, l1 = _scope()
    other = c4_store.create_element(project_id, C4ElementCreate(level="L1", name="Other"))
    cap_other = store.create_capability(project_id, other["id"], CapabilityCreate(name="Foreign"))
    with pytest.raises(store.L1ArchValidationError):
        store.create_capability(project_id, l1, CapabilityCreate(name="Child", parent_id=cap_other["id"]))


def test_readiness_score_progression():
    project_id, l1 = _scope()
    assert service.readiness(project_id, l1)["score"] == 0

    store.update_vision(project_id, l1, VisionUpdate(vision_statement="V", status="approved"))
    store.create_okr(project_id, l1, OkrCreate(objective="O", key_result="KR", target_value="10"))
    store.create_stakeholder(project_id, l1, StakeholderCreate(name="Owner", role="Business Sponsor", raci="Accountable"))
    store.create_capability(project_id, l1, CapabilityCreate(name="Cap"))
    store.create_risk(project_id, l1, RiskCreate(title="R", funding_source="Budget"))
    c4_store.create_element(project_id, C4ElementCreate(level="L2", name="svc", parent_id=l1))

    result = service.readiness(project_id, l1)
    assert result["score"] > 0
    assert len(result["areas"]) == 7
    assert sum(a["weight"] for a in result["areas"]) == 100
    assert any(c["done"] for c in result["checklist"])
    # Gap analysis: incomplete checklist items surface as gaps with recommendations.
    assert isinstance(result["gaps"], list)
    assert isinstance(result["recommendations"], list)


def test_readiness_gaps_on_empty_baseline():
    project_id, l1 = _scope()
    result = service.readiness(project_id, l1)
    assert result["score"] == 0
    assert len(result["gaps"]) >= 1
    assert len(result["recommendations"]) == 7  # every area is a gap


def test_executive_summary_is_markdown_with_mermaid():
    project_id, l1 = _scope()
    store.update_vision(project_id, l1, VisionUpdate(vision_statement="Deliver value"))
    store.create_capability(project_id, l1, CapabilityCreate(name="Payments"))
    store.create_okr(project_id, l1, OkrCreate(objective="Grow"))
    es = service.executive_summary(project_id, l1)
    assert es["markdown"].startswith("# Digital banking")
    assert "```mermaid" in es["markdown"]
    assert "## Vision" in es["markdown"]
    assert "## Portfolio Risk & Funding" in es["markdown"]


def test_traceability_and_orphan_null_on_delete():
    project_id, l1 = _scope()
    epic = c4_store.create_element(project_id, C4ElementCreate(level="L2", name="Epic", parent_id=l1))
    store.create_capability(project_id, l1, CapabilityCreate(name="Onboarding", linked_element_id=epic["id"]))
    store.create_capability(project_id, l1, CapabilityCreate(name="Unlinked"))
    trace = service.traceability(project_id, l1)
    assert trace["total"] == 2 and trace["linked_count"] == 1
    # Deleting the linked element nulls the link (ON DELETE SET NULL) — no orphan.
    c4_store.delete_element(project_id, epic["id"])
    assert service.traceability(project_id, l1)["linked_count"] == 0


def test_impact_analysis_flags_inconsistencies():
    project_id, l1 = _scope()
    store.create_stakeholder(project_id, l1, StakeholderCreate(name="Ex", raci="Accountable", status="inactive"))
    store.create_capability(project_id, l1, CapabilityCreate(name="Ownerless"))
    result = service.impact_analysis(project_id, l1)
    assert result["high"] >= 1  # inactive Accountable stakeholder
    assert any("owner" in f["message"].lower() for f in result["findings"])
    assert result["findings"][0]["severity"] == "high"  # sorted by severity


def test_comment_lifecycle():
    project_id, l1 = _scope()
    comment = store.create_comment(project_id, l1, CommentCreate(body="Add a security owner", author="Reviewer"))
    assert store.list_comments(l1)[0]["status"] == "open"
    store.resolve_comment(project_id, comment["id"])
    assert store.list_comments(l1)[0]["status"] == "resolved"
    store.delete_comment(project_id, comment["id"])
    assert store.list_comments(l1) == []


def test_jira_import_requires_configured_instance():
    from fastapi.testclient import TestClient

    from backend.access import store as access
    from backend.access.models import AccessUpdate
    from backend.resources import store as resources
    from backend.resources.models import StaffCreate

    project_id, l1 = _scope()
    admin = resources.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="Admin"))
    access.set_access(admin["id"], AccessUpdate(role="admin"))
    from backend.api.main import app
    with TestClient(app) as client:
        response = client.post(
            f"/projects/{project_id}/l1/{l1}/arch/import/jira",
            json={"instance": "ghost", "project_code": "PAY"},
            headers={"X-User-Id": admin["id"]},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "jira_not_configured"


def test_executive_summary_endpoint_returns_200():
    """Locks the API response shape — readiness_score is an int, so the route
    must not be typed dict[str, str]."""
    from fastapi.testclient import TestClient

    from backend.access import store as access
    from backend.access.models import AccessUpdate
    from backend.resources import store as resources
    from backend.resources.models import StaffCreate

    project_id, l1 = _scope()
    admin = resources.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="Admin"))
    access.set_access(admin["id"], AccessUpdate(role="admin"))
    store.update_vision(project_id, l1, VisionUpdate(vision_statement="V"))
    store.create_capability(project_id, l1, CapabilityCreate(name="Payments"))

    from backend.api.main import app
    with TestClient(app) as client:
        response = client.get(
            f"/projects/{project_id}/l1/{l1}/arch/executive-summary",
            headers={"X-User-Id": admin["id"]},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["markdown"].startswith("# Digital banking")
    assert "```mermaid" in body["markdown"]


@pytest.mark.asyncio
async def test_ai_generate_and_apply_baseline():
    from backend.ai import agents

    project_id, l1 = _scope()
    draft = await agents.generate_l1_baseline(project_id, l1, "A digital retail banking platform.")
    assert draft.vision_statement
    assert draft.okrs and draft.stakeholders and draft.capabilities and draft.risks
    # exactly one Accountable in the mock draft
    assert sum(1 for s in draft.stakeholders if s.raci == "Accountable") == 1

    result = agents.apply_l1_baseline(project_id, l1, draft.model_dump())
    assert result["okrs"] == len(draft.okrs)
    assert store.get_vision(project_id, l1)["vision_statement"] == draft.vision_statement
    assert len(store.list_capabilities(l1)) == len(draft.capabilities)

    # sections filter applies only the requested artifact types.
    project2, l1b = _scope()
    partial = agents.apply_l1_baseline(project2, l1b, draft.model_dump(), sections=["okrs"])
    assert partial == {"okrs": len(draft.okrs)}
    assert store.list_stakeholders(l1b) == []
