"""Shared SSE streaming helpers used by the estimation and C4 routers."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import HTTPException, Request
from langchain_core.messages import HumanMessage

from backend.anchors import ANCHORS
from backend.graph.build import get_estimation_graph
from backend.models import Story

ResultCallback = Callable[[dict[str, Any]], Awaitable[None]]


def require_llm_config(request: Request) -> None:
    errors = getattr(request.app.state, "configuration_errors", [])
    if errors:
        raise HTTPException(status_code=503, detail={"code": "configuration_error", "message": "LLM configuration is incomplete.", "details": errors})


def sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


def public_result(values: dict[str, Any]) -> dict[str, Any]:
    blocked = {"anchors", "messages", "escalation_required", "refinement"}
    return {key: value for key, value in values.items() if key not in blocked}


async def stream_story(
    story: Story,
    session_id: str,
    refinement: str | None = None,
    on_result: ResultCallback | None = None,
) -> AsyncIterator[bytes]:
    graph = get_estimation_graph()
    config = {"configurable": {"thread_id": session_id}}
    initial = {
        "story": story.model_dump(),
        "anchors": ANCHORS,
        "refinement": refinement,
        "messages": [HumanMessage(content=refinement or f"Estimate: {story.title}")],
    }
    yield sse("started", {"session_id": session_id, "title": story.title})
    try:
        async for update in graph.astream(initial, config=config, stream_mode="updates"):
            node = next(iter(update))
            # Progress carries only completion and safe narrative summaries; the final event is atomic.
            yield sse("node", {"node": node, "status": "completed"})
        snapshot = await graph.aget_state(config)
        result = public_result(dict(snapshot.values))
        if not result.get("plain_language_why") or not result.get("tldr"):
            raise RuntimeError("The model returned points without the required explanation")
        if on_result is not None:
            await on_result(result)
        yield sse("result", result)
    except Exception as exc:
        yield sse("error", {"code": "estimation_error", "message": str(exc), "retryable": True})


async def stream_batch(stories: list[Story], root_session: str, skipped: list[dict[str, Any]] | None = None) -> AsyncIterator[bytes]:
    yield sse("batch_started", {"count": len(stories), "session_id": root_session, "skipped": skipped or []})
    results = []
    for index, story in enumerate(stories):
        item_session = f"{root_session}:{index}"
        yield sse("item_started", {"index": index, "title": story.title})
        async for chunk in stream_story(story, item_session):
            text = chunk.decode()
            if text.startswith("event: result"):
                data = json.loads(text.split("data: ", 1)[1])
                results.append(data)
                yield sse("item_result", {"index": index, "result": data})
            elif text.startswith("event: node"):
                data = json.loads(text.split("data: ", 1)[1])
                yield sse("item_node", {"index": index, **data})
            elif text.startswith("event: error"):
                data = json.loads(text.split("data: ", 1)[1])
                yield sse("item_error", {"index": index, **data})
    yield sse("batch_result", {"results": results, "skipped": skipped or []})
