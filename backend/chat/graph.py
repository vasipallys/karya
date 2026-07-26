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
from backend.ai.nl import classify_read, ground_status_target, is_write_intent, parse_operating_plan_intent
from backend.ai.schemas import ChatCommand
from backend.c4 import service as c4_service
from backend.c4 import store as c4_store
from backend.projects import store as projects_store
from backend.planning import store as planning_store
from backend.workflow import service as workflow_service


class ChatAgentState(TypedDict, total=False):
    project_id: str
    message: str
    history: list[dict[str, str]]
    attachment_context: str
    mode: str
    screen: dict[str, Any]
    plan: dict[str, Any]        # planner branch
    facts: dict[str, Any]       # retrieval branch
    tool_runs: dict[str, Any]   # tools branch
    verdict: dict[str, Any]
    final: dict[str, Any]


def _operating_intent(state: ChatAgentState, elements: list[dict[str, Any]]) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
    units: list[dict[str, str]] = []
    for l1 in [item for item in elements if item["level"] == "L1"]:
        plan = planning_store.get_plan(state["project_id"], l1["id"])
        units.extend({
            "id": str(unit["id"]),
            "name": str(unit["name"]),
            "unit_type": str(unit["unit_type"]),
            "l1_name": str(l1["name"]),
        } for unit in plan["units"])
    screen = state.get("screen") or {}
    screen_l1 = ""
    if screen.get("tab") == "planning" and screen.get("element_id"):
        screen_l1 = next((
            str(item["name"]) for item in elements
            if item["id"] == screen["element_id"] and item["level"] == "L1"
        ), "")
    intent = parse_operating_plan_intent(
        state["message"],
        units,
        [str(item["name"]) for item in elements if item["level"] == "L1"],
        screen_l1,
    ) if state.get("mode", "auto") == "auto" else None
    return intent, units


async def planner(state: ChatAgentState) -> dict[str, Any]:
    command = await agents.interpret_chat(state["project_id"], state["message"], state.get("history"),
                                          state.get("attachment_context", ""), state.get("mode", "auto"),
                                          state.get("screen"))
    return {"plan": command.model_dump()}


def retrieval(state: ChatAgentState) -> dict[str, Any]:
    elements = c4_store.list_graph(state["project_id"])["elements"]
    operating_intent, operating_units = _operating_intent(state, elements)
    if operating_intent:
        action = str(operating_intent.get("action") or "")
        unit_type = str(operating_intent.get("unit_type") or "")
        summary = (
            f"{len(operating_units)} operating-plan unit(s): "
            + ", ".join(f"{unit['unit_type']} {unit['name']}" for unit in operating_units[:8])
        )
        return {"facts": {
            "domain": "operating_plan",
            "action": action,
            "unit_type": unit_type,
            "units": operating_units[:20],
            "summary": summary,
        }}
    names = [str(element["name"]) for element in elements]
    project_name = projects_store.get_project(state["project_id"])["name"]
    status_scope = (ground_status_target(state["message"], project_name, names)
                    if not is_write_intent(state["message"]) else None)
    if status_scope and status_scope["kind"] == "unknown":
        return {"facts": {
            "element_count": 0, "by_level": {}, "proposed": 0, "names": [],
            "summary": f"No platform or C4 element named {status_scope['target']} in {project_name}",
            "requested_target": status_scope["target"], "matched": False,
        }}
    if status_scope and status_scope["kind"] == "element":
        read = ("readiness", "", str(status_scope["name"]))
    elif status_scope and status_scope["kind"] == "project":
        read = ("overview", "", "")
    else:
        read = (classify_read(state["message"], names)
                if not is_write_intent(state["message"]) else None)
    action, _, read_name = read or ("", "", "")
    if action == "describe" and read_name:
        target = next((element for element in elements if element["name"] == read_name), None)
        if target:
            parent = next((element for element in elements if element["id"] == target.get("parent_id")), None)
            children = [element for element in elements if element.get("parent_id") == target["id"]]
            summary = f"{target['level']} {target['name']} · {target['status']}"
            if parent:
                summary += f" · parent: {parent['name']}"
            summary += f" · {len(children)} child item(s)"
            return {"facts": {
                "element_count": 1,
                "by_level": {target["level"]: 1},
                "proposed": int(target["status"] == "proposed"),
                "names": [target["name"]],
                "summary": summary,
                "element": {key: target.get(key) for key in
                            ("id", "name", "level", "kind", "description", "tech", "code_path", "status")},
                "parent": parent["name"] if parent else None,
                "children": [child["name"] for child in children],
            }}
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

    elements = c4_store.list_graph(project_id)["elements"]
    operating_intent, operating_units = _operating_intent(state, elements)
    if operating_intent:
        action = str(operating_intent.get("action") or "")
        calls.append({
            "tool": "operating_plan",
            "summary": (
                f"Validated {action} against {len(operating_units)} existing tribe/squad record(s); "
                "planning invariants will be rechecked on Apply"
            ),
        })
        return {"tool_runs": {"calls": calls, "summary": "Operating-plan context loaded"}}
    names = [str(element["name"]) for element in elements]
    project_name = projects_store.get_project(project_id)["name"]
    status_scope = (ground_status_target(state["message"], project_name, names)
                    if not is_write_intent(state["message"]) else None)
    if status_scope and status_scope["kind"] == "unknown":
        calls.append({"tool": "entity_lookup",
                      "summary": f"No platform or C4 element named {status_scope['target']} in {project_name}"})
        return {"tool_runs": {"calls": calls, "summary": "Requested target was not found"}}
    if status_scope and status_scope["kind"] == "element":
        read = ("readiness", "", str(status_scope["name"]))
    elif status_scope and status_scope["kind"] == "project":
        read = ("overview", "", "")
    else:
        read = (classify_read(state["message"], names)
                if not is_write_intent(state["message"]) else None)
    action, level, read_name = read or ("", "", "")
    if action == "describe" and read_name:
        described = next((element for element in elements if element["name"] == read_name), None)
        if described:
            child_count = sum(1 for element in elements if element.get("parent_id") == described["id"])
            calls.append({
                "tool": "element_context",
                "summary": (f"Loaded {described['level']} {described['name']} from the model with "
                            f"description, architecture workspace, relations, and {child_count} child item(s)"),
            })
        return {"tool_runs": {"calls": calls, "summary": f"{len(calls)} scoped element context result(s)"}}
    if action == "readiness":
        if read_name:
            named = next((element for element in elements if element["name"] == read_name), None)
            if named and named["level"] in _READINESS:
                result = _READINESS[named["level"]](project_id, named["id"])
                calls.append({"tool": "readiness",
                              "summary": f"{named['name']} at {result['score']}% - {result['status_label']}"})
        elif level in _READINESS:
            rows = []
            for element in elements:
                if element["level"] == level:
                    result = _READINESS[level](project_id, element["id"])
                    rows.append(f"{element['name']} {result['score']}%")
            calls.append({"tool": f"{level.lower()}_readiness",
                          "summary": " | ".join(rows) or f"No {level} items"})
        return {"tool_runs": {"calls": calls, "summary": f"{len(calls)} scoped readiness result(s)"}}

    totals = c4_service.rollup(project_id)["totals"]
    stories = totals["estimated_stories"] + totals["unestimated_stories"]
    calls.append({"tool": "rollup",
                  "summary": f"{totals['estimated_stories']}/{stories} stories estimated · {totals['rolled_up_points']} points"})

    guide = workflow_service.guide(project_id)
    calls.append({"tool": "workflow_guide",
                  "summary": f"{guide['overall_pct']}% through the workflow · next: {guide['next_action']['text']}"})

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
