"""API contracts for the L4 code / implementation-detail workspace."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

UnitType = Literal["class", "interface", "function", "module", "config", "migration", "test"]
TestType = Literal["unit", "integration", "e2e", "contract", "manual"]
ChecklistCategory = Literal["code", "tests", "docs", "security", "review", "deploy"]


class L4Update(BaseModel):
    summary: str = Field(default="", max_length=4000)
    code_diagram: str = Field(default="", max_length=20000)
    status: Literal["draft", "reviewed", "approved", "done", "archived"] | None = None


class CodeUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    unit_type: UnitType = "class"
    responsibility: str = Field(default="", max_length=1000)
    tech: str = Field(default="", max_length=200)
    path: str = Field(default="", max_length=400)
    complexity: Literal["high", "medium", "low"] = "medium"
    status: Literal["todo", "in_progress", "done"] = "todo"


class CodeUnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit_type: UnitType | None = None
    responsibility: str | None = Field(default=None, max_length=1000)
    tech: str | None = Field(default=None, max_length=200)
    path: str | None = Field(default=None, max_length=400)
    complexity: Literal["high", "medium", "low"] | None = None
    status: Literal["todo", "in_progress", "done"] | None = None


class TestCaseCreate(BaseModel):
    __test__ = False  # not a pytest test class
    name: str = Field(min_length=1, max_length=200)
    test_type: TestType = "unit"
    scenario: str = Field(default="", max_length=1000)
    expected: str = Field(default="", max_length=1000)
    status: Literal["planned", "passing", "failing"] = "planned"


class TestCaseUpdate(BaseModel):
    __test__ = False  # not a pytest test class
    name: str | None = Field(default=None, min_length=1, max_length=200)
    test_type: TestType | None = None
    scenario: str | None = Field(default=None, max_length=1000)
    expected: str | None = Field(default=None, max_length=1000)
    status: Literal["planned", "passing", "failing"] | None = None


class ChecklistCreate(BaseModel):
    item: str = Field(min_length=1, max_length=400)
    category: ChecklistCategory = "code"
    done: bool = False


class ChecklistUpdate(BaseModel):
    item: str | None = Field(default=None, min_length=1, max_length=400)
    category: ChecklistCategory | None = None
    done: bool | None = None
