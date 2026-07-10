"""API contracts for the L2 container-architecture workspace."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class L2Update(BaseModel):
    summary: str = Field(default="", max_length=4000)
    container_diagram: str = Field(default="", max_length=20000)
    status: Literal["draft", "reviewed", "approved", "baselined", "archived"] | None = None


class ContainerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capability: str = Field(default="", max_length=200)
    responsibilities: str = Field(default="", max_length=2000)
    owns_data: str = Field(default="", max_length=600)
    owner_team: str = Field(default="", max_length=160)
    security_classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    nfr_criticality: Literal["high", "medium", "low"] = "medium"
    status: Literal["active", "planned", "retired"] = "active"


class ContainerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    capability: str | None = Field(default=None, max_length=200)
    responsibilities: str | None = Field(default=None, max_length=2000)
    owns_data: str | None = Field(default=None, max_length=600)
    owner_team: str | None = Field(default=None, max_length=160)
    security_classification: Literal["public", "internal", "confidential", "restricted"] | None = None
    nfr_criticality: Literal["high", "medium", "low"] | None = None
    status: Literal["active", "planned", "retired"] | None = None


class ApiCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(default="", max_length=200)
    consumer: str = Field(default="", max_length=200)
    endpoint: str = Field(default="", max_length=400)
    api_type: Literal["REST", "GraphQL", "gRPC", "Event", "Batch", "File"] = "REST"
    data_classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    authentication: str = Field(default="", max_length=160)
    version: str = Field(default="v1", max_length=40)
    owner: str = Field(default="", max_length=160)
    status: Literal["proposed", "active", "deprecated"] = "proposed"


class ApiUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    consumer: str | None = Field(default=None, max_length=200)
    endpoint: str | None = Field(default=None, max_length=400)
    api_type: Literal["REST", "GraphQL", "gRPC", "Event", "Batch", "File"] | None = None
    data_classification: Literal["public", "internal", "confidential", "restricted"] | None = None
    authentication: str | None = Field(default=None, max_length=160)
    version: str | None = Field(default=None, max_length=40)
    owner: str | None = Field(default=None, max_length=160)
    status: Literal["proposed", "active", "deprecated"] | None = None


class NfrCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: Literal["performance", "security", "availability", "scalability", "privacy", "resilience"] = "performance"
    scenario: str = Field(default="", max_length=1000)
    metric: str = Field(default="", max_length=200)
    baseline: str = Field(default="", max_length=100)
    target: str = Field(default="", max_length=100)
    owner: str = Field(default="", max_length=160)
    risk_level: Literal["high", "medium", "low"] = "medium"
    status: Literal["open", "met", "at_risk"] = "open"


class NfrUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: Literal["performance", "security", "availability", "scalability", "privacy", "resilience"] | None = None
    scenario: str | None = Field(default=None, max_length=1000)
    metric: str | None = Field(default=None, max_length=200)
    baseline: str | None = Field(default=None, max_length=100)
    target: str | None = Field(default=None, max_length=100)
    owner: str | None = Field(default=None, max_length=160)
    risk_level: Literal["high", "medium", "low"] | None = None
    status: Literal["open", "met", "at_risk"] | None = None


class IntegrationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_system: str = Field(default="", max_length=200)
    target_system: str = Field(default="", max_length=200)
    integration_type: Literal["API", "Event", "Batch", "File", "UI", "Manual"] = "API"
    data_exchanged: str = Field(default="", max_length=600)
    security_method: str = Field(default="", max_length=160)
    status: Literal["planned", "active", "blocked", "done"] = "planned"


class IntegrationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_system: str | None = Field(default=None, max_length=200)
    target_system: str | None = Field(default=None, max_length=200)
    integration_type: Literal["API", "Event", "Batch", "File", "UI", "Manual"] | None = None
    data_exchanged: str | None = Field(default=None, max_length=600)
    security_method: str | None = Field(default=None, max_length=160)
    status: Literal["planned", "active", "blocked", "done"] | None = None
