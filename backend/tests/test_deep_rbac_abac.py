"""Deep RBAC + ABAC across the newer endpoints, and the LLM-unconfigured 503 path."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-deep-rbac-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _make_client(work_dir, monkeypatch, provider="mock"):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", provider)
    if provider == "openai":
        monkeypatch.delenv("LLM_API_KEY", raising=False)
    from backend.storage import db
    db._initialized.clear()
    db.init_db()
    from backend.access import store as access
    from backend.access.models import AccessUpdate
    from backend.resources import store as resources
    from backend.resources.models import StaffCreate
    ids = {}
    for role in ("admin", "manager", "contributor", "viewer"):
        person = resources.create_staff(StaffCreate(staff_first_name=role.title(), staff_last_name="User"))
        access.set_access(person["id"], AccessUpdate(role=role))
        ids[role] = person["id"]
    from backend.api.main import app
    client = TestClient(app)
    client.ids = ids
    return client


@pytest.fixture
def client(work_dir, monkeypatch):
    with _make_client(work_dir, monkeypatch) as c:
        yield c


def hdr(sid):
    return {"X-User-Id": sid}


def _project(client):
    return client.post("/projects", json={"name": "P"}, headers=hdr(client.ids["admin"])).json()


def _chain(client):
    pid = _project(client)["id"]
    h = hdr(client.ids["admin"])
    l1 = client.post(f"/projects/{pid}/c4/elements", json={"level": "L1", "name": "I"}, headers=h).json()["id"]
    l2 = client.post(f"/projects/{pid}/c4/elements", json={"level": "L2", "name": "C", "parent_id": l1}, headers=h).json()["id"]
    l3 = client.post(f"/projects/{pid}/c4/elements", json={"level": "L3", "name": "S", "parent_id": l2}, headers=h).json()["id"]
    l4 = client.post(f"/projects/{pid}/c4/elements", json={"level": "L4", "name": "T", "parent_id": l3}, headers=h).json()["id"]
    return pid, l1, l2, l3, l4


# ---- reads open to any signed-in user; writes need platform.edit -------------

def test_arch_reads_are_authenticated_writes_gated(client):
    pid, l1, l2, l3, l4 = _chain(client)
    reads = [
        f"/projects/{pid}/l2/{l2}/arch", f"/projects/{pid}/l3/{l3}/arch",
        f"/projects/{pid}/l4/{l4}/arch", f"/projects/{pid}/workflow",
    ]
    for path in reads:
        assert client.get(path).status_code == 401                                   # anonymous
        assert client.get(path, headers=hdr(client.ids["viewer"])).status_code == 200  # viewer read

    # a representative write at each new level is gated to platform.edit
    writes = [
        ("PATCH", f"/projects/{pid}/l3/{l3}/arch", {"summary": "x"}),
        ("POST", f"/projects/{pid}/l3/{l3}/arch/components", {"name": "c"}),
        ("POST", f"/projects/{pid}/l4/{l4}/arch/code-units", {"name": "u"}),
    ]
    for method, path, body in writes:
        assert client.request(method, path, json=body, headers=hdr(client.ids["viewer"])).status_code == 403
        assert client.request(method, path, json=body, headers=hdr(client.ids["contributor"])).status_code in (200, 201)


def test_integration_config_is_admin_only(client):
    # catalog readable by anyone signed in
    assert client.get("/integrations/catalog", headers=hdr(client.ids["viewer"])).status_code == 200
    # config read/write needs admin.integrations (admin only; managers lack it)
    assert client.get("/integrations/jira/config", headers=hdr(client.ids["manager"])).status_code == 403
    assert client.get("/integrations/jira/config", headers=hdr(client.ids["admin"])).status_code == 200
    body = {"values": {"base_url": "https://x.atlassian.net", "email": "a@a.com", "api_token": "t"}, "enabled": True}
    assert client.patch("/integrations/jira/config", json=body, headers=hdr(client.ids["manager"])).status_code == 403
    assert client.patch("/integrations/jira/config", json=body, headers=hdr(client.ids["admin"])).status_code == 200


def test_chat_query_open_apply_gated(client):
    pid, *_ = _chain(client)
    # a viewer can query/propose via chat...
    proposal = client.post(f"/projects/{pid}/chat", json={"message": "create an L2 called payments"}, headers=hdr(client.ids["viewer"]))
    assert proposal.status_code == 200
    mutation = proposal.json()["mutation"]
    # ...but cannot apply the write
    assert client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=hdr(client.ids["viewer"])).status_code == 403
    assert client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=hdr(client.ids["contributor"])).status_code == 200


# ---- ABAC: a restricted workspace admits only admin/manager -----------------

def test_restricted_project_blocks_viewer_and_contributor_across_levels(client):
    created = client.post("/projects", json={"name": "Secret", "sensitivity": "restricted"}, headers=hdr(client.ids["admin"]))
    pid = created.json()["id"]
    h = hdr(client.ids["admin"])
    l1 = client.post(f"/projects/{pid}/c4/elements", json={"level": "L1", "name": "I"}, headers=h).json()["id"]
    l2 = client.post(f"/projects/{pid}/c4/elements", json={"level": "L2", "name": "C", "parent_id": l1}, headers=h).json()["id"]

    for path in (f"/projects/{pid}/c4/graph", f"/projects/{pid}/l2/{l2}/arch", f"/projects/{pid}/workflow"):
        assert client.get(path, headers=hdr(client.ids["viewer"])).status_code == 403       # viewer blocked
        assert client.get(path, headers=hdr(client.ids["contributor"])).status_code == 403   # contributor blocked
        assert client.get(path, headers=hdr(client.ids["manager"])).status_code == 200        # manager passes
        assert client.get(path, headers=hdr(client.ids["admin"])).status_code == 200


# ---- 503 when the LLM configuration is incomplete ---------------------------

def test_ai_and_chat_return_503_when_llm_unconfigured(client):
    pid, *_ = _chain(client)
    h = hdr(client.ids["admin"])
    # Simulate a startup configuration error (e.g. a provider with a missing key);
    # the lifespan stashes these and LLM routes must fail closed with 503.
    original = list(getattr(client.app.state, "configuration_errors", []))
    client.app.state.configuration_errors = [{"code": "missing_key", "message": "LLM_API_KEY is required"}]
    try:
        assert client.get("/health").json()["llm"]["status"] != "configured"
        assert client.post(f"/projects/{pid}/chat", json={"message": "status?"}, headers=h).status_code == 503
        assert client.post("/ai/orchestrate", json={"request": "draft the vision"}, headers=h).status_code == 503
    finally:
        client.app.state.configuration_errors = original
