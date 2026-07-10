"""API models and level rules for the C4 model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

C4Level = Literal["L1", "L2", "L3", "L4"]
LEVELS: list[str] = ["L1", "L2", "L3", "L4"]

ARTIFACT_FOR_LEVEL: dict[str, str] = {
    "L1": "initiative",
    "L2": "epic",
    "L3": "story",
    "L4": "task",
}

CROSS_CUTTING_LEVELS: dict[str, set[str]] = {
    "bug": {"L3", "L4"},
    "tech_debt": {"L2", "L3"},
    "arch_flow": {"L2", "L3"},
}


class C4ElementCreate(BaseModel):
    level: C4Level
    name: str = Field(min_length=1, max_length=200)
    kind: str = ""
    description: str = ""
    parent_id: str | None = None
    tech: str = ""
    code_path: str = ""
    status: str = "active"
    pos_x: float | None = None
    pos_y: float | None = None


class C4ElementUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    description: str | None = None
    parent_id: str | None = None
    tech: str | None = None
    code_path: str | None = None
    status: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class C4RelationCreate(BaseModel):
    source_id: str
    target_id: str
    label: str = ""
    kind: Literal["sync", "async", "data"] = "sync"


class ArtifactTagRequest(BaseModel):
    artifact_type: Literal["bug", "tech_debt", "arch_flow"]
    jira_issue_key: str | None = None


class ElementEstimateRequest(BaseModel):
    refinement: str | None = None
    session_id: str | None = None


class JiraArtifactRequest(BaseModel):
    confirm: bool = False
    link_existing_key: str | None = None


class JiraImportRequest(BaseModel):
    instance_name: str | None = None
    project_key: str | None = None
    status: str | None = None
    max_issues: int = Field(default=100, ge=1, le=500)


class RepoScanRequest(BaseModel):
    local_path: str | None = None
    apply: bool = False
