"""Persistence for L1 architecture-baseline artifacts."""

from __future__ import annotations

from typing import Any

from backend.l1arch.models import (
    CapabilityCreate,
    CapabilityUpdate,
    CommentCreate,
    OkrCreate,
    OkrUpdate,
    RiskCreate,
    RiskUpdate,
    StakeholderCreate,
    StakeholderUpdate,
    VisionUpdate,
)
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class NotFoundError(LookupError):
    pass


class L1ArchValidationError(ValueError):
    pass


def _require_l1(conn: Any, project_id: str, l1_element_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (l1_element_id, project_id)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"L1 element '{l1_element_id}' was not found")
    if row["level"] != "L1":
        raise L1ArchValidationError("Architecture baselines attach only to L1 elements")
    return dict(row)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


# ---------------------------------------------------------------- vision

_VISION_DEFAULT = {
    "vision_statement": "", "business_problem": "", "target_users": "",
    "vision_statement_details": "", "business_problem_details": "", "target_users_details": "",
    "strategic_theme": "", "status": "draft",
}


def get_vision(project_id: str, l1_element_id: str) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        row = conn.execute("SELECT * FROM l1_vision WHERE l1_element_id = ?", (l1_element_id,)).fetchone()
    if row is None:
        return {"l1_element_id": l1_element_id, "project_id": project_id, **_VISION_DEFAULT, "updated_at": None}
    return dict(row)


def update_vision(project_id: str, l1_element_id: str, payload: VisionUpdate) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        existing = conn.execute("SELECT * FROM l1_vision WHERE l1_element_id = ?", (l1_element_id,)).fetchone()
        merged = dict(existing) if existing else {"l1_element_id": l1_element_id, "project_id": project_id, **_VISION_DEFAULT}
        provided = payload.model_dump(exclude_unset=True)
        merged.update({key: value for key, value in provided.items() if value is not None})
        merged["updated_at"] = utc_now()
        conn.execute(
            """INSERT INTO l1_vision (l1_element_id, project_id, vision_statement, business_problem, target_users,
                 vision_statement_details, business_problem_details, target_users_details, strategic_theme, status, updated_at)
               VALUES (:l1_element_id, :project_id, :vision_statement, :business_problem, :target_users,
                 :vision_statement_details, :business_problem_details, :target_users_details, :strategic_theme, :status, :updated_at)
               ON CONFLICT(l1_element_id) DO UPDATE SET
                 vision_statement=excluded.vision_statement, business_problem=excluded.business_problem,
                 target_users=excluded.target_users, vision_statement_details=excluded.vision_statement_details,
                 business_problem_details=excluded.business_problem_details, target_users_details=excluded.target_users_details,
                 strategic_theme=excluded.strategic_theme, status=excluded.status, updated_at=excluded.updated_at""",
            merged,
        )
    return get_vision(project_id, l1_element_id)


# ---------------------------------------------------------------- generic list/delete helpers

def _list(table: str, l1_element_id: str, order: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE l1_element_id = ? ORDER BY {order}", (l1_element_id,)
        ).fetchall()
    return rows_to_dicts(rows)


