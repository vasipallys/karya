"""HTTP endpoints for the L3 component-architecture workspace."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.l3arch import service, store
from backend.l3arch.models import (
    ComponentCreate,
    ComponentUpdate,
    ConcernCreate,
    ConcernUpdate,
    DependencyCreate,
    DependencyUpdate,
    InterfaceCreate,
    InterfaceUpdate,
    L3Update,
)

router = APIRouter(prefix="/projects/{project_id}/l3/{l3_element_id}/arch", tags=["l3-architecture"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.L3ArchValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "l3arch_validation", "message": str(exc)}) from exc


class ApprovalDecision(BaseModel):
    approve: bool
    decided_by: str = Field(default="", max_length=160)
    comment: str = Field(default="", max_length=1000)


class RaciCell(BaseModel):
    artifact: str
    role: str
    value: str = ""


@router.get("")
async def get_workspace(project_id: str, l3_element_id: str) -> dict[str, Any]:
    return _run(lambda: store.get_workspace(project_id, l3_element_id))


@router.get("/readiness")
async def get_readiness(project_id: str, l3_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.readiness(project_id, l3_element_id))


@router.get("/engineering-summary")
async def get_engineering_summary(project_id: str, l3_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.engineering_summary(project_id, l3_element_id))


@router.patch("")
async def update_arch(project_id: str, l3_element_id: str, payload: L3Update) -> dict[str, Any]:
    return _run(lambda: store.update_l3(project_id, l3_element_id, payload))


@router.get("/traceability")
async def get_traceability(project_id: str, l3_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.traceability(project_id, l3_element_id))


# ---- RACI ----
@router.patch("/raci")
async def set_raci(project_id: str, l3_element_id: str, payload: RaciCell) -> dict[str, Any]:
    return _run(lambda: store.set_raci(project_id, l3_element_id, payload.artifact, payload.role, payload.value))


# ---- approvals ----
@router.post("/approvals/submit")
async def submit_for_review(project_id: str, l3_element_id: str) -> dict[str, Any]:
    return _run(lambda: {"stages": store.submit_for_review(project_id, l3_element_id), **store.approval_state(l3_element_id)})


@router.post("/approvals/{stage}")
async def decide_approval(project_id: str, l3_element_id: str, stage: str, payload: ApprovalDecision) -> dict[str, Any]:
    return _run(lambda: store.decide_approval(project_id, l3_element_id, stage, payload.approve, payload.decided_by, payload.comment))


# ---- components ----
@router.post("/components")
async def create_component(project_id: str, l3_element_id: str, payload: ComponentCreate) -> dict[str, Any]:
    return _run(lambda: store.create_component(project_id, l3_element_id, payload))


@router.patch("/components/{item_id}")
async def update_component(project_id: str, l3_element_id: str, item_id: str, payload: ComponentUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_component(project_id, item_id, payload))


@router.delete("/components/{item_id}")
async def delete_component(project_id: str, l3_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_component(project_id, item_id))
    return {"status": "deleted"}


# ---- interfaces ----
@router.post("/interfaces")
async def create_interface(project_id: str, l3_element_id: str, payload: InterfaceCreate) -> dict[str, Any]:
    return _run(lambda: store.create_interface(project_id, l3_element_id, payload))


@router.patch("/interfaces/{item_id}")
async def update_interface(project_id: str, l3_element_id: str, item_id: str, payload: InterfaceUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_interface(project_id, item_id, payload))


@router.delete("/interfaces/{item_id}")
async def delete_interface(project_id: str, l3_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_interface(project_id, item_id))
    return {"status": "deleted"}


# ---- dependencies ----
@router.post("/dependencies")
async def create_dependency(project_id: str, l3_element_id: str, payload: DependencyCreate) -> dict[str, Any]:
    return _run(lambda: store.create_dependency(project_id, l3_element_id, payload))


@router.patch("/dependencies/{item_id}")
async def update_dependency(project_id: str, l3_element_id: str, item_id: str, payload: DependencyUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_dependency(project_id, item_id, payload))


@router.delete("/dependencies/{item_id}")
async def delete_dependency(project_id: str, l3_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_dependency(project_id, item_id))
    return {"status": "deleted"}


# ---- concerns ----
@router.post("/concerns")
async def create_concern(project_id: str, l3_element_id: str, payload: ConcernCreate) -> dict[str, Any]:
    return _run(lambda: store.create_concern(project_id, l3_element_id, payload))


@router.patch("/concerns/{item_id}")
async def update_concern(project_id: str, l3_element_id: str, item_id: str, payload: ConcernUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_concern(project_id, item_id, payload))


@router.delete("/concerns/{item_id}")
async def delete_concern(project_id: str, l3_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_concern(project_id, item_id))
    return {"status": "deleted"}
