"""Reporting endpoints for the admin console."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.reporting import service

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/overview")
async def overview() -> dict[str, Any]:
    return service.overview()


@router.get("/resource-graph")
async def resource_graph() -> dict[str, Any]:
    return service.resource_graph()


@router.get("/resource/{staff_id}")
async def resource_profile(staff_id: str) -> dict[str, Any]:
    try:
        return service.resource_profile(staff_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
