"""Aggregate counts for admin dashboards. All figures are deterministic SQL — no LLM."""

from __future__ import annotations

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
