from langchain_core.messages import AIMessage

from backend.graph.nodes import _parse_structured_result, _schema_contract
from backend.graph.state import DriversOutput


def test_parses_provider_raw_json_when_langchain_parser_failed():
    result = {
        "raw": AIMessage(content='{"drivers":["dependencies","uncertainty"],"explanation":"External integration determines the estimate."}'),
        "parsed": None,
        "parsing_error": ValueError("provider parser failed"),
    }
    parsed = _parse_structured_result(DriversOutput, result)
    assert parsed.drivers == ["dependencies", "uncertainty"]


def test_uses_actual_result_when_provider_echoes_schema_in_array():
    result = {
        "raw": AIMessage(content='[{"title":"DriversOutput"},{"drivers":["dependencies","testing"],"explanation":"Integration and verification dominate."}]'),
        "parsed": None,
        "parsing_error": ValueError("root should be an object"),
    }
    parsed = _parse_structured_result(DriversOutput, result)
    assert parsed.drivers == ["dependencies", "testing"]


def test_contract_is_plain_text_that_cannot_be_echoed_as_json_schema():
    contract = _schema_contract(DriversOutput)
    assert "`drivers` (required): array" in contract
    assert "minimum 2 items/characters" in contract
    assert '"properties"' not in contract
    assert not contract.lstrip().startswith("{")
