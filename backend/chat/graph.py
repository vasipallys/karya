"""Concurrent chat-agent graph (LangGraph).

Three branches fan out from START **in parallel**:

- ``planner``   — LLM interprets the message (+ history) into a ChatCommand.
- ``retrieval`` — deterministic C4-model facts (counts, names, proposed work).
- ``tools``     — deterministic service calls (roll-up, workflow guide, and the
                  readiness of any element the message names).

They join at ``judge``, which decides whether the collected evidence is
sufficient, and ``respond`` composes the final reply/proposal through the same
``chat.service.dispatch`` used by the non-streaming endpoint — so level rules,
parent inference, and the proposal-first contract are identical on both paths.
Streaming callers surface each branch's partial result the moment it lands.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.ai import agents
from backend.ai.schemas import ChatCommand
from backend.c4 import service as c4_service
from backend.c4 import store as c4_store
from backend.workflow import service as workflow_service


class ChatAgentState(TypedDict, total=False):
    project_id: str
    message: str
    history: list[dict[str, str]]
    attachment_context: str
    mode: str
    plan: dict[str, Any]        # planner branch
    facts: dict[str, Any]       # retrieval branch
    tool_runs: dict[str, Any]   # tools branch
    verdict: dict[str, Any]
    final: dict[str, Any]


async def planner(state: ChatAgentState) -> dict[str, Any]:
    command = await agents.interpret_chat(state["project_id"], state["message"], state.get("history"),
                                          state.get("attachment_context", ""), state.get("mode", "auto"))
    return {"plan": command.model_dump()}


def retrieval(state: ChatAgentState) -> dict[str, Any]:
    elements = c4_store.list_graph(state["project_id"])["elements"]
    by_level: dict[str, int] = {}
    for element in elements:
        by_level[element["level"]] = by_level.get(element["level"], 0) + 1
    proposed = sum(1 for element in elements if element["status"] == "proposed")
    summary = (
        " · ".join(f"{count} {level}" for level, count in sorted(by_level.items()))
        + (f" · {proposed} proposed" if proposed else "")
    ) if elements else "empty model"
    return {"facts": {
        "element_count": len(elements),
        "by_level": by_level,
        "proposed": proposed,
        "names": [element["name"] for element in elements[:12]],
        "summary": summary,
    }}


def tools(state: ChatAgentState) -> dict[str, Any]:
    from backend.chat.service import _READINESS  # local import avoids a cycle

    project_id = state["project_id"]
    low = state["message"].lower()
    calls: list[dict[str, Any]] = []

    totals = c4_service.rollup(project_id)["totals"]
    stories = totals["estimated_stories"] + totals["unestimated_stories"]
    calls.append({"tool": "rollup",
                  "summary": f"{totals['estimated_stories']}/{stories} stories estimated · {totals['rolled_up_points']} points"})

    guide = workflow_service.guide(project_id)
    calls.append({"tool": "workflow_guide",
                  "summary": f"{guide['overall_pct']}% through the workflow · next: {guide['next_action']['text']}"})

    elements = c4_store.list_graph(project_id)["elements"]
    named = next((e for e in sorted(elements, key=lambda e: -len(e["name"])) if e["name"].lower() in low), None)
    if named and named["level"] in _READINESS:
        result = _READINESS[named["level"]](project_id, named["id"])
        calls.append({"tool": "readiness",
                      "summary": f"“{named['name']}” at {result['score']}% — {result['status_label']}"})

    return {"tool_runs": {"calls": calls, "summary": f"{len(calls)} tool result(s)"}}


def judge(state: ChatAgentState) -> dict[str, Any]:
    plan = state.get("plan") or {}
    evidence = sum(1 for key in ("facts", "tool_runs") if state.get(key))
    action = plan.get("action") or "help"
    sufficient = action not in ("help", "none") and evidence >= 1
    return {"verdict": {
        "sufficient": sufficient,
        "action": action,
        "evidence_branches": evidence,
        "reason": ("planner intent resolved and deterministic evidence collected"
                   if sufficient else "intent unclear — answering with guidance"),
    }}


def respond(state: ChatAgentState) -> dict[str, Any]:
    from backend.chat import service as chat_service  # local import avoids a cycle

    command = ChatCommand(**(state.get("plan") or {}))
    final = chat_service.dispatch(state["project_id"], command)
    final["evidence"] = {
        "retrieval": state.get("facts"),
        "tools": (state.get("tool_runs") or {}).get("calls", []),
        "verdict": state.get("verdict"),
    }
    return {"final": final}


@lru_cache
def get_chat_graph():
    builder = StateGraph(ChatAgentState)
    builder.add_node("planner", planner)
    builder.add_node("retrieval", retrieval)
    builder.add_node("tools", tools)
    builder.add_node("judge", judge)
    builder.add_node("respond", respond)
    # Fan out the three branches concurrently; the judge is the barrier join.
    builder.add_edge(START, "planner")
    builder.add_edge(START, "retrieval")
    builder.add_edge(START, "tools")
    builder.add_edge("planner", "judge")
    builder.add_edge("retrieval", "judge")
    builder.add_edge("tools", "judge")
    builder.add_edge("judge", "respond")
    builder.add_edge("respond", END)
    return builder.compile()
