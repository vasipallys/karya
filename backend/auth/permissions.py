"""Role → capability map (kept in sync with frontend/src/auth/permissions.js).

Capabilities: admin (see admin area), admin.access, admin.reporting,
admin.resources, admin.integrations (configure connector URLs/credentials —
admin-only), platform.create, platform.edit.
"""

from __future__ import annotations

ROLE_CAPS: dict[str, list[str]] = {
    "admin": ["*"],
    "manager": ["admin", "admin.reporting", "admin.resources", "platform.create", "platform.edit"],
    "contributor": ["platform.create", "platform.edit"],
    "viewer": [],
}


def can(role: str | None, capability: str) -> bool:
    caps = ROLE_CAPS.get(role or "", [])
    return "*" in caps or capability in caps
