"""Agentic AI endpoints. All require a configured LLM (503 otherwise, like estimation)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.ai import agents
from backend.ai.schemas import L1BaselineDraft, L2Draft, L3Draft, L4Draft, ProposedStory, ScaffoldElement, ScaffoldRelation, StaffingAssignment
from backend.api.streaming import require_llm_config
from backend.c4 import store as c4_store
from backend.l2arch import store as l2_store
from backend.l3arch import store as l3_store
from backend.l4arch import store as l4_store
from backend.planning import store as planning_store
from backend.projects.store import NotFoundError
from backend.reporting import service as reporting_service

router = APIRouter(tags=["ai"])

# Not-found / validation errors raised by any store an agent's apply-step touches,
# so a stale or wrong-level element id becomes a clean 404/400 rather than a 500.
_NOT_FOUND_ERRORS = (NotFoundError, l2_store.NotFoundError, l3_store.NotFoundError, l4_store.NotFoundError)
_VALIDATION_ERRORS = (
    planning_store.PlanningValidationError, c4_store.C4ValidationError,
    l2_store.L2ArchValidationError, l3_store.L3ArchValidationError, l4_store.L4ArchValidationError,
)


def _guard(operation: Any) -> Any:
    try:
        return operation()
    except _NOT_FOUND_ERRORS as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except _VALIDATION_ERRORS as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid", "message": str(exc)}) from exc


# ---- request bodies -----------------------------------------------------

class ApplyStaffing(BaseModel):
    assignments: list[StaffingAssignment] = Field(default_factory=list)


class DecomposeRequest(BaseModel):
    guidance: str = Field(default="", max_length=2000)


class ApplyStories(BaseModel):
    stories: list[ProposedStory] = Field(default_factory=list, max_length=30)


class ScaffoldRequest(BaseModel):
    description: str = Field(min_length=1, max_length=8000)


class L1BaselineRequest(BaseModel):
    brief: str = Field(default="", max_length=8000)


class ApplyL1Baseline(BaseModel):
    draft: L1BaselineDraft
    sections: list[str] | None = None


class L2BaselineRequest(BaseModel):
    brief: str = Field(default="", max_length=8000)


class ApplyL2Baseline(BaseModel):
    draft: L2Draft
    sections: list[str] | None = None


class L3BaselineRequest(BaseModel):
    brief: str = Field(default="", max_length=8000)


class ApplyL3Baseline(BaseModel):
    draft: L3Draft
    sections: list[str] | None = None


class L4BaselineRequest(BaseModel):
    brief: str = Field(default="", max_length=8000)


class ApplyL4Baseline(BaseModel):
    draft: L4Draft
    sections: list[str] | None = None


class OrchestrateRequest(BaseModel):
    request: str = Field(min_length=1, max_length=2000)


class SummarizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    field: str = Field(default="default", max_length=40)


class ApplyScaffold(BaseModel):
    elements: list[ScaffoldElement] = Field(default_factory=list, max_length=60)
    relations: list[ScaffoldRelation] = Field(default_factory=list, max_length=80)


# ---- auto-staffing ------------------------------------------------------

@router.post("/projects/{project_id}/l1/{l1_element_id}/ai/staffing")
async def suggest_staffing(project_id: str, l1_element_id: str, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    proposal = await agents.propose_staffing(project_id, l1_element_id)
    return proposal.model_dump()


@router.post("/projects/{project_id}/ai/staffing/apply")
async def apply_staffing(project_id: str, payload: ApplyStaffing) -> dict[str, Any]:
    return _guard(lambda: agents.apply_staffing(project_id, [a.model_dump() for a in payload.assignments]))


# ---- reporting narrative ------------------------------------------------

@router.post("/reporting/narrative")
async def reporting_narrative(request: Request) -> dict[str, Any]:
    require_llm_config(request)
    narrative = await agents.generate_narrative(reporting_service.overview())
    return narrative.model_dump()


# ---- requirements → stories ---------------------------------------------

@router.post("/projects/{project_id}/c4/elements/{element_id}/ai/decompose")
async def decompose(project_id: str, element_id: str, payload: DecomposeRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    element = _guard(lambda: c4_store.get_element(project_id, element_id))
    if element["level"] == "L4":
        raise HTTPException(status_code=400, detail={"code": "not_decomposable", "message": "L4 tasks are already the lowest level."})
    result = await agents.decompose_element(project_id, element_id, payload.guidance)
    return result.model_dump()


@router.post("/projects/{project_id}/c4/elements/{element_id}/ai/decompose/apply")
async def apply_decompose(project_id: str, element_id: str, payload: ApplyStories) -> dict[str, Any]:
    return _guard(lambda: agents.apply_decomposition(project_id, element_id, [s.model_dump() for s in payload.stories]))


# ---- C4 scaffold --------------------------------------------------------

@router.post("/projects/{project_id}/c4/ai/scaffold")
async def scaffold(project_id: str, payload: ScaffoldRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    result = await agents.scaffold_c4(project_id, payload.description)
    return result.model_dump()


@router.post("/projects/{project_id}/c4/ai/scaffold/apply")
async def apply_scaffold(project_id: str, payload: ApplyScaffold) -> dict[str, Any]:
    return _guard(lambda: agents.apply_scaffold(project_id, payload.model_dump()))


# ---- L1 architecture baseline generator ---------------------------------

@router.post("/projects/{project_id}/l1/{l1_element_id}/ai/baseline")
async def generate_l1_baseline(project_id: str, l1_element_id: str, payload: L1BaselineRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    _guard(lambda: c4_store.get_element(project_id, l1_element_id))
    draft = await agents.generate_l1_baseline(project_id, l1_element_id, payload.brief)
    return draft.model_dump()


@router.post("/projects/{project_id}/l1/{l1_element_id}/ai/baseline/apply")
async def apply_l1_baseline(project_id: str, l1_element_id: str, payload: ApplyL1Baseline) -> dict[str, Any]:
    return _guard(lambda: agents.apply_l1_baseline(project_id, l1_element_id, payload.draft.model_dump(), payload.sections))


# ---- L2 container-architecture generator --------------------------------

@router.post("/projects/{project_id}/l2/{l2_element_id}/ai/l2")
async def generate_l2_baseline(project_id: str, l2_element_id: str, payload: L2BaselineRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    _guard(lambda: c4_store.get_element(project_id, l2_element_id))
    draft = await agents.generate_l2_baseline(project_id, l2_element_id, payload.brief)
    return draft.model_dump()


@router.post("/projects/{project_id}/l2/{l2_element_id}/ai/l2/apply")
async def apply_l2_baseline(project_id: str, l2_element_id: str, payload: ApplyL2Baseline) -> dict[str, Any]:
    return _guard(lambda: agents.apply_l2_baseline(project_id, l2_element_id, payload.draft.model_dump(), payload.sections))


# ---- L3 component-architecture generator --------------------------------

@router.post("/projects/{project_id}/l3/{l3_element_id}/ai/l3")
async def generate_l3_baseline(project_id: str, l3_element_id: str, payload: L3BaselineRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    _guard(lambda: c4_store.get_element(project_id, l3_element_id))
    draft = await agents.generate_l3_baseline(project_id, l3_element_id, payload.brief)
    return draft.model_dump()


@router.post("/projects/{project_id}/l3/{l3_element_id}/ai/l3/apply")
async def apply_l3_baseline(project_id: str, l3_element_id: str, payload: ApplyL3Baseline) -> dict[str, Any]:
    return _guard(lambda: agents.apply_l3_baseline(project_id, l3_element_id, payload.draft.model_dump(), payload.sections))


# ---- L4 implementation-detail generator ---------------------------------

@router.post("/projects/{project_id}/l4/{l4_element_id}/ai/l4")
async def generate_l4_baseline(project_id: str, l4_element_id: str, payload: L4BaselineRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    _guard(lambda: c4_store.get_element(project_id, l4_element_id))
    draft = await agents.generate_l4_baseline(project_id, l4_element_id, payload.brief)
    return draft.model_dump()


@router.post("/projects/{project_id}/l4/{l4_element_id}/ai/l4/apply")
async def apply_l4_baseline(project_id: str, l4_element_id: str, payload: ApplyL4Baseline) -> dict[str, Any]:
    return _guard(lambda: agents.apply_l4_baseline(project_id, l4_element_id, payload.draft.model_dump(), payload.sections))


# ---- orchestrator -------------------------------------------------------

@router.post("/ai/orchestrate")
async def orchestrate(payload: OrchestrateRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    plan = await agents.orchestrate(payload.request)
    return plan.model_dump()


@router.post("/ai/summarize")
async def summarize(payload: SummarizeRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    result = await agents.summarize_field(payload.text, payload.field)
    return result.model_dump()
