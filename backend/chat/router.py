"""Conversational-assistant endpoints."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.ai import agents
from backend.api.streaming import require_llm_config
from backend.c4 import store as c4_store
from backend.chat import service
from backend.projects.store import NotFoundError

router = APIRouter(prefix="/projects/{project_id}", tags=["chat"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except (NotFoundError, c4_store.NotFoundError) as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except (service.ChatError, c4_store.C4ValidationError) as exc:
        raise HTTPException(status_code=400, detail={"code": "chat_invalid", "message": str(exc)}) from exc


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatApplyRequest(BaseModel):
    mutation: dict[str, Any]


@router.post("/chat")
async def chat(project_id: str, payload: ChatRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    _run(lambda: c4_store.list_graph(project_id))  # 404 if the project is unknown
    command = await agents.interpret_chat(project_id, payload.message)
    return _run(lambda: service.dispatch(project_id, command))


@router.post("/chat/apply")
async def chat_apply(project_id: str, payload: ChatApplyRequest) -> dict[str, Any]:
    return _run(lambda: service.apply(project_id, payload.mutation))
