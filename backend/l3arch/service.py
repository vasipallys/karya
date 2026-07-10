"""Deterministic L3 readiness scoring + the Markdown+Mermaid component detail summary."""

from __future__ import annotations

import re
from typing import Any

# Component-design weighted areas (sum = 100).
AREA_WEIGHTS = {
    "l2_alignment": 10,
    "component_diagram": 15,
    "component_breakdown": 15,
    "interfaces": 15,
    "dependencies": 10,
    "design_concerns": 15,
    "security_review": 10,
    "people_raci": 5,
    "approval": 5,
}


def readiness(project_id: str, l3_element_id: str, workspace: dict[str, Any] | None = None) -> dict[str, Any]:
    if workspace is None:
        from backend.l3arch import store
        workspace = {
            "parent": None,
            "arch": store.get_l3(project_id, l3_element_id),
            "components": store.list_components(l3_element_id),
            "interfaces": store.list_interfaces(l3_element_id),
            "dependencies": store.list_dependencies(l3_element_id),
            "concerns": store.list_concerns(l3_element_id),
        }
    arch = workspace["arch"]
    components = workspace["components"]
    interfaces = workspace["interfaces"]
    dependencies = workspace["dependencies"]
    concerns = workspace["concerns"]

    has_diagram = bool((arch["component_diagram"] or "").strip()) or len(components) >= 1
    detailed = [c for c in components if (c["responsibilities"] or "").strip()]
    security_concern = any(c["category"] == "security" for c in concerns)
    owned = [c for c in components if (c["owner"] or "").strip()]

    areas = {
        "l2_alignment": 1.0 if workspace.get("parent") else 0.5,
        "component_diagram": 1.0 if has_diagram else 0.0,
        "component_breakdown": min(1.0, len(detailed) / max(1, len(components))) if components else 0.0,
        "interfaces": 1.0 if interfaces else 0.0,
        "dependencies": 1.0 if dependencies else 0.0,
        "design_concerns": 1.0 if concerns else 0.0,
        "security_review": (0.5 if security_concern else 0.0) + (0.5 if any((i["authentication"] or "").strip() for i in interfaces) else 0.0),
        "people_raci": (len(owned) / len(components)) if components else 0.0,
        "approval": 1.0 if arch["status"] in ("approved", "baselined") else 0.0,
    }
    score = round(sum(min(1.0, areas[k]) * AREA_WEIGHTS[k] for k in AREA_WEIGHTS))

    checklist = [
        ("Linked to an L2 container", bool(workspace.get("parent"))),
        ("Component diagram is created", has_diagram),
        ("Core components are named", len(components) >= 1),
        ("Responsibilities documented per component", len(detailed) >= 1 and len(detailed) == len(components)),
        ("Provided/consumed interfaces captured", len(interfaces) >= 1),
        ("Dependencies mapped", len(dependencies) >= 1),
        ("Design concerns addressed (logging, caching, validation…)", len(concerns) >= 1),
        ("Security concern covered", security_concern or any((i["authentication"] or "").strip() for i in interfaces)),
        ("Owners assigned (RACI)", len(owned) >= 1 and len(owned) == len(components)),
        ("Design approval completed", arch["status"] in ("approved", "baselined")),
    ]
    rec_for = {
        "component_diagram": "Draft the component diagram (or add components to auto-generate one).",
        "component_breakdown": "Give each component clear responsibilities and a type.",
        "interfaces": "Capture the interfaces each component provides/consumes with their contracts.",
        "dependencies": "Map the internal, container and external dependencies.",
        "design_concerns": "Address cross-cutting concerns (logging, caching, validation, error handling).",
        "security_review": "Add a security concern or set authentication on the interfaces.",
        "people_raci": "Assign an owner to every component.",
        "approval": "Complete the design approval workflow to baseline the L3.",
        "l2_alignment": "Link this L3 under an L2 container on the C4 canvas.",
    }
    recommendations = [rec_for[k] for k in sorted(AREA_WEIGHTS, key=lambda x: AREA_WEIGHTS[x], reverse=True) if areas[k] < 1.0 and k in rec_for]

    if score >= 80:
        label = "Ready for L4 implementation"
    elif score >= 50:
        label = "In progress — key gaps remain"
    else:
        label = "Early draft — foundational artifacts missing"

    return {
        "score": score,
        "status_label": label,
        "complete": all(done for _, done in checklist),
        "areas": [{"area": k, "weight": AREA_WEIGHTS[k], "score": round(min(1.0, areas[k]) * 100)} for k in AREA_WEIGHTS],
        "checklist": [{"item": item, "done": done} for item, done in checklist],
        "gaps": [item for item, done in checklist if not done],
        "recommendations": recommendations,
    }


# ---- component detail summary (MD + Mermaid) ----

def _slug(text: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text)[:14]
    return f"{cleaned or 'c'}{index}"


