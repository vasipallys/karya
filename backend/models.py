"""Shared API and domain models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Story(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    user_story: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    technical_breakdown: str | None = None
    existing_points: float | None = None
    key: str | None = None
    status: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    source: Literal["manual", "jira", "upload"] = "manual"
    jira_instance: str | None = None
    c4_context: dict[str, Any] | None = None

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def normalize_criteria(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.replace(";", "\n").splitlines() if part.strip()]
        return [str(part).strip() for part in value if str(part).strip()]


class EstimateRequest(BaseModel):
    story: Story
    session_id: str | None = None
    refinement: str | None = None


class BatchEstimateRequest(BaseModel):
    stories: list[Story] = Field(min_length=1, max_length=100)
    session_id: str | None = None


class UploadEstimateRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    mapping: dict[str, str | None]
    session_id: str | None = None


class JiraWriteRequest(BaseModel):
    points: int
    confirm: bool = False


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: Any | None = None
    retryable: bool = False
