"""Project CRUD and link endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.projects import store
from backend.projects.models import JiraLinkCreate, ProjectCreate, ProjectUpdate, RepoLinkCreate

router = APIRouter(prefix="/projects", tags=["projects"])


def _or_404(operation: Any) -> Any:
    try:
        return operation()
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc


@router.post("")
async def create_project(payload: ProjectCreate) -> dict[str, Any]:
    return store.create_project(payload)


@router.get("")
async def list_projects() -> list[dict[str, Any]]:
    return store.list_projects()


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    return _or_404(lambda: store.get_project(project_id))


@router.patch("/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate) -> dict[str, Any]:
    return _or_404(lambda: store.update_project(project_id, payload))


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict[str, str]:
    _or_404(lambda: store.delete_project(project_id))
    return {"status": "deleted"}


@router.post("/{project_id}/repos")
async def add_repo(project_id: str, payload: RepoLinkCreate) -> dict[str, Any]:
    return _or_404(lambda: store.add_repo_link(project_id, payload))


@router.post("/{project_id}/jira")
async def add_jira(project_id: str, payload: JiraLinkCreate) -> dict[str, Any]:
    return _or_404(lambda: store.add_jira_link(project_id, payload))
