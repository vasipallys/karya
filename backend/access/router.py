"""Access-management endpoints (local demo auth)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.access import store
from backend.access.models import ROLES, AccessUpdate

router = APIRouter(prefix="/access", tags=["access"])


@router.get("/roles")
async def list_roles() -> list[str]:
    return list(ROLES)


@router.get("/users")
async def list_users() -> list[dict[str, Any]]:
    """All staff with their assigned role — for the access-management console."""
    return store.list_users()


@router.get("/login-users")
async def login_users() -> list[dict[str, Any]]:
    """Enabled + active staff only — the pickable identities on the login screen."""
    return store.list_users(enabled_only=True)


@router.patch("/users/{staff_id}")
async def set_access(staff_id: str, payload: AccessUpdate) -> dict[str, Any]:
    try:
        return store.set_access(staff_id, payload)
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
