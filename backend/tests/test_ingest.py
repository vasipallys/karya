import pandas as pd

from backend.ingest.excel import dataframe_payload, rows_to_stories, suggest_mapping


def test_header_mapping_and_row_validation():
    mapping = suggest_mapping(["Summary", "Description", "Acceptance Criteria", "SP"])
    assert mapping == {
        "title": "Summary",
        "user_story": "Description",
        "acceptance_criteria": "Acceptance Criteria",
        "technical_breakdown": None,
        "existing_points": "SP",
    }
    rows = [
        {"Summary": "Valid", "Description": "As a user", "Acceptance Criteria": "One; Two", "SP": "5"},
        {"Summary": "", "Description": "Missing title", "Acceptance Criteria": "", "SP": "bad"},
    ]
    stories, skipped = rows_to_stories(rows, mapping)
    assert stories[0].acceptance_criteria == ["One", "Two"]
    assert stories[0].existing_points == 5
    assert skipped == [{"row": 3, "reason": "Title is blank"}]


def test_dataframe_payload_preserves_all_rows_and_limits_preview():
    payload = dataframe_payload(pd.DataFrame([{"Title": str(index)} for index in range(25)]))
    assert payload["row_count"] == 25
    assert len(payload["preview"]) == 20
    assert len(payload["rows"]) == 25
