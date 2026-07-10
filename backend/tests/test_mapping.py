from pydantic import SecretStr

from backend.config import JiraInstanceSettings
from backend.jira.mapping import adf_to_text, issue_to_story


def config():
    return JiraInstanceSettings(
        name="prod", base_url="https://example.atlassian.net", auth_type="cloud",
        email="a@example.com", api_token=SecretStr("secret"),
        story_points_field="customfield_1", ac_field="customfield_2",
    )


def test_adf_and_custom_fields_are_mapped():
    issue = {"key": "PAY-1", "fields": {
        "summary": "Confirm payment", "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Story body"}]}]},
        "customfield_1": 5, "customfield_2": "First\nSecond", "status": {"name": "Ready"},
        "labels": ["payments"], "components": [{"name": "UI"}],
    }}
    story = issue_to_story(issue, config())
    assert adf_to_text(issue["fields"]["description"]).strip() == "Story body"
    assert story.key == "PAY-1"
    assert story.existing_points == 5
    assert story.acceptance_criteria == ["First", "Second"]


def test_description_acceptance_criteria_fallback():
    issue = {"key": "PAY-2", "fields": {"summary": "Fallback", "description": "Context\nAcceptance Criteria:\n- Audit the change\n- Enforce entitlement"}}
    story = issue_to_story(issue, config().model_copy(update={"ac_field": None}))
    assert story.acceptance_criteria == ["Audit the change", "Enforce entitlement"]
