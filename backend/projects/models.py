"""API models for projects and their repo/Jira links."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """A person accountable for the platform (one or more per platform)."""
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=120)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    leads: list[Lead] = Field(default_factory=list, max_length=20)
    sensitivity: Literal["standard", "restricted"] = "standard"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    leads: list[Lead] | None = Field(default=None, max_length=20)
    sensitivity: Literal["standard", "restricted"] | None = None


class RepoLinkCreate(BaseModel):
    url: str = ""
    local_path: str = ""
    provider: str = "git"
    mode: Literal["existing", "new"] = "existing"
    default_branch: str = "main"


class JiraLinkCreate(BaseModel):
    instance_name: str = Field(min_length=1)
    project_key: str = Field(min_length=1, max_length=50)
