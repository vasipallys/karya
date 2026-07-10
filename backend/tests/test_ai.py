"""Agentic AI service tests (run against the deterministic mock provider)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.ai import agents
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.planning import store as planning_store
from backend.planning.models import AgileUnitCreate
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.reporting import service as reporting_service
from backend.resources import store as resources
from backend.resources.models import StaffCreate
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-ai-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _scope():
    project = create_project(ProjectCreate(name="AI platform"))
    l1 = c4_store.create_element(project["id"], C4ElementCreate(level="L1", name="Growth"))
    return project["id"], l1


@pytest.mark.asyncio
async def test_staffing_proposal_respects_capacity_and_applies():
    project_id, l1 = _scope()
    squad = planning_store.create_unit(project_id, l1["id"], AgileUnitCreate(unit_type="squad", name="Squad A"))
    for i in range(3):
        resources.create_staff(StaffCreate(staff_first_name=f"P{i}", staff_last_name="X"))

    proposal = await agents.propose_staffing(project_id, l1["id"])
    assert proposal.assignments
    assert all(0 < a.allocation_percent <= 100 for a in proposal.assignments)
    assert all(a.squad_id == squad["id"] for a in proposal.assignments)

    result = agents.apply_staffing(project_id, [a.model_dump() for a in proposal.assignments])
    assert result["created"] == len(proposal.assignments)
    plan = planning_store.get_plan(project_id, l1["id"])
    members = plan["units"][0]["members"]
    assert len(members) == len(proposal.assignments)
    assert all(m["resource_staff_id"] for m in members)


@pytest.mark.asyncio
async def test_staffing_never_exceeds_remaining_capacity():
    project_id, l1 = _scope()
    squad = planning_store.create_unit(project_id, l1["id"], AgileUnitCreate(unit_type="squad", name="Squad A"))
    person = resources.create_staff(StaffCreate(staff_first_name="Solo", staff_last_name="Dev"))
    # Pre-allocate 70% elsewhere.
    from backend.planning.models import TeamMemberCreate
    squad_b = planning_store.create_unit(project_id, l1["id"], AgileUnitCreate(unit_type="squad", name="Squad B"))
    planning_store.create_member(project_id, squad_b["id"], TeamMemberCreate(name="Solo Dev", resource_staff_id=person["id"], allocation_percent=70))

    proposal = await agents.propose_staffing(project_id, l1["id"])
    for a in proposal.assignments:
        if a.staff_id == person["id"]:
            assert a.allocation_percent <= 30  # only 30% remained


@pytest.mark.asyncio
async def test_decompose_and_apply_creates_proposed_children():
    project_id, l1 = _scope()
    epic = c4_store.create_element(project_id, C4ElementCreate(level="L2", name="Onboarding", parent_id=l1["id"]))
    result = await agents.decompose_element(project_id, epic["id"])
    assert result.stories
    applied = agents.apply_decomposition(project_id, epic["id"], [s.model_dump() for s in result.stories])
    assert applied["level"] == "L3"
    graph = c4_store.list_graph(project_id)
    children = [e for e in graph["elements"] if e["parent_id"] == epic["id"]]
    assert len(children) == len(result.stories)
    assert all(c["status"] == "proposed" for c in children)


@pytest.mark.asyncio
async def test_scaffold_and_apply_builds_model():
    project_id = create_project(ProjectCreate(name="Blank"))["id"]  # no pre-existing elements
    scaffold = await agents.scaffold_c4(project_id, "A payments platform with a web app, a service, and a database.")
    assert any(e.level == "L1" for e in scaffold.elements)
    applied = agents.apply_scaffold(project_id, scaffold.model_dump())
    assert applied["created_elements"] == len(scaffold.elements)
    graph = c4_store.list_graph(project_id)
    assert len(graph["elements"]) == len(scaffold.elements)
    assert len(graph["relations"]) == applied["created_relations"]
    # Parent refs resolved to real ids (containers hang off the L1 system).
    l1 = next(e for e in graph["elements"] if e["level"] == "L1")
    assert any(e["parent_id"] == l1["id"] for e in graph["elements"] if e["level"] == "L2")


@pytest.mark.asyncio
async def test_narrative_from_overview():
    _scope()
    narrative = await agents.generate_narrative(reporting_service.overview())
    assert narrative.headline
    assert narrative.summary
    assert isinstance(narrative.highlights, list)
