"""Canonical L1-L4 product taxonomy exposed by every architecture workspace."""

from __future__ import annotations

from typing import Any


LEVEL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "L1": {
        "level": "L1",
        "focus": "Value",
        "artifact": "Theme / Initiative",
        "outcomes": ["business goals", "stakeholders", "KPIs", "system context"],
    },
    "L2": {
        "level": "L2",
        "focus": "Structure",
        "artifact": "Epic",
        "outcomes": ["applications", "services", "containers", "APIs", "data stores", "platform", "cloud"],
    },
    "L3": {
        "level": "L3",
        "focus": "Behavior",
        "artifact": "Feature / Story",
        "outcomes": ["user journeys", "components", "sequence flows", "BPMN", "ERD", "test scenarios"],
    },
    "L4": {
        "level": "L4",
        "focus": "Change",
        "artifact": "Task / Sub-task / PR",
        "outcomes": ["code", "tests", "CI", "reviews", "IaC", "release package"],
    },
}


def level_definition(level: str) -> dict[str, Any]:
    """Return a copy so callers cannot mutate the canonical contract."""
    definition = LEVEL_DEFINITIONS[level]
    return {**definition, "outcomes": list(definition["outcomes"])}
