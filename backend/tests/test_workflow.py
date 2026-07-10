"""Cross-level workflow guide: stage detection, per-level status, next-best action, estimation."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db
from backend.workflow import service


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-workflow-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def test_empty_project_points_to_creating_l1():
    project = create_project(ProjectCreate(name="Empty"))
    guide = service.guide(project["id"])
    assert guide["stage"] == "Strategy"
    assert guide["overall_pct"] == 0
    levels = {v["level"]: v for v in guide["levels"]}
    assert levels["L1"]["status"] == "not_started"
    assert guide["next_action"]["tab"] == "canvas"
    assert "L1" in guide["next_action"]["text"] or "initiative" in guide["next_action"]["text"].lower()


def test_levels_and_expectation_propagate():
    project = create_project(ProjectCreate(name="Bank"))
    pid = project["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="Digital banking"))
    c4_store.create_element(pid, C4ElementCreate(level="L2", name="onboarding", parent_id=l1["id"]))
    guide = service.guide(pid)
    levels = {v["level"]: v for v in guide["levels"]}
    assert levels["L1"]["count"] == 1 and levels["L2"]["count"] == 1
    assert levels["L3"]["expected"] is True   # L2 exists → L3 is now expected
    assert levels["L4"]["expected"] is False  # no L3 yet
    assert levels["L2"]["status"] == "in_progress"
    # Each level offers at least one actionable next step with a target tab.
    for view in guide["levels"]:
        assert view["actions"] and all(a["tab"] for a in view["actions"])


def test_estimation_progress_and_endpoint():
    project = create_project(ProjectCreate(name="Est"))
    pid = project["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="I"))
    l2 = c4_store.create_element(pid, C4ElementCreate(level="L2", name="E", parent_id=l1["id"]))
    story = c4_store.create_element(pid, C4ElementCreate(level="L3", name="S", parent_id=l2["id"]))
    guide = service.guide(pid)
    assert guide["estimation"]["total"] == 1 and guide["estimation"]["unestimated"] == 1
    assert guide["estimation"]["status"] == "in_progress"

    c4_store.upsert_artifact(story["id"], "story", points=5)
    guide2 = service.guide(pid)
    assert guide2["estimation"]["estimated"] == 1 and guide2["estimation"]["pct"] == 100
    assert guide2["estimation"]["status"] == "ready"

    with TestClient(app) as client:
        resp = client.get(f"/projects/{pid}/workflow", headers={"X-User-Role": "viewer"})
        assert resp.status_code == 200
        assert resp.json()["project"]["name"] == "Est"
        assert client.get("/projects/missing/workflow", headers={"X-User-Role": "viewer"}).status_code == 404
