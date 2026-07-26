"""Canonical product taxonomy shared by every L1-L4 workspace."""

from backend.c4.taxonomy import LEVEL_DEFINITIONS, level_definition


def test_value_structure_behavior_change_contract():
    assert [LEVEL_DEFINITIONS[level]["focus"] for level in ("L1", "L2", "L3", "L4")] == [
        "Value",
        "Structure",
        "Behavior",
        "Change",
    ]
    assert LEVEL_DEFINITIONS["L1"]["artifact"] == "Theme / Initiative"
    assert LEVEL_DEFINITIONS["L2"]["artifact"] == "Epic"
    assert LEVEL_DEFINITIONS["L3"]["artifact"] == "Feature / Story"
    assert LEVEL_DEFINITIONS["L4"]["artifact"] == "Task / Sub-task / PR"
    assert set(LEVEL_DEFINITIONS["L2"]["outcomes"]) >= {"applications", "APIs", "data stores", "cloud"}
    assert set(LEVEL_DEFINITIONS["L3"]["outcomes"]) >= {"user journeys", "BPMN", "ERD", "test scenarios"}
    assert set(LEVEL_DEFINITIONS["L4"]["outcomes"]) >= {"CI", "reviews", "IaC", "release package"}


def test_level_definition_returns_an_isolated_copy():
    definition = level_definition("L3")
    definition["outcomes"].append("mutated")
    assert "mutated" not in LEVEL_DEFINITIONS["L3"]["outcomes"]
