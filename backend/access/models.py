"""API contracts for access management.

This is local demo auth: application users *are* people in the resource
directory. An access record assigns each a role and an enabled flag. There are
no passwords or tokens — the frontend gates the UI by role. Roles are ordered
admin > manager > contributor > viewer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "manager", "contributor", "viewer"]
ROLES: tuple[str, ...] = ("admin", "manager", "contributor", "viewer")
DEFAULT_ROLE = "viewer"


class AccessUpdate(BaseModel):
    role: Role | None = None
    enabled: bool | None = None


class AccessCreate(BaseModel):
    staff_id: str = Field(min_length=1)
    role: Role = DEFAULT_ROLE
    enabled: bool = True
