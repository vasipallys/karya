from backend.graph.nodes import route_after_points


def test_high_uncertainty_or_thirteen_routes_to_escalation():
    assert route_after_points({"escalation_required": True}) == "escalate"
    assert route_after_points({"escalation_required": False}) == "continue"
