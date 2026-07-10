"""Global resource-directory persistence, validation, and custom-field tests."""

from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

import pytest

from backend.resources import store
from backend.resources.models import (
    CustomFieldCreate,
    CustomFieldUpdate,
    LookupCreate,
    StaffCreate,
    StaffUpdate,
)
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-resources-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    db._initialized.clear()
    yield


def test_create_staff_generates_code_and_name():
    staff = store.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="Lovelace"))
    assert staff["staff_code"] == "STF-0001"
    assert staff["staff_name"] == "Ada Lovelace"
    assert staff["staff_status"] == "Active"
    assert staff["sub_status"] == "UnAllocated"
    assert staff["custom_values"] == {}

    second = store.create_staff(StaffCreate(staff_first_name="Alan", staff_last_name="Turing"))
    assert second["staff_code"] == "STF-0002"


def test_default_lookups_are_seeded():
    lookups = store.list_all_lookups()
    assert {row["code"] for row in lookups["tech_unit"]}
    assert {row["code"] for row in lookups["rank"]}
    assert {row["code"] for row in lookups["hr_role"]}


def test_lookup_value_must_exist():
    with pytest.raises(store.ValidationError):
        store.create_staff(
            StaffCreate(staff_first_name="A", staff_last_name="B", tech_unit="NOPE")
        )
    # A seeded code is accepted.
    store.create_staff(StaffCreate(staff_first_name="A", staff_last_name="B", tech_unit="PLATFORM"))


def test_reporting_manager_validation():
    manager = store.create_staff(StaffCreate(staff_first_name="Grace", staff_last_name="Hopper"))
    report = store.create_staff(
        StaffCreate(staff_first_name="Ken", staff_last_name="Thompson", reporting_manager_id=manager["id"])
    )
    assert report["reporting_manager_id"] == manager["id"]

    with pytest.raises(store.ValidationError):
        store.create_staff(
            StaffCreate(staff_first_name="X", staff_last_name="Y", reporting_manager_id="missing")
        )
    with pytest.raises(store.ValidationError):
        store.update_staff(report["id"], StaffUpdate(reporting_manager_id=report["id"]))


def test_delete_staff_breaks_reporting_chain():
    manager = store.create_staff(StaffCreate(staff_first_name="M", staff_last_name="Gr"))
    report = store.create_staff(
        StaffCreate(staff_first_name="R", staff_last_name="Ep", reporting_manager_id=manager["id"])
    )
    store.delete_staff(manager["id"])
    assert store.get_staff(report["id"])["reporting_manager_id"] is None


def test_date_order_enforced():
    with pytest.raises(ValueError):
        StaffCreate(
            staff_first_name="A",
            staff_last_name="B",
            staff_start_date=date(2026, 5, 1),
            staff_end_date=date(2026, 1, 1),
        )


def test_update_staff_and_filters():
    store.create_staff(StaffCreate(staff_first_name="Ada", staff_last_name="L", staff_status="Active"))
    inactive = store.create_staff(
        StaffCreate(staff_first_name="Alan", staff_last_name="T", staff_status="Active")
    )
    store.update_staff(inactive["id"], StaffUpdate(staff_status="Inactive", sub_status="Allocated"))

    assert len(store.list_staff({"staff_status": "Active"})) == 1
    assert len(store.list_staff({"sub_status": "Allocated"})) == 1
    assert len(store.list_staff({"search": "Ada"})) == 1


def test_custom_fields_lifecycle_and_validation():
    field = store.create_custom_field(
        CustomFieldCreate(key="clearance", label="Security Clearance", field_type="select", options=["SC", "DV"], required=True)
    )
    assert field["required"] is True
    assert field["options"] == ["SC", "DV"]

    # Required field missing -> rejected.
    with pytest.raises(store.ValidationError):
        store.create_staff(StaffCreate(staff_first_name="A", staff_last_name="B"))

    # Invalid select option -> rejected.
    with pytest.raises(store.ValidationError):
        store.create_staff(
            StaffCreate(staff_first_name="A", staff_last_name="B", custom_values={"clearance": "TOP"})
        )

    # Unknown key -> rejected.
    with pytest.raises(store.ValidationError):
        store.create_staff(
            StaffCreate(staff_first_name="A", staff_last_name="B", custom_values={"nope": "x"})
        )

    staff = store.create_staff(
        StaffCreate(staff_first_name="A", staff_last_name="B", custom_values={"clearance": "SC"})
    )
    assert staff["custom_values"]["clearance"] == "SC"

    store.update_custom_field(field["id"], CustomFieldUpdate(required=False))
    # Now a staff record with no custom values is accepted.
    store.create_staff(StaffCreate(staff_first_name="C", staff_last_name="D"))


def test_lookup_crud_and_in_use_guard():
    created = store.create_lookup("tech_unit", LookupCreate(code="AI", label="AI Lab"))
    assert created["code"] == "AI"
    with pytest.raises(store.ValidationError):
        store.create_lookup("tech_unit", LookupCreate(code="AI", label="Dup"))

    staff = store.create_staff(StaffCreate(staff_first_name="A", staff_last_name="B", tech_unit="AI"))
    with pytest.raises(store.ValidationError):
        store.delete_lookup(created["id"])

    store.delete_staff(staff["id"])
    store.delete_lookup(created["id"])
    assert all(row["code"] != "AI" for row in store.list_lookups("tech_unit"))
