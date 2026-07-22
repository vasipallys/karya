"""Access-management endpoints (local demo auth)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.access import pages, store
from backend.access.models import ROLES, AccessUpdate, PagePermissionsUpdate

router = APIRouter(prefix="/access", tags=["access"])


@router.get("/roles")
async def list_roles() -> list[str]:
    return list(ROLES)


@router.get("/users")
async def list_users() -> list[dict[str, Any]]:
    """All staff with their assigned role — for the access-management console."""
    return store.list_users()


@router.get("/pages")
async def list_pages() -> list[dict[str, Any]]:
    return pages.definitions()


@router.get("/me")
async def current_access(request: Request) -> dict[str, Any]:
    staff_id = request.headers.get("X-User-Id")
    if not staff_id:
        raise HTTPException(status_code=400, detail={"code": "missing_identity", "message": "A staff identity is required."})
    try:
        return store.get_user(staff_id)
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc


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


@router.patch("/users/{staff_id}/page-permissions")
async def set_page_permissions(staff_id: str, payload: PagePermissionsUpdate) -> dict[str, Any]:
    try:
        return store.set_page_permissions(staff_id, payload.permissions)
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.ValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_page_permissions", "message": str(exc)}) from exc
