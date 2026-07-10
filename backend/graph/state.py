"""Typed LangGraph state and structured node output contracts."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, field_validator

ScoreLevel = Literal["Low", "Medium", "High"]
PARAMETERS = [
    "complexity",
    "volume",
    "uncertainty",
    "react_scope",
    "spring_scope",
    "existing_code_scope",
    "dependencies",
    "nfrs",
    "testing",
    "compliance_audit",
    "familiarity",
    "dod_overhead",
]


class ParameterScore(BaseModel):
    parameter: Literal[
        "complexity", "volume", "uncertainty", "react_scope", "spring_scope",
        "existing_code_scope", "dependencies", "nfrs", "testing",
        "compliance_audit", "familiarity", "dod_overhead"
    ]
    score: ScoreLevel
    reason: str = Field(min_length=5, max_length=240)


class ScorecardOutput(BaseModel):
    scores: list[ParameterScore]


class DriversOutput(BaseModel):
    drivers: list[str] = Field(min_length=2, max_length=3)
    explanation: str


class AnchorComparisonOutput(BaseModel):
    comparison: str
    anchor_titles: list[str] = Field(min_length=1)

    @field_validator("anchor_titles", mode="after")
    @classmethod
    def keep_top_three(cls, value: list[str]) -> list[str]:
        # Small models often echo every anchor; keep the closest three rather than fail the run.
        return value[:3]


class PointsOutput(BaseModel):
    points: Literal[1, 2, 3, 5, 8, 13]
    derivation: str


class EffortRange(BaseModel):
    optimistic: float = Field(ge=0)
    likely: float = Field(ge=0)
    pessimistic: float = Field(ge=0)


class LayerEffort(BaseModel):
    react: str
    spring: str
    existing_code: str
    person_days: EffortRange


class PlainLanguageOutput(BaseModel):
    plain_language_why: str
    tldr: str
    effort: LayerEffort


class HiddenTask(BaseModel):
    task: str
    weight: str


class HiddenTasksOutput(BaseModel):
    hidden_tasks: list[HiddenTask]


class Risk(BaseModel):
    risk: str
    mitigation_or_assumption: str


class RisksOutput(BaseModel):
    risks: list[Risk] = Field(min_length=1, max_length=3)
    assumptions: list[str]
    spike_recommended: bool
    spike_reason: str | None = None


class SplitOutput(BaseModel):
    split_recommended: bool
    rationale: str
    proposed_stories: list[str] = Field(default_factory=list)


class EstimationState(TypedDict, total=False):
    story: dict[str, Any]
    anchors: list[dict[str, Any]]
    scorecard: list[dict[str, Any]]
    drivers: list[str]
    drivers_explanation: str
    anchor_comparison: str
    anchor_titles: list[str]
    points: int
    points_derivation: str
    plain_language_why: str
    tldr: str
    effort: dict[str, Any]
    hidden_tasks: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    assumptions: list[str]
    spike_recommended: bool
    spike_reason: str | None
    split_recommendation: dict[str, Any]
    escalation_required: bool
    refinement: str | None
    messages: Annotated[list[AnyMessage], add_messages]
