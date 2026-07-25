"""The signed-in user's personal home dashboard — deterministic, no LLM.

Everything here is scoped to one `resource_staff` id (the caller's own identity,
resolved from the request header by the router). It stitches together the work
that touches that person across the planning and architecture modules into three
views the home page renders: a **summary**, a **tasks inbox** (the work items in
the squads they belong to) and **actions pending** (things that need their
attention now — overdue / at-risk work, OKRs and risks they own, review comments
they raised, and, for managers, unstaffed direct reports).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.access.store import effective_role
from backend.reporting.service import (
    _lookup_labels,
    _memberships,
    _staff_aggregates,
    _stories_by_squad,
)
from backend.storage.db import connect

# How soon a work item's end date counts as "due soon" for the actions list.
DUE_SOON_DAYS = 7

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _days_until(value: Any, today: date) -> int | None:
    parsed = _parse_date(value)
    return (parsed - today).days if parsed else None


def personal_dashboard(staff_id: str) -> dict[str, Any]:
    """Assemble the home dashboard for one directory person."""
    today = date.today()
    with connect() as conn:
        row = conn.execute("SELECT * FROM resource_staff WHERE id = ?", (staff_id,)).fetchone()
        if row is None:
            raise LookupError(f"Resource '{staff_id}' was not found")
        person = dict(row)
        name = person["staff_name"] or f"{person['staff_first_name']} {person['staff_last_name']}".strip()

        labels = _lookup_labels(conn)
        memberships = _memberships(conn)
        stories_by_squad = _stories_by_squad(conn)
        my_memberships = memberships.get(staff_id, [])
        agg = _staff_aggregates(staff_id, my_memberships, stories_by_squad)

        squad_ids = [m["unit_id"] for m in my_memberships if m["unit_type"] == "squad"]
        tasks = _tasks(conn, squad_ids, today)
        reports_count = _direct_reports_count(conn, staff_id)
        bench = _bench_reports(conn, staff_id)

        actions: list[dict[str, Any]] = []
        actions += _work_item_actions(tasks)
        actions += _owned_okr_actions(conn, name)
        actions += _owned_risk_actions(conn, name, today)
        actions += _open_comment_actions(conn, name)
        actions += _bench_actions(bench)

    actions.sort(key=lambda a: (_SEVERITY_ORDER.get(a["severity"], 3), a.get("order", 0)))

    open_tasks = [task for task in tasks if task["status"] != "done"]
    summary = {
        "tasks_open": len(open_tasks),
        "tasks_total": len(tasks),
        "at_risk": sum(1 for task in tasks if task["status"] == "at_risk"),
        "overdue": sum(1 for task in tasks if task["overdue"]),
        "actions": len(actions),
        "squads": agg["squad_count"],
        "tribes": agg["tribe_count"],
        "projects": agg["project_count"],
        "stories": agg["story_count"],
        "points": agg["points"],
        "allocation": agg["allocation"],
        "reports": reports_count,
        "bench_reports": len(bench),
    }

    return {
        "scope": "personal",
        "user": {
            "staff_id": staff_id,
            "name": name,
            "code": person["staff_code"],
            "role": effective_role(staff_id),
            "rank": labels.get("rank", {}).get(person["rank"], person["rank"] or "—"),
            "tech_unit": labels.get("tech_unit", {}).get(person["tech_unit"], person["tech_unit"] or "—"),
        },
        "summary": summary,
        "tasks": tasks,
        "actions": actions,
    }


# Cap the org-wide lists so a large portfolio still renders a tidy dashboard.
_ORG_LIST_CAP = 25


def organization_dashboard() -> dict[str, Any]:
    """Portfolio-wide dashboard for an admin who has no personal directory identity
    (the bootstrap "Administrator"). Shows attention-worthy work and actions across
    every platform rather than one person's queue."""
    today = date.today()
    with connect() as conn:
        tasks = _all_open_tasks(conn, today)
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        squads = conn.execute("SELECT COUNT(*) FROM l1_agile_units WHERE unit_type = 'squad'").fetchone()[0]
        resources = conn.execute("SELECT COUNT(*) FROM resource_staff WHERE staff_status = 'Active'").fetchone()[0]
        bench = _all_bench(conn)

        actions: list[dict[str, Any]] = []
        actions += _work_item_actions(tasks)
        actions += _okr_actions(conn, owner=None)
        actions += _risk_actions(conn, owner=None, today=today)
        if bench:
            actions.append({
                "id": "org-bench",
                "type": "bench_pool",
                "severity": "medium",
                "order": 7,
                "title": f"{len(bench)} resource{'s' if len(bench) != 1 else ''} unallocated",
                "detail": "People in the directory with no team allocation",
                "project_id": None,
                "project_name": None,
                "category": "team",
            })

    actions.sort(key=lambda a: (_SEVERITY_ORDER.get(a["severity"], 3), a.get("order", 0)))
    total_actions = len(actions)
    total_tasks = len(tasks)

    summary = {
        "tasks_open": total_tasks,
        "tasks_total": total_tasks,
        "at_risk": sum(1 for task in tasks if task["status"] == "at_risk"),
        "overdue": sum(1 for task in tasks if task["overdue"]),
        "actions": total_actions,
        "projects": projects,
        "squads": squads,
        "resources": resources,
        "on_bench": len(bench),
    }

    return {
        "scope": "organization",
        "user": {"staff_id": None, "name": "Administrator", "role": "admin", "rank": "Platform admin", "tech_unit": "All platforms"},
        "summary": summary,
        "tasks": tasks[:_ORG_LIST_CAP],
        "tasks_truncated": max(0, total_tasks - _ORG_LIST_CAP),
        "actions": actions[:_ORG_LIST_CAP],
        "actions_truncated": max(0, total_actions - _ORG_LIST_CAP),
    }


