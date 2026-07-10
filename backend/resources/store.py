"""Persistence + invariants for the global resource directory."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.resources.models import (
    LOOKUP_CATEGORIES,
    CustomFieldCreate,
    CustomFieldUpdate,
    LookupCreate,
    LookupUpdate,
    StaffCreate,
    StaffUpdate,
)
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now

# Fixed staff columns that map a lookup category to its column name.
_LOOKUP_COLUMN = {"tech_unit": "tech_unit", "rank": "rank", "hr_role": "hr_role"}

_STAFF_COLUMNS = (
    "staff_first_name",
    "staff_last_name",
    "staff_name",
    "staff_type",
    "staff_status",
    "sub_status",
    "tech_unit",
    "citizenship",
    "rank",
    "hr_role",
    "staff_start_date",
    "staff_end_date",
    "reporting_manager_id",
)


class NotFoundError(LookupError):
    pass


class ValidationError(ValueError):
    """Business-rule violation (surfaced as HTTP 400)."""


# ---------------------------------------------------------------- helpers


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _hydrate_staff(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("custom_values")
    if isinstance(raw, str):
        try:
            row["custom_values"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            row["custom_values"] = {}
    elif not isinstance(raw, dict):
        row["custom_values"] = {}
    return row


def _lookup_codes(conn: sqlite3.Connection, category: str) -> set[str]:
    rows = conn.execute(
        "SELECT code FROM resource_lookups WHERE category = ?", (category,)
    ).fetchall()
    return {row["code"] for row in rows}


def _custom_field_defs(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute("SELECT * FROM resource_custom_fields").fetchall()
    defs: dict[str, dict[str, Any]] = {}
    for row in rows:
        field = dict(row)
        field["options"] = json.loads(field.get("options") or "[]")
        field["required"] = bool(field.get("required"))
        defs[field["key"]] = field
    return defs


def _validate_lookups(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    for category, column in _LOOKUP_COLUMN.items():
        value = (values.get(column) or "").strip()
        if value and value not in _lookup_codes(conn, category):
            raise ValidationError(
                f"{column} '{value}' is not defined in the {category} lookup table"
            )


def _validate_manager(conn: sqlite3.Connection, staff_id: str | None, manager_id: str | None) -> None:
    if not manager_id:
        return
    if manager_id == staff_id:
        raise ValidationError("A staff member cannot report to themselves")
    if conn.execute("SELECT 1 FROM resource_staff WHERE id = ?", (manager_id,)).fetchone() is None:
        raise ValidationError(f"reporting_manager_id '{manager_id}' does not exist")


def _validate_custom_values(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    defs = _custom_field_defs(conn)
    unknown = set(values) - set(defs)
    if unknown:
        raise ValidationError(f"Unknown custom field(s): {', '.join(sorted(unknown))}")
    for key, field in defs.items():
        if field["required"] and not str(values.get(key, "")).strip():
            raise ValidationError(f"Custom field '{field['label']}' is required")
        if field["field_type"] == "select" and values.get(key):
            if values[key] not in field["options"]:
                raise ValidationError(
                    f"'{values[key]}' is not a valid option for '{field['label']}'"
                )
    return values


def _next_staff_code(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT staff_code FROM resource_staff WHERE staff_code LIKE 'STF-%' "
        "ORDER BY CAST(SUBSTR(staff_code, 5) AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    last = int(row["staff_code"][4:]) if row else 0
    return f"STF-{last + 1:04d}"


# ---------------------------------------------------------------- staff


def create_staff(payload: StaffCreate) -> dict[str, Any]:
    data = payload.model_dump()
    with connect() as conn:
        _validate_lookups(conn, data)
        _validate_manager(conn, None, data.get("reporting_manager_id"))
        custom_values = _validate_custom_values(conn, data.get("custom_values") or {})
        record = {
            "id": new_id(),
            "staff_code": _next_staff_code(conn),
            **{key: data[key] for key in _STAFF_COLUMNS},
            "staff_start_date": _iso(payload.staff_start_date),
            "staff_end_date": _iso(payload.staff_end_date),
            "custom_values": json.dumps(custom_values),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        columns = ", ".join(record)
        placeholders = ", ".join(f":{key}" for key in record)
        conn.execute(f"INSERT INTO resource_staff ({columns}) VALUES ({placeholders})", record)
    return get_staff(record["id"])


def list_staff(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for key in ("staff_status", "sub_status", "staff_type", "tech_unit", "rank", "hr_role"):
        value = (filters or {}).get(key)
        if value:
            clauses.append(f"{key} = :{key}")
            params[key] = value
    search = (filters or {}).get("search")
    if search:
        clauses.append("(staff_name LIKE :search OR staff_code LIKE :search)")
        params["search"] = f"%{search}%"
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM resource_staff{where} ORDER BY staff_name COLLATE NOCASE", params
        ).fetchall()
    return [_hydrate_staff(dict(row)) for row in rows]


def get_staff(staff_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM resource_staff WHERE id = ?", (staff_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Staff '{staff_id}' was not found")
    return _hydrate_staff(dict(row))


def update_staff(staff_id: str, payload: StaffUpdate) -> dict[str, Any]:
    provided = payload.model_dump(exclude_unset=True)
    with connect() as conn:
        current = conn.execute("SELECT * FROM resource_staff WHERE id = ?", (staff_id,)).fetchone()
        if current is None:
            raise NotFoundError(f"Staff '{staff_id}' was not found")
        merged = _hydrate_staff(dict(current))
        merged.update({key: value for key, value in provided.items() if key != "custom_values"})
        # Regenerate the display name only if the caller cleared it or changed the parts.
        if "staff_name" in provided and not (provided.get("staff_name") or "").strip():
            merged["staff_name"] = f"{merged['staff_first_name']} {merged['staff_last_name']}".strip()

        _validate_lookups(conn, merged)
        _validate_manager(conn, staff_id, merged.get("reporting_manager_id"))
        if merged.get("staff_start_date") and merged.get("staff_end_date"):
            if str(merged["staff_end_date"]) < str(merged["staff_start_date"]):
                raise ValidationError("staff_end_date must be on or after staff_start_date")

        changes: dict[str, Any] = {}
        for key in (*_STAFF_COLUMNS,):
            if key in provided or key == "staff_name":
                value = merged[key]
                changes[key] = _iso(value) if key in ("staff_start_date", "staff_end_date") else value
        if "custom_values" in provided:
            changes["custom_values"] = json.dumps(
                _validate_custom_values(conn, provided.get("custom_values") or {})
            )
        changes["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = :{key}" for key in changes)
        conn.execute(
            f"UPDATE resource_staff SET {assignments} WHERE id = :id", {**changes, "id": staff_id}
        )
    return get_staff(staff_id)


def delete_staff(staff_id: str) -> None:
    with connect() as conn:
        if conn.execute("SELECT 1 FROM resource_staff WHERE id = ?", (staff_id,)).fetchone() is None:
            raise NotFoundError(f"Staff '{staff_id}' was not found")
        # Break reporting chains that pointed at the removed person.
        conn.execute(
            "UPDATE resource_staff SET reporting_manager_id = NULL WHERE reporting_manager_id = ?",
            (staff_id,),
        )
        conn.execute("DELETE FROM resource_staff WHERE id = ?", (staff_id,))


# ---------------------------------------------------------------- lookups


def list_lookups(category: str) -> list[dict[str, Any]]:
    _require_category(category)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM resource_lookups WHERE category = ? ORDER BY label COLLATE NOCASE",
            (category,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_all_lookups() -> dict[str, list[dict[str, Any]]]:
    return {category: list_lookups(category) for category in LOOKUP_CATEGORIES}


def create_lookup(category: str, payload: LookupCreate) -> dict[str, Any]:
    _require_category(category)
    record = {"id": new_id(), "category": category, "code": payload.code, "label": payload.label}
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM resource_lookups WHERE category = ? AND code = ?",
            (category, payload.code),
        ).fetchone()
        if exists:
            raise ValidationError(f"'{payload.code}' already exists in the {category} table")
        conn.execute(
            "INSERT INTO resource_lookups (id, category, code, label) VALUES (:id, :category, :code, :label)",
            record,
        )
    return record


def update_lookup(lookup_id: str, payload: LookupUpdate) -> dict[str, Any]:
    with connect() as conn:
        if conn.execute("SELECT 1 FROM resource_lookups WHERE id = ?", (lookup_id,)).fetchone() is None:
            raise NotFoundError(f"Lookup '{lookup_id}' was not found")
        conn.execute(
            "UPDATE resource_lookups SET label = ? WHERE id = ?", (payload.label, lookup_id)
        )
        row = conn.execute("SELECT * FROM resource_lookups WHERE id = ?", (lookup_id,)).fetchone()
    return dict(row)


def delete_lookup(lookup_id: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM resource_lookups WHERE id = ?", (lookup_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Lookup '{lookup_id}' was not found")
        column = _LOOKUP_COLUMN[row["category"]]
        in_use = conn.execute(
            f"SELECT 1 FROM resource_staff WHERE {column} = ? LIMIT 1", (row["code"],)
        ).fetchone()
        if in_use:
            raise ValidationError(f"'{row['code']}' is assigned to staff and cannot be deleted")
        conn.execute("DELETE FROM resource_lookups WHERE id = ?", (lookup_id,))


# ---------------------------------------------------------------- custom fields


def list_custom_fields() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM resource_custom_fields ORDER BY created_at"
        ).fetchall()
    return [_hydrate_custom_field(dict(row)) for row in rows]


def create_custom_field(payload: CustomFieldCreate) -> dict[str, Any]:
    record = {
        "id": new_id(),
        "key": payload.key,
        "label": payload.label,
        "field_type": payload.field_type,
        "required": 1 if payload.required else 0,
        "options": json.dumps(payload.options),
        "created_at": utc_now(),
    }
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM resource_custom_fields WHERE key = ?", (payload.key,)
        ).fetchone()
        if exists:
            raise ValidationError(f"A custom field with key '{payload.key}' already exists")
        conn.execute(
            """INSERT INTO resource_custom_fields (id, key, label, field_type, required, options, created_at)
               VALUES (:id, :key, :label, :field_type, :required, :options, :created_at)""",
            record,
        )
    return _hydrate_custom_field(record)


def update_custom_field(field_id: str, payload: CustomFieldUpdate) -> dict[str, Any]:
    provided = payload.model_dump(exclude_unset=True)
    with connect() as conn:
        current = conn.execute(
            "SELECT * FROM resource_custom_fields WHERE id = ?", (field_id,)
        ).fetchone()
        if current is None:
            raise NotFoundError(f"Custom field '{field_id}' was not found")
        changes: dict[str, Any] = {}
        if "label" in provided:
            changes["label"] = provided["label"]
        if "field_type" in provided:
            changes["field_type"] = provided["field_type"]
        if "required" in provided:
            changes["required"] = 1 if provided["required"] else 0
        if "options" in provided:
            changes["options"] = json.dumps(provided["options"] or [])
        if changes:
            assignments = ", ".join(f"{key} = :{key}" for key in changes)
            conn.execute(
                f"UPDATE resource_custom_fields SET {assignments} WHERE id = :id",
                {**changes, "id": field_id},
            )
        row = conn.execute("SELECT * FROM resource_custom_fields WHERE id = ?", (field_id,)).fetchone()
    return _hydrate_custom_field(dict(row))


def delete_custom_field(field_id: str) -> None:
    with connect() as conn:
        if conn.execute(
            "SELECT 1 FROM resource_custom_fields WHERE id = ?", (field_id,)
        ).fetchone() is None:
            raise NotFoundError(f"Custom field '{field_id}' was not found")
        conn.execute("DELETE FROM resource_custom_fields WHERE id = ?", (field_id,))


def _hydrate_custom_field(row: dict[str, Any]) -> dict[str, Any]:
    row["options"] = json.loads(row.get("options") or "[]") if isinstance(row.get("options"), str) else row.get("options", [])
    row["required"] = bool(row.get("required"))
    return row


def _require_category(category: str) -> None:
    if category not in LOOKUP_CATEGORIES:
        raise NotFoundError(f"Unknown lookup category '{category}'")
