"""The four agentic services. Each gathers context, prompts the LLM through the
factory's structured output, and returns a *proposal* — nothing is persisted here."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.ai.masking import mask_pii
from backend.ai.nl import classify_read, match_relation, parse_create
from backend.ai.schemas import ChatCommand, C4Scaffold, FieldSummary, L1BaselineDraft, L2Draft, L3Draft, L4Draft, NarrativeOutput, OrchestratorPlan, StaffingProposal, StoryDecomposition
from backend.c4 import store as c4_store
from backend.graph.nodes import _parse_structured_result
from backend.llm.factory import get_llm, get_structured_llm, prefers_text_routing
from backend.planning import store as planning_store
from backend.resources import store as resources_store
from backend.storage.db import connect


async def _invoke(schema: type, system: str, human: str):
    model = get_structured_llm(schema)
    result = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    return _parse_structured_result(schema, result)


# ---- Auto-staffing agent ------------------------------------------------

_STAFFING_SYSTEM = (
    "You are a delivery lead composing squads from an available talent pool.\n"
    "Rules:\n"
    "- Only assign people from the RESOURCE POOL list, by their exact staff_id.\n"
    "- Never exceed a person's remaining capacity; the sum of a person's new allocations must fit their remaining %.\n"
    "- Prefer matching skills/rank/HR role to the squad's mission and the open work.\n"
    "- Leave a person unassigned rather than overloading them.\n"
    "- Give each assignment a short, concrete reason."
)


def _staffing_context(project_id: str, l1_element_id: str) -> tuple[str, dict[str, Any]]:
    plan = planning_store.get_plan(project_id, l1_element_id)
    squads = [u for u in plan["units"] if u["unit_type"] == "squad"]
    staff = resources_store.list_staff({"staff_status": "Active"})

    with connect() as conn:
        alloc = {
            row["resource_staff_id"]: row["total"]
            for row in conn.execute(
                """SELECT resource_staff_id, COALESCE(SUM(allocation_percent), 0) AS total
                   FROM l1_team_members WHERE resource_staff_id IS NOT NULL GROUP BY resource_staff_id"""
            ).fetchall()
        }

    available = []
    for person in staff:
        remaining = 100 - alloc.get(person["id"], 0)
        if remaining <= 0:
            continue
        available.append({
            "staff_id": person["id"],
            "name": person["staff_name"],
            "rank": person["rank"],
            "hr_role": person["hr_role"],
            "tech_unit": person["tech_unit"],
            "remaining_percent": remaining,
        })

    open_work = [
        {"title": w["title"], "squad_id": w.get("squad_id"), "status": w["status"]}
        for w in plan.get("work_items", []) if w["status"] in ("planned", "in_progress", "at_risk")
    ]
    squad_view = [{"squad_id": s["id"], "name": s["name"], "mission": s.get("mission", ""),
                   "current_people": len(s.get("members", []))} for s in squads]

    human = (
        f"INITIATIVE: {plan['element']['name']}\n\n"
        f"SQUADS:\n{json.dumps(squad_view, indent=2)}\n\n"
        f"OPEN WORK ITEMS:\n{json.dumps(open_work, indent=2)}\n\n"
        f"RESOURCE POOL (with remaining capacity):\n{json.dumps(available, indent=2)}\n\n"
        "Propose assignments that staff the squads without exceeding anyone's remaining capacity."
    )
    return human, {"available": {p["staff_id"]: p for p in available}, "squads": {s["id"]: s for s in squads}}


async def propose_staffing(project_id: str, l1_element_id: str) -> StaffingProposal:
    human, index = _staffing_context(project_id, l1_element_id)
    if not index["available"] or not index["squads"]:
        return StaffingProposal(summary="No available resources or squads to staff.", assignments=[])
    proposal: StaffingProposal = await _invoke(StaffingProposal, _STAFFING_SYSTEM, human)

    # Defensively enforce the invariants regardless of what the model returned.
    remaining = {sid: person["remaining_percent"] for sid, person in index["available"].items()}
    clean = []
    for assignment in proposal.assignments:
        person = index["available"].get(assignment.staff_id)
        squad = index["squads"].get(assignment.squad_id)
        if not person or not squad:
            continue
        allocation = min(assignment.allocation_percent, remaining.get(assignment.staff_id, 0))
        if allocation <= 0:
            continue
        remaining[assignment.staff_id] -= allocation
        assignment.allocation_percent = allocation
        assignment.staff_name = person["name"]
        assignment.squad_name = squad["name"]
        clean.append(assignment)
    proposal.assignments = clean
    return proposal


def apply_staffing(project_id: str, assignments: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist accepted staffing assignments as team members (reuses the allocation cap)."""
    from backend.planning.models import TeamMemberCreate

    created = 0
    errors: list[str] = []
    for item in assignments:
        try:
            planning_store.create_member(project_id, item["squad_id"], TeamMemberCreate(
                name=item.get("staff_name", ""),
                resource_staff_id=item["staff_id"],
                role=item.get("role", ""),
                allocation_percent=float(item.get("allocation_percent", 0)),
            ))
            created += 1
        except Exception as exc:  # surfaced, not fatal — partial apply is fine
            errors.append(f"{item.get('staff_name', item.get('staff_id'))}: {exc}")
    return {"created": created, "errors": errors}


