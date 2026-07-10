"""LangGraph StateGraph wiring and checkpointed compiled graph."""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from backend.graph.checkpoint import get_checkpointer
from backend.graph.nodes import (
    assess_risks,
    compare_to_anchors,
    derive_points,
    detect_hidden_tasks,
    escalation_branch,
    identify_drivers,
    recommend_split,
    route_after_points,
    score_parameters,
    write_plain_language_reasoning,
)
from backend.graph.state import EstimationState


@lru_cache
def get_estimation_graph():
    builder = StateGraph(EstimationState)
    builder.add_node("score_parameters", score_parameters)
    builder.add_node("identify_drivers", identify_drivers)
    builder.add_node("compare_to_anchors", compare_to_anchors)
    builder.add_node("derive_points", derive_points)
    builder.add_node("spike_split_branch", escalation_branch)
    builder.add_node("write_plain_language_reasoning", write_plain_language_reasoning)
    builder.add_node("detect_hidden_tasks", detect_hidden_tasks)
    builder.add_node("assess_risks", assess_risks)
    builder.add_node("recommend_split", recommend_split)

    builder.add_edge(START, "score_parameters")
    builder.add_edge("score_parameters", "identify_drivers")
    builder.add_edge("identify_drivers", "compare_to_anchors")
    builder.add_edge("compare_to_anchors", "derive_points")
    builder.add_conditional_edges(
        "derive_points",
        route_after_points,
        {"escalate": "spike_split_branch", "continue": "write_plain_language_reasoning"},
    )
    builder.add_edge("spike_split_branch", "write_plain_language_reasoning")
    builder.add_edge("write_plain_language_reasoning", "detect_hidden_tasks")
    builder.add_edge("detect_hidden_tasks", "assess_risks")
    builder.add_edge("assess_risks", "recommend_split")
    builder.add_edge("recommend_split", END)
    return builder.compile(checkpointer=get_checkpointer())
