"""All estimation node prompts and implementations live here."""

from __future__ import annotations

import asyncio
import json
import re
import types
from typing import Any, Literal, TypeVar, Union, get_args, get_origin

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.graph.state import (
    PARAMETERS,
    AnchorComparisonOutput,
    DriversOutput,
    EstimationState,
    HiddenTasksOutput,
    PlainLanguageOutput,
    PointsOutput,
    RisksOutput,
    ScorecardOutput,
    SplitOutput,
)
from backend.llm.factory import get_structured_llm

T = TypeVar("T", bound=BaseModel)

SYSTEM = """You are a senior full-stack agile estimator for a regulated bank.
The team builds React micro-frontends and Spring Boot microservices on OpenShift.
Be concrete, cautious, concise, and explain every judgment from the supplied evidence.
Never invent requirements. Use plain language and modified Fibonacci only."""


def _context(state: EstimationState, fields: tuple[str, ...]) -> str:
    return json.dumps(
        {field: state.get(field) for field in fields},
        indent=2,
        default=str,
    )


def _parse_structured_result(schema: type[T], result: Any) -> T:
    """Validate structured output, tolerating provider wrappers and JSON envelopes."""
    candidates: list[Any] = []
    parsing_error: Exception | None = None
    if isinstance(result, dict) and {"raw", "parsed", "parsing_error"} <= result.keys():
        if result["parsed"] is not None:
            candidates.append(result["parsed"])
        raw = result.get("raw")
        candidates.append(getattr(raw, "content", raw))
        parsing_error = result.get("parsing_error")
    else:
        candidates.append(result)

    while candidates:
        candidate = candidates.pop(0)
        if candidate is None:
            continue
        if isinstance(candidate, schema):
            return candidate
        if isinstance(candidate, str):
            text = candidate.strip()
            if text.startswith("```"):
                text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                candidates.insert(0, json.loads(text))
            except json.JSONDecodeError:
                continue
            continue
        if isinstance(candidate, list):
            # Some Groq models return [echoed_schema, actual_result]. Prefer the last item.
            candidates[0:0] = list(reversed(candidate))
            continue
        if isinstance(candidate, dict):
            try:
                return schema.model_validate(candidate)
            except Exception:
                for key in ("text", "content", "output"):
                    if key in candidate:
                        candidates.append(candidate[key])

    detail = str(parsing_error or "response did not contain a matching JSON object")
    raise ValueError(detail[:500])


def _annotation_contract(annotation: Any, indent: str = "") -> list[str]:
    """Describe a Pydantic annotation without emitting JSON the model can echo."""
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        return ["one of: " + ", ".join(repr(value) for value in args)]
    if origin is list:
        item = args[0] if args else Any
        description = _annotation_contract(item, indent + "  ")
        return ["array whose items are " + description[0], *description[1:]]
    if origin in {Union, types.UnionType}:
        non_null = [arg for arg in args if arg is not type(None)]
        if len(non_null) == 1:
            return _annotation_contract(non_null[0], indent)
        return [" or ".join(_annotation_contract(arg, indent)[0] for arg in non_null)]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        lines = [f"object `{annotation.__name__}` with fields:"]
        for name, field in annotation.model_fields.items():
            nested = _annotation_contract(field.annotation, indent + "  ")
            requirement = "required" if field.is_required() else "optional"
            lines.append(f"{indent}  - `{name}` ({requirement}): {nested[0]}")
            lines.extend(f"{indent}    {line}" for line in nested[1:])
        return lines
    names = {str: "string", int: "integer", float: "number", bool: "boolean", Any: "any JSON value"}
    return [names.get(annotation, getattr(annotation, "__name__", str(annotation)))]


def _schema_contract(schema: type[BaseModel]) -> str:
    """Create plain-text output instructions rather than an echoable JSON Schema."""
    lines = [
        f"Return one JSON object for `{schema.__name__}`. Do not return the schema itself.",
        "Fields:",
    ]
    for name, field in schema.model_fields.items():
        description = _annotation_contract(field.annotation)
        requirement = "required" if field.is_required() else "optional"
        constraints = []
        for item in field.metadata:
            if hasattr(item, "min_length"):
                constraints.append(f"minimum {item.min_length} items/characters")
            if hasattr(item, "max_length"):
                constraints.append(f"maximum {item.max_length} items/characters")
        suffix = f"; {', '.join(constraints)}" if constraints else ""
        lines.append(f"- `{name}` ({requirement}): {description[0]}{suffix}")
        lines.extend(f"  {line}" for line in description[1:])
    return "\n".join(lines)


def _retry_delay(error: Exception, attempt: int) -> float:
    """Honor provider retry hints, with a small fallback backoff."""
    match = re.search(r"try again in\s+([0-9.]+)s", str(error), flags=re.IGNORECASE)
    return min(float(match.group(1)) + 0.5, 65.0) if match else float(2 ** attempt)


async def _invoke(
    schema: type[T],
    prompt: str,
    state: EstimationState,
    context_fields: tuple[str, ...],
) -> T:
    model = get_structured_llm(schema)
    output_contract = _schema_contract(schema)
    messages = [
        SystemMessage(content=SYSTEM),
        HumanMessage(
            content=(
                f"{prompt}\n\nReturn only one valid JSON object matching the contract exactly. "
                f"The response root must be an object, never an array. Do not use markdown "
                f"or function-call tags.\nOUTPUT CONTRACT:\n{output_contract}"
                f"\n\nCONTEXT:\n{_context(state, context_fields)}"
            )
        ),
    ]
    last_error: Exception | None = None
    for _ in range(2):
        try:
            result = await model.ainvoke(messages)
            return _parse_structured_result(schema, result)
        except Exception as exc:
            last_error = RuntimeError(str(exc)[:500])
            if len(messages) == 2:
                await asyncio.sleep(_retry_delay(exc, 0))
            messages.append(
                HumanMessage(content="The prior output was invalid. Return only schema-valid JSON with every required field.")
            )
    raise RuntimeError(f"The model could not produce valid {schema.__name__} output: {last_error}")


