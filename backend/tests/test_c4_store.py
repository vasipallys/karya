"""Project + C4 store CRUD, validation, seeding, and roll-up tests."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.c4 import service, store
from backend.c4.models import C4ElementCreate, C4ElementUpdate, C4RelationCreate
from backend.c4.scan import scan_repo
from backend.projects import store as projects
from backend.projects.models import Lead, ProjectCreate, ProjectUpdate, RepoLinkCreate
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    db._initialized.clear()
    yield


def make_tree() -> tuple[str, dict, dict, dict]:
    project = projects.create_project(ProjectCreate(name="Payments", description="demo"))
    system = store.create_element(project["id"], C4ElementCreate(level="L1", name="Payments platform", kind="system"))
    container = store.create_element(project["id"], C4ElementCreate(level="L2", name="payment-service", kind="container", parent_id=system["id"]))
    component = store.create_element(project["id"], C4ElementCreate(level="L3", name="Initiation API", kind="component", parent_id=container["id"]))
    return project["id"], system, container, component


def test_project_crud_and_links():
    project = projects.create_project(ProjectCreate(name="Demo"))
    assert projects.get_project(project["id"])["name"] == "Demo"
    projects.add_repo_link(project["id"], RepoLinkCreate(url="https://example.com/repo.git"))
    listed = projects.list_projects()
    assert listed[0]["repos"][0]["url"] == "https://example.com/repo.git"
    projects.delete_project(project["id"])
    with pytest.raises(projects.NotFoundError):
        projects.get_project(project["id"])


def test_platform_leads_create_update_and_hydrate():
    project = projects.create_project(ProjectCreate(
        name="Payments platform",
        leads=[Lead(name="Priya Nair", role="Engineering lead"), Lead(name="Sam Okafor")],
    ))
    # Leads round-trip as parsed objects on both create and list.
    assert project["leads"][0] == {"name": "Priya Nair", "role": "Engineering lead"}
    assert projects.list_projects()[0]["leads"][1]["name"] == "Sam Okafor"

    # A leads-only update replaces them and leaves name/description untouched.
    updated = projects.update_project(project["id"], ProjectUpdate(leads=[Lead(name="Dana Lee", role="Product")]))
    assert updated["name"] == "Payments platform"
    assert updated["leads"] == [{"name": "Dana Lee", "role": "Product"}]

    # Omitting leads on update preserves the existing leads.
    renamed = projects.update_project(project["id"], ProjectUpdate(name="Payments"))
    assert renamed["name"] == "Payments"
    assert renamed["leads"] == [{"name": "Dana Lee", "role": "Product"}]

    with pytest.raises(projects.NotFoundError):
        projects.update_project("missing", ProjectUpdate(name="x"))


def test_parent_level_rule_is_enforced():
    project_id, system, _, _ = make_tree()
    with pytest.raises(store.C4ValidationError):
        store.create_element(project_id, C4ElementCreate(level="L3", name="Bad parent", parent_id=system["id"]))


def test_relations_require_project_membership():
    project_id, _, container, component = make_tree()
    relation = store.create_relation(project_id, C4RelationCreate(source_id=container["id"], target_id=component["id"], label="contains"))
    other = projects.create_project(ProjectCreate(name="Other"))
    with pytest.raises(store.C4ValidationError):
        store.create_relation(other["id"], C4RelationCreate(source_id=container["id"], target_id=component["id"]))
    store.delete_relation(project_id, relation["id"])


def test_cross_cutting_levels():
    project_id, system, container, component = make_tree()
    store.tag_cross_cutting(project_id, component["id"], "bug", "PAY-9")
    with pytest.raises(store.C4ValidationError):
        store.tag_cross_cutting(project_id, system["id"], "bug", None)
    tagged = store.get_element(project_id, component["id"])
    assert any(a["artifact_type"] == "bug" and a["jira_issue_key"] == "PAY-9" for a in tagged["artifacts"])


def test_persist_estimate_seeds_children_and_rollup_counts():
    project_id, _, container, component = make_tree()
    sibling = store.create_element(project_id, C4ElementCreate(level="L3", name="Limits check", parent_id=container["id"]))
    result = {
        "points": 13,
        "spike_recommended": True,
        "hidden_tasks": [{"task": "Add audit logging", "weight": "medium"}],
        "split_recommendation": {"split_recommended": True, "proposed_stories": ["Initiation happy path", "Initiation error handling"]},
    }
    service.persist_estimate(project_id, store.get_element(project_id, component["id"]), "session-1", result)
    # Re-running must not duplicate the seeded elements.
    service.persist_estimate(project_id, store.get_element(project_id, component["id"]), "session-1", result)

    graph = store.list_graph(project_id)
    tasks = [e for e in graph["elements"] if e["level"] == "L4"]
    proposed_siblings = [e for e in graph["elements"] if e["level"] == "L3" and e["status"] == "proposed"]
    assert len(tasks) == 1 and tasks[0]["parent_id"] == component["id"]
    assert {e["name"] for e in proposed_siblings} == {"Initiation happy path", "Initiation error handling"}

    rollup = service.rollup(project_id)
    assert rollup["totals"]["rolled_up_points"] == 13
    assert rollup["totals"]["estimated_stories"] == 1
    # The untouched sibling counts as unestimated; proposed split stories do not.
    assert rollup["totals"]["unestimated_stories"] == 1
    assert rollup["totals"]["spikes"] == 1
    assert rollup["totals"]["pending_splits"] == 1


def test_element_to_story_carries_c4_context():
    project_id, _, container, component = make_tree()
    store.update_element(project_id, component["id"], C4ElementUpdate(code_path="backend/api", tech="Spring Boot"))
    store.create_relation(project_id, C4RelationCreate(source_id=component["id"], target_id=container["id"], label="reads config", kind="sync"))
    story = service.element_to_story(project_id, store.get_element(project_id, component["id"]))
    assert story.title == "Initiation API"
    assert story.c4_context["level"] == "L3"
    assert story.c4_context["artifact_type"] == "story"
    assert [item["name"] for item in story.c4_context["parent_chain"]] == ["Payments platform", "payment-service"]
    assert story.c4_context["relations"][0]["label"] == "reads config"
    assert story.c4_context["code_path"] == "backend/api"


def test_repo_scan_proposes_and_applies(work_dir):
    (work_dir / "backend" / "api").mkdir(parents=True)
    (work_dir / "backend" / "api" / "main.py").write_text("print('hi')")
    (work_dir / "frontend" / "src").mkdir(parents=True)
    (work_dir / "frontend" / "src" / "App.jsx").write_text("export default 1")
    (work_dir / "node_modules").mkdir()

    project = projects.create_project(ProjectCreate(name="Scanned"))
    proposal = scan_repo(str(work_dir), "Scanned")
    names = {c["name"] for c in proposal["containers"]}
    assert names == {"backend", "frontend"}

    outcome = service.apply_scan(project["id"], proposal)
    assert outcome["created"] == 5
    graph = store.list_graph(project["id"])
    levels = sorted(e["level"] for e in graph["elements"])
    assert levels == ["L1", "L2", "L2", "L3", "L3"]
    # Second apply is idempotent.
    assert service.apply_scan(project["id"], proposal)["created"] == 0
