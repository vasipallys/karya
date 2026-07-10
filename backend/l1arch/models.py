"""API contracts for the L1 architecture baseline artifacts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class VisionUpdate(BaseModel):
    vision_statement: str = Field(default="", max_length=4000)
    business_problem: str = Field(default="", max_length=4000)
    target_users: str = Field(default="", max_length=2000)
    # Rich markdown "more details" backing each summary field.
    vision_statement_details: str = Field(default="", max_length=20000)
    business_problem_details: str = Field(default="", max_length=20000)
    target_users_details: str = Field(default="", max_length=20000)
    strategic_theme: str = Field(default="", max_length=200)
    status: Literal["draft", "approved", "baselined", "archived"] | None = None


class OkrCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=400)
    key_result: str = Field(default="", max_length=600)
    metric_name: str = Field(default="", max_length=200)
    baseline_value: str = Field(default="", max_length=100)
    target_value: str = Field(default="", max_length=100)
    current_value: str = Field(default="", max_length=100)
    owner: str = Field(default="", max_length=160)
    status: Literal["on_track", "at_risk", "off_track", "done"] = "on_track"
    linked_element_id: str | None = None


class OkrUpdate(BaseModel):
    objective: str | None = Field(default=None, min_length=1, max_length=400)
    key_result: str | None = Field(default=None, max_length=600)
    metric_name: str | None = Field(default=None, max_length=200)
    baseline_value: str | None = Field(default=None, max_length=100)
    target_value: str | None = Field(default=None, max_length=100)
    current_value: str | None = Field(default=None, max_length=100)
    owner: str | None = Field(default=None, max_length=160)
    status: Literal["on_track", "at_risk", "off_track", "done"] | None = None
    linked_element_id: str | None = None


class StakeholderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    resource_staff_id: str | None = None
    email: str = Field(default="", max_length=200)
    department: str = Field(default="", max_length=160)
    role: str = Field(default="", max_length=160)
    stakeholder_type: Literal["internal", "external", "vendor", "regulator"] = "internal"
    influence: Literal["high", "medium", "low"] = "medium"
    interest: Literal["high", "medium", "low"] = "medium"
    raci: Literal["Responsible", "Accountable", "Consulted", "Informed"] = "Informed"
    owns: str = Field(default="", max_length=600)
    status: Literal["active", "inactive", "replaced"] = "active"


class StakeholderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    resource_staff_id: str | None = None
    email: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=160)
    role: str | None = Field(default=None, max_length=160)
    stakeholder_type: Literal["internal", "external", "vendor", "regulator"] | None = None
    influence: Literal["high", "medium", "low"] | None = None
    interest: Literal["high", "medium", "low"] | None = None
    raci: Literal["Responsible", "Accountable", "Consulted", "Informed"] | None = None
    owns: str | None = Field(default=None, max_length=600)
    status: Literal["active", "inactive", "replaced"] | None = None


class CapabilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    parent_id: str | None = None
    cap_level: Literal["L1", "L2", "L3"] = "L1"
    business_owner: str = Field(default="", max_length=160)
    technology_owner: str = Field(default="", max_length=160)
    criticality: Literal["high", "medium", "low"] = "medium"
    current_maturity: int = Field(default=1, ge=1, le=5)
    target_maturity: int = Field(default=3, ge=1, le=5)
    strategic_priority: Literal["high", "medium", "low"] = "medium"
    status: Literal["active", "planned", "retired"] = "active"
    linked_element_id: str | None = None


class CapabilityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: str | None = None
    cap_level: Literal["L1", "L2", "L3"] | None = None
    business_owner: str | None = Field(default=None, max_length=160)
    technology_owner: str | None = Field(default=None, max_length=160)
    criticality: Literal["high", "medium", "low"] | None = None
    current_maturity: int | None = Field(default=None, ge=1, le=5)
    target_maturity: int | None = Field(default=None, ge=1, le=5)
    strategic_priority: Literal["high", "medium", "low"] | None = None
    status: Literal["active", "planned", "retired"] | None = None
    linked_element_id: str | None = None


class RiskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    category: Literal["delivery", "architecture", "security", "compliance", "operational", "financial"] = "delivery"
    risk_level: Literal["high", "medium", "low"] = "medium"
    owner: str = Field(default="", max_length=160)
    mitigation: str = Field(default="", max_length=2000)
    funding_source: str = Field(default="", max_length=200)
    approved_budget: float = Field(default=0, ge=0)
    forecast_spend: float = Field(default=0, ge=0)
    actual_spend: float = Field(default=0, ge=0)
    status: Literal["proposed", "approved", "active", "blocked", "completed"] = "proposed"
    target_date: date | None = None
    linked_element_id: str | None = None


class ApprovalDecision(BaseModel):
    approve: bool
    decided_by: str = Field(default="", max_length=160)
    comment: str = Field(default="", max_length=1000)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    author: str = Field(default="", max_length=160)
    artifact_type: str = Field(default="baseline", max_length=40)
    artifact_id: str | None = None


class RiskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    category: Literal["delivery", "architecture", "security", "compliance", "operational", "financial"] | None = None
    risk_level: Literal["high", "medium", "low"] | None = None
    owner: str | None = Field(default=None, max_length=160)
    mitigation: str | None = Field(default=None, max_length=2000)
    funding_source: str | None = Field(default=None, max_length=200)
    approved_budget: float | None = Field(default=None, ge=0)
    forecast_spend: float | None = Field(default=None, ge=0)
    actual_spend: float | None = Field(default=None, ge=0)
    status: Literal["proposed", "approved", "active", "blocked", "completed"] | None = None
    target_date: date | None = None
    linked_element_id: str | None = None