def _trace(node: str, summary: str) -> list[AIMessage]:
    return [AIMessage(content=summary, name=node)]


async def score_parameters(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        ScorecardOutput,
        f"Score exactly these 12 parameters once each as Low, Medium, or High, with a one-line evidence-based reason: {', '.join(PARAMETERS)}.",
        state,
        ("story", "refinement"),
    )
    found = {item.parameter for item in result.scores}
    if found != set(PARAMETERS):
        raise RuntimeError(f"Scorecard omitted parameters: {sorted(set(PARAMETERS) - found)}")
    scores = [item.model_dump() for item in result.scores]
    return {"scorecard": scores, "messages": _trace("score_parameters", "Scored all estimation parameters.")}


async def identify_drivers(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        DriversOutput,
        "Name the 2-3 scorecard parameters that genuinely decide the estimate. Explain why they dominate.",
        state,
        ("story", "scorecard"),
    )
    return {"drivers": result.drivers, "drivers_explanation": result.explanation, "messages": _trace("identify_drivers", "Identified the estimate drivers.")}


async def compare_to_anchors(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        AnchorComparisonOutput,
        "Compare explicitly with named fixed anchors and their points. Say bigger than, smaller than, or similar to each selected anchor and why.",
        state,
        ("story", "scorecard", "drivers", "anchors"),
    )
    return {"anchor_comparison": result.comparison, "anchor_titles": result.anchor_titles, "messages": _trace("compare_to_anchors", "Compared the story with calibration anchors.")}


async def derive_points(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        PointsOutput,
        "Conclude 1, 2, 3, 5, 8, or 13 strictly as a consequence of the scorecard, drivers, and anchor comparison. Defend the conclusion; do not guess.",
        state,
        ("story", "scorecard", "drivers", "anchor_comparison"),
    )
    uncertainty = next((item["score"] for item in state["scorecard"] if item["parameter"] == "uncertainty"), "Low")
    escalation = result.points == 13 or uncertainty == "High"
    return {"points": result.points, "points_derivation": result.derivation, "escalation_required": escalation, "messages": _trace("derive_points", "Derived a Fibonacci estimate from the evidence.")}


async def escalation_branch(state: EstimationState) -> dict[str, Any]:
    return {"spike_recommended": True, "spike_reason": "The estimate is 13 or uncertainty is high; reduce uncertainty before commitment.", "messages": _trace("spike_split_branch", "Flagged the story for spike/split treatment.")}


def route_after_points(state: EstimationState) -> str:
    return "escalate" if state.get("escalation_required") else "continue"


async def write_plain_language_reasoning(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        PlainLanguageOutput,
        "Write a 3-5 sentence 'Why this is an N' explanation for a product owner, naming drivers and an anchor in everyday terms. Also write a one-line TL;DR beginning with 'N -'. Provide React, Spring, existing-code effort and optimistic/likely/pessimistic person-days.",
        state,
        ("story", "drivers", "anchor_comparison", "points", "points_derivation"),
    )
    return {"plain_language_why": result.plain_language_why, "tldr": result.tldr, "effort": result.effort.model_dump(), "messages": _trace("write_plain_language_reasoning", "Explained the estimate in plain language.")}


async def detect_hidden_tasks(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        HiddenTasksOutput,
        "Surface sub-tasks implied by the acceptance criteria but easy to miss, especially audit, entitlement, data residency, cross-market, deployment, and testing work. For each, say why it adds weight. Return none when evidence does not imply any.",
        state,
        ("story", "scorecard", "points"),
    )
    return {"hidden_tasks": [item.model_dump() for item in result.hidden_tasks], "messages": _trace("detect_hidden_tasks", "Checked acceptance criteria for hidden work.")}


async def assess_risks(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        RisksOutput,
        "Give the top 3 concrete risks or unknowns and explicit assumptions. Recommend a spike when uncertainty is high. Preserve an already-triggered spike recommendation.",
        state,
        ("story", "scorecard", "points", "hidden_tasks", "spike_recommended"),
    )
    spike = state.get("spike_recommended", False) or result.spike_recommended
    reason = state.get("spike_reason") or result.spike_reason
    return {"risks": [item.model_dump() for item in result.risks], "assumptions": result.assumptions, "spike_recommended": spike, "spike_reason": reason, "messages": _trace("assess_risks", "Assessed risks, assumptions, and spike need.")}


async def recommend_split(state: EstimationState) -> dict[str, Any]:
    result = await _invoke(
        SplitOutput,
        "Recommend whether to split. A 13 must be split and must include proposed independently valuable sub-stories with suggested Fibonacci sizes in their text. Avoid splitting merely by technical layer.",
        state,
        ("story", "points", "drivers", "risks", "spike_recommended"),
    )
    if state.get("points") == 13:
        result.split_recommended = True
    return {"split_recommendation": result.model_dump(), "messages": _trace("recommend_split", "Completed the split recommendation.")}