def _fallback_diagram(name: str, components: list[dict[str, Any]]) -> str:
    lines = ["flowchart TB", f'  root["{name}"]']
    for index, component in enumerate(components):
        node = _slug(component["name"], index)
        lines.append(f'  {node}["{component["name"]}<br/>({component["component_type"]})"]')
        lines.append(f"  root --> {node}")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join((str(cell).replace("|", "\\|") or "—") for cell in row) + " |")
    return "\n".join(out)


def engineering_summary(project_id: str, l3_element_id: str) -> dict[str, Any]:
    from backend.l3arch import store

    workspace = store.get_workspace(project_id, l3_element_id)
    element = workspace["element"]
    arch = workspace["arch"]
    components = workspace["components"]
    interfaces = workspace["interfaces"]
    dependencies = workspace["dependencies"]
    concerns = workspace["concerns"]
    readiness_data = workspace["readiness"]
    name = element["name"]

    md: list[str] = [f"# {name} — L3 Component Architecture\n"]
    md.append(f"> **Readiness: {readiness_data['score']}%** · {readiness_data['status_label']}\n")
    if workspace.get("parent"):
        md.append(f"**Linked L2 container:** {workspace['parent']['name']}\n")
    if arch["summary"]:
        md.append(arch["summary"] + "\n")

    md.append("## Component Diagram\n")
    diagram = (arch["component_diagram"] or "").strip() or (_fallback_diagram(name, components) if components else "")
    md.append("```mermaid\n" + diagram + "\n```\n" if diagram else "_No component diagram yet._\n")

    md.append("## Components & Responsibilities\n")
    md.append(_table(["Component", "Type", "Responsibilities", "Tech", "Pattern", "Owner"],
                     [[c["name"], c["component_type"], c["responsibilities"], c["tech"], c["pattern"], c["owner"]] for c in components]) + "\n"
              if components else "_No components defined yet._\n")

    md.append("## Interfaces & Contracts\n")
    md.append(_table(["Interface", "Direction", "Type", "Contract", "Counterpart", "Auth"],
                     [[i["name"], i["direction"], i["interface_type"], i["contract"], i["counterpart"], i["authentication"]] for i in interfaces]) + "\n"
              if interfaces else "_No interfaces captured yet._\n")

    md.append("## Dependencies\n")
    md.append(_table(["Dependency", "Type", "Target", "Reason", "Criticality"],
                     [[d["name"], d["dependency_type"], d["target"], d["reason"], d["criticality"]] for d in dependencies]) + "\n"
              if dependencies else "_No dependencies mapped yet._\n")

    md.append("## Cross-Cutting Design Concerns\n")
    md.append(_table(["Concern", "Category", "Approach", "Status"],
                     [[c["name"], c["category"], c["approach"], c["status"]] for c in concerns]) + "\n"
              if concerns else "_No design concerns captured yet._\n")

    md.append("## Traceability\n")
    trace = traceability(project_id, l3_element_id)
    md.append("```mermaid\n" + trace["mermaid"] + "\n```\n")

    md.append("## Readiness Breakdown\n")
    md.append(_table(["Area", "Weight", "Score"],
                     [[a["area"].replace("_", " ").title(), f"{a['weight']}%", f"{a['score']}%"] for a in readiness_data["areas"]]) + "\n")

    return {"markdown": "\n".join(md), "readiness_score": readiness_data["score"]}


# ---- traceability L2 → L3 → L4 ----

def traceability(project_id: str, l3_element_id: str) -> dict[str, Any]:
    from backend.storage.db import connect

    with connect() as conn:
        l3 = conn.execute("SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (l3_element_id, project_id)).fetchone()
        if l3 is None:
            from backend.l3arch.store import NotFoundError
            raise NotFoundError(f"L3 element '{l3_element_id}' was not found")
        l2 = None
        if l3["parent_id"]:
            row = conn.execute("SELECT id, name, level FROM c4_elements WHERE id = ?", (l3["parent_id"],)).fetchone()
            l2 = dict(row) if row else None
        l4 = [dict(r) for r in conn.execute(
            "SELECT id, name FROM c4_elements WHERE parent_id = ? AND level = 'L4' ORDER BY name", (l3_element_id,)).fetchall()]

    lines = ["flowchart LR"]
    if l2:
        lines.append(f'  L2["L2 · {l2["name"]}"]')
        lines.append(f'  L3["L3 · {l3["name"]}"]')
        lines.append("  L2 --> L3")
    else:
        lines.append(f'  L3["L3 · {l3["name"]}"]')
    for index, child in enumerate(l4):
        node = f"t{index}"
        lines.append(f'  {node}["L4 · {child["name"]}"]')
        lines.append(f"  L3 --> {node}")
    if not l4:
        lines.append('  none["L4: none yet"]')
        lines.append("  L3 --> none")

    return {
        "l2": l2,
        "l3": {"id": l3["id"], "name": l3["name"]},
        "l4_children": l4,
        "l4_count": len(l4),
        "mermaid": "\n".join(lines),
    }
