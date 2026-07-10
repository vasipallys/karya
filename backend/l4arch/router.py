"""HTTP endpoints for the L4 code / implementation-detail workspace."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from backend.l4arch import service, store
from backend.l4arch.models import (
    ChecklistCreate,
    ChecklistUpdate,
    CodeUnitCreate,
    CodeUnitUpdate,
    L4Update,
    TestCaseCreate,
    TestCaseUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/l4/{l4_element_id}/arch", tags=["l4-architecture"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.L4ArchValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "l4arch_validation", "message": str(exc)}) from exc


@router.get("")
async def get_workspace(project_id: str, l4_element_id: str) -> dict[str, Any]:
    return _run(lambda: store.get_workspace(project_id, l4_element_id))


@router.get("/readiness")
async def get_readiness(project_id: str, l4_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.readiness(project_id, l4_element_id))


@router.get("/implementation-summary")
async def get_implementation_summary(project_id: str, l4_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.implementation_summary(project_id, l4_element_id))


@router.patch("")
async def update_arch(project_id: str, l4_element_id: str, payload: L4Update) -> dict[str, Any]:
    return _run(lambda: store.update_l4(project_id, l4_element_id, payload))


@router.get("/traceability")
async def get_traceability(project_id: str, l4_element_id: str) -> dict[str, Any]:
    return _run(lambda: service.traceability(project_id, l4_element_id))


# ---- code units ----
@router.post("/code-units")
async def create_code_unit(project_id: str, l4_element_id: str, payload: CodeUnitCreate) -> dict[str, Any]:
    return _run(lambda: store.create_code_unit(project_id, l4_element_id, payload))


@router.patch("/code-units/{item_id}")
async def update_code_unit(project_id: str, l4_element_id: str, item_id: str, payload: CodeUnitUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_code_unit(project_id, item_id, payload))


@router.delete("/code-units/{item_id}")
async def delete_code_unit(project_id: str, l4_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_code_unit(project_id, item_id))
    return {"status": "deleted"}


# ---- test cases ----
@router.post("/test-cases")
async def create_test_case(project_id: str, l4_element_id: str, payload: TestCaseCreate) -> dict[str, Any]:
    return _run(lambda: store.create_test_case(project_id, l4_element_id, payload))


@router.patch("/test-cases/{item_id}")
async def update_test_case(project_id: str, l4_element_id: str, item_id: str, payload: TestCaseUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_test_case(project_id, item_id, payload))


@router.delete("/test-cases/{item_id}")
async def delete_test_case(project_id: str, l4_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_test_case(project_id, item_id))
    return {"status": "deleted"}


# ---- checklist ----
@router.post("/checklist")
async def create_checklist_item(project_id: str, l4_element_id: str, payload: ChecklistCreate) -> dict[str, Any]:
    return _run(lambda: store.create_checklist_item(project_id, l4_element_id, payload))


@router.patch("/checklist/{item_id}")
async def update_checklist_item(project_id: str, l4_element_id: str, item_id: str, payload: ChecklistUpdate) -> dict[str, Any]:
    return _run(lambda: store.update_checklist_item(project_id, item_id, payload))


@router.delete("/checklist/{item_id}")
async def delete_checklist_item(project_id: str, l4_element_id: str, item_id: str) -> dict[str, str]:
    _run(lambda: store.delete_checklist_item(project_id, item_id))
    return {"status": "deleted"}