# ---- Reporting narrative agent ------------------------------------------

_NARRATIVE_SYSTEM = (
    "You are a delivery-portfolio analyst. Given a set of metrics, write a crisp executive briefing.\n"
    "Be specific and quantitative, reference the numbers, and keep each list item to one sentence.\n"
    "Do not invent data beyond what is provided."
)


async def generate_narrative(overview: dict[str, Any]) -> NarrativeOutput:
    human = (
        "Write an executive summary of this delivery portfolio snapshot.\n\n"
        f"METRICS:\n{json.dumps(overview, indent=2)}"
    )
    return await _invoke(NarrativeOutput, _NARRATIVE_SYSTEM, human)


# ---- Requirements → stories decomposition -------------------------------

_DECOMPOSE_SYSTEM = (
    "You are a senior BA/tech-lead decomposing a piece of scope into small, independently "
    "deliverable user stories.\n"
    "Rules:\n"
    "- Each story is vertically sliced, testable, and sized to fit a single sprint.\n"
    "- Write the description as a user story with a couple of acceptance criteria.\n"
    "- Aim for 3-8 stories; avoid overlap; cover the happy path plus key edges."
)


async def decompose_element(project_id: str, element_id: str, guidance: str = "") -> StoryDecomposition:
    element = c4_store.get_element(project_id, element_id)
    parent_name = ""
    if element.get("parent_id"):
        try:
            parent_name = c4_store.get_element(project_id, element["parent_id"])["name"]
        except Exception:
            parent_name = ""
    human = (
        f"PARENT: {parent_name or '(top level)'}\n"
        f"ELEMENT ({element['level']}): {element['name']}\n"
        f"DESCRIPTION: {element.get('description') or '(none provided)'}\n"
        f"TECH: {element.get('tech') or '(unspecified)'}\n"
        + (f"EXTRA GUIDANCE: {mask_pii(guidance)}\n" if guidance.strip() else "")
        + "\nPropose the child stories that fully deliver this scope."
    )
    return await _invoke(StoryDecomposition, _DECOMPOSE_SYSTEM, human)


def apply_decomposition(project_id: str, element_id: str, stories: list[dict[str, Any]]) -> dict[str, Any]:
    """Create accepted stories as proposed child elements one level below the parent."""
    from backend.c4.models import C4ElementCreate

    parent = c4_store.get_element(project_id, element_id)
    child_level = {"L1": "L2", "L2": "L3", "L3": "L4"}.get(parent["level"], "L3")
    created = 0
    for story in stories:
        c4_store.create_element(project_id, C4ElementCreate(
            level=child_level,
            name=story["name"][:200],
            description=story.get("description", ""),
            parent_id=element_id,
            kind="component" if child_level == "L3" else "task",
            status="proposed",
        ))
        created += 1
    return {"created": created, "level": child_level}


# ---- C4-from-description scaffold ----------------------------------------

_SCAFFOLD_SYSTEM = (
    "You are a software architect turning a description into a C4 model.\n"
    "Rules:\n"
    "- Produce exactly one L1 system, a handful of L2 containers, and L3 components under them.\n"
    "- Use `ref` as a temporary handle; set each element's parent_ref (L1 has null).\n"
    "- Add relations between containers/components that exchange data or calls.\n"
    "- Keep it to 8-20 elements; use realistic tech for containers."
)


async def scaffold_c4(project_id: str, description: str) -> C4Scaffold:
    human = (
        "Turn this description into a C4 model (one L1 system, L2 containers, L3 components + relations).\n\n"
        f"DESCRIPTION:\n{mask_pii(description.strip())}"
    )
    return await _invoke(C4Scaffold, _SCAFFOLD_SYSTEM, human)


# ---- L1 architecture baseline generator ---------------------------------

_L1_BASELINE_SYSTEM = (
    "You are an enterprise architect drafting an L1 architecture baseline from a brief.\n"
    "Produce: a crisp vision statement, the business problem, target users, 2-4 OKRs with measurable "
    "key results and targets, the key internal/external stakeholders with RACI (exactly one Accountable), "
    "the top business capabilities, and the main portfolio risks with mitigations and a funding source.\n"
    "Be specific to the brief; do not invent unrelated systems."
)


