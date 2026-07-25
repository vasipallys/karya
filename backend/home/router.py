"""Home dashboard endpoint — scoped to the caller's own directory identity."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.home import service

router = APIRouter(prefix="/home", tags=["home"])


@router.get("/inbox")
async def inbox(request: Request) -> dict[str, Any]:
    """The signed-in user's summary, task inbox and pending actions.

    A directory identity (authoritative `X-User-Id` header, never a query/path
    parameter — so a caller only ever sees their own data) gets a **personal**
    dashboard. The bootstrap "Administrator" has no directory id; as an admin it
    gets the **organization-wide** portfolio dashboard instead of an empty one.
    Any other identity-less caller gets an explicit empty payload.
    """
    staff_id = request.headers.get("X-User-Id")
    if staff_id:
        try:
            return service.personal_dashboard(staff_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc

    if request.headers.get("X-User-Role") == "admin":
        return service.organization_dashboard()
    return {"scope": "none", "user": None, "summary": None, "tasks": [], "actions": [], "reason": "no_directory_identity"}
