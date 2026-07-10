"""Deterministic offline LLM for LLM_PROVIDER=mock.

Produces schema-valid, story-dependent outputs with no network or API key, so
demos, tests, and UI work run without a provider. The estimate is derived from
a stable hash of the story title, so the same story always gets the same points
and a 13 exercises the spike/split branch end to end.
"""

from __future__ import annotations

import asyncio
import json
import re
import zlib
from typing import Any

from pydantic import BaseModel

from backend.anchors import ANCHORS
from backend.graph.state import (
    PARAMETERS,
    AnchorComparisonOutput,
    DriversOutput,
    EffortRange,
    HiddenTasksOutput,
    HiddenTask,
    LayerEffort,
    ParameterScore,
    PlainLanguageOutput,
    PointsOutput,
    Risk,
    RisksOutput,
    ScorecardOutput,
    SplitOutput,
)

FIBONACCI = [2, 3, 5, 8, 13]
LEVELS = ["Low", "Medium", "High"]


def _seed(text: str) -> int:
    return zlib.crc32(text.encode("utf-8"))


def _title(messages: list[Any]) -> str:
    text = " ".join(str(getattr(message, "content", message)) for message in messages)
    match = re.search(r'"title":\s*"([^"]+)"', text)
    return match.group(1) if match else "the story"


def _points(title: str) -> int:
    return FIBONACCI[_seed(title) % len(FIBONACCI)]


def _score(title: str, parameter: str) -> str:
    return LEVELS[_seed(f"{title}:{parameter}") % len(LEVELS)]


def _build(schema: type[BaseModel], title: str) -> BaseModel:
    points = _points(title)
    anchor_titles = [anchor["title"] for anchor in ANCHORS[:2]]
    if schema is ScorecardOutput:
        return ScorecardOutput(scores=[
            ParameterScore(parameter=parameter, score=_score(title, parameter),
                           reason=f"Mock assessment of {parameter.replace('_', ' ')} from the supplied evidence.")
            for parameter in PARAMETERS
        ])
    if schema is DriversOutput:
        drivers = sorted(PARAMETERS, key=lambda parameter: _seed(f"{title}:{parameter}"))[:2]
        return DriversOutput(drivers=drivers, explanation=f"Mock mode: {drivers[0]} and {drivers[1]} dominate the effort for '{title}'.")
    if schema is AnchorComparisonOutput:
        return AnchorComparisonOutput(
            comparison=f"Mock mode: '{title}' sits near {anchor_titles[0]} and is judged {'bigger' if points >= 8 else 'similar or smaller'} against {anchor_titles[1]}.",
            anchor_titles=anchor_titles,
        )
    if schema is PointsOutput:
        return PointsOutput(points=points, derivation=f"Mock derivation: hashed scope of '{title}' maps to {points} on the modified Fibonacci scale.")
    if schema is PlainLanguageOutput:
        return PlainLanguageOutput(
            plain_language_why=(
                f"This is a {points} because the mocked scorecard puts the deciding weight on scope and dependencies for '{title}'. "
                f"It compares closest to the anchor '{anchor_titles[0]}'. No real model was consulted (mock mode)."
            ),
            tldr=f"{points} - Mock estimate: scope and dependencies decide it.",
            effort=LayerEffort(
                react="Mocked UI adjustments", spring="Mocked service work", existing_code="Mocked integration touchpoints",
                person_days=EffortRange(optimistic=points * 0.5, likely=float(points), pessimistic=points * 1.6),
            ),
        )
    if schema is HiddenTasksOutput:
        return HiddenTasksOutput(hidden_tasks=[
            HiddenTask(task=f"Mock hidden task: audit logging for {title}", weight="medium"),
            HiddenTask(task=f"Mock hidden task: regression tests around {title}", weight="small"),
        ])
    if schema is RisksOutput:
        spike = points >= 8
        return RisksOutput(
            risks=[
                Risk(risk=f"Mock risk: unclear integration contract for {title}", mitigation_or_assumption="Assume the contract is confirmed in refinement."),
                Risk(risk="Mock risk: environment availability", mitigation_or_assumption="Assume test environments exist."),
            ],
            assumptions=["Mock mode is active; no real analysis was performed."],
            spike_recommended=spike,
            spike_reason="Mock mode flags a spike for larger estimates." if spike else None,
        )
    if schema is SplitOutput:
        split = points == 13
        return SplitOutput(
            split_recommended=split,
            rationale="Mock mode: a 13 must be split." if split else "Mock mode: the story is deliverable as one slice.",
            proposed_stories=[f"{title} — happy path (5)", f"{title} — edge cases and audit (5)"] if split else [],
        )
    raise RuntimeError(f"Mock LLM has no builder for schema '{schema.__name__}'")


