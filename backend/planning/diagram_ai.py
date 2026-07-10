"""LLM-backed diagram authoring: generate a diagram from a requirement and
apply conversational change requests.

Provider selection stays inside the LLM factory; this module only builds
prompts and normalises the returned Mermaid. `LLM_PROVIDER=mock` produces a
deterministic flowchart offline (see backend/llm/mock.py).
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from backend.graph.nodes import _parse_structured_result
from backend.llm.factory import get_structured_llm
from backend.planning.models import DiagramAIOutput

SYSTEM = (
    "You are a senior software architect who expresses systems as Mermaid diagrams.\n"
    "Rules:\n"
    "- Output a single Mermaid diagram matching the requested diagram type and starter header.\n"
    "- Return only syntax that Mermaid 11.x can render.\n"
    "- When the diagram type has addressable nodes, give each node a short alphanumeric id and a clear label.\n"
    "- For flowcharts, shapes you may use include [\"rectangle\"], ([\"stadium\"]), "
    "((\"circle\")), [(\"database\")], {\"decision\"}, {{\"hexagon\"}}, [/\"data\"/], "
    "and v11 object shapes like Node@{ shape: doc, label: \"Document\" }.\n"
    "- For flowchart edges: `A --> B` (dependency), `A -. label .-> B` (event/async), `A ==> B` (primary flow), "
    "`A --- B` (association). Label edges with `A -- text --> B`.\n"
    "- Group related nodes with `subgraph id[\"Title\"] ... end` when it aids clarity.\n"
    "- Keep it readable: prefer 4-15 nodes unless asked for more.\n"
    "- When modifying an existing diagram, keep existing node ids and labels unless the change "
    "requires otherwise, and return the FULL updated diagram, never a diff.\n"
    "Put the diagram in `mermaid` and a one or two sentence summary of what you did in `message`."
)

DEFAULT_HEADERS = {
    "architecture": "flowchart LR",
    "infrastructure": "flowchart TB",
    "architecture_beta": "architecture-beta",
    "block": "block-beta",
    "kanban": "kanban",
    "packet": "packet",
    "sequence": "sequenceDiagram",
    "class": "classDiagram",
    "state": "stateDiagram-v2",
    "er": "erDiagram",
    "requirement": "requirementDiagram",
    "c4": "C4Context",
    "gantt": "gantt",
    "journey": "journey",
    "timeline": "timeline",
    "mindmap": "mindmap",
    "quadrant": "quadrantChart",
    "gitgraph": "gitGraph",
    "pie": "pie showData",
    "xychart": "xychart-beta",
    "sankey": "sankey-beta",
    "radar": "radar-beta",
    "treemap": "treemap-beta",
    "venn": "venn-beta",
}

TYPE_GUIDANCE = {
    "architecture": "Use a readable flowchart for services, boundaries, data stores, events, and dependencies.",
    "infrastructure": "Use a top-to-bottom flowchart with network edges, runtime nodes, queues, databases, and deployment groups.",
    "architecture_beta": "Use Mermaid architecture-beta syntax with group, service, junction, and directional edge declarations.",
    "block": "Use block-beta syntax with columns, blocks, and connectors for precise layout.",
    "kanban": "Use kanban syntax with columns and indented task cards; include task metadata only when useful.",
    "packet": "Use packet syntax with bit ranges or +count fields and quoted field labels.",
    "sequence": "Use sequenceDiagram syntax with actors/participants and request/response messages.",
    "class": "Use classDiagram syntax for domain types, attributes, methods, and relationships.",
    "state": "Use stateDiagram-v2 syntax for lifecycle states and transitions.",
    "er": "Use erDiagram syntax for entities, fields, cardinality, and relationships.",
    "requirement": "Use requirementDiagram syntax for requirements, elements, and satisfy/derive/verify links.",
    "c4": "Use C4Context syntax with Person, System, System_Ext, and Rel declarations.",
    "gantt": "Use gantt syntax with title, dateFormat, sections, task ids, dates, and durations.",
    "journey": "Use journey syntax with sections, steps, scores, and actors.",
    "timeline": "Use timeline syntax with grouped milestones.",
    "mindmap": "Use mindmap syntax with one root and nested branches.",
    "quadrant": "Use quadrantChart syntax with x-axis, y-axis, and coordinate points.",
    "gitgraph": "Use gitGraph syntax with commits, branches, checkouts, and merges.",
    "pie": "Use pie syntax with numeric slices.",
    "xychart": "Use xychart-beta syntax with x-axis, y-axis, and line or bar series.",
    "sankey": "Use sankey-beta syntax with source,target,value rows.",
    "radar": "Use radar-beta syntax with axes, curves, and numeric values.",
    "treemap": "Use treemap-beta syntax with indentation for hierarchy and numeric leaf values.",
    "venn": "Use venn-beta syntax with set and union declarations.",
}

_MERMAID_HEADERS = re.compile(
    r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart|C4Context|requirementDiagram|architecture-beta|block-beta|packet|kanban|radar-beta|treemap-beta|venn-beta|xychart-beta|sankey-beta)\b",
    re.IGNORECASE,
)


def _sanitize_mermaid(text: str, diagram_type: str) -> str:
    """Strip code fences and guarantee a diagram header the renderer accepts."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```[A-Za-z]*\n?", "", body)
        body = re.sub(r"\n?```\s*$", "", body).strip()
    first_line = body.splitlines()[0].strip() if body.splitlines() else ""
    if not _MERMAID_HEADERS.match(first_line):
        body = f"{DEFAULT_HEADERS.get(diagram_type, 'flowchart LR')}\n{body}".strip()
    return body[:50000]


