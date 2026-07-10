"""HTTP endpoints for the L1 architecture baseline."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.l1arch import exports, service, store
from backend.l1arch.models import (
    ApprovalDecision,
    CapabilityCreate,
    CapabilityUpdate,
    CommentCreate,
    OkrCreate,
    OkrUpdate,
    RiskCreate,
    RiskUpdate,
    StakeholderCreate,
    StakeholderUpdate,
    VisionUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/l1/{l1_element_id}/arch", tags=["l1-architecture"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.L1ArchValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "l1arch_validation", "message": str(exc)}) from exc


@router.get("")
async def get_baseline(project_id: str, l1_element_id: str) -> dict[str, Any]:
    return _run(lambda: store.get_baseline(project_id, l1_element_id))


@router.get("/readiness")
async def get_readiness(project_id: str, l1_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.readiness(project_id, l1_element_id))


@router.get("/traceability")
async def get_traceability(project_id: str, l1_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.traceability(project_id, l1_element_id))


@router.get("/impact")
async def get_impact(project_id: str, l1_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.impact_analysis(project_id, l1_element_id))


# ---- comments / review threads ----
@router.get("/comments")
async def list_comments(project_id: str, l1_element_id: str) -> list[dict[str, Any]]:
    return _run(lambda: store.list_comments(l1_element_id))


@router.post("/comments")
async def create_comment(project_id: str, l1_element_id: str, payload: CommentCreate) -> dict[str, Any]:
    return _run(lambda: store.create_comment(project_id, l1_element_id, payload))


@router.patch("/comments/{comment_id}")
async def resolve_comment(project_id: str, l1_element_id: str, comment_id: str, resolved: bool = True) -> dict[str, Any]:
    return _run(lambda: store.resolve_comment(project_id, comment_id, resolved))


@router.delete("/comments/{comment_id}")
async def delete_comment(project_id: str, l1_element_id: str, comment_id: str) -> dict[str, str]:
    _run(lambda: store.delete_comment(project_id, comment_id))
    return {"status": "deleted"}


# ---- live Jira import ----
class JiraImportRequest(BaseModel):
    instance: str
    project_code: str = Field(min_length=1, max_length=50)
    target: str = Field(default="capabilities")
    max_issues: int = Field(default=50, ge=1, le=200)


@router.post("/import/jira")
async def import_jira(project_id: str, l1_element_id: str, payload: JiraImportRequest) -> dict[str, Any]:
    from backend.jira.registry import get_jira_registry

    _run(lambda: store.get_vision(project_id, l1_element_id))  # 404 if L1 invalid
    registry = get_jira_registry()
    if payload.instance not in {item["name"] for item in registry.list_instances()}:
        raise HTTPException(status_code=400, detail={
            "code": "jira_not_configured",
            "message": f"Jira instance '{payload.instance}' is not configured. Set JIRA_INSTANCES and JIRA_<NAME>_* in backend/.env.",
        })
    stories = await registry.get_client(payload.instance).fetch_project_issues(payload.project_code, max_issues=payload.max_issues)
    created = 0
    for story in stories:
        if payload.target == "okrs":
            store.create_okr(project_id, l1_element_id, OkrCreate(objective=story.title[:400]))
        else:
            store.create_capability(project_id, l1_element_id, CapabilityCreate(
                name=story.title[:200], description=(story.user_story or "")[:1000],
            ))
        created += 1
    return {"created": created, "target": payload.target, "source": f"{payload.instance}/{payload.project_code}"}


@router.get("/executive-summary")
async def get_executive_summary(project_id: str, l1_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.executive_summary(project_id, l1_element_id))


class ExecExportRequest(BaseModel):
    diagram_images: list[str] = Field(default_factory=list)


_EXPORT_MEDIA = {
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@router.post("/executive-summary/export/{fmt}")
async def export_summary(project_id: str, l1_element_id: str, fmt: str, payload: ExecExportRequest) -> Response:
    if fmt not in _EXPORT_MEDIA:
        raise HTTPException(status_code=400, detail={"code": "bad_format", "message": "Use md, docx or pptx."})

    def build() -> tuple[bytes, str]:
        if fmt == "md":
            return exports.executive_markdown(project_id, l1_element_id)
        if fmt == "docx":
            return exports.executive_docx(project_id, l1_element_id, payload.diagram_images)
        return exports.executive_pptx(project_id, l1_element_id, payload.diagram_images)

    content, filename = _run(build)
    return Response(
        content,
        media_type=_EXPORT_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- approvals ----
@router.post("/approvals/submit")
async def submit_for_review(project_id: str, l1_element_id: str) -> dict[str, Any]:
    return _run(lambda: {"stages": store.submit_for_review(project_id, l1_element_id), **store.approval_state(l1_element_id)})


@router.post("/approvals/{stage}")
async def decide_approval(project_id: str, l1_element_id: str, stage: str, payload: ApprovalDecision) -> dict[str, Any]:
    return _run(lambda: store.decide_approval(project_id, l1_element_id, stage, payload.approve, payload.decided_by, payload.comment))


# ---- vision ----
@router.patch("/vision")
async def update_vision(project_id: str, l1_element_id: str, payload: VisionUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_vision(project_id, l1_element_id, payload))


# ---- OKRs ----
@router.post("/okrs")
async def create_okr(project_id: str, l1_element_id: str, payload: OkrCreate) -> dict[str, Any]:
    return _run(lambda: store.create_okr(project_id, l1_element_id, payload))


@router.patch("/okrs/{item_id}")
async def update_okr(project_id: str, l1_element_id: str, item_id: str, payload: OkrUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_okr(project_id, item_id, payload))


@router.delete("/okrs/{item_id}")
async def delete_okr(project_id: str, l1_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_okr(project_id, item_id))
    return {"status": "deleted"}


# ---- stakeholders ----
@router.post("/stakeholders")
async def create_stakeholder(project_id: str, l1_element_id: str, payload: StakeholderCreate) -> dict[str, Any]:
    return _run(lambda: store.create_stakeholder(project_id, l1_element_id, payload))


@router.patch("/stakeholders/{item_id}")
async def update_stakeholder(project_id: str, l1_element_id: str, item_id: str, payload: StakeholderUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_stakeholder(project_id, item_id, payload))


@router.delete("/stakeholders/{item_id}")
async def delete_stakeholder(project_id: str, l1_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_stakeholder(project_id, item_id))
    return {"status": "deleted"}


# ---- capabilities ----
@router.post("/capabilities")
async def create_capability(project_id: str, l1_element_id: str, payload: CapabilityCreate) -> dict[str, Any]:
    return _run(lambda: store.create_capability(project_id, l1_element_id, payload))


@router.patch("/capabilities/{item_id}")
async def update_capability(project_id: str, l1_element_id: str, item_id: str, payload: CapabilityUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_capability(project_id, item_id, payload))


@router.delete("/capabilities/{item_id}")
async def delete_capability(project_id: str, l1_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_capability(project_id, item_id))
    return {"status": "deleted"}


# ---- risks ----
@router.post("/risks")
async def create_risk(project_id: str, l1_element_id: str, payload: RiskCreate) -> dict[str, Any]:
    return _run(lambda: store.create_risk(project_id, l1_element_id, payload))


@router.patch("/risks/{item_id}")
async def update_risk(project_id: str, l1_element_id: str, item_id: str, payload: RiskUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_risk(project_id, item_id, payload))


@router.delete("/risks/{item_id}")
async def delete_risk(project_id: str, l1_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_risk(project_id, item_id))
    return {"status": "deleted"}
