"""Dispatch an interpreted chat command.

Reads (overview / list / describe / readiness / report) run immediately against the
deterministic services. Writes (create / update / delete element) are returned as
a *proposal* — the caller confirms, and `apply` re-resolves the names and performs
the change through the C4 store (so the same RBAC and level rules apply).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from backend.ai.schemas import ChatCommand
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate, C4ElementUpdate, C4RelationCreate
from backend.l1arch import service as l1_service
from backend.l2arch import service as l2_service
from backend.l3arch import service as l3_service
from backend.l4arch import service as l4_service
from backend.l1arch import store as l1_store
from backend.l2arch import store as l2_store
from backend.l3arch import store as l3_store
from backend.l4arch import store as l4_store
from backend.planning import store as planning_store
from backend.planning.models import AgileUnitCreate, AgileUnitUpdate, TeamMemberCreate, TeamMemberUpdate
from backend.resources import store as resources_store
from backend.workflow import service as workflow_service

_READINESS = {"L1": l1_service.readiness, "L2": l2_service.readiness, "L3": l3_service.readiness, "L4": l4_service.readiness}
_CONTEXT_LOADERS = {
    "L1": l1_store.get_baseline,
    "L2": l2_store.get_workspace,
    "L3": l3_store.get_workspace,
    "L4": l4_store.get_workspace,
}
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


def _norm_key(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _resolve_l1_scope(project_id: str, scope: str) -> dict[str, Any]:
    """Resolve the L1 that owns an operating plan without guessing."""
    candidates = [
        element for element in _elements(project_id)
        if element["level"] == "L1"
        and "person" not in str(element.get("kind") or "").lower()
        and "external" not in str(element.get("kind") or "").lower()
    ]
    if scope.strip():
        key = _norm_key(scope)
        exact = [element for element in candidates if _norm_key(element["name"]) == key]
        if not exact:
            # Users often append/remove "system", "platform", or "initiative".
            def without_suffix(value: str) -> str:
                normalized = _norm_key(value)
                for suffix in ("system", "platform", "initiative"):
                    if normalized.endswith(suffix):
                        normalized = normalized[:-len(suffix)]
                        break
                return normalized

            exact = [
                element for element in candidates
                if without_suffix(element["name"]) == without_suffix(scope)
            ]
        if len(exact) == 1:
            return exact[0]
        if not exact:
            raise ChatError(f"I couldn't find an L1 operating plan for “{scope}”.")
        raise ChatError(f"“{scope}” matches multiple L1 plans. Please use the exact initiative name.")
    if not candidates:
        raise ChatError("Create an L1 initiative before adding tribes or squads.")
    if len(candidates) > 1:
        names = ", ".join(element["name"] for element in candidates[:6])
        raise ChatError(f"Which L1 operating plan should I use? Options: {names}.")
    return candidates[0]


def _planning_units(project_id: str) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for l1 in [element for element in _elements(project_id) if element["level"] == "L1"]:
        plan = planning_store.get_plan(project_id, l1["id"])
        for unit in plan["units"]:
            units.append({**unit, "l1_name": l1["name"], "l1_element_id": l1["id"]})
    return units


def _find_unit(
    project_id: str,
    name: str,
    scope: str = "",
    unit_type: str = "",
) -> dict[str, Any]:
    if not name.strip():
        raise ChatError("Which tribe or squad? Please name it.")
    units = _planning_units(project_id)
    if scope.strip():
        l1 = _resolve_l1_scope(project_id, scope)
        units = [unit for unit in units if unit["l1_element_id"] == l1["id"]]
    if unit_type in {"tribe", "squad"}:
        units = [unit for unit in units if unit["unit_type"] == unit_type]
    key = _norm_key(name)
    matches = [unit for unit in units if _norm_key(unit["name"]) == key]
    if not matches:
        near = [unit["name"] for unit in units if key and (key in _norm_key(unit["name"]) or _norm_key(unit["name"]) in key)]
        hint = f" Did you mean: {', '.join(near[:5])}?" if near else ""
        raise ChatError(f"I couldn't find a tribe or squad named “{name}”.{hint}")
    if len(matches) > 1:
        plans = ", ".join(f"{unit['name']} ({unit['l1_name']})" for unit in matches[:6])
        raise ChatError(f"“{name}” exists in multiple L1 plans. Specify the initiative: {plans}.")
    return matches[0]


def _resolve_resource(name: str) -> dict[str, Any] | None:
    key = _norm_key(name)
    exact = [
        person for person in resources_store.list_staff()
        if _norm_key(str(person.get("staff_name") or "")) == key
        or _norm_key(str(person.get("staff_code") or "")) == key
    ]
    if len(exact) > 1:
        raise ChatError(f"Multiple people match “{name}”. Use the staff code.")
    return exact[0] if exact else None


def _find_member(unit: dict[str, Any], name: str) -> dict[str, Any]:
    key = _norm_key(name)
    matches = [
        member for member in unit.get("members", [])
        if _norm_key(str(member.get("name") or "")) == key
    ]
    if not matches:
        raise ChatError(f"I couldn't find “{name}” in {unit['unit_type']} “{unit['name']}”.")
    if len(matches) > 1:
        raise ChatError(f"Multiple team members are named “{name}” in “{unit['name']}”.")
    return matches[0]


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
    if action == "describe":
        return _describe(project_id, command)
    if action == "readiness":
        return _readiness(project_id, command)
    if action == "report":
        return _report(project_id, command)
    if action == "list_agile_units":
        return _list_agile_units(project_id, command)
    if action == "web_search":
        return _web_search(command)
    if action in ("answer", "code", "image", "document"):
        return {"reply": command.reply or "I need a little more detail to answer that.", "action": action,
                "data": None, "mutation": None}
    if action in (
        "create_element", "update_element", "delete_element", "create_relation",
        "create_agile_unit", "update_agile_unit", "delete_agile_unit",
        "assign_team_member", "update_team_member", "remove_team_member",
    ):
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
        "• “create a tribe for this initiative” or “create Checkout Squad under Growth Tribe”\n"
        "• “add Priya to Checkout Squad as QA at 50%” or “list tribes and squads”\n"
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
    # A status filter ("pending"→proposed) overrides the default of hiding proposals.
    wanted = command.status.strip().lower()
    if wanted:
        items = [e for e in items if e["status"].lower() == wanted]
    else:
        items = [e for e in items if e["status"] != "proposed"] or items
    rows = [{"id": e["id"], "level": e["level"], "name": e["name"], "status": e["status"]} for e in items]
    scope = level or "all levels"
    label = f"{wanted} " if wanted else ""
    reply = (f"You have {len(rows)} {label}element(s) at {scope}." if rows
             else f"No {label}elements found at {scope}.")
    return {"reply": reply, "action": "list", "data": {"level": level, "status": wanted, "items": rows}, "mutation": None}


def _list_agile_units(project_id: str, command: ChatCommand) -> dict[str, Any]:
    units = _planning_units(project_id)
    scope_name = ""
    if command.scope.strip():
        l1 = _resolve_l1_scope(project_id, command.scope)
        scope_name = l1["name"]
        units = [unit for unit in units if unit["l1_element_id"] == l1["id"]]
    unit_type = command.unit_type.strip().lower()
    if unit_type in {"tribe", "squad"}:
        units = [unit for unit in units if unit["unit_type"] == unit_type]
    rows = [{
        "id": unit["id"],
        "name": unit["name"],
        "unit_type": unit["unit_type"],
        "l1_name": unit["l1_name"],
        "parent_unit_id": unit.get("parent_unit_id"),
        "lead_name": unit.get("lead_name") or "",
        "members": len(unit.get("members") or []),
    } for unit in units]
    noun = f"{unit_type}s" if unit_type else "tribes and squads"
    where = f" in **{scope_name}**" if scope_name else ""
    reply = f"Found **{len(rows)}** {noun}{where}."
    return {
        "reply": reply,
        "action": "list_agile_units",
        "data": {"scope": scope_name, "unit_type": unit_type, "items": rows},
        "mutation": None,
    }


def _describe(project_id: str, command: ChatCommand) -> dict[str, Any]:
    """Describe one element from persisted C4 and level-workspace context."""
    element = _find(project_id, command.name)
    graph = c4_store.list_graph(project_id)
    by_id = {item["id"]: item for item in graph["elements"]}
    parent = by_id.get(element.get("parent_id"))
    children = [
        {"id": item["id"], "name": item["name"], "level": item["level"], "status": item["status"]}
        for item in graph["elements"] if item.get("parent_id") == element["id"]
    ]

    relations = []
    for relation in graph["relations"]:
        if element["id"] not in {relation["source_id"], relation["target_id"]}:
            continue
        source = by_id.get(relation["source_id"], {})
        target = by_id.get(relation["target_id"], {})
        relations.append({
            "source": source.get("name", relation["source_id"]),
            "target": target.get("name", relation["target_id"]),
            "label": relation.get("label") or "uses",
            "kind": relation.get("kind") or "sync",
        })

    workspace = _CONTEXT_LOADERS[element["level"]](project_id, element["id"])
    readiness = workspace.get("readiness") or _READINESS[element["level"]](project_id, element["id"])
    arch = workspace.get("arch") or {}
    vision = workspace.get("vision") or {}
    architecture_summary = str(arch.get("summary") or "").strip()
    vision_statement = str(vision.get("vision_statement") or "").strip()
    description = str(element.get("description") or "").strip()

    collection_keys = {
        "L1": ("okrs", "stakeholders", "capabilities", "risks"),
        "L2": ("containers", "apis", "nfrs", "integrations"),
        "L3": ("components", "interfaces", "dependencies", "concerns"),
        "L4": ("code_units", "test_cases", "checklist"),
    }[element["level"]]
    artifact_counts = {key: len(workspace.get(key) or []) for key in collection_keys}

    level_label = {"L1": "initiative", "L2": "container", "L3": "component", "L4": "task"}[element["level"]]
    location = f" under **{parent['name']}**" if parent else ""
    lines = [
        f"**{element['name']}** is an **{element['level']} {level_label}**{location}. "
        f"Its model status is **{element['status']}**.",
    ]
    if description:
        lines.append(description)
    elif architecture_summary:
        lines.append(architecture_summary)
    elif vision_statement:
        lines.append(vision_statement)
    else:
        lines.append("No narrative description has been recorded for this element yet.")
    if architecture_summary and architecture_summary != description:
        lines.append(f"**Architecture summary:** {architecture_summary}")
    if vision_statement and vision_statement != description:
        lines.append(f"**Vision:** {vision_statement}")
    if element.get("tech"):
        lines.append(f"**Technology:** {element['tech']}")
    if element.get("code_path"):
        lines.append(f"**Code path:** `{element['code_path']}`")
    if children:
        child_names = ", ".join(f"{child['name']} ({child['status']})" for child in children[:12])
        lines.append(f"**Children:** {child_names}")
    populated = [f"{count} {key.replace('_', ' ')}" for key, count in artifact_counts.items() if count]
    if populated:
        lines.append("**Architecture records:** " + ", ".join(populated))
    if relations:
        relation_text = "; ".join(
            f"{item['source']} -[{item['label']}]-> {item['target']}" for item in relations[:12]
        )
        lines.append(f"**Connections:** {relation_text}")
    lines.append(f"**Readiness:** {readiness['score']}% - {readiness['status_label']}")

    data = {
        "element": {key: element.get(key) for key in
                    ("id", "name", "level", "kind", "description", "tech", "code_path", "status")},
        "parent": ({"id": parent["id"], "name": parent["name"], "level": parent["level"]} if parent else None),
        "children": children,
        "relations": relations,
        "architecture_summary": architecture_summary,
        "vision_statement": vision_statement,
        "artifact_counts": artifact_counts,
        "readiness": {"score": readiness["score"], "status_label": readiness["status_label"]},
    }
    return {"reply": "\n\n".join(lines), "action": "describe", "data": data, "mutation": None}


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
    # Level-wide requests return each element's own deterministic score. The
    # aggregate alone cannot answer "status of each L1 item".
    level = _norm_level(command.level)
    if not level:
        raise ChatError("Tell me an element name or a level (L1–L4) to check readiness for.")
    scorer = _READINESS[level]
    elements = [element for element in _elements(project_id) if element["level"] == level]
    rows = []
    for element in elements:
        result = scorer(project_id, element["id"])
        rows.append({
            "id": element["id"], "name": element["name"], "level": level,
            "status": element["status"], "score": int(result["score"]),
            "status_label": result["status_label"],
        })
    rows.sort(key=lambda item: item["name"].lower())
    average = round(sum(item["score"] for item in rows) / len(rows)) if rows else 0
    ready = sum(1 for item in rows if item["score"] >= workflow_service.READY_THRESHOLD)
    reply = (f"{level} readiness by item averages **{average}%** ({ready}/{len(rows)} ready)."
             if rows else f"No {level} elements were found.")
    data = {"level": level, "count": len(rows), "ready": ready, "avg_readiness": average, "items": rows}
    return {"reply": reply, "action": "readiness", "data": data, "mutation": None}


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
    if command.action == "create_agile_unit":
        unit_type = command.unit_type.strip().lower()
        if unit_type not in {"tribe", "squad"}:
            raise ChatError("Should I create a tribe or a squad?")
        if not command.name.strip():
            raise ChatError(f"What should the new {unit_type} be called?")
        l1 = _resolve_l1_scope(project_id, command.scope)
        existing = [
            unit for unit in _planning_units(project_id)
            if unit["l1_element_id"] == l1["id"]
            and unit["unit_type"] == unit_type
            and _norm_key(unit["name"]) == _norm_key(command.name)
        ]
        if existing:
            raise ChatError(f"A {unit_type} named “{existing[0]['name']}” already exists in {l1['name']}.")
        parent = None
        if unit_type == "squad":
            if command.parent.strip():
                parent = _find_unit(project_id, command.parent, l1["name"], "tribe")
            else:
                tribes = [
                    unit for unit in _planning_units(project_id)
                    if unit["l1_element_id"] == l1["id"] and unit["unit_type"] == "tribe"
                ]
                if len(tribes) == 1:
                    parent = tribes[0]
                elif len(tribes) > 1:
                    names = ", ".join(unit["name"] for unit in tribes[:6])
                    raise ChatError(f"Which tribe should own this squad? Options: {names}.")
        summary = f"Create {unit_type} “{command.name.strip()}” in “{l1['name']}”"
        if parent:
            summary += f" under “{parent['name']}”"
        mutation = {
            "action": "create_agile_unit",
            "scope": l1["name"],
            "unit_type": unit_type,
            "name": command.name.strip(),
            "parent": parent["name"] if parent else "",
            "mission": command.description.strip(),
            "lead_name": command.lead_name.strip(),
            "capacity_fte": command.capacity_fte if command.capacity_fte is not None else 0,
            "target_velocity": command.target_velocity if command.target_velocity is not None else 0,
        }
    elif command.action == "update_agile_unit":
        unit = _find_unit(project_id, command.name, command.scope, command.unit_type)
        changes = []
        if command.new_name.strip():
            changes.append(f"rename to “{command.new_name.strip()}”")
        if command.description.strip():
            changes.append("update mission")
        if command.lead_name.strip():
            changes.append(f"set lead to {command.lead_name.strip()}")
        if command.capacity_fte is not None:
            changes.append(f"set capacity to {command.capacity_fte:g} FTE")
        if command.target_velocity is not None:
            changes.append(f"set target velocity to {command.target_velocity:g}")
        if not changes:
            raise ChatError("What should I change on that tribe or squad?")
        summary = f"Update {unit['unit_type']} “{unit['name']}”: " + "; ".join(changes)
        mutation = {
            "action": "update_agile_unit",
            "scope": unit["l1_name"],
            "unit_type": unit["unit_type"],
            "name": unit["name"],
            "new_name": command.new_name.strip(),
            "mission": command.description.strip(),
            "lead_name": command.lead_name.strip(),
            "capacity_fte": command.capacity_fte,
            "target_velocity": command.target_velocity,
        }
    elif command.action == "delete_agile_unit":
        unit = _find_unit(project_id, command.name, command.scope, command.unit_type)
        impact = " Its squads become independent and its members are removed." if unit["unit_type"] == "tribe" else " Its members are removed."
        summary = f"Delete {unit['unit_type']} “{unit['name']}” from “{unit['l1_name']}”.{impact}"
        mutation = {
            "action": "delete_agile_unit",
            "scope": unit["l1_name"],
            "unit_type": unit["unit_type"],
            "name": unit["name"],
        }
    elif command.action == "assign_team_member":
        unit = _find_unit(project_id, command.parent, command.scope)
        if not command.name.strip():
            raise ChatError("Who should I add to the team?")
        person = _resolve_resource(command.name)
        display_name = str(person.get("staff_name")) if person else command.name.strip()
        allocation = command.allocation_percent if command.allocation_percent is not None else 100
        directory_note = "" if person else " as an unlinked external/contract team member"
        summary = (
            f"Add {display_name} to {unit['unit_type']} “{unit['name']}” at "
            f"{allocation:g}% allocation{directory_note}"
        )
        if command.role.strip():
            summary += f" as {command.role.strip()}"
        mutation = {
            "action": "assign_team_member",
            "scope": unit["l1_name"],
            "unit_type": unit["unit_type"],
            "unit": unit["name"],
            "name": display_name,
            "resource_staff_id": person["id"] if person else None,
            "role": command.role.strip(),
            "allocation_percent": allocation,
            "monthly_cost": command.monthly_cost if command.monthly_cost is not None else 0,
        }
    elif command.action == "update_team_member":
        unit = _find_unit(project_id, command.parent, command.scope)
        member = _find_member(unit, command.name)
        changes = []
        if command.role.strip():
            changes.append(f"set role to {command.role.strip()}")
        if command.allocation_percent is not None:
            changes.append(f"set allocation to {command.allocation_percent:g}%")
        if command.monthly_cost is not None:
            changes.append(f"set monthly cost to {command.monthly_cost:g}")
        if not changes:
            raise ChatError("What should I change for that team member?")
        summary = f"Update {member['name']} in “{unit['name']}”: " + "; ".join(changes)
        mutation = {
            "action": "update_team_member",
            "scope": unit["l1_name"],
            "unit_type": unit["unit_type"],
            "unit": unit["name"],
            "name": member["name"],
            "role": command.role.strip(),
            "allocation_percent": command.allocation_percent,
            "monthly_cost": command.monthly_cost,
        }
    elif command.action == "remove_team_member":
        unit = _find_unit(project_id, command.parent, command.scope)
        member = _find_member(unit, command.name)
        summary = f"Remove {member['name']} from {unit['unit_type']} “{unit['name']}”"
        mutation = {
            "action": "remove_team_member",
            "scope": unit["l1_name"],
            "unit_type": unit["unit_type"],
            "unit": unit["name"],
            "name": member["name"],
        }
    elif command.action == "create_element":
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
    if action == "create_agile_unit":
        unit_type = str(mutation.get("unit_type") or "").lower()
        if unit_type not in {"tribe", "squad"}:
            raise ChatError("Invalid agile unit type.")
        name = str(mutation.get("name") or "").strip()
        if not name:
            raise ChatError("The tribe or squad name is required.")
        l1 = _resolve_l1_scope(project_id, str(mutation.get("scope") or ""))
        if any(
            unit["l1_element_id"] == l1["id"]
            and unit["unit_type"] == unit_type
            and _norm_key(unit["name"]) == _norm_key(name)
            for unit in _planning_units(project_id)
        ):
            raise ChatError(f"A {unit_type} named “{name}” already exists in {l1['name']}.")
        parent = None
        if unit_type == "squad" and str(mutation.get("parent") or "").strip():
            parent = _find_unit(project_id, str(mutation["parent"]), l1["name"], "tribe")
        unit = planning_store.create_unit(project_id, l1["id"], AgileUnitCreate(
            unit_type=unit_type,
            name=name,
            parent_unit_id=parent["id"] if parent else None,
            mission=str(mutation.get("mission") or ""),
            lead_name=str(mutation.get("lead_name") or ""),
            capacity_fte=float(mutation.get("capacity_fte") or 0),
            target_velocity=float(mutation.get("target_velocity") or 0),
        ))
        return {
            "reply": f"Created {unit_type} “{unit['name']}” in “{l1['name']}”.",
            "result": {
                "id": unit["id"], "name": unit["name"], "unit_type": unit_type,
                "workspace": "planning", "l1_id": l1["id"],
            },
        }
    if action == "update_agile_unit":
        unit = _find_unit(
            project_id,
            str(mutation.get("name") or ""),
            str(mutation.get("scope") or ""),
            str(mutation.get("unit_type") or ""),
        )
        values: dict[str, Any] = {}
        if str(mutation.get("new_name") or "").strip():
            values["name"] = str(mutation["new_name"]).strip()
        if str(mutation.get("mission") or "").strip():
            values["mission"] = str(mutation["mission"]).strip()
        if str(mutation.get("lead_name") or "").strip():
            values["lead_name"] = str(mutation["lead_name"]).strip()
        if mutation.get("capacity_fte") is not None:
            values["capacity_fte"] = float(mutation["capacity_fte"])
        if mutation.get("target_velocity") is not None:
            values["target_velocity"] = float(mutation["target_velocity"])
        if not values:
            raise ChatError("No tribe or squad changes were supplied.")
        updated = planning_store.update_unit(project_id, unit["id"], AgileUnitUpdate(**values))
        return {
            "reply": f"Updated {unit['unit_type']} “{updated['name']}”.",
            "result": {
                "id": updated["id"], "name": updated["name"], "unit_type": unit["unit_type"],
                "workspace": "planning", "l1_id": unit["l1_element_id"],
            },
        }
    if action == "delete_agile_unit":
        unit = _find_unit(
            project_id,
            str(mutation.get("name") or ""),
            str(mutation.get("scope") or ""),
            str(mutation.get("unit_type") or ""),
        )
        planning_store.delete_unit(project_id, unit["id"])
        return {
            "reply": f"Deleted {unit['unit_type']} “{unit['name']}”.",
            "result": {"id": unit["id"], "name": unit["name"], "unit_type": unit["unit_type"]},
        }
    if action == "assign_team_member":
        unit = _find_unit(
            project_id,
            str(mutation.get("unit") or ""),
            str(mutation.get("scope") or ""),
            str(mutation.get("unit_type") or ""),
        )
        name = str(mutation.get("name") or "").strip()
        if not name:
            raise ChatError("The team member name is required.")
        person = _resolve_resource(name)
        member = planning_store.create_member(project_id, unit["id"], TeamMemberCreate(
            name=str(person.get("staff_name")) if person else name,
            resource_staff_id=person["id"] if person else None,
            role=str(mutation.get("role") or ""),
            allocation_percent=float(mutation.get("allocation_percent", 100)),
            monthly_cost=float(mutation.get("monthly_cost") or 0),
        ))
        return {
            "reply": f"Added {member['name']} to {unit['unit_type']} “{unit['name']}”.",
            "result": {
                "id": member["id"], "name": member["name"], "unit_type": unit["unit_type"],
                "unit_name": unit["name"], "workspace": "planning", "l1_id": unit["l1_element_id"],
            },
        }
    if action == "update_team_member":
        unit = _find_unit(
            project_id,
            str(mutation.get("unit") or ""),
            str(mutation.get("scope") or ""),
            str(mutation.get("unit_type") or ""),
        )
        member = _find_member(unit, str(mutation.get("name") or ""))
        values: dict[str, Any] = {}
        if str(mutation.get("role") or "").strip():
            values["role"] = str(mutation["role"]).strip()
        if mutation.get("allocation_percent") is not None:
            values["allocation_percent"] = float(mutation["allocation_percent"])
        if mutation.get("monthly_cost") is not None:
            values["monthly_cost"] = float(mutation["monthly_cost"])
        if not values:
            raise ChatError("No team-member changes were supplied.")
        updated = planning_store.update_member(project_id, member["id"], TeamMemberUpdate(**values))
        return {
            "reply": f"Updated {updated['name']} in “{unit['name']}”.",
            "result": {
                "id": updated["id"], "name": updated["name"], "unit_type": unit["unit_type"],
                "unit_name": unit["name"], "workspace": "planning", "l1_id": unit["l1_element_id"],
            },
        }
    if action == "remove_team_member":
        unit = _find_unit(
            project_id,
            str(mutation.get("unit") or ""),
            str(mutation.get("scope") or ""),
            str(mutation.get("unit_type") or ""),
        )
        member = _find_member(unit, str(mutation.get("name") or ""))
        planning_store.delete_member(project_id, member["id"])
        return {
            "reply": f"Removed {member['name']} from “{unit['name']}”.",
            "result": {
                "id": member["id"], "name": member["name"], "unit_type": unit["unit_type"],
                "unit_name": unit["name"], "workspace": "planning", "l1_id": unit["l1_element_id"],
            },
        }
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
