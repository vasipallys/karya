"""Workflow-guide endpoint."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from backend.projects.store import NotFoundError
from backend.workflow import service

router = APIRouter(prefix="/projects/{project_id}", tags=["workflow"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc


@router.get("/workflow")
async def get_workflow(project_id: str) -> dict[str, Any]:
    return _run(lambda: service.guide(project_id))
