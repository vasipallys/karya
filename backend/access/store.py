"""Persistence for access management (staff ↔ role assignments)."""

from __future__ import annotations

from typing import Any

from backend.access.models import DEFAULT_ROLE, AccessUpdate
from backend.storage.db import connect, utc_now

# Subset of staff columns surfaced to the access UI / login screen.
_STAFF_FIELDS = "s.id, s.staff_code, s.staff_name, s.staff_type, s.staff_status, s.tech_unit, s.hr_role"


class NotFoundError(LookupError):
    pass


def _bootstrap_admin(conn: Any) -> None:
    """Guarantee at least one admin exists so the app is never locked out.

    Promotes the earliest-created active staff member to admin when no enabled
    admin is assigned yet. Persisted, so it is stable across restarts.
    """
    has_admin = conn.execute(
        """SELECT 1 FROM app_access a JOIN resource_staff s ON s.id = a.staff_id
           WHERE a.role = 'admin' AND a.enabled = 1 LIMIT 1"""
    ).fetchone()
    if has_admin:
        return
    first = conn.execute(
        "SELECT id FROM resource_staff ORDER BY created_at, staff_code LIMIT 1"
    ).fetchone()
    if first is None:
        return
    conn.execute(
        """INSERT INTO app_access (staff_id, role, enabled, updated_at)
           VALUES (?, 'admin', 1, ?)
           ON CONFLICT(staff_id) DO UPDATE SET role = 'admin', enabled = 1, updated_at = excluded.updated_at""",
        (first["id"], utc_now()),
    )


def list_users(enabled_only: bool = False) -> list[dict[str, Any]]:
    """All directory staff with their effective role + enabled flag."""
    with connect() as conn:
        _bootstrap_admin(conn)
        rows = conn.execute(
            f"""SELECT {_STAFF_FIELDS},
                       COALESCE(a.role, ?) AS role,
                       COALESCE(a.enabled, 1) AS enabled,
                       a.updated_at AS access_updated_at
                FROM resource_staff s
                LEFT JOIN app_access a ON a.staff_id = s.id
                ORDER BY s.staff_name COLLATE NOCASE""",
            (DEFAULT_ROLE,),
        ).fetchall()
    users = [dict(row) for row in rows]
    for user in users:
        user["enabled"] = bool(user["enabled"])
    if enabled_only:
        users = [user for user in users if user["enabled"] and user["staff_status"] == "Active"]
    return users


def set_access(staff_id: str, payload: AccessUpdate) -> dict[str, Any]:
    with connect() as conn:
        staff = conn.execute("SELECT id FROM resource_staff WHERE id = ?", (staff_id,)).fetchone()
        if staff is None:
            raise NotFoundError(f"Staff '{staff_id}' was not found")
        existing = conn.execute("SELECT role, enabled FROM app_access WHERE staff_id = ?", (staff_id,)).fetchone()
        role = payload.role if payload.role is not None else (existing["role"] if existing else DEFAULT_ROLE)
        enabled = payload.enabled if payload.enabled is not None else (bool(existing["enabled"]) if existing else True)
        conn.execute(
            """INSERT INTO app_access (staff_id, role, enabled, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(staff_id) DO UPDATE SET role = excluded.role, enabled = excluded.enabled, updated_at = excluded.updated_at""",
            (staff_id, role, 1 if enabled else 0, utc_now()),
        )
    return get_user(staff_id)


def get_user(staff_id: str) -> dict[str, Any]:
    for user in list_users():
        if user["id"] == staff_id:
            return user
    raise NotFoundError(f"Staff '{staff_id}' was not found")


def effective_role(staff_id: str) -> str | None:
    """Lean per-request role lookup for RBAC. Returns None if unknown or disabled."""
    with connect() as conn:
        if conn.execute("SELECT 1 FROM resource_staff WHERE id = ?", (staff_id,)).fetchone() is None:
            return None
        row = conn.execute("SELECT role, enabled FROM app_access WHERE staff_id = ?", (staff_id,)).fetchone()
        if row is None:
            return DEFAULT_ROLE
        return None if not row["enabled"] else row["role"]


def role_counts() -> dict[str, int]:
    counts = {"admin": 0, "manager": 0, "contributor": 0, "viewer": 0, "disabled": 0}
    for user in list_users():
        if not user["enabled"]:
            counts["disabled"] += 1
        counts[user["role"]] = counts.get(user["role"], 0) + 1
    return counts
