"""Persistence for the L4 code / implementation-detail workspace (lean: no RACI/approvals)."""

from __future__ import annotations

from typing import Any

from backend.l4arch.models import (
    ChecklistCreate,
    ChecklistUpdate,
    CodeUnitCreate,
    CodeUnitUpdate,
    L4Update,
    TestCaseCreate,
    TestCaseUpdate,
)
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class NotFoundError(LookupError):
    pass


class L4ArchValidationError(ValueError):
    pass


def _require_l4(conn: Any, project_id: str, l4_element_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (l4_element_id, project_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"L4 element '{l4_element_id}' was not found")
    if row["level"] != "L4":
        raise L4ArchValidationError("Implementation detail attaches only to L4 elements")
    return dict(row)


_L4_DEFAULT = {"summary": "", "code_diagram": "", "status": "draft"}


def get_l4(project_id: str, l4_element_id: str) -> dict[str, Any]:
    with connect() as conn:
        _require_l4(conn, project_id, l4_element_id)
        row = conn.execute("SELECT * FROM l4_arch WHERE l4_element_id = ?", (l4_element_id,)).fetchone()
    if row is None:
        return {"l4_element_id": l4_element_id, "project_id": project_id, **_L4_DEFAULT, "updated_at": None}
    return dict(row)


def update_l4(project_id: str, l4_element_id: str, payload: L4Update) -> dict[str, Any]:
    with connect() as conn:
        _require_l4(conn, project_id, l4_element_id)
        existing = conn.execute("SELECT * FROM l4_arch WHERE l4_element_id = ?", (l4_element_id,)).fetchone()
        merged = dict(existing) if existing else {"l4_element_id": l4_element_id, "project_id": project_id, **_L4_DEFAULT}
        provided = payload.model_dump(exclude_unset=True)
        merged.update({key: value for key, value in provided.items() if value is not None})
        merged["updated_at"] = utc_now()
        conn.execute(
            """INSERT INTO l4_arch (l4_element_id, project_id, summary, code_diagram, status, updated_at)
               VALUES (:l4_element_id, :project_id, :summary, :code_diagram, :status, :updated_at)
               ON CONFLICT(l4_element_id) DO UPDATE SET
                 summary=excluded.summary, code_diagram=excluded.code_diagram,
                 status=excluded.status, updated_at=excluded.updated_at""",
            merged,
        )
    return get_l4(project_id, l4_element_id)


# ---- generic helpers ----

def _list(table: str, l4_element_id: str, order: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM {table} WHERE l4_element_id = ? ORDER BY {order}", (l4_element_id,)).fetchall()
    return rows_to_dicts(rows)


def _delete(table: str, project_id: str, item_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            f"""DELETE FROM {table} WHERE id = ? AND l4_element_id IN
                (SELECT id FROM c4_elements WHERE project_id = ?)""",
            (item_id, project_id),
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Item '{item_id}' was not found")


def _update(table: str, project_id: str, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            f"""SELECT t.* FROM {table} t JOIN c4_elements e ON e.id = t.l4_element_id
                WHERE t.id = ? AND e.project_id = ?""",
            (item_id, project_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Item '{item_id}' was not found")
        if changes:
            assignments = ", ".join(f"{key} = :{key}" for key in changes)
            conn.execute(f"UPDATE {table} SET {assignments} WHERE id = :id", {**changes, "id": item_id})
        updated = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    return dict(updated)


def _create(table: str, project_id: str, l4_element_id: str, columns: list[str], data: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        _require_l4(conn, project_id, l4_element_id)
        record = {"id": new_id(), "l4_element_id": l4_element_id, "created_at": utc_now(), **data}
        cols = ", ".join(["id", "l4_element_id", *columns, "created_at"])
        placeholders = ", ".join(f":{c}" for c in ["id", "l4_element_id", *columns, "created_at"])
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", record)
    return record


# ---- code units ----

_CODE_UNIT_COLS = ["name", "unit_type", "responsibility", "tech", "path", "complexity", "status"]


def list_code_units(l4_element_id: str) -> list[dict[str, Any]]:
    return _list("l4_code_units", l4_element_id, "name COLLATE NOCASE")


def create_code_unit(project_id: str, l4_element_id: str, payload: CodeUnitCreate) -> dict[str, Any]:
    return _create("l4_code_units", project_id, l4_element_id, _CODE_UNIT_COLS, payload.model_dump())


def update_code_unit(project_id: str, item_id: str, payload: CodeUnitUpdate) -> dict[str, Any]:
    return _update("l4_code_units", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_code_unit(project_id: str, item_id: str) -> None:
    _delete("l4_code_units", project_id, item_id)


# ---- test cases ----

_TEST_CASE_COLS = ["name", "test_type", "scenario", "expected", "status"]


def list_test_cases(l4_element_id: str) -> list[dict[str, Any]]:
    return _list("l4_test_cases", l4_element_id, "created_at")


def create_test_case(project_id: str, l4_element_id: str, payload: TestCaseCreate) -> dict[str, Any]:
    return _create("l4_test_cases", project_id, l4_element_id, _TEST_CASE_COLS, payload.model_dump())


def update_test_case(project_id: str, item_id: str, payload: TestCaseUpdate) -> dict[str, Any]:
    return _update("l4_test_cases", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_test_case(project_id: str, item_id: str) -> None:
    _delete("l4_test_cases", project_id, item_id)


# ---- checklist (Definition of Done) ----

_CHECKLIST_COLS = ["item", "category", "done"]


def _hydrate_checklist(row: dict[str, Any]) -> dict[str, Any]:
    row["done"] = bool(row.get("done"))
    return row


def list_checklist(l4_element_id: str) -> list[dict[str, Any]]:
    return [_hydrate_checklist(r) for r in _list("l4_checklist", l4_element_id, "created_at")]


def create_checklist_item(project_id: str, l4_element_id: str, payload: ChecklistCreate) -> dict[str, Any]:
    data = payload.model_dump()
    data["done"] = 1 if data["done"] else 0
    return _hydrate_checklist(_create("l4_checklist", project_id, l4_element_id, _CHECKLIST_COLS, data))


def update_checklist_item(project_id: str, item_id: str, payload: ChecklistUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if "done" in changes:
        changes["done"] = 1 if changes["done"] else 0
    return _hydrate_checklist(_update("l4_checklist", project_id, item_id, changes))


def delete_checklist_item(project_id: str, item_id: str) -> None:
    _delete("l4_checklist", project_id, item_id)


# ---- aggregate ----

def get_workspace(project_id: str, l4_element_id: str) -> dict[str, Any]:
    from backend.l4arch.service import readiness

    with connect() as conn:
        element = _require_l4(conn, project_id, l4_element_id)
        parent = None
        if element.get("parent_id"):
            parent_row = conn.execute("SELECT id, name, level FROM c4_elements WHERE id = ?", (element["parent_id"],)).fetchone()
            parent = dict(parent_row) if parent_row else None
    workspace = {
        "element": element,
        "parent": parent,
        "arch": get_l4(project_id, l4_element_id),
        "code_units": list_code_units(l4_element_id),
        "test_cases": list_test_cases(l4_element_id),
        "checklist": list_checklist(l4_element_id),
    }
    workspace["readiness"] = readiness(project_id, l4_element_id, workspace)
    return workspace
