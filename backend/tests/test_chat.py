"""Conversational assistant: query/report execute, writes propose→apply, RBAC on apply."""

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


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-chat-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _scope():
    project = create_project(ProjectCreate(name="Digital banking"))
    pid = project["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="Digital banking"))
    l2 = c4_store.create_element(pid, C4ElementCreate(level="L2", name="onboarding-web", parent_id=l1["id"]))
    return pid, l1["id"], l2["id"]


ADMIN = {"X-User-Role": "admin"}
VIEWER = {"X-User-Role": "viewer"}


def _chat(client, pid, message, headers=ADMIN):
    return client.post(f"/projects/{pid}/chat", json={"message": message}, headers=headers)


def test_query_and_report_execute():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        overview = _chat(client, pid, "what's the project status?").json()
        assert overview["action"] == "overview" and "%" in overview["reply"]
        listing = _chat(client, pid, "list L2 containers").json()
        assert listing["action"] == "list"
        assert any(i["name"] == "onboarding-web" for i in listing["data"]["items"])
        report = _chat(client, pid, "what should I do next?").json()
        assert report["action"] == "report" and report["mutation"] is None


def test_readiness_of_named_element():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "readiness of onboarding-web").json()
        assert res["action"] == "readiness"
        assert res["data"]["name"] == "onboarding-web" and "score" in res["data"]


def test_unknown_element_is_a_clean_400():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "readiness of does-not-exist")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "chat_invalid"


def test_create_proposes_then_applies_and_rbac():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        proposal = _chat(client, pid, "create an L2 container called payments under Digital banking").json()
        assert proposal["action"] == "create_element"
        mutation = proposal["mutation"]
        assert mutation["level"] == "L2" and mutation["name"] == "payments"
        # nothing created yet
        assert not any(e["name"] == "payments" for e in c4_store.list_graph(pid)["elements"])
        # viewer may propose (query) but not apply
        assert _chat(client, pid, "list L2", VIEWER).status_code == 200
        assert client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=VIEWER).status_code == 403
        # admin applies -> element exists
        applied = client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=ADMIN)
        assert applied.status_code == 200
        assert any(e["name"] == "payments" and e["level"] == "L2" for e in c4_store.list_graph(pid)["elements"])


def test_update_status_via_chat():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        proposal = _chat(client, pid, "set onboarding-web status to reviewed").json()
        assert proposal["action"] == "update_element"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=ADMIN)
        status = next(e["status"] for e in c4_store.list_graph(pid)["elements"] if e["name"] == "onboarding-web")
        assert status == "reviewed"
