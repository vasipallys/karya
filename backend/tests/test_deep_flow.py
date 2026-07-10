"""End-to-end lifecycle coherence (L1→L4 + estimate + roll-up + workflow + chat) and the error envelope."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-deep-flow-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from backend.storage import db
    db._initialized.clear()
    db.init_db()
    from backend.access import store as access
    from backend.access.models import AccessUpdate
    from backend.resources import store as resources
    from backend.resources.models import StaffCreate
    admin = resources.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="Admin"))
    access.set_access(admin["id"], AccessUpdate(role="admin"))
    from backend.api.main import app
    with TestClient(app) as c:
        c.h = {"X-User-Id": admin["id"]}
        yield c


def _el(client, pid, level, name, parent=None):
    body = {"level": level, "name": name}
    if parent:
        body["parent_id"] = parent
    r = client.post(f"/projects/{pid}/c4/elements", json=body, headers=client.h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_full_top_down_lifecycle_is_coherent(client):
    pid = client.post("/projects", json={"name": "Bank"}, headers=client.h).json()["id"]
    l1 = _el(client, pid, "L1", "Digital banking")
    l2 = _el(client, pid, "L2", "onboarding", l1)
    l3 = _el(client, pid, "L3", "pay-api", l2)
    l4 = _el(client, pid, "L4", "PayController", l3)

    # AI-generate each architecture level (mock) then apply, and confirm readiness climbs.
    for level, eid in (("l2", l2), ("l3", l3), ("l4", l4)):
        before = client.get(f"/projects/{pid}/{level}/{eid}/arch/readiness", headers=client.h).json()["score"]
        draft = client.post(f"/projects/{pid}/{level}/{eid}/ai/{level}", json={"brief": "go"}, headers=client.h).json()
        client.post(f"/projects/{pid}/{level}/{eid}/ai/{level}/apply", json={"draft": draft}, headers=client.h)
        after = client.get(f"/projects/{pid}/{level}/{eid}/arch/readiness", headers=client.h).json()["score"]
        assert after > before, f"{level} readiness should rise after applying the AI baseline"

    # traceability chains line up across the levels
    l2_trace = client.get(f"/projects/{pid}/l2/{l2}/arch/traceability", headers=client.h).json()
    assert l2_trace["l1"]["name"] == "Digital banking" and l2_trace["l3_count"] == 1
    l4_trace = client.get(f"/projects/{pid}/l4/{l4}/arch/traceability", headers=client.h).json()
    assert l4_trace["l3"]["name"] == "pay-api" and l4_trace["l2"]["name"] == "onboarding"

    # estimate the L3 story → roll-up and workflow both reflect it
    from backend.c4 import store as c4_store
    c4_store.upsert_artifact(l3, "story", points=5)
    rollup = client.get(f"/projects/{pid}/rollup", headers=client.h).json()
    assert rollup["totals"]["rolled_up_points"] == 5 and rollup["totals"]["estimated_stories"] == 1

    guide = client.get(f"/projects/{pid}/workflow", headers=client.h).json()
    assert guide["estimation"]["estimated"] == 1 and guide["estimation"]["pct"] == 100
    levels = {v["level"]: v for v in guide["levels"]}
    assert all(levels[l]["count"] == 1 for l in ("L1", "L2", "L3", "L4"))

    # the assistant can answer questions about the same project
    overview = client.post(f"/projects/{pid}/chat", json={"message": "what's the status?"}, headers=client.h).json()
    assert overview["action"] == "overview"
    listing = client.post(f"/projects/{pid}/chat", json={"message": "list L3"}, headers=client.h).json()
    assert any(i["name"] == "pay-api" for i in listing["data"]["items"])


def test_chat_create_then_query_reflects_new_element(client):
    pid = client.post("/projects", json={"name": "Flow"}, headers=client.h).json()["id"]
    _el(client, pid, "L1", "Init")
    proposal = client.post(f"/projects/{pid}/chat", json={"message": "create an L2 called payments under Init"}, headers=client.h).json()
    client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=client.h)
    listing = client.post(f"/projects/{pid}/chat", json={"message": "list L2"}, headers=client.h).json()
    assert any(i["name"] == "payments" for i in listing["data"]["items"])


# ---- error envelope consistency ---------------------------------------------

def _err(body):
    assert "error" in body and "code" in body["error"] and "message" in body["error"]
    return body["error"]


def test_error_envelope_shapes(client):
    pid = client.post("/projects", json={"name": "E"}, headers=client.h).json()["id"]
    l1 = _el(client, pid, "L1", "Initiative")

    # 404 — unknown element workspace
    r404 = client.get(f"/projects/{pid}/l2/does-not-exist/arch", headers=client.h)
    assert r404.status_code == 404 and _err(r404.json())["code"] == "not_found"

    # 400 — domain validation (L3 under L1 breaks the level rule)
    r400 = client.post(f"/projects/{pid}/c4/elements", json={"level": "L3", "name": "x", "parent_id": l1}, headers=client.h)
    assert r400.status_code == 400 and _err(r400.json())

    # 422 — request-body validation (missing required name)
    r422 = client.post("/projects", json={}, headers=client.h)
    assert r422.status_code == 422 and _err(r422.json())

    # chat clarifies (400) on an unknown element rather than 500-ing
    rchat = client.post(f"/projects/{pid}/chat", json={"message": "readiness of ghostcomponent"}, headers=client.h)
    assert rchat.status_code == 400 and _err(rchat.json())["code"] == "chat_invalid"


def test_wrong_level_arch_attach_is_400(client):
    pid = client.post("/projects", json={"name": "W"}, headers=client.h).json()["id"]
    l1 = _el(client, pid, "L1", "I")
    # attaching L2 container architecture to an L1 element is rejected cleanly
    r = client.post(f"/projects/{pid}/l2/{l1}/arch/containers", json={"name": "c"}, headers=client.h)
    assert r.status_code == 400 and _err(r.json())
