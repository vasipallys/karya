"""Application pages that administrators can grant or deny per user."""

from __future__ import annotations

from typing import Any

PAGE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"key": "platforms", "label": "Platforms", "capability": "page.platforms",
     "description": "View the platform portfolio and open platform records."},
    {"key": "workspace", "label": "Project workspace", "capability": "page.workspace",
     "description": "Open C4, planning, architecture, workflow and estimation workspaces."},
    {"key": "ask_ai", "label": "Ask AI", "capability": "page.ask_ai",
     "description": "Use the global AI command router."},
    {"key": "guide", "label": "User guide", "capability": "page.guide",
     "description": "Open the application guide from the top navigation."},
    {"key": "admin_access", "label": "Admin · Access", "capability": "admin.access",
     "description": "Manage users, roles and page permissions."},
    {"key": "admin_reporting", "label": "Admin · Reporting", "capability": "admin.reporting",
     "description": "View portfolio and resource reporting."},
    {"key": "admin_resources", "label": "Admin · Resources", "capability": "admin.resources",
     "description": "Manage the shared resource directory and imports."},
    {"key": "admin_integrations", "label": "Admin · Integrations", "capability": "admin.integrations",
     "description": "Configure integration connectors and credentials."},
)

PAGE_KEYS = frozenset(page["key"] for page in PAGE_DEFINITIONS)
CAPABILITY_TO_PAGE = {page["capability"]: page["key"] for page in PAGE_DEFINITIONS}


def definitions() -> list[dict[str, Any]]:
    return [dict(page) for page in PAGE_DEFINITIONS]