# --------------------------------------------------------------------------- #
# Tasks inbox — work items in the squads the person belongs to.
# --------------------------------------------------------------------------- #

def _tasks(conn: Any, squad_ids: list[str], today: date) -> list[dict[str, Any]]:
    if not squad_ids:
        return []
    placeholders = ",".join("?" for _ in squad_ids)
    rows = conn.execute(
        f"""SELECT w.id, w.title, w.status, w.start_date, w.end_date, w.allocation_percent,
                   w.project_id, u.name AS squad_name, p.name AS project_name,
                   e.name AS story_name, a.points
            FROM l1_work_items w
            JOIN l1_agile_units u ON u.id = w.squad_id
            LEFT JOIN projects p ON p.id = w.project_id
            LEFT JOIN c4_elements e ON e.id = w.linked_element_id
            LEFT JOIN artifact_links a ON a.element_id = e.id AND a.points IS NOT NULL
            WHERE w.squad_id IN ({placeholders})
            ORDER BY w.end_date, w.title""",
        squad_ids,
    ).fetchall()

    tasks = []
    for row in rows:
        due_in = _days_until(row["end_date"], today)
        overdue = row["status"] != "done" and due_in is not None and due_in < 0
        tasks.append({
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "squad_name": row["squad_name"],
            "project_id": row["project_id"],
            "project_name": row["project_name"] or "—",
            "story_name": row["story_name"],
            "points": row["points"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "due_in_days": due_in,
            "overdue": overdue,
        })
    # Surface the most urgent work first: at-risk, then overdue, then soonest due.
    def rank(task: dict[str, Any]) -> tuple:
        status_rank = 0 if task["status"] == "at_risk" else 1 if task["overdue"] else 2
        due = task["due_in_days"]
        return (status_rank, due if due is not None else 10_000)
    tasks.sort(key=rank)
    return tasks


# --------------------------------------------------------------------------- #
# Actions pending — each is { id, type, severity, title, detail, project_id }.
# --------------------------------------------------------------------------- #

def _work_item_actions(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for task in tasks:
        base = {
            "project_id": task["project_id"],
            "project_name": task["project_name"],
            "category": "work",
        }
        if task["status"] == "at_risk":
            actions.append({**base, "id": f"wi-risk-{task['id']}", "type": "at_risk_work",
                            "severity": "high", "order": 0,
                            "title": task["title"], "detail": f"At-risk work in {task['squad_name']}"})
        elif task["overdue"]:
            days = abs(task["due_in_days"])
            actions.append({**base, "id": f"wi-over-{task['id']}", "type": "overdue_work",
                            "severity": "high", "order": 1,
                            "title": task["title"], "detail": f"Overdue by {days} day{'s' if days != 1 else ''}"})
        elif task["due_in_days"] is not None and 0 <= task["due_in_days"] <= DUE_SOON_DAYS and task["status"] != "done":
            days = task["due_in_days"]
            when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
            actions.append({**base, "id": f"wi-due-{task['id']}", "type": "due_soon_work",
                            "severity": "medium", "order": 2,
                            "title": task["title"], "detail": f"Due {when} · {task['squad_name']}"})
    return actions


def _okr_actions(conn: Any, owner: str | None) -> list[dict[str, Any]]:
    """Off-track / at-risk OKRs. `owner=None` covers the whole portfolio; a name
    scopes to the OKRs that person owns and phrases the detail accordingly."""
    where = "o.status IN ('off_track','at_risk')"
    params: tuple = ()
    if owner is not None:
        if not owner:
            return []
        where = "o.owner = ? AND " + where
        params = (owner,)
    rows = conn.execute(
        f"""SELECT o.id, o.objective, o.status, o.owner, e.project_id, p.name AS project_name
            FROM l1_okrs o
            JOIN c4_elements e ON e.id = o.l1_element_id
            LEFT JOIN projects p ON p.id = e.project_id
            WHERE {where}""",
        params,
    ).fetchall()
    actions = []
    for row in rows:
        state = row["status"].replace("_", " ")
        detail = f"OKR {state} · you are the owner" if owner else f"OKR {state} · owner {row['owner'] or 'unassigned'}"
        actions.append({
            "id": f"okr-{row['id']}",
            "type": "okr_off_track",
            "severity": "high" if row["status"] == "off_track" else "medium",
            "order": 3,
            "title": row["objective"],
            "detail": detail,
            "project_id": row["project_id"],
            "project_name": row["project_name"] or "—",
            "category": "okr",
        })
    return actions


def _risk_actions(conn: Any, owner: str | None, today: date) -> list[dict[str, Any]]:
    """Active / blocked risks. `owner=None` covers the whole portfolio."""
    where = "r.status IN ('active','blocked')"
    params: tuple = ()
    if owner is not None:
        if not owner:
            return []
        where = "r.owner = ? AND " + where
        params = (owner,)
    rows = conn.execute(
        f"""SELECT r.id, r.title, r.risk_level, r.status, r.target_date, r.owner, e.project_id, p.name AS project_name
            FROM l1_risks r
            JOIN c4_elements e ON e.id = r.l1_element_id
            LEFT JOIN projects p ON p.id = e.project_id
            WHERE {where}""",
        params,
    ).fetchall()
    actions = []
    for row in rows:
        due_in = _days_until(row["target_date"], today)
        overdue = due_in is not None and due_in < 0
        suffix = "you are the owner" if owner else f"owner {row['owner'] or 'unassigned'}"
        detail = f"Risk blocked · {suffix}" if row["status"] == "blocked" else f"Active risk · {suffix}"
        if overdue:
            detail += f" · target {abs(due_in)} day{'s' if abs(due_in) != 1 else ''} overdue"
        actions.append({
            "id": f"risk-{row['id']}",
            "type": "risk_open",
            "severity": "high" if (row["status"] == "blocked" or overdue or row["risk_level"] == "high") else "medium",
            "order": 4,
            "title": row["title"],
            "detail": detail,
            "project_id": row["project_id"],
            "project_name": row["project_name"] or "—",
            "category": "risk",
        })
    return actions


# Personal wrappers keep the readable call sites in personal_dashboard.
def _owned_okr_actions(conn: Any, name: str) -> list[dict[str, Any]]:
    return _okr_actions(conn, owner=name)


def _owned_risk_actions(conn: Any, name: str, today: date) -> list[dict[str, Any]]:
    return _risk_actions(conn, owner=name, today=today)


def _open_comment_actions(conn: Any, name: str) -> list[dict[str, Any]]:
    if not name:
        return []
    rows = conn.execute(
        """SELECT c.id, c.body, e.project_id, p.name AS project_name, e.name AS initiative
           FROM l1_comments c
           JOIN c4_elements e ON e.id = c.l1_element_id
           LEFT JOIN projects p ON p.id = e.project_id
           WHERE c.author = ? AND c.status = 'open'""",
        (name,),
    ).fetchall()
    return [{
        "id": f"cmt-{row['id']}",
        "type": "open_comment",
        "severity": "low",
        "order": 5,
        "title": (row["body"][:80] + "…") if row["body"] and len(row["body"]) > 80 else (row["body"] or "Review comment"),
        "detail": f"Open review comment · {row['initiative']}",
        "project_id": row["project_id"],
        "project_name": row["project_name"] or "—",
        "category": "comment",
    } for row in rows]


def _bench_actions(bench: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "id": f"bench-{member['id']}",
        "type": "unstaffed_report",
        "severity": "medium",
        "order": 6,
        "title": member["name"],
        "detail": "Direct report is on the bench (0% allocated)",
        "project_id": None,
        "project_name": None,
        "category": "team",
    } for member in bench]


# --------------------------------------------------------------------------- #
# Team helpers.
# --------------------------------------------------------------------------- #

def _direct_reports_count(conn: Any, staff_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM resource_staff WHERE reporting_manager_id = ? AND staff_status = 'Active'",
        (staff_id,),
    ).fetchone()[0]


def _bench_reports(conn: Any, staff_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT s.id, s.staff_name AS name, COALESCE(SUM(m.allocation_percent), 0) AS allocated
           FROM resource_staff s
           LEFT JOIN l1_team_members m ON m.resource_staff_id = s.id
           WHERE s.reporting_manager_id = ? AND s.staff_status = 'Active'
           GROUP BY s.id
           HAVING allocated = 0
           ORDER BY s.staff_name COLLATE NOCASE""",
        (staff_id,),
    ).fetchall()
    return [{"id": row["id"], "name": row["name"]} for row in rows]


# --------------------------------------------------------------------------- #
# Organization-wide helpers (portfolio dashboard for the bootstrap admin).
# --------------------------------------------------------------------------- #

def _all_open_tasks(conn: Any, today: date) -> list[dict[str, Any]]:
    """Every not-done work item across all platforms, most urgent first."""
    rows = conn.execute(
        """SELECT w.id, w.title, w.status, w.start_date, w.end_date, w.project_id,
                  u.name AS squad_name, p.name AS project_name, e.name AS story_name, a.points
           FROM l1_work_items w
           LEFT JOIN l1_agile_units u ON u.id = w.squad_id
           LEFT JOIN projects p ON p.id = w.project_id
           LEFT JOIN c4_elements e ON e.id = w.linked_element_id
           LEFT JOIN artifact_links a ON a.element_id = e.id AND a.points IS NOT NULL
           WHERE w.status != 'done'
           ORDER BY w.end_date, w.title""",
    ).fetchall()
    tasks = []
    for row in rows:
        due_in = _days_until(row["end_date"], today)
        overdue = due_in is not None and due_in < 0
        tasks.append({
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "squad_name": row["squad_name"] or "Unassigned",
            "project_id": row["project_id"],
            "project_name": row["project_name"] or "—",
            "story_name": row["story_name"],
            "points": row["points"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "due_in_days": due_in,
            "overdue": overdue,
        })

    def rank(task: dict[str, Any]) -> tuple:
        status_rank = 0 if task["status"] == "at_risk" else 1 if task["overdue"] else 2
        due = task["due_in_days"]
        return (status_rank, due if due is not None else 10_000)
    tasks.sort(key=rank)
    return tasks


def _all_bench(conn: Any) -> list[dict[str, Any]]:
    """Active directory people with no team allocation anywhere."""
    rows = conn.execute(
        """SELECT s.id, s.staff_name AS name, COALESCE(SUM(m.allocation_percent), 0) AS allocated
           FROM resource_staff s
           LEFT JOIN l1_team_members m ON m.resource_staff_id = s.id
           WHERE s.staff_status = 'Active'
           GROUP BY s.id
           HAVING allocated = 0""",
    ).fetchall()
    return [{"id": row["id"], "name": row["name"]} for row in rows]
