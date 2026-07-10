"""FastAPI routes for streaming estimation, Jira, spreadsheet ingestion, and projects."""

from __future__ import annotations

import json
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from backend.api.streaming import require_llm_config, stream_batch, stream_story
from backend.c4.router import router as c4_router
from backend.config import ConfigurationError, get_settings
from backend.graph.build import get_estimation_graph
from backend.graph.checkpoint import set_checkpointer
from backend.ingest.excel import UploadError, dataframe_payload, read_upload, rows_to_stories, template_workbook
from backend.jira.client import JiraError
from backend.jira.registry import get_jira_registry
from backend.llm.factory import validate_factory_config
from backend.models import (
    BatchEstimateRequest,
    ErrorPayload,
    EstimateRequest,
    JiraWriteRequest,
    UploadEstimateRequest,
)
from backend.access.router import router as access_router
from backend.ai.router import router as ai_router
from backend.auth.deps import resolve_role, restricted_block, route_policy
from backend.auth.permissions import can
from backend.integrations.router import router as integrations_router
from backend.l1arch.router import router as l1arch_router
from backend.l2arch.router import router as l2arch_router
from backend.chat.router import router as chat_router
from backend.l3arch.router import router as l3arch_router
from backend.l4arch.router import router as l4arch_router
from backend.planning.router import router as planning_router
from backend.workflow.router import router as workflow_router
from backend.projects.router import router as projects_router
from backend.reporting.router import router as reporting_router
from backend.resources.router import router as resources_router
from backend.storage.db import checkpoint_path, init_db


def error_response(code: str, message: str, status: int, *, details: Any = None, retryable: bool = False) -> JSONResponse:
    payload = ErrorPayload(code=code, message=message, details=details, retryable=retryable)
    return JSONResponse(status_code=status, content={"error": payload.model_dump()})


async def _install_durable_checkpointer(stack: AsyncExitStack) -> None:
    """Swap MemorySaver for AsyncSqliteSaver when the optional dependency is installed."""
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError:
        return

    class JsonSafeMetadataSaver(AsyncSqliteSaver):
        """AsyncSqliteSaver serializes metadata with stdlib json, which crashes on
        LangChain message objects inside node writes. The checkpoint blob itself uses
        the real serializer, so stringifying metadata values is lossless for resume."""

        async def aput(self, config, checkpoint, metadata, new_versions):
            safe_metadata = json.loads(json.dumps(metadata, default=str))
            return await super().aput(config, checkpoint, safe_metadata, new_versions)

    path = checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    saver = await stack.enter_async_context(JsonSafeMetadataSaver.from_conn_string(str(path)))
    set_checkpointer(saver)
    get_estimation_graph.cache_clear()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with AsyncExitStack() as stack:
        await _install_durable_checkpointer(stack)
        try:
            get_settings().validate_startup()
            validate_factory_config()
            app.state.configuration_errors = []
        except ConfigurationError as exc:
            # Keep diagnostics endpoints alive so the UI can render the startup error.
            app.state.configuration_errors = exc.errors
        yield


app = FastAPI(title="Story Pointer API", version="2.0.0", lifespan=lifespan)


@app.middleware("http")
async def rbac_middleware(request: Request, call_next):
    """Local demo RBAC: enforce the capability policy for the resolved caller.

    UI-gating remains the primary control; this is defense in depth. OPTIONS
    (CORS preflight) and public config/login endpoints bypass the check.
    """
    if request.method == "OPTIONS":
        return await call_next(request)
    requires_auth, capability = route_policy(request.method, request.url.path)
    if requires_auth:
        role = resolve_role(request)
        if role is None:
            return error_response("unauthenticated", "Sign in required.", 401)
        if capability and not can(role, capability):
            return error_response("forbidden", f"Your role does not permit this action ({capability}).", 403)
        if restricted_block(request.url.path, role):
            return error_response("forbidden", "This workspace is restricted to managers and admins.", 403)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(projects_router)
