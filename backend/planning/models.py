"""Validated API contracts for L1 operating plans."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DIAGRAM_TYPES = (
    "architecture",
    "infrastructure",
    "architecture_beta",
    "block",
    "kanban",
    "packet",
    "sequence",
    "class",
    "state",
    "er",
    "requirement",
    "c4",
    "gantt",
    "journey",
    "timeline",
    "mindmap",
    "quadrant",
    "gitgraph",
    "pie",
    "xychart",
    "sankey",
    "radar",
    "treemap",
    "venn",
)

DiagramType = Literal[
    "architecture",
    "infrastructure",
    "architecture_beta",
    "block",
    "kanban",
    "packet",
    "sequence",
    "class",
    "state",
    "er",
    "requirement",
    "c4",
    "gantt",
    "journey",
    "timeline",
    "mindmap",
    "quadrant",
    "gitgraph",
    "pie",
    "xychart",
    "sankey",
    "radar",
    "treemap",
    "venn",
]


class AgileUnitCreate(BaseModel):
    unit_type: Literal["tribe", "squad"]
    name: str = Field(min_length=1, max_length=160)
    parent_unit_id: str | None = None
    mission: str = Field(default="", max_length=1200)
    lead_name: str = Field(default="", max_length=160)
    capacity_fte: float = Field(default=0, ge=0, le=10000)
    target_velocity: float = Field(default=0, ge=0, le=100000)


class PlanSettingsUpdate(BaseModel):
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")


class AgileUnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    parent_unit_id: str | None = None
    mission: str | None = Field(default=None, max_length=1200)
    lead_name: str | None = Field(default=None, max_length=160)
    capacity_fte: float | None = Field(default=None, ge=0, le=10000)
    target_velocity: float | None = Field(default=None, ge=0, le=100000)


class TeamMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    # Optional link to a person in the global resource directory. When set, the
    # store validates the person exists and caps their allocation across all teams.
    resource_staff_id: str | None = None
    role: str = Field(default="", max_length=160)
    skills: str = Field(default="", max_length=1000)
    location: str = Field(default="", max_length=160)
    allocation_percent: float = Field(default=100, ge=0, le=100)
    monthly_cost: float = Field(default=0, ge=0, le=100000000)


class TeamMemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    resource_staff_id: str | None = None
    role: str | None = Field(default=None, max_length=160)
    skills: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=160)
    allocation_percent: float | None = Field(default=None, ge=0, le=100)
    monthly_cost: float | None = Field(default=None, ge=0, le=100000000)


class WorkItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=2400)
    squad_id: str | None = None
    linked_element_id: str | None = None
    start_date: date
    end_date: date
    status: Literal["planned", "in_progress", "at_risk", "done"] = "planned"
    allocation_percent: float = Field(default=100, ge=0, le=100)
    budget_cost: float = Field(default=0, ge=0, le=10000000000)
    actual_cost: float = Field(default=0, ge=0, le=10000000000)

    @model_validator(mode="after")
    def dates_in_order(self) -> "WorkItemCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class WorkItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=2400)
    squad_id: str | None = None
    linked_element_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["planned", "in_progress", "at_risk", "done"] | None = None
    allocation_percent: float | None = Field(default=None, ge=0, le=100)
    budget_cost: float | None = Field(default=None, ge=0, le=10000000000)
    actual_cost: float | None = Field(default=None, ge=0, le=10000000000)


class DiagramCreate(BaseModel):
    diagram_type: DiagramType
    title: str = Field(min_length=1, max_length=200)
    mermaid_source: str = Field(min_length=1, max_length=50000)
    # Per-node annotations (explanation, custom properties, links, documents).
    # Free-form JSON keyed by mermaid node id; the frontend owns its shape.
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiagramUpdate(BaseModel):
    diagram_type: DiagramType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    mermaid_source: str | None = Field(default=None, min_length=1, max_length=50000)
    metadata: dict[str, Any] | None = None


class DiagramChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class DiagramGenerateRequest(BaseModel):
    """Create a brand-new diagram from a natural-language requirement."""
    prompt: str = Field(min_length=1, max_length=4000)
    diagram_type: DiagramType = "architecture"
    title: str | None = Field(default=None, max_length=200)


class DiagramAssistRequest(BaseModel):
    """Ask the assistant to modify the diagram the user is currently editing."""
    prompt: str = Field(min_length=1, max_length=4000)
    current_source: str = Field(default="", max_length=50000)
    diagram_type: DiagramType = "architecture"
    history: list[DiagramChatTurn] = Field(default_factory=list, max_length=20)


class DiagramAIOutput(BaseModel):
    """Structured LLM contract: a mermaid diagram plus a short chat reply."""
    mermaid: str = Field(min_length=1)
    message: str = ""


class RequirementDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(default="", max_length=500000)
    actor: str = Field(min_length=1, max_length=160)


class RequirementDocumentUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=500000)
    actor: str = Field(min_length=1, max_length=160)
    change_summary: str = Field(default="", max_length=500)
    expected_version: int = Field(ge=1)


class RequirementCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    actor: str = Field(min_length=1, max_length=160)
    parent_comment_id: str | None = None


class RequirementCommentAction(BaseModel):
    action: Literal["approve", "resolve", "reopen"]
    actor: str = Field(min_length=1, max_length=160)


class RequirementReviewAction(BaseModel):
    action: Literal["submit", "approve", "revoke"]
    actor: str = Field(min_length=1, max_length=160)
    note: str = Field(default="", max_length=2000)


class RequirementExportRequest(BaseModel):
    diagram_images: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def payload_size_is_bounded(self) -> "RequirementExportRequest":
        if sum(len(image) for image in self.diagram_images) > 28_000_000:
            raise ValueError("Rendered diagram images must not exceed 28 MB in total")
        return self
