"""Identity resolution + the route-capability policy used by the RBAC middleware.

Local demo auth: the caller identifies via headers set by the frontend client —
`X-User-Id` (a resource_staff id, whose role is looked up authoritatively) and,
for the password-less bootstrap admin that has no directory id, `X-User-Role`.
"""

from __future__ import annotations

import re

from starlette.requests import Request

from backend.access.models import ROLES
from backend.access.store import effective_role
from backend.storage.db import connect

# Endpoints reachable before/without sign-in.
PUBLIC_PATHS = {"/health", "/config", "/access/login-users", "/access/roles", "/jira/instances", "/docs", "/openapi.json"}

# ABAC: a workspace marked `restricted` admits only these roles (resource sensitivity × role).
_RESTRICTED_ROLES = {"admin", "manager"}
_PROJECT_PATH = re.compile(r"^/projects/([0-9a-f]+)")


def restricted_block(path: str, role: str | None) -> bool:
    """True when the caller's role may not touch this restricted-workspace path."""
    if role in _RESTRICTED_ROLES:
        return False
    match = _PROJECT_PATH.match(path)
    if not match:
        return False
    with connect() as conn:
        row = conn.execute("SELECT sensitivity FROM projects WHERE id = ?", (match.group(1),)).fetchone()
    return bool(row) and row["sensitivity"] == "restricted"


def resolve_role(request: Request) -> str | None:
    staff_id = request.headers.get("X-User-Id")
    if staff_id:
        return effective_role(staff_id)
    header_role = request.headers.get("X-User-Role")
    return header_role if header_role in ROLES else None


def route_policy(method: str, path: str) -> tuple[bool, str | None]:
    """Return (requires_auth, required_capability) for a method+path."""
    if path in PUBLIC_PATHS:
        return False, None
    if path.startswith("/access"):
        return True, "admin.access"
    if path.startswith("/reporting"):
        return True, "admin.reporting"
    if path.startswith("/integrations"):
        # The catalog is readable by any signed-in user; connector configuration
        # (URLs/credentials) is admin-only.
        return (True, None) if path == "/integrations/catalog" else (True, "admin.integrations")
    if path.startswith("/resources"):
        # Reading the directory powers planning dropdowns (contributors need it);
        # only editing it requires the resources capability.
        return (True, None) if method == "GET" else (True, "admin.resources")
    # The chat query/propose endpoint reads and proposes but never persists, so any
    # signed-in user may use it; only /chat/apply (which writes) needs platform.edit.
    if method == "POST" and path.endswith("/chat"):
        return True, None
    if method in ("POST", "PATCH", "PUT", "DELETE"):
        return True, "platform.edit"
    return True, None  # authenticated reads