app.include_router(c4_router)
app.include_router(planning_router)
app.include_router(resources_router)
app.include_router(access_router)
app.include_router(reporting_router)
app.include_router(ai_router)
app.include_router(l1arch_router)
app.include_router(l2arch_router)
app.include_router(l3arch_router)
app.include_router(l4arch_router)
app.include_router(workflow_router)
app.include_router(chat_router)
app.include_router(integrations_router)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response("validation_error", "The request contains invalid fields.", 422, details=exc.errors())


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return error_response(
        detail.get("code", "http_error"),
        detail.get("message", "The request could not be completed."),
        exc.status_code,
        details=detail.get("details"),
    )


@app.exception_handler(JiraError)
async def jira_error(_: Request, exc: JiraError) -> JSONResponse:
    status = 502 if exc.status is None or exc.status >= 500 else 400
    return error_response("jira_error", str(exc), status, retryable=exc.retryable)


@app.exception_handler(UploadError)
async def upload_error(_: Request, exc: UploadError) -> JSONResponse:
    return error_response("parse_error", str(exc), 400)


@app.get("/health")
async def health(request: Request) -> dict[str, Any]:
    errors = getattr(request.app.state, "configuration_errors", [])
    return {
        "status": "degraded" if errors else "ok",
        "llm": {"status": "configuration_error" if errors else "configured", "errors": errors},
        "jira": await get_jira_registry().health(),
    }


@app.get("/config")
async def active_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "llm": {"provider": settings.llm_provider, "model": settings.llm_model},
        "jira_instances": get_jira_registry().list_instances(),
        "jira_write_enabled": settings.jira_write_enabled,
    }


@app.get("/jira/instances")
async def jira_instances() -> list[dict[str, str]]:
    return get_jira_registry().list_instances()


@app.get("/jira/{instance}/project/{code}/issues")
async def jira_issues(
    instance: str,
    code: str,
    status: str | None = None,
    sprint: str | None = None,
    page_size: int = Query(50, ge=1, le=100),
    max_issues: int = Query(500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    stories = await get_jira_registry().get_client(instance).fetch_project_issues(
        code, status=status, sprint=sprint, page_size=page_size, max_issues=max_issues
    )
    return [story.model_dump() for story in stories]


@app.post("/upload/parse")
async def parse_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise UploadError("File exceeds the 15 MB upload limit")
    return dataframe_payload(read_upload(content, file.filename or "upload"))


@app.get("/upload/template")
async def upload_template() -> Response:
    return Response(
        template_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="story-pointer-template.xlsx"'},
    )


@app.post("/estimate")
async def estimate(payload: EstimateRequest, request: Request) -> StreamingResponse:
    require_llm_config(request)
    session = payload.session_id or str(uuid.uuid4())
    return StreamingResponse(stream_story(payload.story, session, payload.refinement), media_type="text/event-stream")


@app.post("/estimate/batch")
async def estimate_batch(payload: BatchEstimateRequest, request: Request) -> StreamingResponse:
    require_llm_config(request)
    session = payload.session_id or str(uuid.uuid4())
    return StreamingResponse(stream_batch(payload.stories, session), media_type="text/event-stream")


@app.post("/upload/estimate")
async def upload_estimate(payload: UploadEstimateRequest, request: Request) -> StreamingResponse:
    require_llm_config(request)
    stories, skipped = rows_to_stories(payload.rows, payload.mapping)
    if not stories:
        raise UploadError("No valid rows remain after mapping")
    session = payload.session_id or str(uuid.uuid4())
    return StreamingResponse(stream_batch(stories, session, skipped), media_type="text/event-stream")


@app.post("/jira/{instance}/{issue_key}/points")
async def write_jira_points(instance: str, issue_key: str, payload: JiraWriteRequest) -> dict[str, Any]:
    settings = get_settings()
    if not settings.jira_write_enabled:
        raise HTTPException(status_code=403, detail={"code": "write_disabled", "message": "Jira write-back is disabled by configuration."})
    if not payload.confirm:
        raise HTTPException(status_code=400, detail={"code": "confirmation_required", "message": "Set confirm=true after explicit user confirmation."})
    await get_jira_registry().get_client(instance).write_points(issue_key, payload.points)
    return {"status": "updated", "issue_key": issue_key, "points": payload.points}
