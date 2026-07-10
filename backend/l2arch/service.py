"""Deterministic L2 readiness scoring + the Markdown+Mermaid engineering summary."""

from __future__ import annotations

import re
from typing import Any

# Section 15 weights.
AREA_WEIGHTS = {
    "l1_alignment": 10,
    "container_diagram": 15,
    "service_boundaries": 15,
    "api_contracts": 15,
    "deployment_topology": 10,
    "nfr_coverage": 15,
    "security_review": 10,
    "people_raci": 5,
    "approval": 5,
}


def readiness(project_id: str, l2_element_id: str, workspace: dict[str, Any] | None = None) -> dict[str, Any]:
    if workspace is None:
        from backend.l2arch import store
        workspace = {
            "parent": None,
            "arch": store.get_l2(project_id, l2_element_id),
            "containers": store.list_containers(l2_element_id),
            "apis": store.list_apis(l2_element_id),
            "nfrs": store.list_nfrs(l2_element_id),
            "integrations": store.list_integrations(l2_element_id),
        }
    arch = workspace["arch"]
    containers = workspace["containers"]
    apis = workspace["apis"]
    nfrs = workspace["nfrs"]
    integrations = workspace["integrations"]

    has_diagram = bool((arch["container_diagram"] or "").strip()) or len(containers) >= 1
    boundaried = [c for c in containers if (c["responsibilities"] or "").strip() and (c["owner_team"] or "").strip()]
    security_nfr = any(n["category"] == "security" for n in nfrs)
    sensitive_owned = any(c["security_classification"] in ("confidential", "restricted") for c in containers)
    owned = [c for c in containers if (c["owner_team"] or "").strip()]

    areas = {
        "l1_alignment": 1.0 if workspace.get("parent") else 0.5,
        "container_diagram": 1.0 if has_diagram else 0.0,
        "service_boundaries": min(1.0, len(boundaried) / max(1, len(containers))) if containers else 0.0,
        "api_contracts": 1.0 if apis else 0.0,
        "deployment_topology": 1.0 if integrations else 0.0,
        "nfr_coverage": 1.0 if nfrs else 0.0,
        "security_review": (0.5 if security_nfr else 0.0) + (0.5 if (sensitive_owned or security_nfr) else 0.0),
        "people_raci": (len(owned) / len(containers)) if containers else 0.0,
        "approval": 1.0 if arch["status"] in ("approved", "baselined") else 0.0,
    }
    score = round(sum(min(1.0, areas[k]) * AREA_WEIGHTS[k] for k in AREA_WEIGHTS))

    checklist = [
        ("Linked to an L1 initiative/epic", bool(workspace.get("parent"))),
        ("Container diagram is created", has_diagram),
        ("Core containers are named", len(containers) >= 1),
        ("Service boundaries documented (responsibilities + owner)", len(boundaried) >= 1),
        ("APIs are identified", len(apis) >= 1),
        ("Data classification captured on APIs", any((a["data_classification"] or "") for a in apis)),
        ("Deployment / integration plan defined", len(integrations) >= 1),
        ("NFRs are captured", len(nfrs) >= 1),
        ("Security review covered", security_nfr or sensitive_owned),
        ("Owners assigned (RACI)", len(owned) >= 1 and len(owned) == len(containers)),
        ("Approval completed", arch["status"] in ("approved", "baselined")),
    ]
    rec_for = {
        "container_diagram": "Draft the C4 container diagram (or add containers to auto-generate one).",
        "service_boundaries": "Give each container clear responsibilities and an owner team.",
        "api_contracts": "Capture the APIs each container provides/consumes with auth + version.",
        "deployment_topology": "Define the integration/deployment plan (source→target, security).",
        "nfr_coverage": "Add the key NFRs (performance, security, availability) with targets.",
        "security_review": "Add a security NFR or mark sensitive-data containers.",
        "people_raci": "Assign an owner team to every container.",
        "approval": "Complete the approval workflow to baseline the L2.",
        "l1_alignment": "Link this L2 under an L1 initiative on the C4 canvas.",
    }
    recommendations = [rec_for[k] for k in sorted(AREA_WEIGHTS, key=lambda x: AREA_WEIGHTS[x], reverse=True) if areas[k] < 1.0 and k in rec_for]

    if score >= 80:
        label = "Ready for L3 component design"
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


# ---- engineering summary (MD + Mermaid) ----

def _slug(text: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text)[:14]
    return f"{cleaned or 'c'}{index}"


def _fallback_diagram(name: str, containers: list[dict[str, Any]]) -> str:
    lines = ["flowchart LR", f'  root["{name}"]']
    for index, container in enumerate(containers):
        node = _slug(container["name"], index)
        lines.append(f'  {node}["{container["name"]}"]')
        lines.append(f"  root --> {node}")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join((str(cell).replace("|", "\\|") or "—") for cell in row) + " |")
    return "\n".join(out)