def _build_human(prompt: str, diagram_type: str, current_source: str, history: list[dict]) -> str:
    parts: list[str] = []
    if history:
        convo = "\n".join(f"{turn['role'].upper()}: {turn['content']}" for turn in history[-8:])
        parts.append(f"CONVERSATION SO FAR:\n{convo}")
    if current_source.strip():
        parts.append(f"CURRENT DIAGRAM:\n```mermaid\n{current_source.strip()}\n```")
        task = "Modify the current diagram according to the instruction. Return the full updated diagram."
    else:
        task = "Create a new diagram that satisfies the instruction."
    parts.append(f"DIAGRAM TYPE: {diagram_type}")
    parts.append(f"STARTER HEADER: {DEFAULT_HEADERS.get(diagram_type, 'flowchart LR')}")
    parts.append(f"TYPE GUIDANCE: {TYPE_GUIDANCE.get(diagram_type, TYPE_GUIDANCE['architecture'])}")
    parts.append(f"INSTRUCTION: {prompt.strip()}")
    parts.append(task)
    return "\n\n".join(parts)


async def assist_diagram(
    *,
    prompt: str,
    diagram_type: str = "architecture",
    current_source: str = "",
    history: list[dict] | None = None,
) -> dict[str, str]:
    """Return `{mermaid, message}` for a generation or edit request."""
    model = get_structured_llm(DiagramAIOutput)
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=_build_human(prompt, diagram_type, current_source, history or []))]
    result = await model.ainvoke(messages)
    output = _parse_structured_result(DiagramAIOutput, result)
    mermaid = _sanitize_mermaid(output.mermaid, diagram_type)
    message = output.message.strip() or ("Updated the diagram." if current_source.strip() else "Here is a first draft.")
    return {"mermaid": mermaid, "message": message}


def title_from_prompt(prompt: str) -> str:
    """A concise diagram title derived from the first line of the prompt."""
    first = (prompt or "").strip().splitlines()[0] if prompt.strip() else "Generated diagram"
    words = first.split()
    title = " ".join(words[:8]).strip(" .,:;-")
    return (title[:80] or "Generated diagram")
