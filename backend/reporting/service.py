"""Aggregate counts for admin dashboards. All figures are deterministic SQL — no LLM."""

from __future__ import annotations

import json
from typing import Any

from backend.access.store import role_counts
from backend.storage.db import connect


def _group(conn: Any, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [{"label": row[0] or "—", "value": row[1]} for row in conn.execute(sql, params).fetchall()]


def overview() -> dict[str, Any]:
    with connect() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        story_row = conn.execute(
            """SELECT
                 SUM(CASE WHEN level = 'L3' THEN 1 ELSE 0 END) AS stories,
                 SUM(CASE WHEN level = 'L3' AND id IN (
                   SELECT element_id FROM artifact_links WHERE points IS NOT NULL
                 ) THEN 1 ELSE 0 END) AS estimated
               FROM c4_elements"""
        ).fetchone()
        stories = story_row["stories"] or 0
        estimated = story_row["estimated"] or 0

        staff_total = conn.execute("SELECT COUNT(*) FROM resource_staff").fetchone()[0]
        staff_active = conn.execute(
            "SELECT COUNT(*) FROM resource_staff WHERE staff_status = 'Active'"
        ).fetchone()[0]

        by_sub_status = _group(
            conn, "SELECT sub_status, COUNT(*) FROM resource_staff GROUP BY sub_status ORDER BY 2 DESC"
        )
        by_type = _group(
            conn, "SELECT staff_type, COUNT(*) FROM resource_staff GROUP BY staff_type ORDER BY 2 DESC"
        )
        by_tech_unit = _group(
            conn,
            """SELECT COALESCE(l.label, s.tech_unit), COUNT(*)
               FROM resource_staff s LEFT JOIN resource_lookups l
                 ON l.category = 'tech_unit' AND l.code = s.tech_unit
               GROUP BY s.tech_unit ORDER BY 2 DESC""",
        )

        # Allocation utilisation: sum each active person's allocation across all teams.
        alloc_rows = conn.execute(
            """SELECT s.id, COALESCE(SUM(m.allocation_percent), 0) AS allocated
               FROM resource_staff s
               LEFT JOIN l1_team_members m ON m.resource_staff_id = s.id
               WHERE s.staff_status = 'Active'
               GROUP BY s.id"""
        ).fetchall()
        on_bench = sum(1 for row in alloc_rows if row["allocated"] == 0)
        fully_allocated = sum(1 for row in alloc_rows if row["allocated"] >= 100)
        partially = sum(1 for row in alloc_rows if 0 < row["allocated"] < 100)
        avg_util = round(
            sum(min(row["allocated"], 100) for row in alloc_rows) / len(alloc_rows), 1
        ) if alloc_rows else 0

        squads = conn.execute("SELECT COUNT(*) FROM l1_agile_units WHERE unit_type = 'squad'").fetchone()[0]
        members = conn.execute("SELECT COUNT(*) FROM l1_team_members").fetchone()[0]
        at_risk = conn.execute(
            "SELECT COUNT(*) FROM l1_work_items WHERE status = 'at_risk'"
        ).fetchone()[0]

        # Per-platform delivery breakdown.
        platforms = []
        for project in conn.execute("SELECT id, name FROM projects ORDER BY created_at DESC").fetchall():
            row = conn.execute(
                """SELECT
                     SUM(CASE WHEN level = 'L3' THEN 1 ELSE 0 END) AS stories,
                     SUM(CASE WHEN level = 'L3' AND id IN (
                       SELECT element_id FROM artifact_links WHERE points IS NOT NULL
                     ) THEN 1 ELSE 0 END) AS estimated
                   FROM c4_elements WHERE project_id = ?""",
                (project["id"],),
            ).fetchone()
            p_stories = row["stories"] or 0
            p_estimated = row["estimated"] or 0
            platforms.append({
                "id": project["id"],
                "name": project["name"],
                "stories": p_stories,
                "estimated": p_estimated,
                "estimated_pct": round(p_estimated / p_stories * 100) if p_stories else 0,
            })

    return {
        "access": role_counts(),
        "portfolio": {
            "projects": projects,
            "stories": stories,
            "estimated": estimated,
            "estimated_pct": round(estimated / stories * 100) if stories else 0,
            "squads": squads,
            "members": members,
            "at_risk_work_items": at_risk,
            "platforms": platforms,
        },
        "resources": {
            "total": staff_total,
            "active": staff_active,
            "on_bench": on_bench,
            "fully_allocated": fully_allocated,
            "partially_allocated": partially,
            "avg_utilisation": avg_util,
            "by_sub_status": by_sub_status,
            "by_type": by_type,
            "by_tech_unit": by_tech_unit,
        },
    }


# --------------------------------------------------------------------------- #
# Resource view: the reporting org hierarchy enriched with each person's teams,
# squads, tribes, projects and stories — feeds the tree / sunburst / treemap /
# network charts and the per-resource drill-down. All deterministic SQL, no LLM.
# --------------------------------------------------------------------------- #


def _parse_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _lookup_labels(conn: Any) -> dict[str, dict[str, str]]:
    """category -> {code: label} for tech_unit / rank / hr_role decoding."""
    labels: dict[str, dict[str, str]] = {}
    for row in conn.execute("SELECT category, code, label FROM resource_lookups").fetchall():
        labels.setdefault(row["category"], {})[row["code"]] = row["label"]
    return labels


def _memberships(conn: Any) -> dict[str, list[dict[str, Any]]]:
    """resource_staff_id -> the agile-unit memberships that person holds."""
    rows = conn.execute(
        """SELECT m.resource_staff_id AS staff_id, m.role, m.allocation_percent, m.monthly_cost,
                  u.id AS unit_id, u.name AS unit_name, u.unit_type, u.parent_unit_id,
                  u.project_id, u.l1_element_id,
                  parent.name AS tribe_name,
                  p.name AS project_name, e.name AS initiative_name
           FROM l1_team_members m
           JOIN l1_agile_units u ON u.id = m.unit_id
           LEFT JOIN l1_agile_units parent ON parent.id = u.parent_unit_id
           LEFT JOIN projects p ON p.id = u.project_id
           LEFT JOIN c4_elements e ON e.id = u.l1_element_id
           WHERE m.resource_staff_id IS NOT NULL"""
    ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["staff_id"], []).append(dict(row))
    return out


def _stories_by_squad(conn: Any) -> dict[str, list[dict[str, Any]]]:
    """squad_id -> the distinct L3 stories its work items point at (with points/code)."""
    rows = conn.execute(
        """SELECT w.squad_id, w.status AS work_status,
                  e.id AS story_id, e.name AS story_name, e.code_path,
                  a.points, a.spike_recommended, a.split_recommended,
                  p.name AS project_name
           FROM l1_work_items w
           JOIN c4_elements e ON e.id = w.linked_element_id
           LEFT JOIN projects p ON p.id = e.project_id
           LEFT JOIN artifact_links a ON a.element_id = e.id AND a.points IS NOT NULL
           WHERE w.squad_id IS NOT NULL AND w.linked_element_id IS NOT NULL"""
    ).fetchall()
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        bucket = out.setdefault(row["squad_id"], {})
        bucket[row["story_id"]] = {
            "id": row["story_id"],
            "name": row["story_name"],
            "code_path": row["code_path"] or "",
            "points": row["points"],
            "work_status": row["work_status"],
            "project_name": row["project_name"] or "—",
        }
    return {squad_id: list(stories.values()) for squad_id, stories in out.items()}


def _staff_aggregates(
    staff_id: str,
    memberships: list[dict[str, Any]],
    stories_by_squad: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Collapse one person's memberships into distinct teams/projects/stories."""
    squads = {m["unit_id"]: m for m in memberships if m["unit_type"] == "squad"}
    tribe_names: set[str] = set()
    project_names: set[str] = set()
    for m in memberships:
        if m["unit_type"] == "tribe":
            tribe_names.add(m["unit_name"])
        if m.get("tribe_name"):
            tribe_names.add(m["tribe_name"])
        if m.get("project_name"):
            project_names.add(m["project_name"])

    stories: dict[str, dict[str, Any]] = {}
    for squad_id in squads:
        for story in stories_by_squad.get(squad_id, []):
            stories[story["id"]] = story
    code_paths = sorted({s["code_path"] for s in stories.values() if s["code_path"]})
    points = sum(s["points"] or 0 for s in stories.values())
    allocation = sum(m["allocation_percent"] for m in memberships)

    return {
        "squad_names": sorted({m["unit_name"] for m in squads.values()}),
        "tribe_names": sorted(tribe_names),
        "project_names": sorted(project_names),
        "stories": list(stories.values()),
        "code_paths": code_paths,
        "squad_count": len(squads),
        "tribe_count": len(tribe_names),
        "project_count": len(project_names),
        "story_count": len(stories),
        "points": points,
        "allocation": round(allocation, 1),
    }


def _staff_node(row: dict[str, Any], labels: dict[str, dict[str, str]], agg: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["staff_name"] or f"{row['staff_first_name']} {row['staff_last_name']}".strip(),
        "code": row["staff_code"],
        "type": row["staff_type"],
        "status": row["staff_status"],
        "sub_status": row["sub_status"],
        "tech_unit": labels.get("tech_unit", {}).get(row["tech_unit"], row["tech_unit"] or "—"),
        "rank": labels.get("rank", {}).get(row["rank"], row["rank"] or "—"),
        "hr_role": labels.get("hr_role", {}).get(row["hr_role"], row["hr_role"] or "—"),
        "manager_id": row["reporting_manager_id"],
        "squads": agg["squad_names"],
        "tribes": agg["tribe_names"],
        "projects": agg["project_names"],
        "squad_count": agg["squad_count"],
        "tribe_count": agg["tribe_count"],
        "project_count": agg["project_count"],
        "story_count": agg["story_count"],
        "points": agg["points"],
        "allocation": agg["allocation"],
    }


def resource_graph() -> dict[str, Any]:
    """Reporting-hierarchy forest + flat node/edge lists for the resource charts."""
    with connect() as conn:
        labels = _lookup_labels(conn)
        memberships = _memberships(conn)
        stories_by_squad = _stories_by_squad(conn)
        staff_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM resource_staff ORDER BY staff_name COLLATE NOCASE"
            ).fetchall()
        ]

    nodes: dict[str, dict[str, Any]] = {}
    for row in staff_rows:
        agg = _staff_aggregates(row["id"], memberships.get(row["id"], []), stories_by_squad)
        nodes[row["id"]] = _staff_node(row, labels, agg)

    # Build the reporting forest. A manager pointer to a missing/removed person is
    # treated as a root so nobody is dropped from the chart.
    children: dict[str, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for node in nodes.values():
        manager_id = node["manager_id"]
        if manager_id and manager_id in nodes:
            children.setdefault(manager_id, []).append(node)
            edges.append({"source": manager_id, "target": node["id"]})
        else:
            roots.append(node)

    def attach(node: dict[str, Any]) -> int:
        kids = sorted(children.get(node["id"], []), key=lambda n: n["name"].lower())
        node["reports_count"] = len(kids)
        subtree = 1
        node["children"] = kids
        for kid in kids:
            subtree += attach(kid)
        node["weight"] = subtree  # headcount in this subtree (for sunburst/treemap sizing)
        return subtree

    for root in sorted(roots, key=lambda n: n["name"].lower()):
        attach(root)

    tree = sorted(roots, key=lambda n: (-n["weight"], n["name"].lower()))
    # Flat node list (children stripped) for the force/network view.
    flat = [{k: v for k, v in n.items() if k != "children"} for n in nodes.values()]

    # Distinct squads that at least one directory person belongs to.
    staffed_squads = {
        m["unit_id"]
        for member_list in memberships.values()
        for m in member_list
        if m["unit_type"] == "squad"
    }

    return {
        "tree": tree,
        "nodes": flat,
        "edges": edges,
        "totals": {
            "resources": len(nodes),
            "managers": len(children),
            "roots": len(roots),
            "squads": len(staffed_squads),
        },
    }


def resource_profile(staff_id: str) -> dict[str, Any]:
    """Full drill-down for one person: chain, reports, teams, projects, stories, code."""
    with connect() as conn:
        labels = _lookup_labels(conn)
        memberships = _memberships(conn)
        stories_by_squad = _stories_by_squad(conn)

        row = conn.execute("SELECT * FROM resource_staff WHERE id = ?", (staff_id,)).fetchone()
        if row is None:
            raise LookupError(f"Resource '{staff_id}' was not found")
        row = dict(row)

        # Manager chain upward (guard against cycles).
        chain: list[dict[str, Any]] = []
        seen = {staff_id}
        current = row["reporting_manager_id"]
        while current and current not in seen:
            seen.add(current)
            m = conn.execute(
                "SELECT id, staff_name, staff_code FROM resource_staff WHERE id = ?", (current,)
            ).fetchone()
            if m is None:
                break
            chain.append({"id": m["id"], "name": m["staff_name"], "code": m["staff_code"]})
            current = conn.execute(
                "SELECT reporting_manager_id FROM resource_staff WHERE id = ?", (m["id"],)
            ).fetchone()[0]

        reports = [
            {"id": r["id"], "name": r["staff_name"], "code": r["staff_code"],
             "rank": labels.get("rank", {}).get(r["rank"], r["rank"] or "—")}
            for r in conn.execute(
                "SELECT id, staff_name, staff_code, rank FROM resource_staff "
                "WHERE reporting_manager_id = ? ORDER BY staff_name COLLATE NOCASE",
                (staff_id,),
            ).fetchall()
        ]

    my_memberships = memberships.get(staff_id, [])
    agg = _staff_aggregates(staff_id, my_memberships, stories_by_squad)
    node = _staff_node(row, labels, agg)

    teams = [
        {
            "unit_id": m["unit_id"],
            "unit_name": m["unit_name"],
            "unit_type": m["unit_type"],
            "tribe_name": m.get("tribe_name") or ("—" if m["unit_type"] == "squad" else None),
            "project_name": m.get("project_name") or "—",
            "initiative_name": m.get("initiative_name") or "—",
            "role": m["role"] or "—",
            "allocation_percent": m["allocation_percent"],
            "monthly_cost": m["monthly_cost"],
        }
        for m in sorted(my_memberships, key=lambda x: (x["unit_type"], x["unit_name"]))
    ]

    return {
        "profile": {
            **node,
            "first_name": row["staff_first_name"],
            "last_name": row["staff_last_name"],
            "citizenship": row["citizenship"],
            "start_date": row["staff_start_date"],
            "end_date": row["staff_end_date"],
            "custom_values": _parse_json(row.get("custom_values")),
        },
        "manager_chain": chain,
        "reports": reports,
        "teams": teams,
        "stories": sorted(agg["stories"], key=lambda s: s["name"].lower()),
        "code_paths": agg["code_paths"],
        "summary": {
            "squad_count": agg["squad_count"],
            "tribe_count": agg["tribe_count"],
            "project_count": agg["project_count"],
            "story_count": agg["story_count"],
            "points": agg["points"],
            "allocation": agg["allocation"],
            "reports_count": len(reports),
        },
    }