def engineering_summary(project_id: str, l2_element_id: str) -> dict[str, Any]:
    from backend.l2arch import store

    workspace = store.get_workspace(project_id, l2_element_id)
    element = workspace["element"]
    arch = workspace["arch"]
    containers = workspace["containers"]
    apis = workspace["apis"]
    nfrs = workspace["nfrs"]
    integrations = workspace["integrations"]
    readiness_data = workspace["readiness"]
    name = element["name"]

    md: list[str] = [f"# {name} — L2 Container Architecture\n"]
    md.append(f"> **Readiness: {readiness_data['score']}%** · {readiness_data['status_label']}\n")
    if workspace.get("parent"):
        md.append(f"**Linked L1:** {workspace['parent']['name']}\n")
    if arch["summary"]:
        md.append(arch["summary"] + "\n")

    md.append("## Container Diagram\n")
    diagram = (arch["container_diagram"] or "").strip() or (_fallback_diagram(name, containers) if containers else "")
    md.append("```mermaid\n" + diagram + "\n```\n" if diagram else "_No container diagram yet._\n")

    md.append("## Containers & Service Boundaries\n")
    md.append(_table(["Container", "Capability", "Owner team", "Security", "Criticality"],
                     [[c["name"], c["capability"], c["owner_team"], c["security_classification"], c["nfr_criticality"]] for c in containers]) + "\n"
              if containers else "_No containers defined yet._\n")

    md.append("## API & Data Contracts\n")
    md.append(_table(["API", "Provider", "Consumer", "Type", "Data class", "Auth", "Version"],
                     [[a["name"], a["provider"], a["consumer"], a["api_type"], a["data_classification"], a["authentication"], a["version"]] for a in apis]) + "\n"
              if apis else "_No API contracts yet._\n")

    md.append("## Non-Functional Requirements\n")
    md.append(_table(["NFR", "Category", "Metric", "Target", "Risk", "Status"],
                     [[n["name"], n["category"], n["metric"], n["target"], n["risk_level"], n["status"]] for n in nfrs]) + "\n"
              if nfrs else "_No NFRs captured yet._\n")

    md.append("## Integration Plan\n")
    md.append(_table(["Integration", "Source", "Target", "Type", "Security", "Status"],
                     [[i["name"], i["source_system"], i["target_system"], i["integration_type"], i["security_method"], i["status"]] for i in integrations]) + "\n"
              if integrations else "_No integrations planned yet._\n")

    md.append("## Traceability\n")
    trace = traceability(project_id, l2_element_id)
    md.append("```mermaid\n" + trace["mermaid"] + "\n```\n")

    md.append("## Readiness Breakdown\n")
    md.append(_table(["Area", "Weight", "Score"],
                     [[a["area"].replace("_", " ").title(), f"{a['weight']}%", f"{a['score']}%"] for a in readiness_data["areas"]]) + "\n")

    return {"markdown": "\n".join(md), "readiness_score": readiness_data["score"]}


# ---- traceability L1 → L2 → L3 ----

def traceability(project_id: str, l2_element_id: str) -> dict[str, Any]:
    from backend.storage.db import connect

    with connect() as conn:
        l2 = conn.execute("SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (l2_element_id, project_id)).fetchone()
        if l2 is None:
            from backend.l2arch.store import NotFoundError
            raise NotFoundError(f"L2 element '{l2_element_id}' was not found")
        l1 = None
        if l2["parent_id"]:
            row = conn.execute("SELECT id, name, level FROM c4_elements WHERE id = ?", (l2["parent_id"],)).fetchone()
            l1 = dict(row) if row else None
        l3 = [dict(r) for r in conn.execute(
            "SELECT id, name FROM c4_elements WHERE parent_id = ? AND level = 'L3' ORDER BY name", (l2_element_id,)).fetchall()]

    lines = ["flowchart LR"]
    if l1:
        lines.append(f'  L1["L1 · {l1["name"]}"]')
        lines.append(f'  L2["L2 · {l2["name"]}"]')
        lines.append("  L1 --> L2")
    else:
        lines.append(f'  L2["L2 · {l2["name"]}"]')
    for index, child in enumerate(l3):
        node = f"c{index}"
        lines.append(f'  {node}["L3 · {child["name"]}"]')
        lines.append(f"  L2 --> {node}")
    if not l3:
        lines.append('  none["L3: none yet"]')
        lines.append("  L2 --> none")

    return {
        "l1": l1,
        "l2": {"id": l2["id"], "name": l2["name"]},
        "l3_children": l3,
        "l3_count": len(l3),
        "mermaid": "\n".join(lines),
    }
