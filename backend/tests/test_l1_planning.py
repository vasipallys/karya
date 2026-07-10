"""L1 operating-plan persistence, validation, and metric tests."""

from __future__ import annotations

import base64
import io
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.planning import exports, requirements, store
from backend.planning.models import (
    AgileUnitCreate,
    DiagramCreate,
    DiagramUpdate,
    PlanSettingsUpdate,
    RequirementCommentAction,
    RequirementCommentCreate,
    RequirementDocumentCreate,
    RequirementDocumentUpdate,
    RequirementReviewAction,
    TeamMemberCreate,
    TeamMemberUpdate,
    WorkItemCreate,
    WorkItemUpdate,
)
from backend.projects import store as projects
from backend.projects.models import ProjectCreate
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-planning-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    db._initialized.clear()
    yield


def make_scope():
    project = projects.create_project(ProjectCreate(name="Digital bank"))
    initiative = c4_store.create_element(project["id"], C4ElementCreate(level="L1", name="Customer growth"))
    epic = c4_store.create_element(
        project["id"],
        C4ElementCreate(level="L2", name="Onboarding", parent_id=initiative["id"]),
    )
    return project["id"], initiative, epic


def test_member_resource_link_and_allocation_cap():
    from backend.resources import store as resources
    from backend.resources.models import StaffCreate

    project_id, initiative, _ = make_scope()
    squad_a = store.create_unit(project_id, initiative["id"], AgileUnitCreate(unit_type="squad", name="Squad A"))
    squad_b = store.create_unit(project_id, initiative["id"], AgileUnitCreate(unit_type="squad", name="Squad B"))
    person = resources.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="Lovelace"))

    # An unknown resource id is rejected.
    with pytest.raises(store.PlanningValidationError):
        store.create_member(project_id, squad_a["id"], TeamMemberCreate(name="X", resource_staff_id="missing", allocation_percent=10))

    # First allocation of 60% is fine and the link round-trips.
    first = store.create_member(
        project_id, squad_a["id"],
        TeamMemberCreate(name="Ada Lovelace", resource_staff_id=person["id"], allocation_percent=60),
    )
    assert first["resource_staff_id"] == person["id"]

    # Adding the same person on another squad at 60% would reach 120% -> rejected.
    with pytest.raises(store.PlanningValidationError):
        store.create_member(
            project_id, squad_b["id"],
            TeamMemberCreate(name="Ada Lovelace", resource_staff_id=person["id"], allocation_percent=60),
        )

    # 40% fits exactly to 100%.
    store.create_member(
        project_id, squad_b["id"],
        TeamMemberCreate(name="Ada Lovelace", resource_staff_id=person["id"], allocation_percent=40),
    )

    # Bumping the first membership now would exceed 100% -> rejected.
    with pytest.raises(store.PlanningValidationError):
        store.update_member(project_id, first["id"], TeamMemberUpdate(allocation_percent=70))

    # Members without a resource link are unconstrained (legacy free-text behavior).
    store.create_member(project_id, squad_a["id"], TeamMemberCreate(name="Contractor", allocation_percent=100))


def test_full_operating_plan_and_cost_metrics():
    project_id, initiative, epic = make_scope()
    tribe = store.create_unit(
        project_id,
        initiative["id"],
        AgileUnitCreate(unit_type="tribe", name="Growth tribe", lead_name="Morgan"),
    )
    squad = store.create_unit(
        project_id,
        initiative["id"],
        AgileUnitCreate(
            unit_type="squad",
            name="Onboarding squad",
            parent_unit_id=tribe["id"],
            capacity_fte=6,
            target_velocity=34,
        ),
    )
    store.create_member(
        project_id,
        squad["id"],
        TeamMemberCreate(
            name="Ari",
            role="Engineer",
            skills="React, Java",
            allocation_percent=80,
            monthly_cost=10000,
        ),
    )
    store.create_work_item(
        project_id,
        initiative["id"],
        WorkItemCreate(
            title="Onboarding release",
            squad_id=squad["id"],
            linked_element_id=epic["id"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 9, 30),
            budget_cost=120000,
            actual_cost=45000,
            status="in_progress",
        ),
    )
    diagram = store.create_diagram(
        project_id,
        initiative["id"],
        DiagramCreate(
            diagram_type="architecture",
            title="Solution view",
            mermaid_source="flowchart LR\n  Web --> API",
        ),
    )
    store.update_settings(project_id, initiative["id"], PlanSettingsUpdate(currency_code="INR"))

    plan = store.get_plan(project_id, initiative["id"])
    assert plan["settings"]["currency_code"] == "INR"
    assert plan["metrics"] == {
        "tribes": 1,
        "squads": 1,
        "people": 1,
        "allocated_fte": 0.8,
        "monthly_run_rate": 8000.0,
        "planned_cost": 120000.0,
        "actual_cost": 45000.0,
        "cost_variance": 75000.0,
        "at_risk_work": 0,
    }
    assert next(unit for unit in plan["units"] if unit["unit_type"] == "squad")["members"][0]["name"] == "Ari"
    assert plan["work_items"][0]["linked_element_name"] == "Onboarding"
    assert plan["diagrams"][0]["id"] == diagram["id"]


