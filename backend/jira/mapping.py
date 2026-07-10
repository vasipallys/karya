"""Custom-field-aware Jira issue mapping in one tunable module."""

from __future__ import annotations

import re
from typing import Any

from backend.config import JiraInstanceSettings
from backend.models import Story


def adf_to_text(value: Any) -> str:
    """Flatten Jira Cloud Atlassian Document Format or accept plain server text."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (adf_to_text(item) for item in value)))
    if isinstance(value, dict):
        text = value.get("text", "")
        children = adf_to_text(value.get("content", []))
        return "\n".join(filter(None, (text, children)))
    return str(value)


def split_acceptance_criteria(value: Any, description: str) -> list[str]:
    text = adf_to_text(value).strip()
    if not text:
        match = re.search(
            r"(?:acceptance criteria|given\s.+?when\s.+?then)\s*:?\s*(.+)",
            description,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = match.group(1) if match else ""
    lines = re.split(r"(?:\r?\n|;)+", text)
    return [re.sub(r"^[\s*\-\d.)]+", "", line).strip() for line in lines if line.strip()]


def issue_to_story(issue: dict[str, Any], config: JiraInstanceSettings) -> Story:
    fields = issue.get("fields") or {}
    description = adf_to_text(fields.get("description"))
    ac_value = fields.get(config.ac_field) if config.ac_field else None
    points = fields.get(config.story_points_field) if config.story_points_field else None
    return Story(
        title=fields.get("summary") or issue.get("key") or "Untitled Jira issue",
        user_story=description,
        acceptance_criteria=split_acceptance_criteria(ac_value, description),
        existing_points=points,
        key=issue.get("key"),
        status=(fields.get("status") or {}).get("name"),
        labels=fields.get("labels") or [],
        components=[item.get("name", "") for item in fields.get("components") or [] if item.get("name")],
        source="jira",
        jira_instance=config.name,
    )
