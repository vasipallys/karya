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
    path = Path(tempfile.mkdtemp(prefix="karya-chat-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("KARYA_DB", str(work_dir / "test.db"))
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
        assert all(i["id"] for i in listing["data"]["items"])  # ids power UI deep links
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


def test_create_without_parent_attaches_to_the_system_l1():
    """“create an L2 container called payments” (no ‘under …’) must not create
    an orphan on the system landscape — it attaches to the only suitable L1."""
    pid, l1_id, _ = _scope()
    # Persons/externals must not be picked as container parents.
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Retail customer", kind="person"))
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Core banking", kind="external system"))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "create an L2 container called payments").json()
        assert proposal["mutation"]["parent"] == "Digital banking"
        assert "under “Digital banking”" in proposal["mutation"]["summary"]
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=ADMIN)
        created = next(e for e in c4_store.list_graph(pid)["elements"] if e["name"] == "payments")
        assert created["parent_id"] == l1_id


def test_create_with_ambiguous_parent_asks_instead_of_guessing():
    pid, _, _ = _scope()
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Payments platform", kind="system"))
    with TestClient(app) as client:
        res = _chat(client, pid, "create an L2 container called payments")
        assert res.status_code == 400
        message = res.json()["error"]["message"]
        assert "Which L1" in message and "Digital banking" in message and "Payments platform" in message


def test_create_rejects_wrong_level_parent():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "create an L4 task called cleanup under Digital banking")
        assert res.status_code == 400
        assert "needs an L3 parent" in res.json()["error"]["message"]


def test_compound_create_and_route_in_one_message():
    """“create a L2 payments container and route it to the api-gateway” must
    extract the inline name, attach to the L1, and create the relation."""
    pid, l1_id, _ = _scope()
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1_id))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "create a L2 payments container and route it to the api gateway").json()
        mutation = proposal["mutation"]
        assert mutation["action"] == "create_element"
        assert mutation["name"] == "payments"
        assert mutation["target"] == "api-gateway"
        assert "api-gateway" in mutation["summary"]
        applied = client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=ADMIN)
        assert applied.status_code == 200
        assert "connected it to “api-gateway”" in applied.json()["reply"]
        graph = c4_store.list_graph(pid)
        payments = next(e for e in graph["elements"] if e["name"] == "payments")
        assert payments["parent_id"] == l1_id
        assert any(r["source_id"] == payments["id"] and r["target_id"] == gw["id"] for r in graph["relations"])


def test_standalone_relation_between_existing_elements():
    pid, l1_id, l2_id = _scope()
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1_id))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "route onboarding-web to api-gateway").json()
        assert proposal["mutation"]["action"] == "create_relation"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=ADMIN)
        relations = c4_store.list_graph(pid)["relations"]
        assert any(r["source_id"] == l2_id and r["target_id"] == gw["id"] for r in relations)


def test_followup_answer_uses_conversation_history():
    """After the assistant asks for a name, a bare answer like “payments”
    must complete the pending create instead of falling back to help."""
    pid, l1_id, _ = _scope()
    with TestClient(app) as client:
        first = _chat(client, pid, "create an L2 container")
        assert first.status_code == 400  # asks for the name
        history = [
            {"role": "user", "text": "create an L2 container"},
            {"role": "assistant", "text": "What should the new element be called?"},
        ]
        followup = client.post(f"/projects/{pid}/chat", json={"message": "payments", "history": history}, headers=ADMIN).json()
        mutation = followup["mutation"]
        assert mutation["action"] == "create_element" and mutation["name"] == "payments"
        assert mutation["parent"] == "Digital banking"


def test_chat_stream_runs_branches_concurrently_then_judges():
    """The agent graph fans out planner/retrieval/tools, streams a `branch`
    event per branch, a `judge` verdict, then the final `result` in the same
    shape as POST /chat (so the Apply flow is shared)."""
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = client.post(f"/projects/{pid}/chat/stream", json={"message": "list L2 containers"}, headers=ADMIN)
        assert res.status_code == 200
        body = res.text
        assert body.count("event: branch") == 3
        for branch in ("planner", "retrieval", "tools"):
            assert f'"branch": "{branch}"' in body
        assert "event: judge" in body and '"sufficient": true' in body
        assert "event: result" in body and '"action": "list"' in body
        assert '"evidence"' in body  # retrieval/tools attached to the final payload
        # branch partials must arrive before the verdict, which precedes the result
        assert body.index("event: branch") < body.index("event: judge") < body.index("event: result")


def test_chat_stream_write_proposal_and_error_paths():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        # A write streams the same proposal mutation the non-streaming path builds.
        res = client.post(f"/projects/{pid}/chat/stream",
                          json={"message": "create an L2 container called payments"}, headers=ADMIN)
        assert '"mutation"' in res.text and '"parent": "Digital banking"' in res.text
        # A dispatch failure becomes a clean in-stream error event.
        res = client.post(f"/projects/{pid}/chat/stream",
                          json={"message": "readiness of does-not-exist"}, headers=ADMIN)
        assert "event: error" in res.text and '"code": "chat_invalid"' in res.text


def test_update_status_via_chat():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        proposal = _chat(client, pid, "set onboarding-web status to reviewed").json()
        assert proposal["action"] == "update_element"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=ADMIN)
        status = next(e["status"] for e in c4_store.list_graph(pid)["elements"] if e["name"] == "onboarding-web")
        assert status == "reviewed"


def test_conversations_persist_and_are_user_scoped():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        result = _chat(client, pid, "what's the project status?").json()
        conversation_id = result["conversation_id"]
        listing = client.get(f"/projects/{pid}/chat/conversations", headers=ADMIN).json()
        assert listing[0]["id"] == conversation_id
        assert listing[0]["message_count"] == 2
        loaded = client.get(f"/projects/{pid}/chat/conversations/{conversation_id}", headers=ADMIN).json()
        assert [message["role"] for message in loaded["messages"]] == ["user", "assistant"]
        assert client.get(f"/projects/{pid}/chat/conversations/{conversation_id}", headers=VIEWER).status_code == 404


def test_text_attachment_is_saved_and_linked_to_message():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        conversation = client.post(f"/projects/{pid}/chat/conversations", headers=ADMIN).json()
        uploaded = client.post(
            f"/projects/{pid}/chat/conversations/{conversation['id']}/attachments",
            files={"file": ("notes.md", b"# Release notes\nPayments launch is at risk.", "text/markdown")},
            headers=ADMIN,
        )
        assert uploaded.status_code == 200
        response = client.post(f"/projects/{pid}/chat", json={
            "message": "summarize this file", "conversation_id": conversation["id"],
            "attachment_ids": [uploaded.json()["id"]],
        }, headers=ADMIN)
        assert response.status_code == 200
        loaded = client.get(f"/projects/{pid}/chat/conversations/{conversation['id']}", headers=ADMIN).json()
        assert loaded["messages"][0]["attachments"][0]["filename"] == "notes.md"