def test_diagram_metadata_round_trips_through_create_update_and_plan():
    project_id, initiative, _ = make_scope()
    created = store.create_diagram(
        project_id,
        initiative["id"],
        DiagramCreate(
            diagram_type="architecture",
            title="Solution view",
            mermaid_source="flowchart LR\n  Web --> API",
            metadata={
                "nodes": {"Web": {"explanation": "Front door", "links": [{"label": "Docs", "url": "https://x"}]}},
                "positions": {"Web": {"x": 40, "y": 60}},
            },
        ),
    )
    assert created["metadata"]["nodes"]["Web"]["explanation"] == "Front door"

    # Metadata survives a fresh read (parsed back from the stored JSON string).
    plan = store.get_plan(project_id, initiative["id"])
    assert plan["diagrams"][0]["metadata"]["positions"]["Web"] == {"x": 40, "y": 60}

    updated = store.update_diagram(
        project_id,
        created["id"],
        DiagramUpdate(metadata={"nodes": {"API": {"explanation": "Edge"}}, "positions": {}}),
    )
    assert updated["metadata"]["nodes"] == {"API": {"explanation": "Edge"}}
    # A metadata-only update must not disturb the mermaid source.
    assert updated["mermaid_source"] == "flowchart LR\n  Web --> API"


def test_new_mermaid_diagram_types_are_persisted():
    project_id, initiative, _ = make_scope()
    created = store.create_diagram(
        project_id,
        initiative["id"],
        DiagramCreate(
            diagram_type="kanban",
            title="Delivery board",
            mermaid_source="kanban\n  todo[Todo]\n    task1[Clarify scope]",
        ),
    )

    plan = store.get_plan(project_id, initiative["id"])
    assert created["diagram_type"] == "kanban"
    assert plan["diagrams"][0]["diagram_type"] == "kanban"


def test_plan_rejects_cross_initiative_assignments_and_bad_dates():
    project_id, initiative, _ = make_scope()
    other = c4_store.create_element(project_id, C4ElementCreate(level="L1", name="Operations"))
    other_squad = store.create_unit(
        project_id,
        other["id"],
        AgileUnitCreate(unit_type="squad", name="Operations squad"),
    )
    with pytest.raises(store.PlanningValidationError):
        store.create_work_item(
            project_id,
            initiative["id"],
            WorkItemCreate(
                title="Invalid ownership",
                squad_id=other_squad["id"],
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 2),
            ),
        )
    with pytest.raises(ValueError):
        WorkItemCreate(
            title="Backwards",
            start_date=date(2026, 7, 2),
            end_date=date(2026, 7, 1),
        )


def test_updates_validate_combined_work_dates():
    project_id, initiative, _ = make_scope()
    work = store.create_work_item(
        project_id,
        initiative["id"],
        WorkItemCreate(
            title="Release",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        ),
    )
    with pytest.raises(store.PlanningValidationError):
        store.update_work_item(
            project_id,
            work["id"],
            WorkItemUpdate(start_date=date(2026, 8, 1)),
        )


