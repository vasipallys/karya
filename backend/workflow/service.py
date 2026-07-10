"""Deterministic cross-level workflow guide.

Assembles, for a project, the state of the top-down C4 workflow (L1 strategy →
L2 containers → L3 components → L4 implementation → estimation & roll-up) and the
next-best actions at each stage so a user can drive the app effectively. No LLM:
element counts come from the C4 graph, readiness from each level's own scorer, and
estimation progress from the deterministic roll-up.
"""

from __future__ import annotations

from statistics import mean
from typing import Any

from backend.c4 import service as c4_service
from backend.c4 import store as c4_store
from backend.l1arch import service as l1_service
from backend.l2arch import service as l2_service
from backend.l3arch import service as l3_service
from backend.l4arch import service as l4_service
from backend.projects.store import get_project

READY_THRESHOLD = 80

# level -> (label, purpose, frontend tab id, child level, readiness scorer)
_LEVELS: list[dict[str, Any]] = [
    {"level": "L1", "label": "Strategy & initiatives", "tab": "planning", "child": "L2",
     "purpose": "Frame the initiative: vision, OKRs, stakeholders, capabilities and portfolio risks.",
     "scorer": l1_service.readiness},
    {"level": "L2", "label": "Container architecture", "tab": "l2arch", "child": "L3",
     "purpose": "Break the initiative into containers with APIs, NFRs and integrations.",
     "scorer": l2_service.readiness},
    {"level": "L3", "label": "Component design", "tab": "l3arch", "child": "L4",
     "purpose": "Design each container's internal components, interfaces and dependencies.",
     "scorer": l3_service.readiness},
    {"level": "L4", "label": "Implementation detail", "tab": "l4arch", "child": None,
     "purpose": "Specify code units, tests and Definition-of-Done for each task.",
     "scorer": l4_service.readiness},
]


