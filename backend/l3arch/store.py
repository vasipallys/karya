"""Persistence for the L3 component-architecture workspace."""

from __future__ import annotations

import json
from typing import Any

from backend.l3arch.models import (
    ComponentCreate,
    ComponentUpdate,
    ConcernCreate,
    ConcernUpdate,
    DependencyCreate,
    DependencyUpdate,
    InterfaceCreate,
    InterfaceUpdate,
    L3Update,
)
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class NotFoundError(LookupError):
    pass


class L3ArchValidationError(ValueError):
    pass


def _require_l3(conn: Any, project_id: str, l3_element_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (l3_element_id, project_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"L3 element '{l3_element_id}' was not found")
    if row["level"] != "L3":
        raise L3ArchValidationError("Component architecture attaches only to L3 elements")
    return dict(row)


_L3_DEFAULT = {"summary": "", "component_diagram": "", "raci": "{}", "status": "draft"}

# RACI grid (component design responsibilities).
RACI_ARTIFACTS = ("component_diagram", "component_breakdown", "interfaces", "dependencies",
                  "design_concerns", "security", "testing", "documentation")
RACI_ROLES = ("product_owner", "tech_lead", "engineer", "security_engineer", "qa", "sre")


def _hydrate_arch(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raci")
    if isinstance(raw, str):
        try:
            row["raci"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            row["raci"] = {}
    return row


def get_l3(project_id: str, l3_element_id: str) -> dict[str, Any]:
    with connect() as conn:
        _require_l3(conn, project_id, l3_element_id)
        row = conn.execute("SELECT * FROM l3_arch WHERE l3_element_id = ?", (l3_element_id,)).fetchone()
    if row is None:
        return _hydrate_arch({"l3_element_id": l3_element_id, "project_id": project_id, **_L3_DEFAULT, "updated_at": None})
    return _hydrate_arch(dict(row))


def update_l3(project_id: str, l3_element_id: str, payload: L3Update) -> dict[str, Any]:
    with connect() as conn:
        _require_l3(conn, project_id, l3_element_id)
        existing = conn.execute("SELECT * FROM l3_arch WHERE l3_element_id = ?", (l3_element_id,)).fetchone()
        merged = dict(existing) if existing else {"l3_element_id": l3_element_id, "project_id": project_id, **_L3_DEFAULT}
        provided = payload.model_dump(exclude_unset=True)
        merged.update({key: value for key, value in provided.items() if value is not None})
        merged["updated_at"] = utc_now()
        conn.execute(
            """INSERT INTO l3_arch (l3_element_id, project_id, summary, component_diagram, status, updated_at)
               VALUES (:l3_element_id, :project_id, :summary, :component_diagram, :status, :updated_at)
               ON CONFLICT(l3_element_id) DO UPDATE SET
                 summary=excluded.summary, component_diagram=excluded.component_diagram,
                 status=excluded.status, updated_at=excluded.updated_at""",
            merged,
        )
    return get_l3(project_id, l3_element_id)


# ---- generic helpers ----

def _list(table: str, l3_element_id: str, order: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM {table} WHERE l3_element_id = ? ORDER BY {order}", (l3_element_id,)).fetchall()
    return rows_to_dicts(rows)


def _delete(table: str, project_id: str, item_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            f"""DELETE FROM {table} WHERE id = ? AND l3_element_id IN
                (SELECT id FROM c4_elements WHERE project_id = ?)""",
            (item_id, project_id),
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Item '{item_id}' was not found")


def _update(table: str, project_id: str, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            f"""SELECT t.* FROM {table} t JOIN c4_elements e ON e.id = t.l3_element_id
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


def _create(table: str, project_id: str, l3_element_id: str, columns: list[str], data: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        _require_l3(conn, project_id, l3_element_id)
        record = {"id": new_id(), "l3_element_id": l3_element_id, "created_at": utc_now(), **data}
        cols = ", ".join(["id", "l3_element_id", *columns, "created_at"])
        placeholders = ", ".join(f":{c}" for c in ["id", "l3_element_id", *columns, "created_at"])
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", record)
    return record


# ---- components ----

_COMPONENT_COLS = ["name", "component_type", "responsibilities", "tech", "pattern", "owner", "status"]


def list_components(l3_element_id: str) -> list[dict[str, Any]]:
    return _list("l3_components", l3_element_id, "name COLLATE NOCASE")


def create_component(project_id: str, l3_element_id: str, payload: ComponentCreate) -> dict[str, Any]:
    return _create("l3_components", project_id, l3_element_id, _COMPONENT_COLS, payload.model_dump())


def update_component(project_id: str, item_id: str, payload: ComponentUpdate) -> dict[str, Any]:
    return _update("l3_components", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_component(project_id: str, item_id: str) -> None:
    _delete("l3_components", project_id, item_id)


# ---- interfaces ----

_INTERFACE_COLS = ["name", "direction", "interface_type", "contract", "counterpart", "authentication", "status"]


def list_interfaces(l3_element_id: str) -> list[dict[str, Any]]:
    return _list("l3_interfaces", l3_element_id, "name COLLATE NOCASE")


def create_interface(project_id: str, l3_element_id: str, payload: InterfaceCreate) -> dict[str, Any]:
    return _create("l3_interfaces", project_id, l3_element_id, _INTERFACE_COLS, payload.model_dump())


def update_interface(project_id: str, item_id: str, payload: InterfaceUpdate) -> dict[str, Any]:
    return _update("l3_interfaces", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_interface(project_id: str, item_id: str) -> None:
    _delete("l3_interfaces", project_id, item_id)


# ---- dependencies ----

_DEPENDENCY_COLS = ["name", "dependency_type", "target", "reason", "criticality", "status"]


def list_dependencies(l3_element_id: str) -> list[dict[str, Any]]:
    return _list("l3_dependencies", l3_element_id, "name COLLATE NOCASE")


def create_dependency(project_id: str, l3_element_id: str, payload: DependencyCreate) -> dict[str, Any]:
    return _create("l3_dependencies", project_id, l3_element_id, _DEPENDENCY_COLS, payload.model_dump())


def update_dependency(project_id: str, item_id: str, payload: DependencyUpdate) -> dict[str, Any]:
    return _update("l3_dependencies", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_dependency(project_id: str, item_id: str) -> None:
    _delete("l3_dependencies", project_id, item_id)


# ---- concerns ----

_CONCERN_COLS = ["name", "category", "approach", "owner", "status"]


def list_concerns(l3_element_id: str) -> list[dict[str, Any]]:
    return _list("l3_concerns", l3_element_id, "created_at")


def create_concern(project_id: str, l3_element_id: str, payload: ConcernCreate) -> dict[str, Any]:
    return _create("l3_concerns", project_id, l3_element_id, _CONCERN_COLS, payload.model_dump())


def update_concern(project_id: str, item_id: str, payload: ConcernUpdate) -> dict[str, Any]:
    return _update("l3_concerns", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_concern(project_id: str, item_id: str) -> None:
    _delete("l3_concerns", project_id, item_id)


# ---- RACI matrix ----

def set_raci(project_id: str, l3_element_id: str, artifact: str, role: str, value: str) -> dict[str, Any]:
    if artifact not in RACI_ARTIFACTS or role not in RACI_ROLES:
        raise L3ArchValidationError("Unknown RACI artifact or role")
    if value not in ("R", "A", "C", "I", ""):
        raise L3ArchValidationError("RACI value must be R, A, C, I or empty")
    update_l3(project_id, l3_element_id, L3Update())  # ensure the arch row exists
    with connect() as conn:
        row = conn.execute("SELECT raci FROM l3_arch WHERE l3_element_id = ?", (l3_element_id,)).fetchone()
        matrix = json.loads(row["raci"] or "{}") if row else {}
        key = f"{artifact}:{role}"
        if value:
            matrix[key] = value
        else:
            matrix.pop(key, None)
        conn.execute("UPDATE l3_arch SET raci = ?, updated_at = ? WHERE l3_element_id = ?",
                     (json.dumps(matrix), utc_now(), l3_element_id))
    return get_l3(project_id, l3_element_id)["raci"]


# ---- approvals (component design sign-off) ----

APPROVAL_STAGES: tuple[tuple[str, str], ...] = (
    ("design", "Design review"),
    ("interfaces", "Interface & contract review"),
    ("security", "Security review"),
    ("testing", "Test strategy review"),
    ("architecture", "Architecture approval"),
    ("tech_lead", "Tech-lead sign-off"),
)
_STAGE_LABEL = dict(APPROVAL_STAGES)
_STAGE_ORDER = {stage: index for index, (stage, _) in enumerate(APPROVAL_STAGES)}


def list_approvals(l3_element_id: str) -> list[dict[str, Any]]:
    rows = _list("l3_approvals", l3_element_id, "ordinal")
    for row in rows:
        row["label"] = _STAGE_LABEL.get(row["stage"], row["stage"])
    return rows


def submit_for_review(project_id: str, l3_element_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        _require_l3(conn, project_id, l3_element_id)
        conn.execute("DELETE FROM l3_approvals WHERE l3_element_id = ?", (l3_element_id,))
        for stage, _ in APPROVAL_STAGES:
            conn.execute(
                "INSERT INTO l3_approvals (id, l3_element_id, stage, ordinal, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                (new_id(), l3_element_id, stage, _STAGE_ORDER[stage], utc_now()),
            )
    return list_approvals(l3_element_id)


def decide_approval(project_id: str, l3_element_id: str, stage: str, approve: bool, decided_by: str, comment: str) -> dict[str, Any]:
    if stage not in _STAGE_ORDER:
        raise L3ArchValidationError(f"Unknown approval stage '{stage}'")
    with connect() as conn:
        _require_l3(conn, project_id, l3_element_id)
        rows = {r["stage"]: dict(r) for r in conn.execute(
            "SELECT * FROM l3_approvals WHERE l3_element_id = ?", (l3_element_id,)).fetchall()}
        if not rows:
            raise L3ArchValidationError("Submit for review before recording approvals")
        for earlier, order in _STAGE_ORDER.items():
            if order < _STAGE_ORDER[stage] and rows.get(earlier, {}).get("status") != "approved":
                raise L3ArchValidationError(f"'{_STAGE_LABEL[earlier]}' must be approved before '{_STAGE_LABEL[stage]}'")
        conn.execute(
            "UPDATE l3_approvals SET status = ?, decided_by = ?, decided_at = ?, comment = ? WHERE l3_element_id = ? AND stage = ?",
            ("approved" if approve else "rejected", decided_by, utc_now(), comment, l3_element_id, stage),
        )
        statuses = [r["status"] for r in conn.execute("SELECT status FROM l3_approvals WHERE l3_element_id = ?", (l3_element_id,)).fetchall()]
        all_approved = all(s == "approved" for s in statuses) and len(statuses) == len(APPROVAL_STAGES)
    if all_approved:
        update_l3(project_id, l3_element_id, L3Update(status="baselined"))
    elif not approve and get_l3(project_id, l3_element_id)["status"] == "baselined":
        update_l3(project_id, l3_element_id, L3Update(status="reviewed"))
    return approval_state(l3_element_id)


def approval_state(l3_element_id: str) -> dict[str, Any]:
    stages = list_approvals(l3_element_id)
    approved = [s for s in stages if s["status"] == "approved"]
    current = next((s for s in stages if s["status"] == "pending"), None)
    return {
        "submitted": len(stages) > 0,
        "stages": stages,
        "approved_count": len(approved),
        "total": len(APPROVAL_STAGES),
        "rejected": any(s["status"] == "rejected" for s in stages),
        "current_stage": current["stage"] if current else None,
        "complete": len(stages) > 0 and len(approved) == len(APPROVAL_STAGES),
    }


# ---- aggregate ----

def get_workspace(project_id: str, l3_element_id: str) -> dict[str, Any]:
    from backend.l3arch.service import readiness

    with connect() as conn:
        element = _require_l3(conn, project_id, l3_element_id)
        parent = None
        if element.get("parent_id"):
            parent_row = conn.execute("SELECT id, name, level FROM c4_elements WHERE id = ?", (element["parent_id"],)).fetchone()
            parent = dict(parent_row) if parent_row else None
    workspace = {
        "element": element,
        "parent": parent,
        "arch": get_l3(project_id, l3_element_id),
        "components": list_components(l3_element_id),
        "interfaces": list_interfaces(l3_element_id),
        "dependencies": list_dependencies(l3_element_id),
        "concerns": list_concerns(l3_element_id),
        "approvals": approval_state(l3_element_id),
        "raci_artifacts": list(RACI_ARTIFACTS),
        "raci_roles": list(RACI_ROLES),
    }
    workspace["readiness"] = readiness(project_id, l3_element_id, workspace)
    return workspace