def _delete(table: str, project_id: str, item_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            f"""DELETE FROM {table} WHERE id = ? AND l1_element_id IN
                (SELECT id FROM c4_elements WHERE project_id = ?)""",
            (item_id, project_id),
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Item '{item_id}' was not found")


def _update(table: str, project_id: str, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            f"""SELECT t.* FROM {table} t JOIN c4_elements e ON e.id = t.l1_element_id
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


# ---------------------------------------------------------------- OKRs

def list_okrs(l1_element_id: str) -> list[dict[str, Any]]:
    return _list("l1_okrs", l1_element_id, "created_at")


def create_okr(project_id: str, l1_element_id: str, payload: OkrCreate) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        record = {"id": new_id(), "l1_element_id": l1_element_id, "created_at": utc_now(), **payload.model_dump()}
        conn.execute(
            """INSERT INTO l1_okrs (id, l1_element_id, linked_element_id, objective, key_result, metric_name, baseline_value, target_value, current_value, owner, status, created_at)
               VALUES (:id, :l1_element_id, :linked_element_id, :objective, :key_result, :metric_name, :baseline_value, :target_value, :current_value, :owner, :status, :created_at)""",
            record,
        )
    return record


def update_okr(project_id: str, item_id: str, payload: OkrUpdate) -> dict[str, Any]:
    return _update("l1_okrs", project_id, item_id, payload.model_dump(exclude_unset=True))


def delete_okr(project_id: str, item_id: str) -> None:
    _delete("l1_okrs", project_id, item_id)


# ---------------------------------------------------------------- stakeholders

def list_stakeholders(l1_element_id: str) -> list[dict[str, Any]]:
    return _list("l1_stakeholders", l1_element_id, "name COLLATE NOCASE")


def create_stakeholder(project_id: str, l1_element_id: str, payload: StakeholderCreate) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        _check_resource(conn, payload.resource_staff_id)
        record = {"id": new_id(), "l1_element_id": l1_element_id, "created_at": utc_now(), **payload.model_dump()}
        conn.execute(
            """INSERT INTO l1_stakeholders (id, l1_element_id, resource_staff_id, name, email, department, role, stakeholder_type, influence, interest, raci, owns, status, created_at)
               VALUES (:id, :l1_element_id, :resource_staff_id, :name, :email, :department, :role, :stakeholder_type, :influence, :interest, :raci, :owns, :status, :created_at)""",
            record,
        )
    return record


def update_stakeholder(project_id: str, item_id: str, payload: StakeholderUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if "resource_staff_id" in changes:
        with connect() as conn:
            _check_resource(conn, changes["resource_staff_id"])
    return _update("l1_stakeholders", project_id, item_id, changes)


def delete_stakeholder(project_id: str, item_id: str) -> None:
    _delete("l1_stakeholders", project_id, item_id)


def _check_resource(conn: Any, resource_staff_id: str | None) -> None:
    if resource_staff_id and conn.execute(
        "SELECT 1 FROM resource_staff WHERE id = ?", (resource_staff_id,)
    ).fetchone() is None:
        raise L1ArchValidationError(f"Resource '{resource_staff_id}' was not found")


# ---------------------------------------------------------------- capabilities

def list_capabilities(l1_element_id: str) -> list[dict[str, Any]]:
    return _list("l1_capabilities", l1_element_id, "cap_level, name COLLATE NOCASE")


def create_capability(project_id: str, l1_element_id: str, payload: CapabilityCreate) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        _check_parent_capability(conn, l1_element_id, payload.parent_id)
        record = {"id": new_id(), "l1_element_id": l1_element_id, "created_at": utc_now(), **payload.model_dump()}
        conn.execute(
            """INSERT INTO l1_capabilities (id, l1_element_id, parent_id, linked_element_id, name, description, cap_level, business_owner, technology_owner, criticality, current_maturity, target_maturity, strategic_priority, status, created_at)
               VALUES (:id, :l1_element_id, :parent_id, :linked_element_id, :name, :description, :cap_level, :business_owner, :technology_owner, :criticality, :current_maturity, :target_maturity, :strategic_priority, :status, :created_at)""",
            record,
        )
    return record


def update_capability(project_id: str, item_id: str, payload: CapabilityUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("parent_id") == item_id:
        raise L1ArchValidationError("A capability cannot be its own parent")
    return _update("l1_capabilities", project_id, item_id, changes)


def delete_capability(project_id: str, item_id: str) -> None:
    _delete("l1_capabilities", project_id, item_id)


def _check_parent_capability(conn: Any, l1_element_id: str, parent_id: str | None) -> None:
    if not parent_id:
        return
    row = conn.execute("SELECT l1_element_id FROM l1_capabilities WHERE id = ?", (parent_id,)).fetchone()
    if row is None or row["l1_element_id"] != l1_element_id:
        raise L1ArchValidationError("Parent capability must belong to the same L1 initiative")


# ---------------------------------------------------------------- risks

def list_risks(l1_element_id: str) -> list[dict[str, Any]]:
    return _list("l1_risks", l1_element_id, "created_at")


def create_risk(project_id: str, l1_element_id: str, payload: RiskCreate) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        data = payload.model_dump()
        record = {"id": new_id(), "l1_element_id": l1_element_id, "created_at": utc_now(), **data, "target_date": _iso(payload.target_date)}
        conn.execute(
            """INSERT INTO l1_risks (id, l1_element_id, linked_element_id, title, category, risk_level, owner, mitigation, funding_source, approved_budget, forecast_spend, actual_spend, status, target_date, created_at)
               VALUES (:id, :l1_element_id, :linked_element_id, :title, :category, :risk_level, :owner, :mitigation, :funding_source, :approved_budget, :forecast_spend, :actual_spend, :status, :target_date, :created_at)""",
            record,
        )
    return record


def update_risk(project_id: str, item_id: str, payload: RiskUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if "target_date" in changes:
        changes["target_date"] = _iso(payload.target_date)
    return _update("l1_risks", project_id, item_id, changes)


def delete_risk(project_id: str, item_id: str) -> None:
    _delete("l1_risks", project_id, item_id)


# ---------------------------------------------------------------- approvals

# Sequential sign-off chain (requirement section 9.3).
APPROVAL_STAGES: tuple[tuple[str, str], ...] = (
    ("product", "Product owner review"),
    ("architecture", "Architecture review"),
    ("security", "Security review"),
    ("risk", "Risk review"),
    ("finance", "Finance review"),
    ("sponsor", "Business sponsor approval"),
)
_STAGE_LABEL = dict(APPROVAL_STAGES)
_STAGE_ORDER = {stage: index for index, (stage, _) in enumerate(APPROVAL_STAGES)}


def list_approvals(l1_element_id: str) -> list[dict[str, Any]]:
    rows = _list("l1_approvals", l1_element_id, "ordinal")
    for row in rows:
        row["label"] = _STAGE_LABEL.get(row["stage"], row["stage"])
    return rows


def submit_for_review(project_id: str, l1_element_id: str) -> list[dict[str, Any]]:
    """(Re)start the sign-off chain: reset every stage to pending."""
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        conn.execute("DELETE FROM l1_approvals WHERE l1_element_id = ?", (l1_element_id,))
        for stage, _ in APPROVAL_STAGES:
            conn.execute(
                """INSERT INTO l1_approvals (id, l1_element_id, stage, ordinal, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (new_id(), l1_element_id, stage, _STAGE_ORDER[stage], utc_now()),
            )
    return list_approvals(l1_element_id)


def decide_approval(project_id: str, l1_element_id: str, stage: str, approve: bool, decided_by: str, comment: str) -> dict[str, Any]:
    if stage not in _STAGE_ORDER:
        raise L1ArchValidationError(f"Unknown approval stage '{stage}'")
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        rows = {r["stage"]: dict(r) for r in conn.execute(
            "SELECT * FROM l1_approvals WHERE l1_element_id = ?", (l1_element_id,)
        ).fetchall()}
        if not rows:
            raise L1ArchValidationError("Submit the baseline for review before recording approvals")
        # Enforce the sequential chain: earlier stages must be approved first.
        for earlier, order in _STAGE_ORDER.items():
            if order < _STAGE_ORDER[stage] and rows.get(earlier, {}).get("status") != "approved":
                raise L1ArchValidationError(f"'{_STAGE_LABEL[earlier]}' must be approved before '{_STAGE_LABEL[stage]}'")
        conn.execute(
            "UPDATE l1_approvals SET status = ?, decided_by = ?, decided_at = ?, comment = ? WHERE l1_element_id = ? AND stage = ?",
            ("approved" if approve else "rejected", decided_by, utc_now(), comment, l1_element_id, stage),
        )
        # If every stage is now approved, baseline the L1 vision.
        statuses = conn.execute(
            "SELECT status FROM l1_approvals WHERE l1_element_id = ?", (l1_element_id,)
        ).fetchall()
        all_approved = all(row["status"] == "approved" for row in statuses) and len(statuses) == len(APPROVAL_STAGES)
    if all_approved:
        update_vision(project_id, l1_element_id, VisionUpdate(status="baselined"))
    elif not approve:
        # A rejection un-baselines and reverts to draft for rework.
        current = get_vision(project_id, l1_element_id)
        if current["status"] == "baselined":
            update_vision(project_id, l1_element_id, VisionUpdate(status="draft"))
    return approval_state(l1_element_id)


def approval_state(l1_element_id: str) -> dict[str, Any]:
    stages = list_approvals(l1_element_id)
    submitted = len(stages) > 0
    approved = [s for s in stages if s["status"] == "approved"]
    rejected = [s for s in stages if s["status"] == "rejected"]
    current = next((s for s in stages if s["status"] == "pending"), None)
    return {
        "submitted": submitted,
        "stages": stages,
        "approved_count": len(approved),
        "total": len(APPROVAL_STAGES),
        "rejected": bool(rejected),
        "current_stage": current["stage"] if current else None,
        "complete": submitted and len(approved) == len(APPROVAL_STAGES),
    }


# ---------------------------------------------------------------- comments

def list_comments(l1_element_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM l1_comments WHERE l1_element_id = ? ORDER BY created_at DESC", (l1_element_id,)
        ).fetchall()
    return rows_to_dicts(rows)


def create_comment(project_id: str, l1_element_id: str, payload: CommentCreate) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        record = {"id": new_id(), "l1_element_id": l1_element_id, "status": "open", "created_at": utc_now(), **payload.model_dump()}
        conn.execute(
            """INSERT INTO l1_comments (id, l1_element_id, artifact_type, artifact_id, body, author, status, created_at)
               VALUES (:id, :l1_element_id, :artifact_type, :artifact_id, :body, :author, :status, :created_at)""",
            record,
        )
    return record


def resolve_comment(project_id: str, comment_id: str, resolved: bool = True) -> dict[str, Any]:
    return _update("l1_comments", project_id, comment_id, {"status": "resolved" if resolved else "open"})


def delete_comment(project_id: str, comment_id: str) -> None:
    _delete("l1_comments", project_id, comment_id)


# ---------------------------------------------------------------- aggregate

def get_baseline(project_id: str, l1_element_id: str) -> dict[str, Any]:
    """Everything for the L1 architecture tab in one call."""
    from backend.l1arch.service import readiness

    with connect() as conn:
        element = _require_l1(conn, project_id, l1_element_id)
    baseline = {
        "element": element,
        "vision": get_vision(project_id, l1_element_id),
        "okrs": list_okrs(l1_element_id),
        "stakeholders": list_stakeholders(l1_element_id),
        "capabilities": list_capabilities(l1_element_id),
        "risks": list_risks(l1_element_id),
        "approvals": approval_state(l1_element_id),
        "comments": list_comments(l1_element_id),
    }
    baseline["readiness"] = readiness(project_id, l1_element_id, baseline)
    return baseline