async def generate_l1_baseline(project_id: str, l1_element_id: str, brief: str) -> L1BaselineDraft:
    element = c4_store.get_element(project_id, l1_element_id)
    human = (
        f"L1 INITIATIVE: {element['name']}\n"
        f"EXISTING DESCRIPTION: {element.get('description') or '(none)'}\n\n"
        f"BRIEF:\n{mask_pii(brief.strip()) or '(use the initiative name and description)'}\n\n"
        "Draft the L1 architecture baseline."
    )
    return await _invoke(L1BaselineDraft, _L1_BASELINE_SYSTEM, human)


# ---- L2 container-architecture generator --------------------------------

_L2_SYSTEM = (
    "You are an L2 container-architecture assistant. From the L1 context and a brief, draft the "
    "container architecture for one epic/platform slice.\n"
    "Produce: a short summary, a C4-style Mermaid container diagram (flowchart LR), the containers "
    "(with capability, responsibilities, owner team, security classification), the API/data contracts "
    "(provider, consumer, type, data classification, auth), the key NFRs (with metric + target), and the "
    "main integrations. Link to the L1 capability where possible; mark unknowns rather than inventing systems."
)


async def generate_l2_baseline(project_id: str, l2_element_id: str, brief: str) -> L2Draft:
    element = c4_store.get_element(project_id, l2_element_id)
    parent_name = ""
    if element.get("parent_id"):
        try:
            parent_name = c4_store.get_element(project_id, element["parent_id"])["name"]
        except Exception:
            parent_name = ""
    human = (
        f"L2 EPIC/CONTAINER SLICE: {element['name']}\n"
        f"PARENT L1 INITIATIVE: {parent_name or '(none)'}\n"
        f"EXISTING DESCRIPTION: {element.get('description') or '(none)'}\n\n"
        f"BRIEF:\n{mask_pii(brief.strip()) or '(use the element name and description)'}\n\n"
        "Draft the L2 container architecture."
    )
    return await _invoke(L2Draft, _L2_SYSTEM, human)


def apply_l2_baseline(project_id: str, l2_element_id: str, draft: dict[str, Any], sections: list[str] | None = None) -> dict[str, Any]:
    from backend.l2arch import store as l2_store
    from backend.l2arch.models import ApiCreate, ContainerCreate, IntegrationCreate, L2Update, NfrCreate

    wanted = set(sections or ["summary", "containers", "apis", "nfrs", "integrations"])
    result: dict[str, int] = {}
    if "summary" in wanted and (draft.get("summary") or draft.get("container_diagram")):
        l2_store.update_l2(project_id, l2_element_id, L2Update(
            summary=draft.get("summary", ""), container_diagram=draft.get("container_diagram", ""),
        ))
        result["summary"] = 1
    if "containers" in wanted:
        for item in draft.get("containers", []):
            l2_store.create_container(project_id, l2_element_id, ContainerCreate(**item))
        result["containers"] = len(draft.get("containers", []))
    if "apis" in wanted:
        for item in draft.get("apis", []):
            l2_store.create_api(project_id, l2_element_id, ApiCreate(**item))
        result["apis"] = len(draft.get("apis", []))
    if "nfrs" in wanted:
        for item in draft.get("nfrs", []):
            l2_store.create_nfr(project_id, l2_element_id, NfrCreate(**item))
        result["nfrs"] = len(draft.get("nfrs", []))
    if "integrations" in wanted:
        for item in draft.get("integrations", []):
            l2_store.create_integration(project_id, l2_element_id, IntegrationCreate(**item))
        result["integrations"] = len(draft.get("integrations", []))
    return result


# ---- L3 component-architecture generator --------------------------------

_L3_SYSTEM = (
    "You are an L3 component-architecture assistant. From the L2 container context and a brief, draft the "
    "internal component design for one component/story.\n"
    "Produce: a short summary, a Mermaid component diagram (flowchart TB), the internal components "
    "(with type — controller/service/repository/gateway/model/client — responsibilities, tech and design "
    "pattern), the provided/consumed interfaces (with contract + auth), the dependencies (internal/container/"
    "external/library), and the cross-cutting design concerns (logging, caching, validation, security, error "
    "handling). Keep it implementable; mark unknowns rather than inventing systems."
)


