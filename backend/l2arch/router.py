"""HTTP endpoints for the L2 container-architecture workspace."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.l2arch import imports, service, store
from backend.l2arch.models import (
    ApiCreate,
    ApiUpdate,
    ContainerCreate,
    ContainerUpdate,
    IntegrationCreate,
    IntegrationUpdate,
    L2Update,
    NfrCreate,
    NfrUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/l2/{l2_element_id}/arch", tags=["l2-architecture"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except (store.L2ArchValidationError, imports.ImportError_) as exc:
        raise HTTPException(status_code=400, detail={"code": "l2arch_validation", "message": str(exc)}) from exc


class ApprovalDecision(BaseModel):
    approve: bool
    decided_by: str = Field(default="", max_length=160)
    comment: str = Field(default="", max_length=1000)


class RaciCell(BaseModel):
    artifact: str
    role: str
    value: str = ""


class ImportRequest(BaseModel):
    kind: str = Field(pattern="^(openapi|kubernetes)$")
    content: str = Field(min_length=1, max_length=200000)


@router.get("")
async def get_workspace(project_id: str, l2_element_id: str) -> dict[str, Any]:
    return _run(lambda: store.get_workspace(project_id, l2_element_id))


@router.get("/readiness")
async def get_readiness(project_id: str, l2_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.readiness(project_id, l2_element_id))


@router.get("/engineering-summary")
async def get_engineering_summary(project_id: str, l2_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.engineering_summary(project_id, l2_element_id))


@router.patch("")
async def update_arch(project_id: str, l2_element_id: str, payload: L2Update) -> dict[str, Any]:
    return _run(lambda: store.update_l2(project_id, l2_element_id, payload))


@router.get("/traceability")
async def get_traceability(project_id: str, l2_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.traceability(project_id, l2_element_id))


# ---- RACI ----
@router.patch("/raci")
async def set_raci(project_id: str, l2_element_id: str, payload: RaciCell) -> dict[str, Any]:
    return _run(lambda: store.set_raci(project_id, l2_element_id, payload.artifact, payload.role, payload.value))


# ---- approvals ----
@router.post("/approvals/submit")
async def submit_for_review(project_id: str, l2_element_id: str) -> dict[str, Any]:
    return _run(lambda: {"stages": store.submit_for_review(project_id, l2_element_id), **store.approval_state(l2_element_id)})


@router.post("/approvals/{stage}")
async def decide_approval(project_id: str, l2_element_id: str, stage: str, payload: ApprovalDecision) -> dict[str, Any]:
    return _run(lambda: store.decide_approval(project_id, l2_element_id, stage, payload.approve, payload.decided_by, payload.comment))


# ---- imports ----
@router.post("/import")
async def import_source(project_id: str, l2_element_id: str, payload: ImportRequest) -> dict[str, Any]:
    return _run(lambda: imports.run_import(project_id, l2_element_id, payload.kind, payload.content))


# ---- containers ----
@router.post("/containers")
async def create_container(project_id: str, l2_element_id: str, payload: ContainerCreate) -> dict[str, Any]:
    return _run(lambda: store.create_container(project_id, l2_element_id, payload))


@router.patch("/containers/{item_id}")
async def update_container(project_id: str, l2_element_id: str, item_id: str, payload: ContainerUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_container(project_id, item_id, payload))


@router.delete("/containers/{item_id}")
async def delete_container(project_id: str, l2_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_container(project_id, item_id))
    return {"status": "deleted"}


# ---- apis ----
@router.post("/apis")
async def create_api(project_id: str, l2_element_id: str, payload: ApiCreate) -> dict[str, Any]:
    return _run(lambda: store.create_api(project_id, l2_element_id, payload))


@router.patch("/apis/{item_id}")
async def update_api(project_id: str, l2_element_id: str, item_id: str, payload: ApiUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_api(project_id, item_id, payload))


@router.delete("/apis/{item_id}")
async def delete_api(project_id: str, l2_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_api(project_id, item_id))
    return {"status": "deleted"}


# ---- nfrs ----
@router.post("/nfrs")
async def create_nfr(project_id: str, l2_element_id: str, payload: NfrCreate) -> dict[str, Any]:
    return _run(lambda: store.create_nfr(project_id, l2_element_id, payload))


@router.patch("/nfrs/{item_id}")
async def update_nfr(project_id: str, l2_element_id: str, item_id: str, payload: NfrUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_nfr(project_id, item_id, payload))


@router.delete("/nfrs/{item_id}")
async def delete_nfr(project_id: str, l2_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_nfr(project_id, item_id))
    return {"status": "deleted"}


# ---- integrations ----
@router.post("/integrations")
async def create_integration(project_id: str, l2_element_id: str, payload: IntegrationCreate) -> dict[str, Any]:
    return _run(lambda: store.create_integration(project_id, l2_element_id, payload))


@router.patch("/integrations/{item_id}")
async def update_integration(project_id: str, l2_element_id: str, item_id: str, payload: IntegrationUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_integration(project_id, item_id, payload))


@router.delete("/integrations/{item_id}")
async def delete_integration(project_id: str, l2_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_integration(project_id, item_id))
    return {"status": "deleted"}
