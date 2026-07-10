"""HTTP-level RBAC middleware tests (local demo auth)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-rbac-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from backend.storage import db
    db._initialized.clear()

    from backend.access import store as access
    from backend.access.models import AccessUpdate
    from backend.resources import store as resources
    from backend.resources.models import StaffCreate

    db.init_db()
    admin = resources.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="Admin"))
    viewer = resources.create_staff(StaffCreate(staff_first_name="Val", staff_last_name="Viewer"))
    manager = resources.create_staff(StaffCreate(staff_first_name="Mia", staff_last_name="Manager"))
    access.set_access(admin["id"], AccessUpdate(role="admin"))
    access.set_access(viewer["id"], AccessUpdate(role="viewer"))
    access.set_access(manager["id"], AccessUpdate(role="manager"))

    from backend.api.main import app
    with TestClient(app) as test_client:
        test_client.ids = {"admin": admin["id"], "viewer": viewer["id"], "manager": manager["id"]}
        yield test_client


def hdr(staff_id):
    return {"X-User-Id": staff_id}


def test_public_endpoints_need_no_auth(client):
    assert client.get("/health").status_code == 200
    assert client.get("/access/login-users").status_code == 200


def test_reads_require_authentication(client):
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers=hdr(client.ids["viewer"])).status_code == 200


def test_writes_require_capability(client):
    body = {"name": "Test platform"}
    # Viewer cannot create.
    assert client.post("/projects", json=body, headers=hdr(client.ids["viewer"])).status_code == 403
    # Manager (has platform.edit) can.
    assert client.post("/projects", json=body, headers=hdr(client.ids["manager"])).status_code == 200


def test_reporting_requires_reporting_capability(client):
    assert client.get("/reporting/overview", headers=hdr(client.ids["viewer"])).status_code == 403
    assert client.get("/reporting/overview", headers=hdr(client.ids["manager"])).status_code == 200


def test_access_management_is_admin_only(client):
    target = client.ids["viewer"]
    body = {"role": "contributor"}
    assert client.patch(f"/access/users/{target}", json=body, headers=hdr(client.ids["manager"])).status_code == 403
    assert client.patch(f"/access/users/{target}", json=body, headers=hdr(client.ids["admin"])).status_code == 200


def test_resource_reads_allowed_for_contributors_writes_gated(client):
    # A viewer can read the directory (planning dropdowns need it)...
    assert client.get("/resources/staff", headers=hdr(client.ids["viewer"])).status_code == 200
    # ...but cannot edit it.
    new_person = {"staff_first_name": "New", "staff_last_name": "Hire"}
    assert client.post("/resources/staff", json=new_person, headers=hdr(client.ids["viewer"])).status_code == 403
    assert client.post("/resources/staff", json=new_person, headers=hdr(client.ids["admin"])).status_code == 200


def test_bootstrap_admin_role_header_fallback(client):
    # The password-less bootstrap admin has no directory id, only a role header.
    assert client.get("/reporting/overview", headers={"X-User-Role": "admin"}).status_code == 200
    # A spoofed role that isn't recognised is rejected.
    assert client.get("/reporting/overview", headers={"X-User-Role": "superuser"}).status_code == 401
