"""Deterministic L4 implementation-readiness scoring + the Markdown+Mermaid implementation summary."""

from __future__ import annotations

import re
from typing import Any

# Implementation-readiness weighted areas (sum = 100) — lean, execution-focused.
AREA_WEIGHTS = {
    "l3_alignment": 15,
    "code_units": 25,
    "test_coverage": 25,
    "dod_checklist": 25,
    "diagram": 10,
}


def readiness(project_id: str, l4_element_id: str, workspace: dict[str, Any] | None = None) -> dict[str, Any]:
    if workspace is None:
        from backend.l4arch import store
        workspace = {
            "parent": None,
            "arch": store.get_l4(project_id, l4_element_id),
            "code_units": store.list_code_units(l4_element_id),
            "test_cases": store.list_test_cases(l4_element_id),
            "checklist": store.list_checklist(l4_element_id),
        }
    arch = workspace["arch"]
    code_units = workspace["code_units"]
    test_cases = workspace["test_cases"]
    checklist = workspace["checklist"]

    has_diagram = bool((arch["code_diagram"] or "").strip())
    described = [u for u in code_units if (u["responsibility"] or "").strip()]
    dod_done = [c for c in checklist if c["done"]]

    areas = {
        "l3_alignment": 1.0 if workspace.get("parent") else 0.5,
        "code_units": min(1.0, len(described) / max(1, len(code_units))) if code_units else 0.0,
        "test_coverage": 1.0 if test_cases else 0.0,
        "dod_checklist": (len(dod_done) / len(checklist)) if checklist else 0.0,
        "diagram": 1.0 if has_diagram else 0.0,
    }
    score = round(sum(min(1.0, areas[k]) * AREA_WEIGHTS[k] for k in AREA_WEIGHTS))

    checklist_items = [
        ("Linked to an L3 component", bool(workspace.get("parent"))),
        ("Code units are identified", len(code_units) >= 1),
        ("Responsibilities documented per unit", len(described) >= 1 and len(described) == len(code_units)),
        ("Test cases are planned", len(test_cases) >= 1),
        ("Definition-of-Done checklist started", len(checklist) >= 1),
        ("Definition-of-Done complete", len(checklist) >= 1 and len(dod_done) == len(checklist)),
        ("Class/sequence diagram drafted", has_diagram),
    ]
    rec_for = {
        "code_units": "Break the task into code units (classes/functions) with responsibilities.",
        "test_coverage": "Add the test cases (unit/integration) that will prove the task.",
        "dod_checklist": "Work through the Definition-of-Done checklist items.",
        "diagram": "Draft a class or sequence diagram for the implementation.",
        "l3_alignment": "Link this L4 task under an L3 component on the C4 canvas.",
    }
    recommendations = [rec_for[k] for k in sorted(AREA_WEIGHTS, key=lambda x: AREA_WEIGHTS[x], reverse=True) if areas[k] < 1.0 and k in rec_for]

    if score >= 80:
        label = "Ready to implement"
    elif score >= 50:
        label = "In progress — details being filled in"
    else:
        label = "Early draft — implementation not yet specified"

    return {
        "score": score,
        "status_label": label,
        "complete": all(done for _, done in checklist_items),
        "areas": [{"area": k, "weight": AREA_WEIGHTS[k], "score": round(min(1.0, areas[k]) * 100)} for k in AREA_WEIGHTS],
        "checklist": [{"item": item, "done": done} for item, done in checklist_items],
        "gaps": [item for item, done in checklist_items if not done],
        "recommendations": recommendations,
    }


# ---- implementation summary (MD + Mermaid) ----

def _slug(text: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text)[:14]
    return f"{cleaned or 'u'}{index}"


def _fallback_diagram(name: str, code_units: list[dict[str, Any]]) -> str:
    lines = ["classDiagram"]
    if not code_units:
        return ""
    for index, unit in enumerate(code_units):
        cls = _slug(unit["name"], index)
        lines.append(f'  class {cls} {{')
        lines.append(f'    <<{unit["unit_type"]}>>')
        if (unit["responsibility"] or "").strip():
            lines.append(f'    +{re.sub(r"[^A-Za-z0-9 ]", "", unit["responsibility"])[:40]}')
        lines.append("  }")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join((str(cell).replace("|", "\\|") or "—") for cell in row) + " |")
    return "\n".join(out)


