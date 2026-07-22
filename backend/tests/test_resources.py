"""Global resource-directory persistence, validation, and custom-field tests."""

from __future__ import annotations

import shutil
import tempfile
from io import BytesIO
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.integrations import store as integration_store
from backend.resources import imports as resource_imports
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
    path = Path(tempfile.mkdtemp(prefix="karya-resources-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("KARYA_DB", str(work_dir / "test.db"))
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


def _workbook(rows: list[dict]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Resources")
    return output.getvalue()


def test_excel_import_supports_single_bulk_skip_and_update():
    content = _workbook([
        {"First Name": "Ada", "Last Name": "Lovelace", "Staff Type": "Perm", "Citizenship": "GB"},
        {"First Name": "Alan", "Last Name": "Turing", "Staff Type": "Contract", "Citizenship": "GB"},
    ])
    first = resource_imports.import_excel(content, "people.xlsx")
    assert first["counts"] == {"created": 2, "updated": 0, "skipped": 0, "errors": 0}

    repeated = resource_imports.import_excel(content, "people.xlsx")
    assert repeated["counts"] == {"created": 0, "updated": 0, "skipped": 2, "errors": 0}

    changed = _workbook([{"Display Name": "Ada Lovelace", "Staff Status": "Inactive"}])
    updated = resource_imports.import_excel(changed, "one-person.xlsx", update_existing=True)
    assert updated["counts"]["updated"] == 1
    assert store.list_staff({"search": "Ada"})[0]["staff_status"] == "Inactive"


def test_excel_import_reports_row_errors_without_losing_valid_rows():
    custom = store.create_custom_field(
        CustomFieldCreate(key="clearance", label="Clearance", field_type="select", options=["SC", "DV"])
    )
    assert custom["key"] == "clearance"
    content = _workbook([
        {"First Name": "Grace", "Last Name": "Hopper", "custom:clearance": "SC"},
        {"First Name": "Bad", "Last Name": "Value", "custom:clearance": "INVALID"},
    ])
    result = resource_imports.import_excel(content, "people.xlsx")
    assert result["counts"] == {"created": 1, "updated": 0, "skipped": 0, "errors": 1}
    assert result["errors"][0]["row"] == 3
    assert store.list_staff()[0]["custom_values"] == {"clearance": "SC"}


def test_ldap_import_uses_enabled_connector_and_maps_directory_entries(monkeypatch):
    integration_store.save_config("ldap", {
        "server_url": "ldaps://directory.example.com:636",
        "bind_dn": "cn=reader,dc=example,dc=com",
        "bind_password": "SECRET",
        "base_dn": "ou=people,dc=example,dc=com",
    }, enabled=True)
    monkeypatch.setattr(resource_imports, "_fetch_ldap_entries", lambda settings, search_filter, max_results: [
        {"givenName": ["Linus"], "sn": ["Torvalds"], "displayName": ["Linus Torvalds"],
         "employeeType": ["Contractor"], "department": ["PLATFORM"], "c": ["FI"]},
        {"givenName": ["Margaret"], "sn": ["Hamilton"], "displayName": ["Margaret Hamilton"],
         "userAccountControl": ["514"]},
    ])
    result = resource_imports.import_ldap("ldap", "(objectClass=person)", 100)
    assert result["counts"]["created"] == 2
    people = {person["staff_name"]: person for person in store.list_staff()}
    assert people["Linus Torvalds"]["staff_type"] == "Contract"
    assert people["Linus Torvalds"]["tech_unit"] == "PLATFORM"
    assert people["Margaret Hamilton"]["staff_status"] == "Inactive"


def test_single_ldap_import_builds_escaped_identity_filter(monkeypatch):
    integration_store.save_config("ldap", {
        "server_url": "ldaps://directory.example.com", "bind_dn": "cn=reader",
        "bind_password": "SECRET", "base_dn": "dc=example,dc=com",
    }, enabled=True)
    captured = {}

    def fake_fetch(settings, search_filter, max_results):
        captured.update(filter=search_filter, max_results=max_results)
        return [{"givenName": ["Ada"], "sn": ["Lovelace"], "displayName": ["Ada Lovelace"]}]

    monkeypatch.setattr(resource_imports, "_fetch_ldap_entries", fake_fetch)
    result = resource_imports.import_ldap(
        "ldap", "(objectClass=person)", 500, identifier="ada*(test)@example.com",
    )
    assert result["counts"]["created"] == 1
    assert captured["max_results"] == 1
    assert "ada\\2a\\28test\\29@example.com" in captured["filter"]
    assert captured["filter"].startswith("(&(objectClass=person)(|")


def test_resource_import_endpoints_and_rbac():
    content = _workbook([{"First Name": "Katherine", "Last Name": "Johnson"}])
    with TestClient(app) as client:
        template = client.get("/resources/import/template", headers={"X-User-Role": "viewer"})
        assert template.status_code == 200
        assert template.headers["content-type"].startswith("application/vnd.openxmlformats")
        forbidden = client.post(
            "/resources/import/excel", files={"file": ("people.xlsx", content)},
            headers={"X-User-Role": "contributor"},
        )
        assert forbidden.status_code == 403
        imported = client.post(
            "/resources/import/excel", files={"file": ("people.xlsx", content)},
            headers={"X-User-Role": "admin"},
        )
        assert imported.status_code == 200
        assert imported.json()["counts"]["created"] == 1
