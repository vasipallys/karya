"""Structured-output contracts for the agentic services.

These schemas are the contract between the agent prompts and the callers; the
mock provider builds valid instances of each for offline runs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---- Auto-staffing agent ------------------------------------------------

class StaffingAssignment(BaseModel):
    staff_id: str = Field(description="resource_staff_id of the person to assign")
    staff_name: str = ""
    squad_id: str = Field(description="id of the squad to place them in")
    squad_name: str = ""
    role: str = Field(default="", description="role this person plays in the squad")
    allocation_percent: float = Field(ge=0, le=100)
    reason: str = Field(default="", max_length=400)


class StaffingProposal(BaseModel):
    summary: str = Field(default="", max_length=1200)
    assignments: list[StaffingAssignment] = Field(default_factory=list)


# ---- Reporting narrative agent ------------------------------------------

class NarrativeOutput(BaseModel):
    headline: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=2000)
    highlights: list[str] = Field(default_factory=list, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=8)
    recommendations: list[str] = Field(default_factory=list, max_length=8)


# ---- Requirements → stories decomposition -------------------------------

class ProposedStory(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    rationale: str = Field(default="", max_length=400)


class StoryDecomposition(BaseModel):
    summary: str = Field(default="", max_length=1200)
    stories: list[ProposedStory] = Field(default_factory=list, max_length=20)


# ---- C4-from-description scaffold ----------------------------------------

class ScaffoldElement(BaseModel):
    ref: str = Field(description="temporary id used to wire relations within this proposal")
    level: Literal["L1", "L2", "L3"]
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="", max_length=60)
    description: str = Field(default="", max_length=1200)
    tech: str = Field(default="", max_length=200)
    parent_ref: str | None = Field(default=None, description="ref of the parent element, or null for L1")

    @field_validator("ref", "parent_ref", mode="before")
    @classmethod
    def _strip_refs(cls, value):
        return value.strip() if isinstance(value, str) else value


class ScaffoldRelation(BaseModel):
    source_ref: str
    target_ref: str
    label: str = Field(default="", max_length=120)
    kind: str = Field(default="sync", max_length=40)

    @field_validator("source_ref", "target_ref", mode="before")
    @classmethod
    def _strip_refs(cls, value):
        return value.strip() if isinstance(value, str) else value


class C4Scaffold(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    elements: list[ScaffoldElement] = Field(min_length=1, max_length=40)
    relations: list[ScaffoldRelation] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def _valid_tree_and_relations(self) -> "C4Scaffold":
        refs = [element.ref for element in self.elements]
        if any(not ref.strip() for ref in refs):
            raise ValueError("Every scaffold element requires a non-empty ref")
        if len(refs) != len(set(refs)):
            raise ValueError("Scaffold element refs must be unique")

        by_ref = {element.ref: element for element in self.elements}
        roots = [element for element in self.elements if element.level == "L1"]
        if len(roots) != 1:
            raise ValueError("A scaffold requires exactly one L1 root")

        expected_parent = {"L2": "L1", "L3": "L2"}
        for element in self.elements:
            if element.level == "L1":
                if element.parent_ref is not None:
                    raise ValueError("The L1 scaffold root cannot have a parent_ref")
                continue
            if not element.parent_ref:
                raise ValueError(f"A scaffold {element.level} element requires parent_ref")
            parent = by_ref.get(element.parent_ref)
            if parent is None:
                raise ValueError(
                    f"Scaffold parent_ref '{element.parent_ref}' does not reference an element"
                )
            if parent.level != expected_parent[element.level]:
                raise ValueError(
                    f"A scaffold {element.level} element requires an "
                    f"{expected_parent[element.level]} parent"
                )

        for relation in self.relations:
            if relation.source_ref not in by_ref or relation.target_ref not in by_ref:
                raise ValueError("Every scaffold relation endpoint must reference an element")
        return self


# ---- L1 architecture baseline generator ---------------------------------

class DraftOkr(BaseModel):
    objective: str = Field(min_length=1, max_length=400)
    key_result: str = Field(default="", max_length=600)
    metric_name: str = Field(default="", max_length=200)
    target_value: str = Field(default="", max_length=100)
    owner: str = Field(default="", max_length=160)


class DraftStakeholder(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(default="", max_length=160)
    stakeholder_type: Literal["internal", "external", "vendor", "regulator"] = "internal"
    influence: Literal["high", "medium", "low"] = "medium"
    interest: Literal["high", "medium", "low"] = "medium"
    raci: Literal["Responsible", "Accountable", "Consulted", "Informed"] = "Informed"


class DraftCapability(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    criticality: Literal["high", "medium", "low"] = "medium"


class DraftRisk(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    category: Literal["delivery", "architecture", "security", "compliance", "operational", "financial"] = "delivery"
    risk_level: Literal["high", "medium", "low"] = "medium"
    mitigation: str = Field(default="", max_length=1000)
    funding_source: str = Field(default="", max_length=200)


OrchestratorAction = Literal[
    "generate_l1_baseline", "auto_staffing", "decompose_story", "scaffold_c4",
    "reporting_narrative", "review_readiness", "none",
]


class OrchestratorPlan(BaseModel):
    action: OrchestratorAction = "none"
    rationale: str = Field(default="", max_length=600)
    suggested_prompt: str = Field(default="", max_length=1000)


class FieldSummary(BaseModel):
    summary: str = Field(default="", max_length=2000)


# ---- L2 container-architecture generator --------------------------------

class DraftContainer(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capability: str = Field(default="", max_length=200)
    responsibilities: str = Field(default="", max_length=1000)
    owner_team: str = Field(default="", max_length=160)
    security_classification: Literal["public", "internal", "confidential", "restricted"] = "internal"


class DraftApi(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(default="", max_length=200)
    consumer: str = Field(default="", max_length=200)
    api_type: Literal["REST", "GraphQL", "gRPC", "Event", "Batch", "File"] = "REST"
    data_classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    authentication: str = Field(default="", max_length=160)


class DraftNfr(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: Literal["performance", "security", "availability", "scalability", "privacy", "resilience"] = "performance"
    metric: str = Field(default="", max_length=200)
    target: str = Field(default="", max_length=100)


class DraftIntegration(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_system: str = Field(default="", max_length=200)
    target_system: str = Field(default="", max_length=200)
    integration_type: Literal["API", "Event", "Batch", "File", "UI", "Manual"] = "API"


class L2Draft(BaseModel):
    summary: str = Field(default="", max_length=1600)
    container_diagram: str = Field(default="", max_length=8000)
    containers: list[DraftContainer] = Field(default_factory=list, max_length=20)
    apis: list[DraftApi] = Field(default_factory=list, max_length=20)
    nfrs: list[DraftNfr] = Field(default_factory=list, max_length=15)
    integrations: list[DraftIntegration] = Field(default_factory=list, max_length=15)


class L1BaselineDraft(BaseModel):
    summary: str = Field(default="", max_length=1200)
    vision_statement: str = Field(default="", max_length=2000)
    business_problem: str = Field(default="", max_length=2000)
    target_users: str = Field(default="", max_length=1000)
    okrs: list[DraftOkr] = Field(default_factory=list, max_length=12)
    stakeholders: list[DraftStakeholder] = Field(default_factory=list, max_length=20)
    capabilities: list[DraftCapability] = Field(default_factory=list, max_length=20)
    risks: list[DraftRisk] = Field(default_factory=list, max_length=15)


# ---- L3 component-architecture generator --------------------------------

class DraftComponent(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    component_type: Literal["controller", "service", "repository", "gateway", "model", "client", "config", "ui", "other"] = "service"
    responsibilities: str = Field(default="", max_length=1000)
    tech: str = Field(default="", max_length=200)
    pattern: str = Field(default="", max_length=200)


class DraftInterface(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    direction: Literal["provided", "consumed"] = "provided"
    interface_type: Literal["REST", "GraphQL", "gRPC", "Event", "Function", "Message"] = "REST"
    contract: str = Field(default="", max_length=600)
    authentication: str = Field(default="", max_length=160)


class DraftDependency(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dependency_type: Literal["internal", "container", "external", "library"] = "internal"
    target: str = Field(default="", max_length=200)
    criticality: Literal["high", "medium", "low"] = "medium"


class DraftConcern(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: Literal["logging", "caching", "validation", "security", "error_handling", "config", "observability", "resilience"] = "security"
    approach: str = Field(default="", max_length=600)


class L3Draft(BaseModel):
    summary: str = Field(default="", max_length=1600)
    component_diagram: str = Field(default="", max_length=8000)
    components: list[DraftComponent] = Field(default_factory=list, max_length=20)
    interfaces: list[DraftInterface] = Field(default_factory=list, max_length=20)
    dependencies: list[DraftDependency] = Field(default_factory=list, max_length=20)
    concerns: list[DraftConcern] = Field(default_factory=list, max_length=15)


# ---- L4 implementation-detail generator ---------------------------------

class DraftCodeUnit(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    unit_type: Literal["class", "interface", "function", "module", "config", "migration", "test"] = "class"
    responsibility: str = Field(default="", max_length=600)
    tech: str = Field(default="", max_length=200)
    complexity: Literal["high", "medium", "low"] = "medium"


class DraftTestCase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    test_type: Literal["unit", "integration", "e2e", "contract", "manual"] = "unit"
    scenario: str = Field(default="", max_length=600)
    expected: str = Field(default="", max_length=600)


class DraftChecklistItem(BaseModel):
    item: str = Field(min_length=1, max_length=400)
    category: Literal["code", "tests", "docs", "security", "review", "deploy"] = "code"


class L4Draft(BaseModel):
    summary: str = Field(default="", max_length=1600)
    code_diagram: str = Field(default="", max_length=8000)
    code_units: list[DraftCodeUnit] = Field(default_factory=list, max_length=25)
    test_cases: list[DraftTestCase] = Field(default_factory=list, max_length=25)
    checklist: list[DraftChecklistItem] = Field(default_factory=list, max_length=20)


# ---- Conversational assistant -------------------------------------------

class ChatCommand(BaseModel):
    """One interpreted chat intent. Reads execute immediately; the *_element writes
    are surfaced to the user as a proposal to apply."""
    action: Literal[
        "overview", "list", "describe", "readiness", "report",
        "create_element", "update_element", "delete_element", "create_relation",
        "answer", "code", "web_search", "image", "document", "help", "none",
    ] = "help"
    level: str = Field(default="", max_length=4)       # L1–L4 (list / create)
    name: str = Field(default="", max_length=200)      # target element name
    parent: str = Field(default="", max_length=200)    # parent element name (create)
    new_name: str = Field(default="", max_length=200)  # rename target
    status: str = Field(
        default="",
        max_length=40,
        description="Named element status for a list filter or update; use an empty string when no status was requested.",
    )
    description: str = Field(default="", max_length=2000)
    target: str = Field(default="", max_length=200)    # relation target name (create_relation, or create_element + route)
    label: str = Field(default="", max_length=120)     # relation label, e.g. "routes"
    reply: str = Field(default="", max_length=12000)   # markdown answer / generated code

    @field_validator("status", mode="before")
    @classmethod
    def normalize_boolean_status(cls, value):
        """Treat a provider's boolean 'has status' flag as an omitted filter.

        Guessing that true means a concrete lifecycle status could silently
        filter reads or propose the wrong mutation, so the safe value is empty.
        """
        if value is None or isinstance(value, bool):
            return ""
        return value