async def generate_l3_baseline(project_id: str, l3_element_id: str, brief: str) -> L3Draft:
    element = c4_store.get_element(project_id, l3_element_id)
    parent_name = ""
    if element.get("parent_id"):
        try:
            parent_name = c4_store.get_element(project_id, element["parent_id"])["name"]
        except Exception:
            parent_name = ""
    human = (
        f"L3 COMPONENT/STORY: {element['name']}\n"
        f"PARENT L2 CONTAINER: {parent_name or '(none)'}\n"
        f"EXISTING DESCRIPTION: {element.get('description') or '(none)'}\n\n"
        f"BRIEF:\n{mask_pii(brief.strip()) or '(use the element name and description)'}\n\n"
        "Draft the L3 component architecture."
    )
    return await _invoke(L3Draft, _L3_SYSTEM, human)


def apply_l3_baseline(project_id: str, l3_element_id: str, draft: dict[str, Any], sections: list[str] | None = None) -> dict[str, Any]:
    from backend.l3arch import store as l3_store
    from backend.l3arch.models import ComponentCreate, ConcernCreate, DependencyCreate, InterfaceCreate, L3Update

    wanted = set(sections or ["summary", "components", "interfaces", "dependencies", "concerns"])
    result: dict[str, int] = {}
    if "summary" in wanted and (draft.get("summary") or draft.get("component_diagram")):
        l3_store.update_l3(project_id, l3_element_id, L3Update(
            summary=draft.get("summary", ""), component_diagram=draft.get("component_diagram", ""),
        ))
        result["summary"] = 1
    if "components" in wanted:
        for item in draft.get("components", []):
            l3_store.create_component(project_id, l3_element_id, ComponentCreate(**item))
        result["components"] = len(draft.get("components", []))
    if "interfaces" in wanted:
        for item in draft.get("interfaces", []):
            l3_store.create_interface(project_id, l3_element_id, InterfaceCreate(**item))
        result["interfaces"] = len(draft.get("interfaces", []))
    if "dependencies" in wanted:
        for item in draft.get("dependencies", []):
            l3_store.create_dependency(project_id, l3_element_id, DependencyCreate(**item))
        result["dependencies"] = len(draft.get("dependencies", []))
    if "concerns" in wanted:
        for item in draft.get("concerns", []):
            l3_store.create_concern(project_id, l3_element_id, ConcernCreate(**item))
        result["concerns"] = len(draft.get("concerns", []))
    return result


# ---- L4 implementation-detail generator ---------------------------------

_L4_SYSTEM = (
    "You are an L4 implementation assistant. From the L3 component context and a brief, draft the concrete "
    "implementation plan for one task.\n"
    "Produce: a short summary, a Mermaid class or sequence diagram, the code units (classes/interfaces/"
    "functions/modules with responsibility, tech and complexity), the test cases (unit/integration/e2e with a "
    "scenario and expected result), and a Definition-of-Done checklist (code, tests, docs, security, review, "
    "deploy). Keep it concrete and buildable; do not invent unrelated files."
)


async def generate_l4_baseline(project_id: str, l4_element_id: str, brief: str) -> L4Draft:
    element = c4_store.get_element(project_id, l4_element_id)
    parent_name = ""
    if element.get("parent_id"):
        try:
            parent_name = c4_store.get_element(project_id, element["parent_id"])["name"]
        except Exception:
            parent_name = ""
    human = (
        f"L4 TASK: {element['name']}\n"
        f"PARENT L3 COMPONENT: {parent_name or '(none)'}\n"
        f"EXISTING DESCRIPTION: {element.get('description') or '(none)'}\n\n"
        f"BRIEF:\n{mask_pii(brief.strip()) or '(use the element name and description)'}\n\n"
        "Draft the L4 implementation detail."
    )
    return await _invoke(L4Draft, _L4_SYSTEM, human)


def apply_l4_baseline(project_id: str, l4_element_id: str, draft: dict[str, Any], sections: list[str] | None = None) -> dict[str, Any]:
    from backend.l4arch import store as l4_store
    from backend.l4arch.models import ChecklistCreate, CodeUnitCreate, L4Update, TestCaseCreate

    wanted = set(sections or ["summary", "code_units", "test_cases", "checklist"])
    result: dict[str, int] = {}
    if "summary" in wanted and (draft.get("summary") or draft.get("code_diagram")):
        l4_store.update_l4(project_id, l4_element_id, L4Update(
            summary=draft.get("summary", ""), code_diagram=draft.get("code_diagram", ""),
        ))
        result["summary"] = 1
    if "code_units" in wanted:
        for item in draft.get("code_units", []):
            l4_store.create_code_unit(project_id, l4_element_id, CodeUnitCreate(**item))
        result["code_units"] = len(draft.get("code_units", []))
    if "test_cases" in wanted:
        for item in draft.get("test_cases", []):
            l4_store.create_test_case(project_id, l4_element_id, TestCaseCreate(**item))
        result["test_cases"] = len(draft.get("test_cases", []))
    if "checklist" in wanted:
        for item in draft.get("checklist", []):
            l4_store.create_checklist_item(project_id, l4_element_id, ChecklistCreate(**item))
        result["checklist"] = len(draft.get("checklist", []))
    return result


