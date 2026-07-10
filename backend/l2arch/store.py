"""Persistence for the L2 container-architecture workspace."""

from __future__ import annotations

import json
from typing import Any

from backend.l2arch.models import (
    ApiCreate,
    ApiUpdate,
    ContainerCreate,
    ContainerUpdate,
    IntegrationCreate,
    IntegrationUpdate,
    L2Update,
    NfrCreate,
    NfrUpdate,
)
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class NotFoundError(LookupError):
    pass


class L2ArchValidationError(ValueError):
    pass


def _require_l2(conn: Any, project_id: str, l2_element_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (l2_element_id, project_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"L2 element '{l2_element_id}' was not found")
    if row["level"] != "L2":
        raise L2ArchValidationError("Container architecture attaches only to L2 elements")
    return dict(row)


_L2_DEFAULT = {"summary": "", "container_diagram": "", "raci": "{}", "status": "draft"}

# RACI grid (requirement section 10.3).
RACI_ARTIFACTS = ("container_diagram", "service_boundaries", "api_contracts", "data_contracts",
                  "deployment_topology", "nfrs", "integration_plan", "security_review")
RACI_ROLES = ("product_owner", "solution_architect", "engineering_lead", "security_architect",
              "data_owner", "sre", "risk_owner")


def _hydrate_arch(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raci")
    if isinstance(raw, str):
        try:
            row["raci"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            row["raci"] = {}
    return row


def get_l2(project_id: str, l2_element_id: str) -> dict[str, Any]:
    with connect() as conn:
        _require_l2(conn, project_id, l2_element_id)
        row = conn.execute("SELECT * FROM l2_arch WHERE l2_element_id = ?", (l2_element_id,)).fetchone()
    if row is None:
        return _hydrate_arch({"l2_element_id": l2_element_id, "project_id": project_id, **_L2_DEFAULT, "updated_at": None})
    return _hydrate_arch(dict(row))


def update_l2(project_id: str, l2_element_id: str, payload: L2Update) -> dict[str, Any]:
    with connect() as conn:
        _require_l2(conn, project_id, l2_element_id)
        existing = conn.execute("SELECT * FROM l2_arch WHERE l2_element_id = ?", (l2_element_id,)).fetchone()
        merged = dict(existing) if existing else {"l2_element_id": l2_element_id, "project_id": project_id, **_L2_DEFAULT}
        provided = payload.model_dump(exclude_unset=True)
        merged.update({key: value for key, value in provided.items() if value is not None})
        merged["updated_at"] = utc_now()
        conn.execute(
            """INSERT INTO l2_arch (l2_element_id, project_id, summary, container_diagram, status, updated_at)
               VALUES (:l2_element_id, :project_id, :summary, :container_diagram, :status, :updated_at)
               ON CONFLICT(l2_element_id) DO UPDATE SET
                 summary=excluded.summary, container_diagram=excluded.container_diagram,
                 status=excluded.status, updated_at=excluded.updated_at""",
            merged,
        )
    return get_l2(project_id, l2_element_id)


# ---- generic helpers ----

def _list(table: str, l2_element_id: str, order: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM {table} WHERE l2_element_id = ? ORDER BY {order}", (l2_element_id,)).fetchall()
    return rows_to_dicts(rows)


def _delete(table: str, project_id: str, item_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            f"""DELETE FROM {table} WHERE id = ? AND l2_element_id IN
                (SELECT id FROM c4_elements WHERE project_id = ?)""",
            (item_id, project_id),
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Item '{item_id}' was not found")


def _update(table: str, project_id: str, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            f"""SELECT t.* FROM {table} t JOIN c4_elements e ON e.id = t.l2_element_id
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


def _create(table: str, project_id: str, l2_element_id: str, columns: list[str], data: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        _require_l2(conn, project_id, l2_element_id)
        record = {"id": new_id(), "l2_element_id": l2_element_id, "created_at": utc_now(), **data}
        cols = ", ".join(["id", "l2_element_id", *columns, "created_at"])
        placeholders = ", ".join(f":{c}" for c in ["id", "l2_element_id", *columns, "created_at"])
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", record)
    return record


# ---- containers ----

_CONTAINER_COLS = ["name", "capability", "responsibilities", "owns_data", "owner_team", "security_classification", "nfr_criticality", "status"]


def list_containers(l2_element_id: str) -> list[dict[str, Any]]:
    return _list("l2_containers", l2_element_id, "name COLLATE NOCASE")


def create_container(project_id: str, l2_element_id: str, payload: ContainerCreate) -> dict[str, Any]:
    return _create("l2_containers", project_id, l2_element_id, _CONTAINER_COLS, payload.model_dump())


def update_container(project_id: str, item_id: str, payload: ContainerUpdate) -> dict[str, Any]:
    return _update("l2_containers", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_container(project_id: str, item_id: str) -> None:
    _delete("l2_containers", project_id, item_id)


# ---- APIs ----

_API_COLS = ["name", "provider", "consumer", "endpoint", "api_type", "data_classification", "authentication", "version", "owner", "status"]


def list_apis(l2_element_id: str) -> list[dict[str, Any]]:
    return _list("l2_apis", l2_element_id, "name COLLATE NOCASE")


def create_api(project_id: str, l2_element_id: str, payload: ApiCreate) -> dict[str, Any]:
    return _create("l2_apis", project_id, l2_element_id, _API_COLS, payload.model_dump())


def update_api(project_id: str, item_id: str, payload: ApiUpdate) -> dict[str, Any]:
    return _update("l2_apis", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_api(project_id: str, item_id: str) -> None:
    _delete("l2_apis", project_id, item_id)


# ---- NFRs ----

_NFR_COLS = ["name", "category", "scenario", "metric", "baseline", "target", "owner", "risk_level", "status"]


def list_nfrs(l2_element_id: str) -> list[dict[str, Any]]:
    return _list("l2_nfrs", l2_element_id, "created_at")


def create_nfr(project_id: str, l2_element_id: str, payload: NfrCreate) -> dict[str, Any]:
    return _create("l2_nfrs", project_id, l2_element_id, _NFR_COLS, payload.model_dump())


def update_nfr(project_id: str, item_id: str, payload: NfrUpdate) -> dict[str, Any]:
    return _update("l2_nfrs", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_nfr(project_id: str, item_id: str) -> None:
    _delete("l2_nfrs", project_id, item_id)


# ---- integrations ----

_INTEGRATION_COLS = ["name", "source_system", "target_system", "integration_type", "data_exchanged", "security_method", "status"]


def list_integrations(l2_element_id: str) -> list[dict[str, Any]]:
    return _list("l2_integrations", l2_element_id, "created_at")


def create_integration(project_id: str, l2_element_id: str, payload: IntegrationCreate) -> dict[str, Any]:
    return _create("l2_integrations", project_id, l2_element_id, _INTEGRATION_COLS, payload.model_dump())


def update_integration(project_id: str, item_id: str, payload: IntegrationUpdate) -> dict[str, Any]:
    return _update("l2_integrations", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_integration(project_id: str, item_id: str) -> None:
    _delete("l2_integrations", project_id, item_id)


# ---- RACI matrix ----

def set_raci(project_id: str, l2_element_id: str, artifact: str, role: str, value: str) -> dict[str, Any]:
    from backend.l2arch.models import L2Update
    if artifact not in RACI_ARTIFACTS or role not in RACI_ROLES:
        raise L2ArchValidationError("Unknown RACI artifact or role")
    if value not in ("R", "A", "C", "I", ""):
        raise L2ArchValidationError("RACI value must be R, A, C, I or empty")
    update_l2(project_id, l2_element_id, L2Update())  # ensure the arch row exists
    with connect() as conn:
        row = conn.execute("SELECT raci FROM l2_arch WHERE l2_element_id = ?", (l2_element_id,)).fetchone()
        matrix = json.loads(row["raci"] or "{}") if row else {}
        key = f"{artifact}:{role}"
        if value:
            matrix[key] = value
        else:
            matrix.pop(key, None)
        conn.execute("UPDATE l2_arch SET raci = ?, updated_at = ? WHERE l2_element_id = ?",
                     (json.dumps(matrix), utc_now(), l2_element_id))
    return get_l2(project_id, l2_element_id)["raci"]


# ---- approvals (requirement section 14) ----

APPROVAL_STAGES: tuple[tuple[str, str], ...] = (
    ("engineering", "Engineering review"),
    ("security", "Security review"),
    ("nfr", "NFR review"),
    ("data", "Data ownership review"),
    ("architecture", "Architecture approval"),
    ("sponsor", "Sponsor sign-off"),
)
_STAGE_LABEL = dict(APPROVAL_STAGES)
_STAGE_ORDER = {stage: index for index, (stage, _) in enumerate(APPROVAL_STAGES)}


def list_approvals(l2_element_id: str) -> list[dict[str, Any]]:
    rows = _list("l2_approvals", l2_element_id, "ordinal")
    for row in rows:
        row["label"] = _STAGE_LABEL.get(row["stage"], row["stage"])
    return rows


def submit_for_review(project_id: str, l2_element_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        _require_l2(conn, project_id, l2_element_id)
        conn.execute("DELETE FROM l2_approvals WHERE l2_element_id = ?", (l2_element_id,))
        for stage, _ in APPROVAL_STAGES:
            conn.execute(
                "INSERT INTO l2_approvals (id, l2_element_id, stage, ordinal, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                (new_id(), l2_element_id, stage, _STAGE_ORDER[stage], utc_now()),
            )
    return list_approvals(l2_element_id)


def decide_approval(project_id: str, l2_element_id: str, stage: str, approve: bool, decided_by: str, comment: str) -> dict[str, Any]:
    from backend.l2arch.models import L2Update
    if stage not in _STAGE_ORDER:
        raise L2ArchValidationError(f"Unknown approval stage '{stage}'")
    with connect() as conn:
        _require_l2(conn, project_id, l2_element_id)
        rows = {r["stage"]: dict(r) for r in conn.execute(
            "SELECT * FROM l2_approvals WHERE l2_element_id = ?", (l2_element_id,)).fetchall()}
        if not rows:
            raise L2ArchValidationError("Submit for review before recording approvals")
        for earlier, order in _STAGE_ORDER.items():
            if order < _STAGE_ORDER[stage] and rows.get(earlier, {}).get("status") != "approved":
                raise L2ArchValidationError(f"'{_STAGE_LABEL[earlier]}' must be approved before '{_STAGE_LABEL[stage]}'")
        conn.execute(
            "UPDATE l2_approvals SET status = ?, decided_by = ?, decided_at = ?, comment = ? WHERE l2_element_id = ? AND stage = ?",
            ("approved" if approve else "rejected", decided_by, utc_now(), comment, l2_element_id, stage),
        )
        statuses = [r["status"] for r in conn.execute("SELECT status FROM l2_approvals WHERE l2_element_id = ?", (l2_element_id,)).fetchall()]
        all_approved = all(s == "approved" for s in statuses) and len(statuses) == len(APPROVAL_STAGES)
    if all_approved:
        update_l2(project_id, l2_element_id, L2Update(status="baselined"))
    elif not approve and get_l2(project_id, l2_element_id)["status"] == "baselined":
        update_l2(project_id, l2_element_id, L2Update(status="reviewed"))
    return approval_state(l2_element_id)


def approval_state(l2_element_id: str) -> dict[str, Any]:
    stages = list_approvals(l2_element_id)
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

def get_workspace(project_id: str, l2_element_id: str) -> dict[str, Any]:
    from backend.l2arch.service import readiness

    with connect() as conn:
        element = _require_l2(conn, project_id, l2_element_id)
        parent = None
        if element.get("parent_id"):
            parent_row = conn.execute("SELECT id, name, level FROM c4_elements WHERE id = ?", (element["parent_id"],)).fetchone()
            parent = dict(parent_row) if parent_row else None
    workspace = {
        "element": element,
        "parent": parent,
        "arch": get_l2(project_id, l2_element_id),
        "containers": list_containers(l2_element_id),
        "apis": list_apis(l2_element_id),
        "nfrs": list_nfrs(l2_element_id),
        "integrations": list_integrations(l2_element_id),
        "approvals": approval_state(l2_element_id),
        "raci_artifacts": list(RACI_ARTIFACTS),
        "raci_roles": list(RACI_ROLES),
    }
    workspace["readiness"] = readiness(project_id, l2_element_id, workspace)
    return workspace
