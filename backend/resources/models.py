"""API contracts for the global team-resource directory.

The directory is app-global (not project-scoped) so any module that needs a
person — L1 squads, work-item owners, reporting chains — can point at the same
staff records. The fixed columns mirror the standard staff schema; anything a
team needs beyond that lives in user-defined custom fields (`custom_values`).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

StaffType = Literal["Perm", "Contract"]
StaffStatus = Literal["Active", "Inactive"]
SubStatus = Literal["Allocated", "UnAllocated", "PartiallyAllocated"]

# Reference tables the fixed staff columns draw from. A single lookup store keyed
# by category keeps the three "… defined in X Table" fields uniform and extensible.
LookupCategory = Literal["tech_unit", "rank", "hr_role"]
LOOKUP_CATEGORIES: tuple[str, ...] = ("tech_unit", "rank", "hr_role")

CustomFieldType = Literal["text", "number", "date", "select", "boolean"]


class StaffBase(BaseModel):
    staff_first_name: str = Field(min_length=1, max_length=120)
    staff_last_name: str = Field(min_length=1, max_length=120)
    # Display name; generated from first + last when the client leaves it blank.
    staff_name: str = Field(default="", max_length=240)
    staff_type: StaffType = "Perm"
    staff_status: StaffStatus = "Active"
    sub_status: SubStatus = "UnAllocated"
    tech_unit: str = Field(default="", max_length=120)
    citizenship: str = Field(default="", max_length=120)
    rank: str = Field(default="", max_length=120)
    hr_role: str = Field(default="", max_length=120)
    staff_start_date: date | None = None
    staff_end_date: date | None = None
    reporting_manager_id: str | None = None
    custom_values: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _defaults_and_dates(self) -> "StaffBase":
        if not self.staff_name.strip():
            self.staff_name = f"{self.staff_first_name} {self.staff_last_name}".strip()
        if self.staff_start_date and self.staff_end_date and self.staff_end_date < self.staff_start_date:
            raise ValueError("staff_end_date must be on or after staff_start_date")
        return self


class StaffCreate(StaffBase):
    pass


class StaffUpdate(BaseModel):
    staff_first_name: str | None = Field(default=None, min_length=1, max_length=120)
    staff_last_name: str | None = Field(default=None, min_length=1, max_length=120)
    staff_name: str | None = Field(default=None, max_length=240)
    staff_type: StaffType | None = None
    staff_status: StaffStatus | None = None
    sub_status: SubStatus | None = None
    tech_unit: str | None = Field(default=None, max_length=120)
    citizenship: str | None = Field(default=None, max_length=120)
    rank: str | None = Field(default=None, max_length=120)
    hr_role: str | None = Field(default=None, max_length=120)
    staff_start_date: date | None = None
    staff_end_date: date | None = None
    reporting_manager_id: str | None = None
    custom_values: dict[str, Any] | None = None


class LookupCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)


class LookupUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=160)


class CustomFieldCreate(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    label: str = Field(min_length=1, max_length=160)
    field_type: CustomFieldType = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _select_needs_options(self) -> "CustomFieldCreate":
        if self.field_type == "select" and not self.options:
            raise ValueError("select fields require at least one option")
        return self


class CustomFieldUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=160)
    field_type: CustomFieldType | None = None
    required: bool | None = None
    options: list[str] | None = Field(default=None, max_length=100)
