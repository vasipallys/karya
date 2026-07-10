"""The four agentic services. Each gathers context, prompts the LLM through the
factory's structured output, and returns a *proposal* — nothing is persisted here."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.ai.masking import mask_pii
from backend.ai.schemas import ChatCommand, C4Scaffold, FieldSummary, L1BaselineDraft, L2Draft, L3Draft, L4Draft, NarrativeOutput, OrchestratorPlan, StaffingProposal, StoryDecomposition
from backend.c4 import store as c4_store
from backend.graph.nodes import _parse_structured_result
from backend.llm.factory import get_structured_llm
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
    "You are the Story Pointer assistant. Interpret the user's message into ONE structured command over "
    "the project's C4 model (levels L1 initiative, L2 container, L3 component/story, L4 task).\n"
    "Actions: overview (project status/next step), list (elements at a level), readiness (of a named element "
    "or level), report (roll-up / what to do next), create_element (level+name, optional parent name), "
    "update_element (name + new_name/status/description), delete_element (name), help, or none.\n"
    "Resolve names against the PROJECT ELEMENTS list. For create/update/delete set the exact element name(s). "
    "Always write a short, friendly `reply`. Never invent elements that aren't in the list for reads."
)


async def interpret_chat(project_id: str, message: str) -> ChatCommand:
    elements = c4_store.list_graph(project_id)["elements"]
    listing = "\n".join(f"- {e['level']} · {e['name']} ({e['status']})" for e in elements[:100]) or "(no elements yet)"
    human = (
        f"PROJECT ELEMENTS:\n{listing}\n\n"
        f"USER MESSAGE:\n{mask_pii(message.strip())}\n\n"
        "Interpret into one command."
    )
    return await _invoke(ChatCommand, _CHAT_SYSTEM, human)


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
