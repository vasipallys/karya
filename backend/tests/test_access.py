"""Access management (roles) and reporting overview tests."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.access import store as access
from backend.access.models import AccessUpdate
from backend.reporting import service
from backend.resources import store as resources
from backend.resources.models import StaffCreate, StaffUpdate
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="karya-access-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("KARYA_DB", str(work_dir / "test.db"))
    db._initialized.clear()
    yield


def make_staff(first, last):
    return resources.create_staff(StaffCreate(staff_first_name=first, staff_last_name=last))


def test_bootstrap_promotes_first_staff_to_admin():
    first = make_staff("Diana", "Prince")
    make_staff("Marcus", "Chen")
    users = access.list_users()
    assert len(users) == 2
    diana = next(u for u in users if u["id"] == first["id"])
    assert diana["role"] == "admin"
    # Everyone else defaults to viewer.
    assert all(u["role"] == "viewer" for u in users if u["id"] != first["id"])


def test_no_staff_no_crash():
    assert access.list_users() == []
    assert access.list_users(enabled_only=True) == []


def test_set_role_and_enabled():
    make_staff("Diana", "Prince")
    marcus = make_staff("Marcus", "Chen")
    updated = access.set_access(marcus["id"], AccessUpdate(role="manager"))
    assert updated["role"] == "manager"
    assert updated["enabled"] is True

    disabled = access.set_access(marcus["id"], AccessUpdate(enabled=False))
    assert disabled["enabled"] is False
    assert disabled["role"] == "manager"  # role preserved when only toggling

    # Disabled users drop off the login list.
    login_ids = {u["id"] for u in access.list_users(enabled_only=True)}
    assert marcus["id"] not in login_ids


def test_inactive_staff_cannot_authenticate_and_active_admin_is_rebootstrapped():
    first = make_staff("Diana", "Prince")
    second = make_staff("Marcus", "Chen")
    access.list_users()  # bootstrap Diana

    resources.update_staff(first["id"], StaffUpdate(staff_status="Inactive"))

    assert access.effective_role(first["id"]) is None
    users = access.list_users()
    marcus = next(user for user in users if user["id"] == second["id"])
    assert marcus["role"] == "admin"
    assert {user["id"] for user in access.list_users(enabled_only=True)} == {second["id"]}


def test_unknown_staff_rejected():
    with pytest.raises(access.NotFoundError):
        access.set_access("missing", AccessUpdate(role="admin"))


def test_page_permissions_inherit_override_and_reset():
    make_staff("Diana", "Prince")
    viewer = make_staff("Victor", "Stone")
    initial = access.get_user(viewer["id"])
    assert initial["page_permissions"]["platforms"] is True
    assert initial["page_permissions"]["admin_reporting"] is False
    assert initial["page_permission_overrides"] == {}

    changed = access.set_page_permissions(viewer["id"], {"platforms": False, "admin_reporting": True})
    assert changed["page_permissions"]["platforms"] is False
    assert changed["page_permissions"]["admin_reporting"] is True
    assert changed["page_permission_overrides"] == {"platforms": False, "admin_reporting": True}
    assert access.page_permission_override(viewer["id"], "page.platforms") is False

    reset = access.set_page_permissions(viewer["id"], {"platforms": None})
    assert reset["page_permissions"]["platforms"] is True
    assert "platforms" not in reset["page_permission_overrides"]


def test_admin_page_permissions_cannot_be_overridden_and_unknown_pages_rejected():
    admin = make_staff("Diana", "Prince")
    with pytest.raises(access.ValidationError):
        access.set_page_permissions(admin["id"], {"platforms": False})
    viewer = make_staff("Victor", "Stone")
    with pytest.raises(access.ValidationError):
        access.set_page_permissions(viewer["id"], {"not_a_page": True})


def test_role_counts_and_reporting_overview():
    diana = make_staff("Diana", "Prince")   # bootstrapped admin
    marcus = make_staff("Marcus", "Chen")
    access.set_access(marcus["id"], AccessUpdate(role="manager"))

    counts = access.role_counts()
    assert counts["admin"] == 1
    assert counts["manager"] == 1

    overview = service.overview()
    assert overview["access"]["admin"] == 1
    assert overview["resources"]["total"] == 2
    assert overview["resources"]["active"] == 2
    assert overview["resources"]["on_bench"] == 2
    assert "by_tech_unit" in overview["resources"]
    assert overview["portfolio"]["projects"] == 0
    # Diana is referenced so the linter/reader sees the bootstrap subject.
    assert diana["staff_code"] == "STF-0001"
