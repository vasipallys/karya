"""SQLite persistence and invariants for L1 operating plans."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from backend.planning.models import (
    AgileUnitCreate,
    AgileUnitUpdate,
    DiagramCreate,
    DiagramUpdate,
    PlanSettingsUpdate,
    TeamMemberCreate,
    TeamMemberUpdate,
    WorkItemCreate,
    WorkItemUpdate,
)
from backend.projects.store import NotFoundError, get_project
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class PlanningValidationError(ValueError):
    pass


def _require_l1(conn: Any, project_id: str, l1_element_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM c4_elements WHERE id = ? AND project_id = ?",
        (l1_element_id, project_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"L1 element '{l1_element_id}' was not found")
    if row["level"] != "L1":
        raise PlanningValidationError("Operating plans can only be attached to L1 elements")
    return dict(row)


def _require_unit(conn: Any, project_id: str, unit_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM l1_agile_units WHERE id = ? AND project_id = ?",
        (unit_id, project_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Agile unit '{unit_id}' was not found")
    return dict(row)


def _check_parent_unit(
    conn: Any,
    project_id: str,
    l1_element_id: str,
    unit_type: str,
    parent_unit_id: str | None,
) -> None:
    if unit_type == "tribe" and parent_unit_id:
        raise PlanningValidationError("A tribe cannot be nested under another agile unit")
    if unit_type == "squad" and parent_unit_id:
        parent = _require_unit(conn, project_id, parent_unit_id)
        if parent["l1_element_id"] != l1_element_id or parent["unit_type"] != "tribe":
            raise PlanningValidationError("A squad parent must be a tribe in the same L1 plan")


def _serialize_dates(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value.isoformat() if isinstance(value, date) else value for key, value in values.items()}


def get_plan(project_id: str, l1_element_id: str) -> dict[str, Any]:
    get_project(project_id)
    with connect() as conn:
        element = _require_l1(conn, project_id, l1_element_id)
        units = rows_to_dicts(
            conn.execute(
                "SELECT * FROM l1_agile_units WHERE project_id = ? AND l1_element_id = ? ORDER BY unit_type, name",
                (project_id, l1_element_id),
            ).fetchall()
        )
        members = rows_to_dicts(
            conn.execute(
                """SELECT m.* FROM l1_team_members m
                   JOIN l1_agile_units u ON u.id = m.unit_id
                   WHERE u.project_id = ? AND u.l1_element_id = ?
                   ORDER BY m.name""",
                (project_id, l1_element_id),
            ).fetchall()
        )
        work_items = rows_to_dicts(
            conn.execute(
                """SELECT w.*, u.name AS squad_name, e.name AS linked_element_name
                   FROM l1_work_items w
                   LEFT JOIN l1_agile_units u ON u.id = w.squad_id
                   LEFT JOIN c4_elements e ON e.id = w.linked_element_id
                   WHERE w.project_id = ? AND w.l1_element_id = ?
                   ORDER BY w.start_date, w.title""",
                (project_id, l1_element_id),
            ).fetchall()
        )
        diagrams = [
            _hydrate_diagram(diagram)
            for diagram in rows_to_dicts(
                conn.execute(
                    "SELECT * FROM l1_diagrams WHERE project_id = ? AND l1_element_id = ? ORDER BY updated_at DESC",
                    (project_id, l1_element_id),
                ).fetchall()
            )
        ]
        settings_row = conn.execute(
            "SELECT currency_code, updated_at FROM l1_plan_settings WHERE l1_element_id = ?",
            (l1_element_id,),
        ).fetchone()

    members_by_unit: dict[str, list[dict[str, Any]]] = {}
    for member in members:
        members_by_unit.setdefault(member["unit_id"], []).append(member)
    for unit in units:
        unit["members"] = members_by_unit.get(unit["id"], [])

    allocated_fte = sum(member["allocation_percent"] / 100 for member in members)
    monthly_run_rate = sum(member["monthly_cost"] * member["allocation_percent"] / 100 for member in members)
    budget = sum(item["budget_cost"] for item in work_items)
    actual = sum(item["actual_cost"] for item in work_items)
    metrics = {
        "tribes": sum(unit["unit_type"] == "tribe" for unit in units),
        "squads": sum(unit["unit_type"] == "squad" for unit in units),
        "people": len(members),
        "allocated_fte": round(allocated_fte, 2),
        "monthly_run_rate": round(monthly_run_rate, 2),
        "planned_cost": round(budget, 2),
        "actual_cost": round(actual, 2),
        "cost_variance": round(budget - actual, 2),
        "at_risk_work": sum(item["status"] == "at_risk" for item in work_items),
    }
    return {
        "element": element,
        "units": units,
        "work_items": work_items,
        "diagrams": diagrams,
        "settings": dict(settings_row) if settings_row else {"currency_code": "USD", "updated_at": None},
        "metrics": metrics,
    }


def update_settings(project_id: str, l1_element_id: str, payload: PlanSettingsUpdate) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        conn.execute(
            """INSERT INTO l1_plan_settings (l1_element_id, project_id, currency_code, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(l1_element_id) DO UPDATE SET currency_code = excluded.currency_code, updated_at = excluded.updated_at""",
            (l1_element_id, project_id, payload.currency_code, now),
        )
    return {"currency_code": payload.currency_code, "updated_at": now}


def create_unit(project_id: str, l1_element_id: str, payload: AgileUnitCreate) -> dict[str, Any]:
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        _check_parent_unit(conn, project_id, l1_element_id, payload.unit_type, payload.parent_unit_id)
        record = {
            "id": new_id(),
            "project_id": project_id,
            "l1_element_id": l1_element_id,
            "created_at": utc_now(),
            **payload.model_dump(),
        }
        conn.execute(
            """INSERT INTO l1_agile_units
               (id, project_id, l1_element_id, unit_type, parent_unit_id, name, mission, lead_name, capacity_fte, target_velocity, created_at)
               VALUES (:id, :project_id, :l1_element_id, :unit_type, :parent_unit_id, :name, :mission, :lead_name, :capacity_fte, :target_velocity, :created_at)""",
            record,
        )
    record["members"] = []
    return record


def update_unit(project_id: str, unit_id: str, payload: AgileUnitUpdate) -> dict[str, Any]:
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    if "parent_unit_id" in payload.model_fields_set:
        changes["parent_unit_id"] = payload.parent_unit_id
    with connect() as conn:
        current = _require_unit(conn, project_id, unit_id)
        parent_id = changes.get("parent_unit_id", current["parent_unit_id"])
        _check_parent_unit(conn, project_id, current["l1_element_id"], current["unit_type"], parent_id)
        if changes:
            assignments = ", ".join(f"{key} = :{key}" for key in changes)
            conn.execute(
                f"UPDATE l1_agile_units SET {assignments} WHERE id = :id AND project_id = :project_id",
                {**changes, "id": unit_id, "project_id": project_id},
            )
        row = conn.execute("SELECT * FROM l1_agile_units WHERE id = ?", (unit_id,)).fetchone()
    return dict(row)


def delete_unit(project_id: str, unit_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM l1_agile_units WHERE id = ? AND project_id = ?", (unit_id, project_id)
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Agile unit '{unit_id}' was not found")


def _require_resource(conn: Any, resource_staff_id: str | None) -> None:
    if resource_staff_id and conn.execute(
        "SELECT 1 FROM resource_staff WHERE id = ?", (resource_staff_id,)
    ).fetchone() is None:
        raise PlanningValidationError(f"Resource '{resource_staff_id}' was not found in the directory")


def _assert_allocation_within_cap(
    conn: Any, resource_staff_id: str | None, allocation_percent: float, exclude_member_id: str | None = None
) -> None:
    """A directory person's allocation across every team must stay within 100%."""
    if not resource_staff_id:
        return
    sql = "SELECT COALESCE(SUM(allocation_percent), 0) FROM l1_team_members WHERE resource_staff_id = ?"
    params: list[Any] = [resource_staff_id]
    if exclude_member_id:
        sql += " AND id != ?"
        params.append(exclude_member_id)
    existing = conn.execute(sql, params).fetchone()[0]
    total = existing + allocation_percent
    if total > 100:
        name_row = conn.execute("SELECT staff_name FROM resource_staff WHERE id = ?", (resource_staff_id,)).fetchone()
        who = name_row[0] if name_row else "This resource"
        raise PlanningValidationError(
            f"{who} would be allocated {total:g}% across teams (already {existing:g}%); the total cannot exceed 100%."
        )


def create_member(project_id: str, unit_id: str, payload: TeamMemberCreate) -> dict[str, Any]:
    with connect() as conn:
        _require_unit(conn, project_id, unit_id)
        _require_resource(conn, payload.resource_staff_id)
        _assert_allocation_within_cap(conn, payload.resource_staff_id, payload.allocation_percent)
        record = {"id": new_id(), "unit_id": unit_id, "created_at": utc_now(), **payload.model_dump()}
        conn.execute(
            """INSERT INTO l1_team_members
               (id, unit_id, resource_staff_id, name, role, skills, location, allocation_percent, monthly_cost, created_at)
               VALUES (:id, :unit_id, :resource_staff_id, :name, :role, :skills, :location, :allocation_percent, :monthly_cost, :created_at)""",
            record,
        )
    return record


def update_member(project_id: str, member_id: str, payload: TeamMemberUpdate) -> dict[str, Any]:
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    with connect() as conn:
        row = conn.execute(
            """SELECT m.* FROM l1_team_members m JOIN l1_agile_units u ON u.id = m.unit_id
               WHERE m.id = ? AND u.project_id = ?""",
            (member_id, project_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Team member '{member_id}' was not found")
        resource_staff_id = changes.get("resource_staff_id", row["resource_staff_id"])
        allocation = changes.get("allocation_percent", row["allocation_percent"])
        _require_resource(conn, resource_staff_id)
        _assert_allocation_within_cap(conn, resource_staff_id, allocation, exclude_member_id=member_id)
        if changes:
            assignments = ", ".join(f"{key} = :{key}" for key in changes)
            conn.execute(
                f"UPDATE l1_team_members SET {assignments} WHERE id = :id",
                {**changes, "id": member_id},
            )
        updated = conn.execute("SELECT * FROM l1_team_members WHERE id = ?", (member_id,)).fetchone()
    return dict(updated)


def delete_member(project_id: str, member_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            """DELETE FROM l1_team_members WHERE id = ? AND unit_id IN
               (SELECT id FROM l1_agile_units WHERE project_id = ?)""",
            (member_id, project_id),
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Team member '{member_id}' was not found")


def _check_work_links(
    conn: Any,
    project_id: str,
    l1_element_id: str,
    squad_id: str | None,
    linked_element_id: str | None,
) -> None:
    if squad_id:
        squad = _require_unit(conn, project_id, squad_id)
        if squad["l1_element_id"] != l1_element_id or squad["unit_type"] != "squad":
            raise PlanningValidationError("Work must be assigned to a squad in the same L1 plan")
    if linked_element_id:
        row = conn.execute(
            "SELECT id, level, parent_id FROM c4_elements WHERE id = ? AND project_id = ?",
            (linked_element_id, project_id),
        ).fetchone()
        if row is None or row["level"] == "L1":
            raise PlanningValidationError("linked_element_id must reference an L2-L4 element in this project")
        ancestor = row
        while ancestor and ancestor["parent_id"] != l1_element_id:
            ancestor = conn.execute(
                "SELECT id, level, parent_id FROM c4_elements WHERE id = ?",
                (ancestor["parent_id"],),
            ).fetchone()
        if ancestor is None:
            raise PlanningValidationError("The linked C4 element must belong to this L1 initiative")


def create_work_item(project_id: str, l1_element_id: str, payload: WorkItemCreate) -> dict[str, Any]:
    values = _serialize_dates(payload.model_dump())
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        _check_work_links(conn, project_id, l1_element_id, payload.squad_id, payload.linked_element_id)
        record = {
            "id": new_id(),
            "project_id": project_id,
            "l1_element_id": l1_element_id,
            "created_at": utc_now(),
            **values,
        }
        conn.execute(
            """INSERT INTO l1_work_items
               (id, project_id, l1_element_id, squad_id, linked_element_id, title, description, start_date, end_date,
                status, allocation_percent, budget_cost, actual_cost, created_at)
               VALUES (:id, :project_id, :l1_element_id, :squad_id, :linked_element_id, :title, :description, :start_date, :end_date,
                :status, :allocation_percent, :budget_cost, :actual_cost, :created_at)""",
            record,
        )
    return record


def update_work_item(project_id: str, work_item_id: str, payload: WorkItemUpdate) -> dict[str, Any]:
    changes = _serialize_dates({key: value for key, value in payload.model_dump().items() if value is not None})
    for nullable_link in ("squad_id", "linked_element_id"):
        if nullable_link in payload.model_fields_set:
            changes[nullable_link] = getattr(payload, nullable_link)
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM l1_work_items WHERE id = ? AND project_id = ?",
            (work_item_id, project_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Work item '{work_item_id}' was not found")
        combined = {**dict(row), **changes}
        if combined["end_date"] < combined["start_date"]:
            raise PlanningValidationError("end_date must be on or after start_date")
        _check_work_links(
            conn,
            project_id,
            row["l1_element_id"],
            combined["squad_id"],
            combined["linked_element_id"],
        )
        if changes:
            assignments = ", ".join(f"{key} = :{key}" for key in changes)
            conn.execute(
                f"UPDATE l1_work_items SET {assignments} WHERE id = :id AND project_id = :project_id",
                {**changes, "id": work_item_id, "project_id": project_id},
            )
        updated = conn.execute("SELECT * FROM l1_work_items WHERE id = ?", (work_item_id,)).fetchone()
    return dict(updated)


def delete_work_item(project_id: str, work_item_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM l1_work_items WHERE id = ? AND project_id = ?",
            (work_item_id, project_id),
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Work item '{work_item_id}' was not found")


def _hydrate_diagram(diagram: dict[str, Any]) -> dict[str, Any]:
    """Parse the stored metadata JSON string back into a dict for API responses."""
    raw = diagram.get("metadata")
    if isinstance(raw, str):
        try:
            diagram["metadata"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            diagram["metadata"] = {}
    elif raw is None:
        diagram["metadata"] = {}
    return diagram


def create_diagram(project_id: str, l1_element_id: str, payload: DiagramCreate) -> dict[str, Any]:
    now = utc_now()
    data = payload.model_dump()
    metadata = data.pop("metadata", {})
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        record = {
            "id": new_id(),
            "project_id": project_id,
            "l1_element_id": l1_element_id,
            "created_at": now,
            "updated_at": now,
            **data,
            "metadata": metadata,
        }
        conn.execute(
            """INSERT INTO l1_diagrams
               (id, project_id, l1_element_id, diagram_type, title, mermaid_source, metadata, created_at, updated_at)
               VALUES (:id, :project_id, :l1_element_id, :diagram_type, :title, :mermaid_source, :metadata, :created_at, :updated_at)""",
            {**record, "metadata": json.dumps(metadata)},
        )
    return record


def update_diagram(project_id: str, diagram_id: str, payload: DiagramUpdate) -> dict[str, Any]:
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    changes["updated_at"] = utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM l1_diagrams WHERE id = ? AND project_id = ?",
            (diagram_id, project_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Diagram '{diagram_id}' was not found")
        bindings = dict(changes)
        if "metadata" in bindings:
            bindings["metadata"] = json.dumps(bindings["metadata"])
        assignments = ", ".join(f"{key} = :{key}" for key in changes)
        conn.execute(
            f"UPDATE l1_diagrams SET {assignments} WHERE id = :id AND project_id = :project_id",
            {**bindings, "id": diagram_id, "project_id": project_id},
        )
        updated = conn.execute("SELECT * FROM l1_diagrams WHERE id = ?", (diagram_id,)).fetchone()
    return _hydrate_diagram(dict(updated))


def delete_diagram(project_id: str, diagram_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM l1_diagrams WHERE id = ? AND project_id = ?", (diagram_id, project_id)
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Diagram '{diagram_id}' was not found")