# ---- AI orchestrator ----------------------------------------------------

_ORCHESTRATOR_SYSTEM = (
    "You route a user's natural-language request to exactly one specialized capability.\n"
    "Actions: generate_l1_baseline (draft vision/OKRs/stakeholders/capabilities/risks), "
    "auto_staffing (assign people to squads), decompose_story (break scope into stories), "
    "scaffold_c4 (build a C4 model from a description), reporting_narrative (executive summary of metrics), "
    "review_readiness (assess L1 completeness), or none if nothing fits.\n"
    "Pick the single best action and give a one-line rationale."
)


async def orchestrate(request_text: str) -> OrchestratorPlan:
    human = f"USER REQUEST:\n{mask_pii(request_text.strip())}\n\nChoose the single best action."
    return await _invoke(OrchestratorPlan, _ORCHESTRATOR_SYSTEM, human)


# ---- Conversational assistant -------------------------------------------

_CHAT_SYSTEM = (
    "You are the Karya assistant. Interpret the user's message into ONE structured command over "
    "the project's C4 model (levels L1 initiative, L2 container, L3 component/story, L4 task).\n"
    "Actions: overview (project status/next step), list (elements at a level), readiness (of a named element "
    "or level), report (roll-up / what to do next), create_element (level+name, optional parent name), "
    "update_element (name + new_name/status/description), delete_element (name), "
    "create_relation (name=source element, target=target element, optional label) — connects two "
    "elements that ALREADY exist; e.g. “add route to payments through api-gateway” means api-gateway → "
    "payments (the element named after through/via is the source), and “connect A to B” means A → B, "
    "web_search (current/external facts; put the search query in description), code (generate or explain code), "
    "image (create an image prompt, visual specification, SVG, or Mermaid source), document (write, transform, or "
    "review document content in Markdown), answer (general questions and product guidance), help, or none.\n"
    "The element name may be inline (“create an L2 payments container” → name payments). A compound request "
    "like “create X and route/connect it to Y” is ONE create_element with `target` set to Y (and an optional "
    "`label` like routes/calls/publishes) — the relation is created with the element.\n"
    "Use CONVERSATION so far to resolve follow-ups: if you previously asked for a missing detail (e.g. a name), "
    "interpret a short answer as that detail of the pending command.\n"
    "Resolve names against the PROJECT ELEMENTS list. For create/update/delete set the exact element name(s). "
    "REQUEST MODE is authoritative when it is not auto: chat→answer, code→code, research→web_search, "
    "image→image, document→document. Do not reinterpret a forced mode as a workspace mutation. "
    "For answer/code/image/document, give a complete useful Markdown response grounded in supplied context. "
    "Image mode is text-only: produce an excellent generation prompt, SVG/Mermaid source, or visual spec; never "
    "claim that a bitmap was generated or that image pixels were inspected. "
    "For web_search, do not invent results; set description to a focused query and let the search tool answer. "
    "Never invent elements that aren't in the list for reads. "
    "Prefer the grounded read actions for questions about the model: project status/health → overview; "
    "'what should I do next' / roll-up / points → report; 'list/show/summary of <level>' → list; how ready/complete "
    "an element or level is → readiness. Only use answer for genuinely open-ended questions, and then ground every "
    "claim (counts, points, status, next step) in the PROJECT SNAPSHOT and PLATFORM GUIDE — never fabricate numbers. "
    "When a message omits the level or element (e.g. a bare 'readiness' or 'list'), default it from CURRENT SCREEN "
    "if present — the open element for readiness, the open level for list."
)


# Documentation grounding: a concise, always-true description of what the app is,
# so free-form "how do I / what is X" answers are anchored to real capabilities.
_PLATFORM_GUIDE = (
    "PLATFORM GUIDE:\n"
    "Karya is an evidence-led story-point estimator and top-down architecture workspace for a C4 model "
    "(L1 initiative → L2 container → L3 component/story → L4 task). Each level has an architecture workspace "
    "with a readiness score, artifacts, governance sign-off, and an AI baseline generator. Story points use a "
    "modified Fibonacci scale (1/2/3/5/8/13) and roll up deterministically from L3 stories to epics and "
    "initiatives. The assistant can query the model (status, lists, readiness, roll-up) and propose changes "
    "(create/rename/delete an element, connect two elements) that you review before anything is saved."
)


