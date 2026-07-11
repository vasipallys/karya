"""Dispatch an interpreted chat command.

Reads (overview / list / readiness / report) run immediately against the
deterministic services. Writes (create / update / delete element) are returned as
a *proposal* — the caller confirms, and `apply` re-resolves the names and performs
the change through the C4 store (so the same RBAC and level rules apply).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from backend.ai.schemas import ChatCommand
from backend.c4 import service as c4_service
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate, C4ElementUpdate, C4RelationCreate
from backend.l1arch import service as l1_service
from backend.l2arch import service as l2_service
from backend.l3arch import service as l3_service
from backend.l4arch import service as l4_service
from backend.workflow import service as workflow_service

_READINESS = {"L1": l1_service.readiness, "L2": l2_service.readiness, "L3": l3_service.readiness, "L4": l4_service.readiness}
_LEVELS = ("L1", "L2", "L3", "L4")


class ChatError(ValueError):
    pass


def _elements(project_id: str) -> list[dict[str, Any]]:
    return c4_store.list_graph(project_id)["elements"]


def _find(project_id: str, name: str) -> dict[str, Any]:
    if not name.strip():
        raise ChatError("Which element? Please name it.")
    matches = [e for e in _elements(project_id) if e["name"].lower() == name.strip().lower()]
    if not matches:
        near = [e["name"] for e in _elements(project_id) if name.strip().lower() in e["name"].lower()]
        hint = f" Did you mean: {', '.join(near[:5])}?" if near else ""
        raise ChatError(f"I couldn't find an element named “{name}”.{hint}")
    if len(matches) > 1:
        raise ChatError(f"“{name}” matches {len(matches)} elements — please be more specific.")
    return matches[0]


def _norm_level(level: str) -> str:
    lvl = (level or "").strip().upper()
    return lvl if lvl in _LEVELS else ""


def _resolve_parent(project_id: str, level: str, parent_name: str) -> dict[str, Any] | None:
    """Resolve (or infer) the parent for a new element so the C4 level rule
    (parent exactly one level up) always holds — a chat request like
    “create an L2 container called payments” must never produce an orphan
    floating on the system landscape."""
    expected = _LEVELS[_LEVELS.index(level) - 1] if level != "L1" else None
    if parent_name.strip():
        parent = _find(project_id, parent_name)
        if expected is None:
            raise ChatError("L1 elements are top-level — they can't be created under a parent.")
        if parent["level"] != expected:
            raise ChatError(f"“{parent['name']}” is {parent['level']} — a {level} element needs an {expected} parent.")
        return parent
    if expected is None:
        return None
    candidates = [e for e in _elements(project_id) if e["level"] == expected and e["status"] != "proposed"]
    if level == "L2":
        # An L2 container lives inside a *system*, not a person or external system.
        systems = [e for e in candidates if "person" not in e["kind"].lower() and "external" not in e["kind"].lower()]
        candidates = systems or candidates
    if not candidates:
        raise ChatError(f"A {level} element needs an {expected} parent — create the {expected} first.")
    if len(candidates) > 1:
        names = ", ".join(e["name"] for e in candidates[:5])
        raise ChatError(f"Which {expected} should it live under? Say e.g. “… under {candidates[0]['name']}”. Options: {names}.")
    return candidates[0]


# ---- read dispatch ------------------------------------------------------

def dispatch(project_id: str, command: ChatCommand) -> dict[str, Any]:
    action = command.action
    if action == "overview":
        return _overview(project_id, command)
    if action == "list":
        return _list(project_id, command)
    if action == "readiness":
        return _readiness(project_id, command)
    if action == "report":
        return _report(project_id, command)
    if action == "web_search":
        return _web_search(command)
    if action in ("answer", "code"):
        return {"reply": command.reply or "I need a little more detail to answer that.", "action": action,
                "data": None, "mutation": None}
    if action in ("create_element", "update_element", "delete_element", "create_relation"):
        return _propose(project_id, command)
    return {"reply": command.reply or _help_text(), "action": "help", "data": None, "mutation": None}


def _web_search(command: ChatCommand) -> dict[str, Any]:
    """Lightweight public web research with explicit citations and hard safety limits.

    DuckDuckGo's HTML endpoint needs no stored credential. Failure is returned as a
    useful answer rather than silently fabricating current information.
    """
    query = (command.description or command.reply).strip()[:500]
    if not query:
        raise ChatError("What should I search the web for?")
    try:
        response = httpx.get(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            headers={"User-Agent": "Karya/2.0 research assistant"}, timeout=10.0, follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {"reply": f"I couldn't reach web search just now: {exc}. Try again or check network access.",
                "action": "web_search", "data": {"query": query, "sources": []}, "mutation": None}
    import html
    import re
    matches = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', response.text, re.I | re.S)
    sources = []
    for url, title in matches[:6]:
        clean_title = re.sub(r"<[^>]+>", "", html.unescape(title)).strip()
        clean_url = html.unescape(url)
        if clean_url.startswith("//"):
            clean_url = "https:" + clean_url
        parsed = urlparse(clean_url)
        if "duckduckgo.com" in parsed.netloc:
            clean_url = unquote(parse_qs(parsed.query).get("uddg", [clean_url])[0])
        if clean_title and clean_url.startswith(("http://", "https://")):
            sources.append({"title": clean_title, "url": clean_url})
    if not sources:
        return {"reply": f"No reliable web results were returned for **{query}**.", "action": "web_search",
                "data": {"query": query, "sources": []}, "mutation": None}
    lines = [f"Web results for **{query}**:"] + [f"- [{s['title']}]({s['url']})" for s in sources]
    return {"reply": "\n".join(lines), "action": "web_search", "data": {"query": query, "sources": sources}, "mutation": None}


def _help_text() -> str:
    return (
        "I can help across the whole model. Try:\n"
        "• “what's the project status?” or “what should I do next?”\n"
        "• “list L2 containers” · “readiness of onboarding-web”\n"
        "• “create an L2 container called payments under Digital banking”\n"
        "• “rename pay-api to payments-api” · “set onboarding-web status to reviewed”\n"
        "• “delete the L4 task X”. Changes are proposed first — you confirm before anything is saved."
    )


def _overview(project_id: str, command: ChatCommand) -> dict[str, Any]:
    guide = workflow_service.guide(project_id)
    na = guide["next_action"]
    reply = (
        f"{guide['project']['name']} is **{guide['overall_pct']}%** through the workflow (stage: {guide['stage']}). "
        f"Next best step: {na['text']}."
    )
    return {"reply": reply, "action": "overview", "data": guide, "mutation": None}


def _list(project_id: str, command: ChatCommand) -> dict[str, Any]:
    level = _norm_level(command.level)
    items = [e for e in _elements(project_id) if not level or e["level"] == level]
    items = [e for e in items if e["status"] != "proposed"] or items
    rows = [{"id": e["id"], "level": e["level"], "name": e["name"], "status": e["status"]} for e in items]
    scope = level or "all levels"
    reply = f"You have {len(rows)} element(s) at {scope}." if rows else f"No elements found at {scope} yet."
    return {"reply": reply, "action": "list", "data": {"level": level, "items": rows}, "mutation": None}


def _readiness(project_id: str, command: ChatCommand) -> dict[str, Any]:
    if command.name.strip():
        element = _find(project_id, command.name)
        scorer = _READINESS.get(element["level"])
        if not scorer:
            raise ChatError(f"“{element['name']}” is an {element['level']} element and has no readiness score.")
        result = scorer(project_id, element["id"])
        reply = f"**{element['name']}** ({element['level']}) is at **{result['score']}%** — {result['status_label']}."
        data = {"id": element["id"], "name": element["name"], "level": element["level"], **result}
        return {"reply": reply, "action": "readiness", "data": data, "mutation": None}
    # level-wide summary from the workflow guide
    guide = workflow_service.guide(project_id)
    level = _norm_level(command.level)
    view = next((v for v in guide["levels"] if v["level"] == level), None)
    if not view:
        raise ChatError("Tell me an element name or a level (L1–L4) to check readiness for.")
    reply = f"{level} average readiness is **{view['avg_readiness']}%** ({view['ready']}/{view['count']} ready)."
    return {"reply": reply, "action": "readiness", "data": view, "mutation": None}


def _report(project_id: str, command: ChatCommand) -> dict[str, Any]:
    guide = workflow_service.guide(project_id)
    est = guide["estimation"]
    reply = (
        f"Roll-up: {est['estimated']}/{est['total']} stories estimated ({est['pct']}%), "
        f"{est['points']} points, {est['spikes']} spike(s), {est['pending_splits']} split(s) pending. "
        f"Next: {guide['next_action']['text']}."
    )
    return {"reply": reply, "action": "report", "data": {"estimation": est, "next_action": guide["next_action"], "stage": guide["stage"]}, "mutation": None}


# ---- write proposals ----------------------------------------------------

def _propose(project_id: str, command: ChatCommand) -> dict[str, Any]:
    if command.action == "create_element":
        level = _norm_level(command.level)
        if not level:
            raise ChatError("Which level (L1–L4) should I create?")
        if not command.name.strip():
            raise ChatError("What should the new element be called?")
        parent = _resolve_parent(project_id, level, command.parent)
        target = _find(project_id, command.target) if command.target.strip() else None
        label = command.label.strip() or "uses"
        summary = f"Create {level} “{command.name.strip()}”" + (f" under “{parent['name']}”" if parent else "")
        if target:
            summary += f", {label} “{target['name']}”"
        mutation = {"action": "create_element", "level": level, "name": command.name.strip(),
                    "parent": parent["name"] if parent else "",
                    "target": target["name"] if target else "", "label": label if target else ""}
    elif command.action == "update_element":
        element = _find(project_id, command.name)
        changes = []
        if command.new_name.strip():
            changes.append(f"rename to “{command.new_name.strip()}”")
        if command.status.strip():
            changes.append(f"set status to {command.status.strip()}")
        if command.description.strip():
            changes.append("update description")
        if not changes:
            raise ChatError("What should I change? Try a new name, status, or description.")
        summary = f"Update “{element['name']}”: " + "; ".join(changes)
        mutation = {"action": "update_element", "name": element["name"], "new_name": command.new_name.strip(),
                    "status": command.status.strip(), "description": command.description.strip()}
    elif command.action == "create_relation":
        source = _find(project_id, command.name)
        target = _find(project_id, command.target)
        label = command.label.strip() or "uses"
        summary = f"Connect “{source['name']}” → “{target['name']}” ({label})"
        mutation = {"action": "create_relation", "name": source["name"], "target": target["name"], "label": label}
    else:  # delete_element
        element = _find(project_id, command.name)
        summary = f"Delete {element['level']} “{element['name']}” (and its children)"
        mutation = {"action": "delete_element", "name": element["name"]}
    mutation["summary"] = summary
    # Always reply with the deterministic summary for writes — it names the
    # resolved parent, which the model's own phrasing may omit.
    reply = f"{summary}? Review and Apply to confirm."
    return {"reply": reply, "action": command.action, "data": None, "mutation": mutation}


# ---- apply a confirmed write --------------------------------------------

def apply(project_id: str, mutation: dict[str, Any]) -> dict[str, Any]:
    action = mutation.get("action")
    if action == "create_element":
        parent = _resolve_parent(project_id, mutation["level"], mutation.get("parent", ""))
        target = _find(project_id, mutation["target"]) if mutation.get("target") else None
        element = c4_store.create_element(project_id, C4ElementCreate(
            level=mutation["level"], name=mutation["name"], parent_id=parent["id"] if parent else None,
        ))
        reply = f"Created {element['level']} “{element['name']}”."
        if target:
            c4_store.create_relation(project_id, C4RelationCreate(
                source_id=element["id"], target_id=target["id"], label=mutation.get("label") or "uses",
            ))
            reply = f"Created {element['level']} “{element['name']}” and connected it to “{target['name']}”."
        return {"reply": reply, "result": {"id": element["id"], "level": element["level"], "name": element["name"]}}
    if action == "create_relation":
        source = _find(project_id, mutation["name"])
        target = _find(project_id, mutation["target"])
        relation = c4_store.create_relation(project_id, C4RelationCreate(
            source_id=source["id"], target_id=target["id"], label=mutation.get("label") or "uses",
        ))
        return {"reply": f"Connected “{source['name']}” → “{target['name']}”.", "result": {"id": relation["id"], "source": source["name"], "target": target["name"]}}
    if action == "update_element":
        element = _find(project_id, mutation["name"])
        payload = C4ElementUpdate(
            name=mutation["new_name"] or None,
            status=mutation.get("status") or None,
            description=mutation.get("description") or None,
        )
        updated = c4_store.update_element(project_id, element["id"], payload)
        return {"reply": f"Updated “{updated['name']}”.", "result": {"id": updated["id"], "name": updated["name"], "status": updated["status"]}}
    if action == "delete_element":
        element = _find(project_id, mutation["name"])
        c4_store.delete_element(project_id, element["id"])
        return {"reply": f"Deleted “{element['name']}”.", "result": {"id": element["id"], "name": element["name"]}}
    raise ChatError(f"Don't know how to apply '{action}'.")