def _active(elements: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    return [e for e in elements if e["level"] == level and e["status"] != "proposed"]


def _level_view(project_id: str, meta: dict[str, Any], elements: list[dict[str, Any]], parent_count: int) -> dict[str, Any]:
    level = meta["level"]
    items = _active(elements, level)
    count = len(items)
    proposed = len([e for e in elements if e["level"] == level and e["status"] == "proposed"])
    scores = []
    for element in items:
        try:
            scores.append(int(meta["scorer"](project_id, element["id"])["score"]))
        except Exception:
            scores.append(0)
    avg = round(mean(scores)) if scores else 0
    ready = sum(1 for s in scores if s >= READY_THRESHOLD)
    # "expected" — the workflow reaches this level once its parent exists (L1 is always expected).
    expected = True if level == "L1" else parent_count > 0
    if count == 0:
        status = "not_started"
    elif ready == count and avg >= READY_THRESHOLD:
        status = "ready"
    else:
        status = "in_progress"

    actions: list[dict[str, Any]] = []
    if level == "L1" and count == 0:
        actions.append({"text": "Create an initiative (L1) on the C4 canvas", "tab": "canvas", "tone": "primary"})
    elif level != "L1" and parent_count == 0:
        actions.append({"text": f"Add a parent {_LEVELS[_index(level) - 1]['level']} first", "tab": _LEVELS[_index(level) - 1]["tab"], "tone": "normal"})
    elif count == 0:
        actions.append({"text": f"Add {level} elements under the level above on the canvas", "tab": "canvas", "tone": "primary"})
    else:
        if avg < READY_THRESHOLD:
            actions.append({"text": f"Open the {meta['label']} workspace and raise readiness", "tab": meta["tab"], "tone": "primary"})
            actions.append({"text": f"Use “AI generate {level}” to bootstrap, then review", "tab": meta["tab"], "tone": "normal"})
        else:
            actions.append({"text": f"{meta['label']} looks ready — review governance / traceability", "tab": meta["tab"], "tone": "done"})
        if meta["child"] and expected:
            child_count = len(_active(elements, meta["child"]))
            if child_count == 0:
                actions.append({"text": f"Decompose into {meta['child']} elements on the canvas", "tab": "canvas", "tone": "normal"})

    return {
        "level": level, "label": meta["label"], "purpose": meta["purpose"], "tab": meta["tab"],
        "count": count, "proposed": proposed, "ready": ready, "avg_readiness": avg,
        "status": status, "expected": expected, "actions": actions,
    }


def _index(level: str) -> int:
    return next(i for i, meta in enumerate(_LEVELS) if meta["level"] == level)


def guide(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    elements = c4_store.list_graph(project_id)["elements"]

    views: list[dict[str, Any]] = []
    parent_count = 1  # L1's "parent" is the project itself.
    for meta in _LEVELS:
        view = _level_view(project_id, meta, elements, parent_count)
        views.append(view)
        parent_count = view["count"]

    rollup = c4_service.rollup(project_id)["totals"]
    estimated = rollup["estimated_stories"]
    unestimated = rollup["unestimated_stories"]
    total_stories = estimated + unestimated
    est_pct = round(100 * estimated / total_stories) if total_stories else 0
    estimation = {
        "label": "Estimation & roll-up", "tab": "rollup",
        "estimated": estimated, "unestimated": unestimated, "total": total_stories,
        "pct": est_pct, "points": rollup["rolled_up_points"],
        "spikes": rollup["spikes"], "pending_splits": rollup["pending_splits"],
        "status": "not_started" if total_stories == 0 else ("ready" if unestimated == 0 else "in_progress"),
        "actions": _estimation_actions(total_stories, unestimated, rollup),
    }

    # Overall progress = mean of expected levels' readiness, folding in estimation coverage.
    expected_scores = [v["avg_readiness"] for v in views if v["expected"]]
    parts = expected_scores + ([est_pct] if total_stories else [])
    overall = round(mean(parts)) if parts else 0

    stage, next_action = _stage_and_next(views, estimation)

    return {
        "project": {"id": project["id"], "name": project["name"]},
        "levels": views,
        "estimation": estimation,
        "overall_pct": overall,
        "stage": stage,
        "next_action": next_action,
    }


def _estimation_actions(total: int, unestimated: int, rollup: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if total == 0:
        actions.append({"text": "Add L3 stories, then estimate them from the canvas", "tab": "canvas", "tone": "normal"})
    elif unestimated > 0:
        actions.append({"text": f"Estimate the {unestimated} remaining story(ies) from the canvas", "tab": "canvas", "tone": "primary"})
        actions.append({"text": "Or run a one-off Quick estimate", "tab": "quick", "tone": "normal"})
    else:
        actions.append({"text": "All stories estimated — review the roll-up", "tab": "rollup", "tone": "done"})
    if rollup.get("spikes"):
        actions.append({"text": f"{rollup['spikes']} spike(s) flagged — plan the investigation", "tab": "rollup", "tone": "normal"})
    if rollup.get("pending_splits"):
        actions.append({"text": f"{rollup['pending_splits']} story(ies) recommended for split", "tab": "rollup", "tone": "normal"})
    return actions


def _stage_and_next(views: list[dict[str, Any]], estimation: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    stage_labels = {"L1": "Strategy", "L2": "Architecture", "L3": "Component design", "L4": "Implementation"}
    for view in views:
        if view["expected"] and view["status"] != "ready" and view["actions"]:
            return stage_labels[view["level"]], {**view["actions"][0], "level": view["level"], "label": view["label"]}
    if estimation["status"] != "ready" and estimation["actions"]:
        return "Estimation & roll-up", {**estimation["actions"][0], "level": "estimate", "label": estimation["label"]}
    return "Complete", {"text": "All levels ready and stories estimated — keep governance current.", "tab": "rollup", "tone": "done", "level": "done", "label": "Done"}