def test_work_assignments_can_be_cleared():
    project_id, initiative, epic = make_scope()
    squad = store.create_unit(
        project_id,
        initiative["id"],
        AgileUnitCreate(unit_type="squad", name="Journey squad"),
    )
    work = store.create_work_item(
        project_id,
        initiative["id"],
        WorkItemCreate(
            title="Release",
            squad_id=squad["id"],
            linked_element_id=epic["id"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        ),
    )
    updated = store.update_work_item(
        project_id,
        work["id"],
        WorkItemUpdate(squad_id=None, linked_element_id=None),
    )
    assert updated["squad_id"] is None
    assert updated["linked_element_id"] is None


def test_requirement_versions_comments_approval_and_audit():
    project_id, initiative, _ = make_scope()
    created = requirements.create_document(
        project_id,
        initiative["id"],
        RequirementDocumentCreate(
            title="Onboarding requirements",
            content="# Goal\n\n```mermaid\nflowchart LR\n  Need --> Outcome\n```",
            actor="Ari Analyst",
        ),
    )
    comment = requirements.add_comment(
        project_id,
        created["id"],
        RequirementCommentCreate(body="Confirm the availability target.", actor="Riley Reviewer"),
    )
    requirements.act_on_comment(
        project_id,
        comment["id"],
        RequirementCommentAction(action="approve", actor="Morgan Owner"),
    )
    requirements.review_document(
        project_id,
        created["id"],
        RequirementReviewAction(action="submit", actor="Ari Analyst"),
    )
    approved = requirements.review_document(
        project_id,
        created["id"],
        RequirementReviewAction(action="approve", actor="Morgan Owner", note="Ready for delivery."),
    )

    assert approved["status"] == "approved"
    assert approved["approved_by"] == "Morgan Owner"
    assert approved["comments"][0]["status"] == "approved"
    assert {event["event_type"] for event in approved["audit"]} >= {
        "document_created",
        "comment_added",
        "comment_approved",
        "review_submit",
        "review_approve",
    }

    updated = requirements.update_document(
        project_id,
        created["id"],
        RequirementDocumentUpdate(
            title="Onboarding requirements",
            content=created["content"] + "\n\n## SLO\n\n99.9% availability.",
            actor="Ari Analyst",
            change_summary="Added availability target",
            expected_version=1,
        ),
    )
    assert updated["version"] == 2
    assert updated["status"] == "draft"
    assert updated["approved_by"] is None
    assert [item["version"] for item in updated["versions"]] == [2, 1]
    assert requirements.get_version(project_id, created["id"], 1)["content"] == created["content"]


def test_requirement_update_rejects_stale_editor_and_exports_office_files():
    project_id, initiative, _ = make_scope()
    created = requirements.create_document(
        project_id,
        initiative["id"],
        RequirementDocumentCreate(
            title="Payments capability",
            content="# Scope\n\n- Authorize a payment\n- Preserve an audit record",
            actor="Plan owner",
        ),
    )
    requirements.update_document(
        project_id,
        created["id"],
        RequirementDocumentUpdate(
            title=created["title"],
            content=created["content"] + "\n",
            actor="Plan owner",
            expected_version=1,
        ),
    )
    with pytest.raises(requirements.PlanningConflictError):
        requirements.update_document(
            project_id,
            created["id"],
            RequirementDocumentUpdate(
                title=created["title"],
                content=created["content"] + "\n\nStale overwrite",
                actor="Another editor",
                expected_version=1,
            ),
        )

    image_buffer = io.BytesIO()
    Image.new("RGB", (16, 9), "white").save(image_buffer, format="PNG")
    png = "data:image/png;base64," + base64.b64encode(image_buffer.getvalue()).decode()
    diagram_document = requirements.create_document(
        project_id,
        initiative["id"],
        RequirementDocumentCreate(
            title="Diagram export",
            content="# Flow\n\n```mermaid\nflowchart LR\n  Need --> Outcome\n```",
            actor="Plan owner",
        ),
    )
    word, word_name = exports.word_export(project_id, diagram_document["id"], [png])
    slides, slide_name = exports.powerpoint_export(project_id, diagram_document["id"], [png])
    assert word[:2] == b"PK" and word_name == "diagram-export.docx"
    assert slides[:2] == b"PK" and slide_name == "diagram-export.pptx"
    with zipfile.ZipFile(io.BytesIO(word)) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())
    with zipfile.ZipFile(io.BytesIO(slides)) as archive:
        assert any(name.startswith("ppt/media/") for name in archive.namelist())
