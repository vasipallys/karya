"""FastAPI routes for initiative-level operating plans."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend.api.streaming import require_llm_config
from backend.planning import diagram_ai, exports, requirements, store
from backend.planning.models import (
    AgileUnitCreate,
    AgileUnitUpdate,
    DiagramAssistRequest,
    DiagramCreate,
    DiagramGenerateRequest,
    DiagramUpdate,
    PlanSettingsUpdate,
    RequirementCommentAction,
    RequirementCommentCreate,
    RequirementDocumentCreate,
    RequirementDocumentUpdate,
    RequirementExportRequest,
    RequirementReviewAction,
    TeamMemberCreate,
    TeamMemberUpdate,
    WorkItemCreate,
    WorkItemUpdate,
)
from backend.projects.store import NotFoundError

router = APIRouter(prefix="/projects/{project_id}", tags=["l1-planning"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.PlanningValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "planning_validation", "message": str(exc)}) from exc
    except requirements.PlanningConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "planning_conflict", "message": str(exc)}) from exc


@router.get("/l1/{l1_element_id}/plan")
async def get_plan(project_id: str, l1_element_id: str) -> dict[str, Any]:
    return _run(lambda: store.get_plan(project_id, l1_element_id))


@router.patch("/l1/{l1_element_id}/plan")
async def update_plan(project_id: str, l1_element_id: str, payload: PlanSettingsUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_settings(project_id, l1_element_id, payload))


@router.post("/l1/{l1_element_id}/units")
async def create_unit(project_id: str, l1_element_id: str, payload: AgileUnitCreate) -> dict[str, Any]:
    return _run(lambda: store.create_unit(project_id, l1_element_id, payload))


@router.patch("/l1/units/{unit_id}")
async def update_unit(project_id: str, unit_id: str, payload: AgileUnitUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_unit(project_id, unit_id, payload))


@router.delete("/l1/units/{unit_id}")
async def delete_unit(project_id: str, unit_id: str) -> dict[str, str]:
    _run(lambda: store.delete_unit(project_id, unit_id))
    return {"status": "deleted"}


@router.post("/l1/units/{unit_id}/members")
async def create_member(project_id: str, unit_id: str, payload: TeamMemberCreate) -> dict[str, Any]:
    return _run(lambda: store.create_member(project_id, unit_id, payload))


@router.patch("/l1/members/{member_id}")
async def update_member(project_id: str, member_id: str, payload: TeamMemberUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_member(project_id, member_id, payload))


@router.delete("/l1/members/{member_id}")
async def delete_member(project_id: str, member_id: str) -> dict[str, str]:
    _run(lambda: store.delete_member(project_id, member_id))
    return {"status": "deleted"}


@router.post("/l1/{l1_element_id}/work")
async def create_work_item(project_id: str, l1_element_id: str, payload: WorkItemCreate) -> dict[str, Any]:
    return _run(lambda: store.create_work_item(project_id, l1_element_id, payload))


@router.patch("/l1/work/{work_item_id}")
async def update_work_item(project_id: str, work_item_id: str, payload: WorkItemUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_work_item(project_id, work_item_id, payload))


@router.delete("/l1/work/{work_item_id}")
async def delete_work_item(project_id: str, work_item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_work_item(project_id, work_item_id))
    return {"status": "deleted"}


@router.post("/l1/{l1_element_id}/diagrams")
async def create_diagram(project_id: str, l1_element_id: str, payload: DiagramCreate) -> dict[str, Any]:
    return _run(lambda: store.create_diagram(project_id, l1_element_id, payload))


@router.patch("/l1/diagrams/{diagram_id}")
async def update_diagram(project_id: str, diagram_id: str, payload: DiagramUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_diagram(project_id, diagram_id, payload))


@router.delete("/l1/diagrams/{diagram_id}")
async def delete_diagram(project_id: str, diagram_id: str) -> dict[str, str]:
    _run(lambda: store.delete_diagram(project_id, diagram_id))
    return {"status": "deleted"}


async def _run_ai(coro: Any) -> Any:
    try:
        return await coro
    except Exception as exc:  # LLM/provider failures surface as a retryable 502
        raise HTTPException(status_code=502, detail={"code": "diagram_ai_error", "message": str(exc)[:400], "retryable": True}) from exc


@router.post("/l1/{l1_element_id}/diagrams/generate")
async def generate_diagram(project_id: str, l1_element_id: str, payload: DiagramGenerateRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    draft = await _run_ai(diagram_ai.assist_diagram(prompt=payload.prompt, diagram_type=payload.diagram_type))
    title = (payload.title or "").strip() or diagram_ai.title_from_prompt(payload.prompt)
    return _run(lambda: store.create_diagram(
        project_id,
        l1_element_id,
        DiagramCreate(diagram_type=payload.diagram_type, title=title, mermaid_source=draft["mermaid"]),
    ))


@router.post("/l1/{l1_element_id}/diagrams/assist")
async def assist_diagram(project_id: str, l1_element_id: str, payload: DiagramAssistRequest, request: Request) -> dict[str, str]:
    require_llm_config(request)
    return await _run_ai(diagram_ai.assist_diagram(
        prompt=payload.prompt,
        diagram_type=payload.diagram_type,
        current_source=payload.current_source,
        history=[turn.model_dump() for turn in payload.history],
    ))


@router.get("/l1/{l1_element_id}/requirements")
async def list_requirement_documents(project_id: str, l1_element_id: str) -> list[dict[str, Any]]:
    return _run(lambda: requirements.list_documents(project_id, l1_element_id))


@router.post("/l1/{l1_element_id}/requirements")
async def create_requirement_document(
    project_id: str,
    l1_element_id: str,
    payload: RequirementDocumentCreate,
) -> dict[str, Any]:
    return _run(lambda: requirements.create_document(project_id, l1_element_id, payload))


@router.get("/l1/requirements/{document_id}")
async def get_requirement_document(project_id: str, document_id: str) -> dict[str, Any]:
    return _run(lambda: requirements.get_document(project_id, document_id))


@router.patch("/l1/requirements/{document_id}")
async def update_requirement_document(
    project_id: str,
    document_id: str,
    payload: RequirementDocumentUpdate,
) -> dict[str, Any]:
    return _run(lambda: requirements.update_document(project_id, document_id, payload))


@router.get("/l1/requirements/{document_id}/versions/{version}")
async def get_requirement_version(project_id: str, document_id: str, version: int) -> dict[str, Any]:
    return _run(lambda: requirements.get_version(project_id, document_id, version))


@router.post("/l1/requirements/{document_id}/comments")
async def add_requirement_comment(
    project_id: str,
    document_id: str,
    payload: RequirementCommentCreate,
) -> dict[str, Any]:
    return _run(lambda: requirements.add_comment(project_id, document_id, payload))


@router.patch("/l1/requirements/comments/{comment_id}")
async def act_on_requirement_comment(
    project_id: str,
    comment_id: str,
    payload: RequirementCommentAction,
) -> dict[str, Any]:
    return _run(lambda: requirements.act_on_comment(project_id, comment_id, payload))


@router.post("/l1/requirements/{document_id}/review")
async def review_requirement_document(
    project_id: str,
    document_id: str,
    payload: RequirementReviewAction,
) -> dict[str, Any]:
    return _run(lambda: requirements.review_document(project_id, document_id, payload))


@router.post("/l1/requirements/{document_id}/export/{export_format}")
async def export_requirement_document(
    project_id: str,
    document_id: str,
    export_format: str,
    payload: RequirementExportRequest,
) -> Response:
    if export_format == "docx":
        content, filename = _run(
            lambda: exports.word_export(project_id, document_id, payload.diagram_images)
        )
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif export_format == "pptx":
        content, filename = _run(
            lambda: exports.powerpoint_export(project_id, document_id, payload.diagram_images)
        )
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        raise HTTPException(
            status_code=400,
            detail={"code": "planning_validation", "message": "Export format must be docx or pptx"},
        )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