def _project_snapshot(project_id: str, elements: list[dict[str, Any]]) -> str:
    """A compact, deterministic status line built from the DB so answers cite real
    numbers. Best-effort — never let a snapshot failure break interpretation."""
    by_level: dict[str, int] = {}
    for element in elements:
        by_level[element["level"]] = by_level.get(element["level"], 0) + 1
    proposed = sum(1 for e in elements if e.get("status") == "proposed")
    counts = " · ".join(f"{n} {lvl}" for lvl, n in sorted(by_level.items())) or "no elements yet"
    lines = [f"Elements: {counts}" + (f" ({proposed} proposed)" if proposed else "")]
    try:
        from backend.c4 import service as c4_service
        from backend.workflow import service as workflow_service

        totals = c4_service.rollup(project_id)["totals"]
        stories = totals["estimated_stories"] + totals["unestimated_stories"]
        lines.append(f"Roll-up: {totals['estimated_stories']}/{stories} stories estimated · {totals['rolled_up_points']} points")
        guide = workflow_service.guide(project_id)
        lines.append(f"Workflow: {guide['overall_pct']}% complete (stage {guide['stage']}) · next: {guide['next_action']['text']}")
    except Exception:  # noqa: BLE001 - snapshot is advisory grounding only
        pass
    return "\n".join(lines)


