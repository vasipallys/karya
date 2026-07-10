"""Reporting endpoints for the admin console."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.reporting import service

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/overview")
async def overview() -> dict[str, Any]:
    return service.overview()
