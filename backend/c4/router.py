"""C4 model, per-element estimation, roll-up, and import endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.c4 import service, store
from backend.c4.models import (
    ArtifactTagRequest,
    C4ElementCreate,
    C4ElementUpdate,
    C4RelationCreate,
    ElementEstimateRequest,
    JiraArtifactRequest,
    JiraImportRequest,
    RepoScanRequest,
)
from backend.api.streaming import require_llm_config, stream_story
from backend.config import get_settings
from backend.jira.registry import get_jira_registry
from backend.projects.store import NotFoundError, get_project

router = APIRouter(prefix="/projects/{project_id}", tags=["c4"])


def _run(operation: Any) -> Any:
    try:
        return operation()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.C4ValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "c4_validation", "message": str(exc)}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "scan_error", "message": str(exc)}) from exc


@router.get("/c4/graph")
async def get_graph(project_id: str) -> dict[str, Any]:
    return _run(lambda: store.list_graph(project_id))


@router.post("/c4/elements")
async def create_element(project_id: str, payload: C4ElementCreate) -> dict[str, Any]:
    return _run(lambda: store.create_element(project_id, payload))


@router.get("/c4/elements/{element_id}")
async def get_element(project_id: str, element_id: str) -> dict[str, Any]:
    return _run(lambda: store.get_element(project_id, element_id))


@router.patch("/c4/elements/{element_id}")
async def update_element(project_id: str, element_id: str, payload: C4ElementUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_element(project_id, element_id, payload))


@router.delete("/c4/elements/{element_id}")
async def delete_element(project_id: str, element_id: str) -> dict[str, str]:
    _run(lambda: store.delete_element(project_id, element_id))
    return {"status": "deleted"}


@router.post("/c4/relations")
async def create_relation(project_id: str, payload: C4RelationCreate) -> dict[str, Any]:
    return _run(lambda: store.create_relation(project_id, payload))


@router.delete("/c4/relations/{relation_id}")
async def delete_relation(project_id: str, relation_id: str) -> dict[str, str]:
    _run(lambda: store.delete_relation(project_id, relation_id))
    return {"status": "deleted"}


@router.post("/c4/elements/{element_id}/tag")
async def tag_element(project_id: str, element_id: str, payload: ArtifactTagRequest) -> dict[str, Any]:
    return _run(lambda: store.tag_cross_cutting(project_id, element_id, payload.artifact_type, payload.jira_issue_key))


@router.get("/rollup")
async def get_rollup(project_id: str) -> dict[str, Any]:
    return _run(lambda: service.rollup(project_id))


@router.post("/c4/import/repo-scan")
async def import_repo_scan(project_id: str, payload: RepoScanRequest) -> dict[str, Any]:
    proposal = _run(lambda: service.scan_project_repo(project_id, payload.local_path))
    if not payload.apply:
        return {"proposal": proposal, "applied": False}
    outcome = _run(lambda: service.apply_scan(project_id, proposal))
    return {"proposal": proposal, "applied": True, **outcome}


@router.post("/c4/import/jira")
async def import_jira(project_id: str, payload: JiraImportRequest) -> dict[str, Any]:
    project = _run(lambda: get_project(project_id))
    link = next(iter(project["jira"]), None)
    instance = payload.instance_name or (link and link["instance_name"])
    project_key = payload.project_key or (link and link["project_key"])
    if not instance or not project_key:
        raise HTTPException(status_code=400, detail={"code": "jira_link_missing", "message": "Link a Jira instance and project key first, or pass them explicitly."})
    stories = await get_jira_registry().get_client(instance).fetch_project_issues(
        project_key, status=payload.status, max_issues=payload.max_issues
    )
    return _run(lambda: service.import_jira_stories(project_id, stories))


@router.post("/elements/{element_id}/estimate")
async def estimate_element(project_id: str, element_id: str, payload: ElementEstimateRequest, request: Request) -> StreamingResponse:
    require_llm_config(request)
    element = _run(lambda: store.get_element(project_id, element_id))
    if element["level"] not in {"L3", "L4"}:
        raise HTTPException(status_code=400, detail={
            "code": "not_estimable",
            "message": f"{element['level']} elements aggregate child estimates; estimate the L3 stories beneath them.",
        })
    stored = next(
        (a["estimate_session_id"] for a in element["artifacts"] if a["estimate_session_id"]),
        None,
    )
    session = payload.session_id or (stored if payload.refinement else None) or f"c4-{element_id}-{uuid.uuid4().hex[:8]}"
    story = service.element_to_story(project_id, element)

    async def persist(result: dict[str, Any]) -> None:
        service.persist_estimate(project_id, element, session, result)

    return StreamingResponse(
        stream_story(story, session, payload.refinement, on_result=persist),
        media_type="text/event-stream",
    )


@router.post("/elements/{element_id}/artifact")
async def create_jira_artifact(project_id: str, element_id: str, payload: JiraArtifactRequest) -> dict[str, Any]:
    element = _run(lambda: store.get_element(project_id, element_id))
    artifact_type = store.default_artifact_type(element["level"])
    if payload.link_existing_key:
        record = store.upsert_artifact(element["id"], artifact_type, jira_issue_key=payload.link_existing_key)
        return {"status": "linked", "artifact": record}
    settings = get_settings()
    if not settings.jira_write_enabled:
        raise HTTPException(status_code=403, detail={"code": "write_disabled", "message": "Jira write-back is disabled by configuration."})
    if not payload.confirm:
        raise HTTPException(status_code=400, detail={"code": "confirmation_required", "message": "Set confirm=true after explicit user confirmation."})
    project = _run(lambda: get_project(project_id))
    link = next(iter(project["jira"]), None)
    if link is None:
        raise HTTPException(status_code=400, detail={"code": "jira_link_missing", "message": "Link a Jira instance and project key to this project first."})
    issue_type = {"initiative": "Epic", "epic": "Epic", "story": "Story", "task": "Task"}[artifact_type]
    key = await get_jira_registry().get_client(link["instance_name"]).create_issue(
        link["project_key"], issue_type, element["name"], element["description"]
    )
    record = store.upsert_artifact(element["id"], artifact_type, jira_issue_key=key)
    return {"status": "created", "issue_key": key, "artifact": record}
