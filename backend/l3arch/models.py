"""API contracts for the L3 component-architecture workspace."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ComponentType = Literal["controller", "service", "repository", "gateway", "model", "client", "config", "ui", "other"]
Direction = Literal["provided", "consumed"]
InterfaceType = Literal["REST", "GraphQL", "gRPC", "Event", "Function", "Message"]
DependencyType = Literal["internal", "container", "external", "library"]
ConcernCategory = Literal["logging", "caching", "validation", "security", "error_handling", "config", "observability", "resilience"]


class L3Update(BaseModel):
    summary: str = Field(default="", max_length=4000)
    component_diagram: str = Field(default="", max_length=20000)
    status: Literal["draft", "reviewed", "approved", "baselined", "archived"] | None = None


class ComponentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    component_type: ComponentType = "service"
    responsibilities: str = Field(default="", max_length=2000)
    tech: str = Field(default="", max_length=200)
    pattern: str = Field(default="", max_length=200)
    owner: str = Field(default="", max_length=160)
    status: Literal["active", "planned", "retired"] = "active"


class ComponentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    component_type: ComponentType | None = None
    responsibilities: str | None = Field(default=None, max_length=2000)
    tech: str | None = Field(default=None, max_length=200)
    pattern: str | None = Field(default=None, max_length=200)
    owner: str | None = Field(default=None, max_length=160)
    status: Literal["active", "planned", "retired"] | None = None


class InterfaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    direction: Direction = "provided"
    interface_type: InterfaceType = "REST"
    contract: str = Field(default="", max_length=1000)
    counterpart: str = Field(default="", max_length=200)
    authentication: str = Field(default="", max_length=160)
    status: Literal["proposed", "active", "deprecated"] = "proposed"


class InterfaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    direction: Direction | None = None
    interface_type: InterfaceType | None = None
    contract: str | None = Field(default=None, max_length=1000)
    counterpart: str | None = Field(default=None, max_length=200)
    authentication: str | None = Field(default=None, max_length=160)
    status: Literal["proposed", "active", "deprecated"] | None = None


class DependencyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dependency_type: DependencyType = "internal"
    target: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=600)
    criticality: Literal["high", "medium", "low"] = "medium"
    status: Literal["active", "planned", "retired"] = "active"


class DependencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    dependency_type: DependencyType | None = None
    target: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=600)
    criticality: Literal["high", "medium", "low"] | None = None
    status: Literal["active", "planned", "retired"] | None = None


class ConcernCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: ConcernCategory = "security"
    approach: str = Field(default="", max_length=1000)
    owner: str = Field(default="", max_length=160)
    status: Literal["planned", "implemented", "gap"] = "planned"


class ConcernUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: ConcernCategory | None = None
    approach: str | None = Field(default=None, max_length=1000)
    owner: str | None = Field(default=None, max_length=160)
    status: Literal["planned", "implemented", "gap"] | None = None
