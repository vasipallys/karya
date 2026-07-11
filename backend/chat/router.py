"""Conversational-assistant endpoints."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Callable

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.ai import agents
from backend.api.streaming import require_llm_config, sse
from backend.c4 import store as c4_store
from backend.chat import service
from backend.chat import store as chat_store
from backend.chat.graph import get_chat_graph
from backend.projects.store import NotFoundError

router = APIRouter(prefix="/projects/{project_id}", tags=["chat"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except (NotFoundError, c4_store.NotFoundError, chat_store.ChatStoreError) as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except (service.ChatError, c4_store.C4ValidationError) as exc:
        raise HTTPException(status_code=400, detail={"code": "chat_invalid", "message": str(exc)}) from exc


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Recent turns [{role: user|assistant, text}] so follow-up answers keep context.
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    conversation_id: str | None = None
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


class ChatApplyRequest(BaseModel):
    mutation: dict[str, Any]


def _user_id(request: Request) -> str:
    return request.headers.get("X-User-Id") or f"role:{request.headers.get('X-User-Role', 'unknown')}"


def _conversation(project_id: str, request: Request, conversation_id: str | None) -> dict[str, Any]:
    if conversation_id:
        return chat_store.get_conversation(project_id, conversation_id, _user_id(request))
    return chat_store.create_conversation(project_id, _user_id(request))


def _extract_file(filename: str, content: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    text_types = {"txt", "md", "markdown", "csv", "json", "yaml", "yml", "xml", "html", "css", "js", "jsx",
                  "ts", "tsx", "py", "java", "kt", "sql", "sh", "ps1", "c", "cpp", "h", "go", "rs"}
    if suffix in text_types:
        return content.decode("utf-8", errors="replace")
    if suffix == "docx":
        from docx import Document
        doc = Document(BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if suffix in {"xlsx", "xls"}:
        import pandas as pd
        sheets = pd.read_excel(BytesIO(content), sheet_name=None)
        return "\n\n".join(f"SHEET: {name}\n{frame.head(200).to_csv(index=False)}" for name, frame in sheets.items())
    if suffix in {"png", "jpg", "jpeg", "gif", "webp"}:
        return f"Image attachment {filename}. Visual OCR is not available in this local runtime."
    raise service.ChatError("Unsupported attachment type. Use text/code, CSV/Excel, Word, or an image.")


@router.get("/chat/conversations")
async def conversations(project_id: str, request: Request) -> list[dict[str, Any]]:
    return chat_store.list_conversations(project_id, _user_id(request))


@router.post("/chat/conversations")
async def new_conversation(project_id: str, request: Request) -> dict[str, Any]:
    _run(lambda: c4_store.list_graph(project_id))
    return chat_store.create_conversation(project_id, _user_id(request))


@router.get("/chat/conversations/{conversation_id}")
async def conversation(project_id: str, conversation_id: str, request: Request) -> dict[str, Any]:
    return _run(lambda: chat_store.get_conversation(project_id, conversation_id, _user_id(request)))


@router.delete("/chat/conversations/{conversation_id}")
async def remove_conversation(project_id: str, conversation_id: str, request: Request) -> dict[str, str]:
    _run(lambda: chat_store.delete_conversation(project_id, conversation_id, _user_id(request)))
    return {"status": "deleted"}


@router.post("/chat/conversations/{conversation_id}/attachments")
async def upload_attachment(project_id: str, conversation_id: str, request: Request,
                            file: UploadFile = File(...)) -> dict[str, Any]:
    _run(lambda: chat_store.get_conversation(project_id, conversation_id, _user_id(request)))
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail={"code": "empty_file", "message": "The attachment is empty."})
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail={"code": "file_too_large", "message": "Attachments are limited to 10 MB."})
    extracted = _run(lambda: _extract_file(file.filename or "attachment", content))
    return chat_store.add_attachment(conversation_id, file.filename or "attachment",
                                     file.content_type or "application/octet-stream", len(content), extracted[:100_000])


@router.post("/chat")
async def chat(project_id: str, payload: ChatRequest, request: Request) -> dict[str, Any]:
    require_llm_config(request)
    _run(lambda: c4_store.list_graph(project_id))  # 404 if the project is unknown
    convo = _run(lambda: _conversation(project_id, request, payload.conversation_id))
    stored_history = [{"role": m["role"], "text": m["text"]} for m in convo.get("messages", [])[-12:]]
    attachment_text, attachment_meta = chat_store.attachment_context(convo["id"], payload.attachment_ids)
    user_message = chat_store.add_message(convo["id"], "user", payload.message, {"attachments": attachment_meta})
    chat_store.attach_to_message(payload.attachment_ids, user_message["id"])
    command = await agents.interpret_chat(project_id, payload.message, stored_history or payload.history, attachment_text)
    result = _run(lambda: service.dispatch(project_id, command))
    chat_store.add_message(convo["id"], "assistant", result["reply"], result)
    return {**result, "conversation_id": convo["id"]}


@router.post("/chat/stream")
async def chat_stream(project_id: str, payload: ChatRequest, request: Request) -> StreamingResponse:
    """Concurrent-agent chat over SSE: a `branch` event per parallel branch as
    it completes (planner / retrieval / tools), a `judge` verdict, then the
    final `result` in the exact shape POST /chat returns (so Apply is shared)."""
    require_llm_config(request)
    _run(lambda: c4_store.list_graph(project_id))  # 404 if the project is unknown

    async def generate():
        convo = _run(lambda: _conversation(project_id, request, payload.conversation_id))
        stored_history = [{"role": m["role"], "text": m["text"]} for m in convo.get("messages", [])[-12:]]
        attachment_text, attachment_meta = chat_store.attachment_context(convo["id"], payload.attachment_ids)
        user_message = chat_store.add_message(convo["id"], "user", payload.message, {"attachments": attachment_meta})
        chat_store.attach_to_message(payload.attachment_ids, user_message["id"])
        state = {"project_id": project_id, "message": payload.message,
                 "history": stored_history or payload.history, "attachment_context": attachment_text}
        try:
            async for update in get_chat_graph().astream(state, stream_mode="updates"):
                for node, values in update.items():
                    if node == "respond":
                        final = {**values["final"], "conversation_id": convo["id"]}
                        chat_store.add_message(convo["id"], "assistant", final["reply"], final)
                        yield sse("result", final)
                    elif node == "judge":
                        yield sse("judge", values["verdict"])
                    else:
                        yield sse("branch", {"branch": node, **values})
        except (service.ChatError, c4_store.C4ValidationError) as exc:
            yield sse("error", {"code": "chat_invalid", "message": str(exc), "retryable": False})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/chat/apply")
async def chat_apply(project_id: str, payload: ChatApplyRequest) -> dict[str, Any]:
    return _run(lambda: service.apply(project_id, payload.mutation))