_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "with", "that", "this", "add", "create",
    "new", "diagram", "show", "make", "into", "from", "using", "please", "our", "then", "when",
    "flow", "between", "should", "which", "node", "connect", "change", "update", "modify",
}


def _keywords(text: str, limit: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", text)
    picks: list[str] = []
    for word in words:
        if word.lower() in _STOPWORDS or len(word) < 3:
            continue
        capital = word[:1].upper() + word[1:]
        if capital not in picks:
            picks.append(capital)
        if len(picks) >= limit:
            break
    return picks or ["System", "Service", "Data"]


def _node_id(label: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", label)[:14]
    return f"{cleaned or 'node'}{index}"


_MOCK_DIAGRAMS = {
    "architecture_beta": "\n".join([
        "architecture-beta",
        "  group cloud(cloud)[Production cloud]",
        "  service web(internet)[Web] in cloud",
        "  service api(server)[API] in cloud",
        "  service db(database)[Database] in cloud",
        "  web:R --> L:api",
        "  api:R --> L:db",
    ]),
    "block": "\n".join([
        "block-beta",
        "  columns 3",
        "  web[\"Web\"] api[\"API\"] db[(\"DB\")]",
        "  web --> api",
        "  api --> db",
    ]),
    "packet": "\n".join([
        "packet",
        "  0-15: \"Source port\"",
        "  16-31: \"Destination port\"",
        "  32-63: \"Sequence number\"",
    ]),
    "class": "\n".join([
        "classDiagram",
        "  class Story",
        "  class Estimator",
        "  Story --> Estimator : analyzed by",
    ]),
    "state": "\n".join([
        "stateDiagram-v2",
        "  [*] --> Draft",
        "  Draft --> InReview",
        "  InReview --> Approved",
    ]),
    "er": "\n".join([
        "erDiagram",
        "  PROJECT ||--o{ STORY : contains",
        "  STORY ||--o{ TASK : proposes",
    ]),
    "requirement": "\n".join([
        "requirementDiagram",
        "  performanceRequirement availability {",
        "    id: NFR1",
        "    text: \"99.9 percent availability\"",
        "    risk: Medium",
        "    verifymethod: Test",
        "  }",
        "  element platform {",
        "    type: system",
        "    docref: platform.md",
        "  }",
        "  platform - satisfies -> availability",
    ]),
    "c4": "\n".join([
        "C4Context",
        "  Person(user, \"User\")",
        "  System(app, \"Story Pointer\")",
        "  Rel(user, app, \"Estimates stories\")",
    ]),
    "gantt": "\n".join([
        "gantt",
        "  title Mock plan",
        "  dateFormat YYYY-MM-DD",
        "  section Delivery",
        "  Build slice :2026-07-01, 5d",
    ]),
    "journey": "\n".join([
        "journey",
        "  title Mock journey",
        "  section Use",
        "    Submit story: 4: User",
        "    Review estimate: 5: User",
    ]),
    "timeline": "\n".join([
        "timeline",
        "  title Mock timeline",
        "  Discover : Scope",
        "  Deliver : Build : Validate",
    ]),
    "mindmap": "\n".join([
        "mindmap",
        "  root((Initiative))",
        "    Experience",
        "    Platform",
        "    Operations",
    ]),
    "quadrant": "\n".join([
        "quadrantChart",
        "  title Mock prioritization",
        "  x-axis Low effort --> High effort",
        "  y-axis Low value --> High value",
        "  \"Core\": [0.35, 0.80]",
    ]),
    "gitgraph": "\n".join([
        "gitGraph",
        "  commit id: \"init\"",
        "  branch feature",
        "  checkout feature",
        "  commit id: \"build\"",
    ]),
    "pie": "\n".join([
        "pie showData",
        "  title Mock effort",
        "  \"Frontend\" : 35",
        "  \"Backend\" : 45",
        "  \"Testing\" : 20",
    ]),
    "xychart": "\n".join([
        "xychart-beta",
        "  title \"Mock velocity\"",
        "  x-axis [Sprint 1, Sprint 2, Sprint 3]",
        "  y-axis \"Points\" 0 --> 50",
        "  line [20, 28, 34]",
    ]),
    "sankey": "\n".join([
        "sankey-beta",
        "  Discovery,Delivery,8",
        "  Delivery,Testing,5",
        "  Testing,Release,4",
    ]),
    "treemap": "\n".join([
        "treemap-beta",
        "  \"Initiative\"",
        "    \"Experience\": 34",
        "    \"Platform\": 21",
    ]),
    "venn": "\n".join([
        "venn-beta",
        "  set Frontend[\"Frontend\"]: 3",
        "  set Backend[\"Backend\"]: 3",
        "  union Frontend,Backend[\"API contracts\"]: 1",
    ]),
}


def _build_diagram_ai(messages: list[Any]) -> BaseModel:
    """Deterministic offline diagram authoring for LLM_PROVIDER=mock."""
    from backend.planning.models import DiagramAIOutput

    text = " ".join(str(getattr(message, "content", message)) for message in messages)
    type_match = re.search(r"DIAGRAM TYPE:\s*([A-Za-z0-9_]+)", text)
    diagram_type = type_match.group(1) if type_match else "architecture"
    instruction = ""
    match = re.search(r"INSTRUCTION:\s*(.+)", text)
    if match:
        instruction = match.group(1).splitlines()[0].strip()
    current = ""
    block = re.search(r"CURRENT DIAGRAM:\s*```mermaid\s*(.+?)```", text, re.DOTALL)
    if block and block.group(1).strip():
        current = block.group(1).strip()

    if current and not re.match(r"^(flowchart|graph)\b", current.strip(), re.IGNORECASE):
        mermaid = current
        message = "Mock mode: kept the current non-flowchart diagram for text editing."
    elif current:
        label = _keywords(instruction, 1)[0]
        node = f"{_node_id(label, 0)}x"
        lines = [current.rstrip(), f'  {node}["{label}"]']
        anchor = re.search(r"^\s*([A-Za-z0-9_]+)\s*[\[({]", current, re.MULTILINE) or re.search(r"\b([A-Za-z0-9_]+)\s*(?:--|==|-\.)", current)
        if anchor:
            lines.append(f"  {anchor.group(1)} --> {node}")
        mermaid = "\n".join(lines)
        message = f"Mock mode: added '{label}' to the diagram."
    elif diagram_type == "sequence":
        mermaid = "\n".join([
            "sequenceDiagram",
            "  actor User",
            "  participant Web",
            "  participant API",
            "  User->>Web: Request estimate",
            "  Web->>API: Stream story",
            "  API-->>Web: Points and reasoning",
        ])
        message = "Mock mode: drafted a sequence diagram from your prompt."
    elif diagram_type in _MOCK_DIAGRAMS:
        mermaid = _MOCK_DIAGRAMS[diagram_type]
        message = f"Mock mode: drafted a {diagram_type.replace('_', ' ')} diagram from your prompt."
    elif diagram_type == "kanban":
        mermaid = "\n".join([
            "kanban",
            "  backlog[Backlog]",
            "    task1[Clarify scope]@{ priority: 'High', assigned: 'Team' }",
            "  delivery[In delivery]",
            "    task2[Build slice]",
            "  done[Done]",
            "    task3[Seed sample data]",
        ])
        message = "Mock mode: drafted a kanban diagram from your prompt."
    elif diagram_type == "radar":
        mermaid = "\n".join([
            "radar-beta",
            "  title Mock readiness",
            "  axis Security, Scale, Delivery, Cost",
            "  curve Current{70, 60, 65, 55}",
            "  curve Target{90, 85, 80, 75}",
            "  max 100",
        ])
        message = "Mock mode: drafted a radar diagram from your prompt."
    else:
        labels = _keywords(instruction)
        ids = [_node_id(label, index) for index, label in enumerate(labels)]
        lines = ["flowchart LR"]
        lines += [f'  {node}["{label}"]' for node, label in zip(ids, labels)]
        lines += [f"  {source} --> {target}" for source, target in zip(ids, ids[1:])]
        mermaid = "\n".join(lines)
        message = f"Mock mode: drafted a {len(ids)}-node flowchart from your prompt."
    return DiagramAIOutput(mermaid=mermaid, message=message)


def _json_after(text: str, label: str) -> Any:
    """Extract the bracket-balanced JSON array/object that follows a label."""
    start = text.find(label)
    if start == -1:
        return None
    segment = text[start + len(label):]
    open_index = next((i for i, ch in enumerate(segment) if ch in "[{"), -1)
    if open_index == -1:
        return None
    opener = segment[open_index]
    closer = "]" if opener == "[" else "}"
    depth = 0
    for i in range(open_index, len(segment)):
        if segment[i] == opener:
            depth += 1
        elif segment[i] == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(segment[open_index:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _build_agentic(schema: type[BaseModel], messages: list[Any]) -> BaseModel:
    """Deterministic offline proposals for the agentic services (LLM_PROVIDER=mock)."""
    from backend.ai.schemas import (
        ChatCommand, C4Scaffold, DraftApi, DraftCapability, DraftChecklistItem, DraftCodeUnit, DraftComponent, DraftConcern,
        DraftContainer, DraftDependency, DraftIntegration, DraftInterface, DraftNfr, DraftOkr, DraftRisk,
        DraftStakeholder, DraftTestCase, FieldSummary, L1BaselineDraft, L2Draft, L3Draft, L4Draft,
        NarrativeOutput, OrchestratorPlan, ProposedStory, ScaffoldElement, ScaffoldRelation,
        StaffingAssignment, StaffingProposal, StoryDecomposition,
    )

    # Parse the human message only — labels like "RESOURCE POOL" also appear in
    # the system instructions, so joining both would match the wrong occurrence.
    human_messages = [m for m in messages if getattr(m, "type", "") == "human"]
    source = human_messages or messages
    text = " ".join(str(getattr(message, "content", message)) for message in source)

    if schema is StaffingProposal:
        available = _json_after(text, "RESOURCE POOL") or []
        squads = _json_after(text, "SQUADS:") or []
        assignments = []
        for index, person in enumerate(available):
            if not squads:
                break
            squad = squads[index % len(squads)]
            allocation = min(person.get("remaining_percent", 0), 50)
            if allocation <= 0:
                continue
            assignments.append(StaffingAssignment(
                staff_id=person["staff_id"], staff_name=person.get("name", ""),
                squad_id=squad["squad_id"], squad_name=squad.get("name", ""),
                role=person.get("hr_role", "") or "Contributor",
                allocation_percent=allocation,
                reason=f"Mock mode: {person.get('name', 'this person')} has {person.get('remaining_percent', 0)}% free and fits {squad.get('name', 'the squad')}.",
            ))
        return StaffingProposal(summary=f"Mock staffing: proposed {len(assignments)} assignment(s) across {len(squads)} squad(s).", assignments=assignments)

    if schema is NarrativeOutput:
        metrics = _json_after(text, "METRICS:") or {}
        portfolio = metrics.get("portfolio", {})
        resources = metrics.get("resources", {})
        return NarrativeOutput(
            headline=f"{portfolio.get('projects', 0)} platforms · {portfolio.get('estimated_pct', 0)}% estimated",
            summary=(
                f"Mock briefing: the portfolio spans {portfolio.get('projects', 0)} platforms with "
                f"{portfolio.get('estimated', 0)}/{portfolio.get('stories', 0)} stories estimated. "
                f"{resources.get('active', 0)} of {resources.get('total', 0)} resources are active, "
                f"{resources.get('on_bench', 0)} on the bench, at {resources.get('avg_utilisation', 0)}% average utilisation."
            ),
            highlights=[
                f"{portfolio.get('squads', 0)} squads with {portfolio.get('members', 0)} people assigned.",
                f"{resources.get('fully_allocated', 0)} people fully allocated.",
            ],
            risks=(["Work items are flagged at risk."] if portfolio.get("at_risk_work_items") else ["No work items are currently at risk."]),
            recommendations=[
                "Move bench resources onto open squads." if resources.get("on_bench") else "Utilisation looks healthy; keep monitoring.",
            ],
        )

    if schema is StoryDecomposition:
        match = re.search(r"ELEMENT \([^)]*\):\s*(.+)", text)
        name = match.group(1).splitlines()[0].strip() if match else "the scope"
        seeds = [("Happy path", "core flow"), ("Validation & errors", "edge cases"), ("Persistence & audit", "data and traceability"), ("Tests & observability", "quality gates")]
        stories = [ProposedStory(
            name=f"{name}: {title}",
            description=f"As a user, I can complete the {focus} for {name}.\nAcceptance:\n- {focus} works end to end\n- covered by tests",
            rationale=f"Mock decomposition slice covering {focus}.",
        ) for title, focus in seeds]
        return StoryDecomposition(summary=f"Mock mode: decomposed '{name}' into {len(stories)} stories.", stories=stories)

    if schema is C4Scaffold:
        desc_match = re.search(r"DESCRIPTION:\s*(.+)", text, re.DOTALL)
        keywords = _keywords(desc_match.group(1) if desc_match else text, 3)
        elements = [
            ScaffoldElement(ref="sys", level="L1", name=f"{keywords[0]} platform", kind="system", description="Mock-scaffolded system."),
            ScaffoldElement(ref="web", level="L2", name=f"{keywords[0].lower()}-web", kind="container", tech="React", parent_ref="sys", description="User-facing web app."),
            ScaffoldElement(ref="svc", level="L2", name=f"{keywords[0].lower()}-service", kind="container", tech="Spring Boot", parent_ref="sys", description="Core service."),
            ScaffoldElement(ref="db", level="L2", name=f"{keywords[0].lower()}-db", kind="container", tech="PostgreSQL", parent_ref="sys", description="System of record."),
            ScaffoldElement(ref="cmp1", level="L3", name=f"{keywords[1]} module", kind="component", parent_ref="svc", description="Mock component."),
            ScaffoldElement(ref="cmp2", level="L3", name=f"{keywords[2]} module", kind="component", parent_ref="svc", description="Mock component."),
        ]
        relations = [
            ScaffoldRelation(source_ref="web", target_ref="svc", label="calls", kind="sync"),
            ScaffoldRelation(source_ref="svc", target_ref="db", label="reads/writes", kind="data"),
        ]
        return C4Scaffold(summary=f"Mock mode: scaffolded a C4 model around '{keywords[0]}'.", elements=elements, relations=relations)

    if schema is L1BaselineDraft:
        name_match = re.search(r"L1 INITIATIVE:\s*(.+)", text)
        name = name_match.group(1).splitlines()[0].strip() if name_match else "the initiative"
        return L1BaselineDraft(
            summary=f"Mock mode: drafted an L1 baseline for '{name}'.",
            vision_statement=f"Deliver {name} as a reliable, secure platform that measurably improves customer and business outcomes.",
            business_problem=f"Today, {name} capabilities are fragmented, slowing delivery and weakening governance.",
            target_users="Customers, product, architecture, engineering, security and portfolio teams.",
            okrs=[
                DraftOkr(objective=f"Establish the {name} baseline", key_result="80% of L1 artifacts approved", metric_name="L1 readiness", target_value="80%", owner="Product Owner"),
                DraftOkr(objective="Improve delivery predictability", key_result="Reduce lead time by 30%", metric_name="Lead time", target_value="-30%", owner="Delivery Manager"),
            ],
            stakeholders=[
                DraftStakeholder(name="Business Sponsor", role="Business Sponsor", stakeholder_type="internal", influence="high", interest="high", raci="Accountable"),
                DraftStakeholder(name="Product Owner", role="Product Owner", stakeholder_type="internal", influence="high", interest="high", raci="Responsible"),
                DraftStakeholder(name="Enterprise Architect", role="Enterprise Architect", stakeholder_type="internal", influence="high", interest="medium", raci="Consulted"),
                DraftStakeholder(name="Security Architect", role="Security Architect", stakeholder_type="internal", influence="medium", interest="medium", raci="Consulted"),
            ],
            capabilities=[
                DraftCapability(name="Customer Experience", description="Channels and journeys.", criticality="high"),
                DraftCapability(name="Core Processing", description="Primary business transactions.", criticality="high"),
                DraftCapability(name="Data & Analytics", description="Reporting and insight.", criticality="medium"),
            ],
            risks=[
                DraftRisk(title="Unclear system ownership", category="architecture", risk_level="high", mitigation="Assign accountable owners in the stakeholder map.", funding_source="Change budget"),
                DraftRisk(title="Integration dependency risk", category="delivery", risk_level="medium", mitigation="Map upstream/downstream dependencies early.", funding_source="Run budget"),
            ],
        )

    if schema is FieldSummary:
        match = re.search(r"DETAIL NOTES:\s*(.+?)\n\nSummarize", text, re.DOTALL)
        notes = (match.group(1) if match else text).strip()
        # Strip markdown syntax and pick the first prose sentence — deterministic offline summary.
        cleaned = []
        for line in notes.splitlines():
            stripped = re.sub(r"^\s*(#{1,6}\s+|[-*+]\s+|>\s+|\d+\.\s+)", "", line).strip()
            stripped = re.sub(r"[*_`#]", "", stripped)
            if stripped:
                cleaned.append(stripped)
        prose = " ".join(cleaned)
        first = re.split(r"(?<=[.!?])\s+", prose)[0] if prose else ""
        summary = (first[:200].strip() or "Summary unavailable (no detail provided).")
        return FieldSummary(summary=summary + (" (mock summary)" if "unavailable" not in summary else ""))

    if schema is L2Draft:
        match = re.search(r"L2 EPIC/CONTAINER SLICE:\s*(.+)", text)
        name = match.group(1).splitlines()[0].strip() if match else "the slice"
        diagram = "\n".join([
            "flowchart LR",
            "  User[User] --> Web[Web App]",
            "  Web --> BFF[BFF API]",
            "  BFF --> Svc[Domain Service]",
            "  Svc --> DB[(Database)]",
            "  BFF --> IAM[Identity Provider]",
        ])
        return L2Draft(
            summary=f"Mock mode: an L2 container architecture for '{name}' — a web app, a BFF, a domain service and a database, secured via the identity provider.",
            container_diagram=diagram,
            containers=[
                DraftContainer(name="Web App", capability="Experience", responsibilities="User-facing UI and journeys.", owner_team="Experience Squad", security_classification="internal"),
                DraftContainer(name="BFF API", capability="Experience", responsibilities="Backend-for-frontend orchestration.", owner_team="Experience Squad", security_classification="internal"),
                DraftContainer(name="Domain Service", capability="Core Processing", responsibilities="Core business logic and rules.", owner_team="Platform Squad", security_classification="confidential"),
                DraftContainer(name="Database", capability="Data", responsibilities="System of record.", owner_team="Platform Squad", security_classification="restricted"),
            ],
            apis=[
                DraftApi(name="GET /profile", provider="Domain Service", consumer="BFF API", api_type="REST", data_classification="confidential", authentication="OAuth2"),
                DraftApi(name="events.updated", provider="Domain Service", consumer="Analytics", api_type="Event", data_classification="internal", authentication="mTLS"),
            ],
            nfrs=[
                DraftNfr(name="API latency", category="performance", metric="p95 latency", target="< 300ms"),
                DraftNfr(name="Availability", category="availability", metric="uptime", target="99.9%"),
                DraftNfr(name="Data encryption", category="security", metric="encryption coverage", target="100%"),
            ],
            integrations=[
                DraftIntegration(name="Identity", source_system="BFF API", target_system="Identity Provider", integration_type="API"),
                DraftIntegration(name="Core Banking", source_system="Domain Service", target_system="Core Banking", integration_type="API"),
            ],
        )

    if schema is L3Draft:
        match = re.search(r"L3 COMPONENT/STORY:\s*(.+)", text)
        name = match.group(1).splitlines()[0].strip() if match else "the component"
        diagram = "\n".join([
            "flowchart TB",
            "  API[Controller] --> SVC[Service]",
            "  SVC --> REPO[Repository]",
            "  SVC --> GW[Gateway]",
            "  REPO --> DB[(Database)]",
        ])
        return L3Draft(
            summary=f"Mock mode: an L3 component design for '{name}' — a controller, a service, a repository and an outbound gateway.",
            component_diagram=diagram,
            components=[
                DraftComponent(name="Controller", component_type="controller", responsibilities="Handle inbound requests and validation.", tech="Spring MVC", pattern="MVC"),
                DraftComponent(name="Service", component_type="service", responsibilities="Business logic and orchestration.", tech="Spring", pattern="Service Layer"),
                DraftComponent(name="Repository", component_type="repository", responsibilities="Persistence and queries.", tech="Spring Data JPA", pattern="Repository"),
                DraftComponent(name="Gateway", component_type="gateway", responsibilities="Outbound calls to dependencies.", tech="Feign", pattern="Gateway"),
            ],
            interfaces=[
                DraftInterface(name="POST /resource", direction="provided", interface_type="REST", contract="Create resource", authentication="OAuth2"),
                DraftInterface(name="ledger.debit", direction="consumed", interface_type="Event", contract="Debit event", authentication="mTLS"),
            ],
            dependencies=[
                DraftDependency(name="Ledger Service", dependency_type="container", target="Ledger Service", criticality="high"),
                DraftDependency(name="Validation library", dependency_type="library", target="hibernate-validator", criticality="low"),
            ],
            concerns=[
                DraftConcern(name="Input validation", category="validation", approach="Bean validation on the request DTOs."),
                DraftConcern(name="Structured logging", category="logging", approach="Correlation id on every request."),
                DraftConcern(name="AuthN/AuthZ", category="security", approach="OAuth2 scopes enforced at the controller."),
            ],
        )

    if schema is L4Draft:
        match = re.search(r"L4 TASK:\s*(.+)", text)
        name = match.group(1).splitlines()[0].strip() if match else "the task"
        diagram = "\n".join([
            "classDiagram",
            "  class Controller {",
            "    +create(req) Response",
            "  }",
            "  class Service {",
            "    +handle(cmd) Result",
            "  }",
            "  Controller --> Service",
        ])
        return L4Draft(
            summary=f"Mock mode: an L4 implementation plan for '{name}' — a controller method, a service method, and their tests.",
            code_diagram=diagram,
            code_units=[
                DraftCodeUnit(name="Controller.create", unit_type="function", responsibility="Parse request, call service, map response.", tech="Java", complexity="low"),
                DraftCodeUnit(name="Service.handle", unit_type="function", responsibility="Apply business rules and persist.", tech="Java", complexity="medium"),
                DraftCodeUnit(name="RequestDto", unit_type="class", responsibility="Validated inbound payload.", tech="Java", complexity="low"),
            ],
            test_cases=[
                DraftTestCase(name="rejects invalid payload", test_type="unit", scenario="Given a request missing required fields", expected="Returns 400 with field errors."),
                DraftTestCase(name="persists on happy path", test_type="integration", scenario="Given a valid request", expected="Record is stored and 201 returned."),
            ],
            checklist=[
                DraftChecklistItem(item="Implement controller + service", category="code"),
                DraftChecklistItem(item="Unit + integration tests green", category="tests"),
                DraftChecklistItem(item="Update API docs", category="docs"),
                DraftChecklistItem(item="Security review of inputs", category="security"),
                DraftChecklistItem(item="Peer code review", category="review"),
            ],
        )

    if schema is ChatCommand:
        msg_match = re.search(r"USER MESSAGE:\s*(.+?)\n\nInterpret", text, re.DOTALL)
        msg = (msg_match.group(1) if msg_match else text).strip()
        low = msg.lower()
        # Known element names from the PROJECT ELEMENTS listing help resolve targets.
        names = re.findall(r"·\s*(.+?)\s*\(", text)
        names.sort(key=len, reverse=True)
        found = next((n for n in names if n.lower() in low), "")
        level_match = re.search(r"\bl([1-4])\b", low)
        level = f"L{level_match.group(1)}" if level_match else ""

        def _after(*words):
            for w in words:
                m = re.search(rf"\b{w}\s+(.+)", msg, re.IGNORECASE)
                if m:
                    return m.group(1).strip().strip('"“”').rstrip("?.")
            return ""

        if re.search(r"\brename\b", low):
            target = re.search(r"rename\s+(.+?)\s+to\s+(.+)", msg, re.IGNORECASE)
            if target:
                return ChatCommand(action="update_element", name=target.group(1).strip(), new_name=target.group(2).strip().rstrip("?."),
                                   reply=f"Rename “{target.group(1).strip()}” — Apply to confirm.")
        if "status" in low and " to " in low:
            st = re.search(r"status\s+to\s+(\w+)", low)
            return ChatCommand(action="update_element", name=found, status=(st.group(1) if st else ""),
                               reply=f"Update status of “{found}” — Apply to confirm.")
        if re.search(r"\b(delete|remove)\b", low):
            return ChatCommand(action="delete_element", name=found or _after("delete", "remove"),
                               reply="Delete that element — Apply to confirm.")
        if re.search(r"\b(create|add|new)\b", low):
            name = ""
            nm = re.search(r"(?:called|named)\s+(.+?)(?:\s+under\s+|$)", msg, re.IGNORECASE)
            if nm:
                name = nm.group(1).strip().strip('"“”')
            parent = ""
            pm = re.search(r"\bunder\s+(.+)", msg, re.IGNORECASE)
            if pm:
                parent = pm.group(1).strip().strip('"“”').rstrip("?.")
            return ChatCommand(action="create_element", level=level, name=name, parent=parent,
                               reply=f"Create {level or 'element'} “{name}” — Apply to confirm.")
        if re.search(r"\b(list|show|how many)\b", low):
            return ChatCommand(action="list", level=level, reply="Here's what I found.")
        if re.search(r"readiness|ready|complete", low):
            return ChatCommand(action="readiness", level=level, name=found, reply="Checking readiness.")
        if re.search(r"next|what should|recommend|roll.?up|report|estimat", low):
            return ChatCommand(action="report", reply="Here's the roll-up and next step.")
        if re.search(r"overview|status|progress|where am i|summary", low):
            return ChatCommand(action="overview", reply="Here's the project status.")
        if "help" in low or "what can you" in low:
            return ChatCommand(action="help", reply="")
        return ChatCommand(action="help", reply="")

    if schema is OrchestratorPlan:
        request = text.lower()
        rules = [
            ("auto_staffing", ("staff", "assign", "squad", "team", "allocat")),
            ("scaffold_c4", ("c4", "context diagram", "scaffold", "architecture model")),
            ("decompose_story", ("decompose", "break", "split", "stories", "story")),
            ("generate_l1_baseline", ("vision", "okr", "baseline", "stakeholder", "capabilit", "risk")),
            ("reporting_narrative", ("report", "summary", "executive", "portfolio")),
            ("review_readiness", ("ready", "readiness", "complete", "govern")),
        ]
        action = "none"
        for candidate, keywords in rules:
            if any(k in request for k in keywords):
                action = candidate
                break
        return OrchestratorPlan(
            action=action,
            rationale=f"Mock router matched the request to '{action}'." if action != "none" else "Mock router found no matching capability.",
            suggested_prompt=text.strip()[:200],
        )

    raise RuntimeError(f"Mock LLM has no agentic builder for schema '{schema.__name__}'")


_AGENTIC_SCHEMAS = {"StaffingProposal", "NarrativeOutput", "StoryDecomposition", "C4Scaffold", "L1BaselineDraft", "OrchestratorPlan", "FieldSummary", "L2Draft", "L3Draft", "L4Draft", "ChatCommand"}


class MockStructuredLLM:
    """Stands in for a structured chat model; returns a valid schema instance."""

    def __init__(self, schema: type[BaseModel]) -> None:
        self.schema = schema

    async def ainvoke(self, messages: list[Any]) -> BaseModel:
        await asyncio.sleep(0.15)  # let the streaming pipeline view animate
        if self.schema.__name__ == "DiagramAIOutput":
            return _build_diagram_ai(messages)
        if self.schema.__name__ in _AGENTIC_SCHEMAS:
            return _build_agentic(self.schema, messages)
        return _build(self.schema, _title(messages))