def _resolve_screen(screen: dict[str, Any] | None, elements: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Turn the frontend's screen descriptor into (level, element_name, label).

    The user's current tab and selected element are context, not commands — they
    only fill in a level/element the message leaves implicit."""
    if not screen:
        return "", "", ""
    level = str(screen.get("level") or "").strip().upper()
    if level not in {"L1", "L2", "L3", "L4"}:
        level = ""
    label = str(screen.get("tab_label") or screen.get("tab") or "").strip()[:60]
    element_name = ""
    eid = screen.get("element_id")
    if eid:
        element_name = next((str(e["name"]) for e in elements if e.get("id") == eid), "")
    return level, element_name, label


def _apply_screen_defaults(command: ChatCommand, screen_level: str, screen_element: str) -> None:
    """Fill an omitted level/element on a read from the current screen, so a bare
    "list" or "readiness" acts on what the user is looking at."""
    if command.action == "list" and not command.level.strip() and screen_level:
        command.level = screen_level
    elif command.action == "readiness" and not command.name.strip() and not command.level.strip():
        if screen_element:
            command.name = screen_element
        elif screen_level:
            command.level = screen_level


async def interpret_chat(project_id: str, message: str, history: list[dict[str, str]] | None = None,
                         attachment_context: str = "", mode: str = "auto",
                         screen: dict[str, Any] | None = None) -> ChatCommand:
    elements = c4_store.list_graph(project_id)["elements"]
    listing = "\n".join(f"- {e['level']} · {e['name']} ({e['status']})" for e in elements[:100]) or "(no elements yet)"
    screen_level, screen_element, screen_label = _resolve_screen(screen, elements)
    screen_line = ""
    if screen_level or screen_element or screen_label:
        parts = [f"view={screen_label}" if screen_label else "", f"level={screen_level}" if screen_level else "",
                 f"element={screen_element}" if screen_element else ""]
        screen_line = ("CURRENT SCREEN: " + " | ".join(p for p in parts if p)
                       + "\nUse this only to fill a level or element the message leaves implicit.\n\n")
    convo = "\n".join(
        f"{(turn.get('role') or 'user').upper()}: {mask_pii(str(turn.get('text') or '').strip())[:300]}"
        for turn in (history or [])[-8:] if str(turn.get('text') or '').strip()
    )
    human = (
        f"REQUEST MODE: {mode}\n\n{_PLATFORM_GUIDE}\n\n"
        f"PROJECT SNAPSHOT (deterministic, from the database):\n{_project_snapshot(project_id, elements)}\n\n"
        + screen_line
        + f"PROJECT ELEMENTS:\n{listing}\n\n"
        + (f"CONVERSATION SO FAR:\n{convo}\n\n" if convo else "")
        + (f"ATTACHED FILE CONTENT:\n{mask_pii(attachment_context)}\n\n" if attachment_context else "")
        + f"USER MESSAGE:\n{mask_pii(message.strip())}\n\n"
        "Interpret into one command."
    )
    if prefers_text_routing():
        command = await _interpret_local_chat(message, mode, elements, human, screen_level, screen_element, history)
    else:
        command = await _invoke(ChatCommand, _CHAT_SYSTEM, human)
        forced = {"chat": "answer", "code": "code", "research": "web_search",
                  "image": "image", "document": "document"}.get(mode)
        if forced:
            command.action = forced
            if forced == "web_search":
                command.description = command.description.strip() or message.strip()
    _apply_screen_defaults(command, screen_level, screen_element)
    return command


async def _interpret_local_chat(message: str, mode: str, elements: list[dict], context: str,
                                screen_level: str = "", screen_element: str = "",
                                history: list[dict[str, str]] | None = None) -> ChatCommand:
    """Deterministic routing + free-form Gemma response, following Gemma Studio.

    Gemma 3 1B should not be asked to serialize the large ChatCommand schema.
    Recognizable project operations are routed without an LLM; open-ended modes
    use Gemma only for the Markdown reply.
    """
    text = message.strip()
    low = text.lower()
    names = sorted((str(item["name"]) for item in elements), key=len, reverse=True)
    found = next((name for name in names if name.lower() in low), "")
    level_match = re.search(r"\bl([1-4])\b", low)
    level = f"L{level_match.group(1)}" if level_match else ""
    forced = {"chat": "answer", "code": "code", "research": "web_search",
              "image": "image", "document": "document"}.get(mode)
    if forced == "web_search":
        return ChatCommand(action="web_search", description=text, reply="Searching the web.")
    if forced:
        return ChatCommand(action=forced, reply=await _local_markdown_reply(forced, context))

    # ---- writes first (strong, unambiguous intent) ----
    rename = re.search(r"\brename\s+(.+?)\s+to\s+(.+?)[?.]*$", text, re.I)
    if rename:
        return ChatCommand(action="update_element", name=rename.group(1).strip(),
                           new_name=rename.group(2).strip(), reply="Review this rename before applying.")
    status = re.search(r"\bstatus\s+(?:of\s+.+?\s+)?to\s+(active|proposed|reviewed|draft|deprecated|baselined|done|planned)\b", low)
    if status and found:
        return ChatCommand(action="update_element", name=found, status=status.group(1),
                           reply="Review this status change before applying.")
    if re.search(r"\b(delete|remove)\b", low):
        target = found or re.sub(r"^.*?\b(?:delete|remove)\b\s+", "", text, flags=re.I).rstrip("?.")
        return ChatCommand(action="delete_element", name=target, reply="Review this deletion before applying.")
    # A route/connection between two existing elements → create_relation. Checked
    # before create so "add route to payments through api-gateway" isn't read as a
    # new element; match_relation only fires when both endpoints are known.
    relation = match_relation(text, names)
    if relation:
        source, target, label = relation
        return ChatCommand(action="create_relation", name=source, target=target, label=label,
                           reply=f"Connect “{source}” to “{target}” — Apply to confirm.")
    created = parse_create(text, names)
    if created and (created["name"] or created["level"] or re.match(r"^\s*(?:create|add)\b", text, re.I)):
        return ChatCommand(action="create_element", level=created["level"], name=created["name"],
                           parent=created["parent"], target=created["target"], label=created["label"],
                           reply="Review this new element before applying.")
    # A bare follow-up ("Payments") after we asked for a missing detail: replay the
    # pending create/rename intent from history with this answer as the name.
    if history and len(text) <= 60:
        pending = next((str(t.get("text") or "") for t in reversed(history)
                        if t.get("role") == "user" and re.search(r"\b(create|add|new|rename)\b", str(t.get("text") or ""), re.I)), "")
        if pending:
            retry = parse_create(f"{pending.rstrip('?. ')} called {text.strip()}", names)
            if retry and retry["name"]:
                return ChatCommand(action="create_element", level=retry["level"], name=retry["name"],
                                   parent=retry["parent"], target=retry["target"], label=retry["label"],
                                   reply="Review this new element before applying.")
    if re.search(r"\b(search|browse|internet|web|latest|current news)\b", low):
        return ChatCommand(action="web_search", description=text, reply="Searching the web.")
    # Grounded reads (overview / report / list / readiness) answer from the DB via
    # chat.service — never the model — so status/summary questions can't hallucinate.
    # The current screen fills an implicit level/element ("readiness" of the open one).
    read = classify_read(text, names, screen_level, screen_element)
    if read:
        action, read_level, read_name = read
        return ChatCommand(action=action, level=read_level, name=read_name,
                           reply="Here's what I found.")
    action = "code" if re.search(r"\b(code|function|class|script|implement|debug)\b", low) else "answer"
    return ChatCommand(action=action, reply=await _local_markdown_reply(action, context))


async def _local_markdown_reply(mode: str, context: str) -> str:
    system = (
        "You are Karya, a precise local assistant. Answer directly in Markdown. "
        "Use only supplied project/file facts; distinguish evidence from inference."
    )
    if mode == "code":
        system += " Produce production-quality code and mention correctness or security risks."
    elif mode == "image":
        system += " Produce a visual brief, image prompt, SVG, or Mermaid source; do not claim bitmap generation."
    elif mode == "document":
        system += " Write or review the requested document with clear headings."
    answer_context = context.replace("\n\nInterpret into one command.", "\n\nAnswer the user request directly.")
    raw = await get_llm().ainvoke(
        [SystemMessage(content=system), HumanMessage(content=answer_context)],
        max_new_tokens=256,
    )
    content = raw.content
    return content if isinstance(content, str) else "\n".join(str(part) for part in content)


# ---- Summarize detail → parent field ------------------------------------

_SUMMARIZE_STYLES = {
    "vision": "a single crisp vision sentence (who it's for, what it provides, the outcome)",
    "problem": "a one-to-two sentence business-problem statement",
    "users": "a short comma-separated list of the primary user segments",
    "default": "one concise, executive-ready sentence",
}


async def summarize_field(text: str, field: str = "default") -> FieldSummary:
    style = _SUMMARIZE_STYLES.get(field, _SUMMARIZE_STYLES["default"])
    system = (
        "You distil detailed notes into a crisp summary for an executive strategy field. "
        f"Return {style}. No preamble, no markdown, no bullet points — just the summary text."
    )
    human = f"DETAIL NOTES:\n{mask_pii(text.strip())}\n\nSummarize into {style}."
    return await _invoke(FieldSummary, system, human)


def apply_l1_baseline(project_id: str, l1_element_id: str, draft: dict[str, Any], sections: list[str] | None = None) -> dict[str, Any]:
    """Persist accepted parts of the draft. `sections` filters which artifact types to apply."""
    from backend.l1arch import store as l1_store
    from backend.l1arch.models import (
        CapabilityCreate, OkrCreate, RiskCreate, StakeholderCreate, VisionUpdate,
    )

    wanted = set(sections or ["vision", "okrs", "stakeholders", "capabilities", "risks"])
    result: dict[str, int] = {}

    if "vision" in wanted and (draft.get("vision_statement") or draft.get("business_problem")):
        l1_store.update_vision(project_id, l1_element_id, VisionUpdate(
            vision_statement=draft.get("vision_statement", ""),
            business_problem=draft.get("business_problem", ""),
            target_users=draft.get("target_users", ""),
        ))
        result["vision"] = 1
    if "okrs" in wanted:
        for okr in draft.get("okrs", []):
            l1_store.create_okr(project_id, l1_element_id, OkrCreate(**okr))
        result["okrs"] = len(draft.get("okrs", []))
    if "stakeholders" in wanted:
        for person in draft.get("stakeholders", []):
            l1_store.create_stakeholder(project_id, l1_element_id, StakeholderCreate(**person))
        result["stakeholders"] = len(draft.get("stakeholders", []))
    if "capabilities" in wanted:
        for cap in draft.get("capabilities", []):
            l1_store.create_capability(project_id, l1_element_id, CapabilityCreate(**cap))
        result["capabilities"] = len(draft.get("capabilities", []))
    if "risks" in wanted:
        for risk in draft.get("risks", []):
            l1_store.create_risk(project_id, l1_element_id, RiskCreate(**risk))
        result["risks"] = len(draft.get("risks", []))
    return result


def apply_scaffold(project_id: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    """Create the proposed elements + relations, resolving temporary refs to real ids."""
    from backend.c4.models import C4ElementCreate, C4RelationCreate

    ref_to_id: dict[str, str] = {}
    order = {"L1": 0, "L2": 1, "L3": 2}
    elements = sorted(scaffold.get("elements", []), key=lambda e: order.get(e["level"], 3))
    created_elements = 0
    for element in elements:
        parent_ref = element.get("parent_ref")
        parent_id = ref_to_id.get(parent_ref) if parent_ref else None
        record = c4_store.create_element(project_id, C4ElementCreate(
            level=element["level"],
            name=element["name"][:200],
            kind=element.get("kind", ""),
            description=element.get("description", ""),
            tech=element.get("tech", ""),
            parent_id=parent_id,
            status="proposed",
        ))
        ref_to_id[element["ref"]] = record["id"]
        created_elements += 1

    created_relations = 0
    for relation in scaffold.get("relations", []):
        source = ref_to_id.get(relation["source_ref"])
        target = ref_to_id.get(relation["target_ref"])
        if not source or not target:
            continue
        kind = relation.get("kind", "sync")
        if kind not in ("sync", "async", "data"):
            kind = "sync"
        c4_store.create_relation(project_id, C4RelationCreate(
            source_id=source, target_id=target, label=relation.get("label", ""), kind=kind,
        ))
        created_relations += 1
    return {"created_elements": created_elements, "created_relations": created_relations}