def implementation_summary(project_id: str, l4_element_id: str) -> dict[str, Any]:
    from backend.l4arch import store

    workspace = store.get_workspace(project_id, l4_element_id)
    element = workspace["element"]
    arch = workspace["arch"]
    code_units = workspace["code_units"]
    test_cases = workspace["test_cases"]
    checklist = workspace["checklist"]
    readiness_data = workspace["readiness"]
    name = element["name"]

    md: list[str] = [f"# {name} — L4 Implementation Detail\n"]
    md.append(f"> **Readiness: {readiness_data['score']}%** · {readiness_data['status_label']}\n")
    if workspace.get("parent"):
        md.append(f"**Linked L3 component:** {workspace['parent']['name']}\n")
    if arch["summary"]:
        md.append(arch["summary"] + "\n")

    md.append("## Implementation Diagram\n")
    diagram = (arch["code_diagram"] or "").strip() or _fallback_diagram(name, code_units)
    md.append("```mermaid\n" + diagram + "\n```\n" if diagram else "_No implementation diagram yet._\n")

    md.append("## Code Units\n")
    md.append(_table(["Unit", "Type", "Responsibility", "Tech", "Path", "Complexity", "Status"],
                     [[u["name"], u["unit_type"], u["responsibility"], u["tech"], u["path"], u["complexity"], u["status"]] for u in code_units]) + "\n"
              if code_units else "_No code units defined yet._\n")

    md.append("## Test Cases\n")
    md.append(_table(["Test", "Type", "Scenario", "Expected", "Status"],
                     [[t["name"], t["test_type"], t["scenario"], t["expected"], t["status"]] for t in test_cases]) + "\n"
              if test_cases else "_No test cases planned yet._\n")

    md.append("## Definition of Done\n")
    if checklist:
        md.append("\n".join(f"- [{'x' if c['done'] else ' '}] **{c['category']}** — {c['item']}" for c in checklist) + "\n")
    else:
        md.append("_No Definition-of-Done items yet._\n")

    md.append("## Traceability\n")
    trace = traceability(project_id, l4_element_id)
    md.append("```mermaid\n" + trace["mermaid"] + "\n```\n")

    md.append("## Readiness Breakdown\n")
    md.append(_table(["Area", "Weight", "Score"],
                     [[a["area"].replace("_", " ").title(), f"{a['weight']}%", f"{a['score']}%"] for a in readiness_data["areas"]]) + "\n")

    return {"markdown": "\n".join(md), "readiness_score": readiness_data["score"]}


# ---- traceability L2 → L3 → L4 (upward chain, this task highlighted) ----

def traceability(project_id: str, l4_element_id: str) -> dict[str, Any]:
    from backend.storage.db import connect

    with connect() as conn:
        l4 = conn.execute("SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (l4_element_id, project_id)).fetchone()
        if l4 is None:
            from backend.l4arch.store import NotFoundError
            raise NotFoundError(f"L4 element '{l4_element_id}' was not found")
        l3 = None
        l2 = None
        if l4["parent_id"]:
            row = conn.execute("SELECT id, name, level, parent_id FROM c4_elements WHERE id = ?", (l4["parent_id"],)).fetchone()
            l3 = dict(row) if row else None
            if l3 and l3.get("parent_id"):
                prow = conn.execute("SELECT id, name, level FROM c4_elements WHERE id = ?", (l3["parent_id"],)).fetchone()
                l2 = dict(prow) if prow else None

    lines = ["flowchart LR"]
    prev = None
    if l2:
        lines.append(f'  L2["L2 · {l2["name"]}"]')
        prev = "L2"
    if l3:
        lines.append(f'  L3["L3 · {l3["name"]}"]')
        if prev:
            lines.append(f"  {prev} --> L3")
        prev = "L3"
    lines.append(f'  L4["L4 · {l4["name"]}"]')
    if prev:
        lines.append(f"  {prev} --> L4")

    return {
        "l2": {"id": l2["id"], "name": l2["name"]} if l2 else None,
        "l3": {"id": l3["id"], "name": l3["name"]} if l3 else None,
        "l4": {"id": l4["id"], "name": l4["name"]},
        "mermaid": "\n".join(lines),
    }
