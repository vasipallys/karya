"""Deterministic readiness scoring and the living Markdown+Mermaid executive summary.

No LLM is involved here — the readiness score and the executive document are
computed straight from the stored artifacts. The executive summary is the
"PowerPoint replacement": one Markdown document with embedded Mermaid that any
Markdown renderer (including this app's own viewer) turns into a live deck.
"""

from __future__ import annotations

import re
from typing import Any

from backend.storage.db import connect

# Section 13 weights.
AREA_WEIGHTS = {
    "vision_okrs": 15,
    "stakeholders": 15,
    "capability_map": 15,
    "system_context": 20,
    "risk_funding": 15,
    "traceability": 10,
    "approval": 10,
}


def _context_counts(conn: Any, l1_element_id: str) -> dict[str, int]:
    l2 = conn.execute(
        "SELECT COUNT(*) FROM c4_elements WHERE parent_id = ? AND level = 'L2'", (l1_element_id,)
    ).fetchone()[0]
    relations = conn.execute(
        """SELECT COUNT(*) FROM c4_relations r JOIN c4_elements e ON e.id = r.source_id
           WHERE e.parent_id = ? OR r.source_id = ? OR r.target_id = ?""",
        (l1_element_id, l1_element_id, l1_element_id),
    ).fetchone()[0]
    diagrams = conn.execute(
        "SELECT COUNT(*) FROM l1_diagrams WHERE l1_element_id = ?", (l1_element_id,)
    ).fetchone()[0]
    return {"l2_children": l2, "relations": relations, "diagrams": diagrams}


def readiness(project_id: str, l1_element_id: str, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    if baseline is None:
        from backend.l1arch import store
        baseline = {
            "vision": store.get_vision(project_id, l1_element_id),
            "okrs": store.list_okrs(l1_element_id),
            "stakeholders": store.list_stakeholders(l1_element_id),
            "capabilities": store.list_capabilities(l1_element_id),
            "risks": store.list_risks(l1_element_id),
        }
    vision = baseline["vision"]
    okrs = baseline["okrs"]
    stakeholders = [s for s in baseline["stakeholders"] if s["status"] == "active"]
    capabilities = baseline["capabilities"]
    risks = baseline["risks"]

    with connect() as conn:
        counts = _context_counts(conn, l1_element_id)

    roles_present = {(s["role"] or "").lower() for s in stakeholders}

    def has_role(*keywords: str) -> bool:
        return any(any(k in role for k in keywords) for role in roles_present)

    measurable_okrs = [o for o in okrs if (o["key_result"] or "").strip() and (o["target_value"] or "").strip()]
    funded_risks = [r for r in risks if (r["funding_source"] or "").strip() or r["approved_budget"] > 0]

    # Completeness checklist (section 12).
    checklist = [
        ("Vision is defined", bool((vision["vision_statement"] or "").strip())),
        ("At least one objective is defined", len(okrs) >= 1),
        ("Each objective has measurable key results", bool(okrs) and len(measurable_okrs) == len(okrs)),
        ("Primary stakeholders are identified", len(stakeholders) >= 1),
        ("Business owner is assigned", has_role("business", "sponsor")),
        ("Product owner is assigned", has_role("product")),
        ("Architecture owner is assigned", has_role("architect")),
        ("Security owner is assigned", has_role("security")),
        ("Business capabilities are mapped", len(capabilities) >= 1),
        ("System context diagram is available", counts["l2_children"] >= 1 or counts["diagrams"] >= 1),
        ("Internal/external systems are identified", counts["l2_children"] >= 1),
        ("Risks are captured", len(risks) >= 1),
        ("Funding source is captured", len(funded_risks) >= 1),
        ("Approvals are completed", vision["status"] in ("approved", "baselined")),
        ("L1 is linked to at least one initiative or epic", counts["l2_children"] >= 1),
    ]

    # Weighted area scores (0..1 each).
    areas = {
        "vision_okrs": (1.0 if (vision["vision_statement"] or "").strip() else 0.0) * 0.5
                       + (min(len(measurable_okrs), 1)) * 0.5,
        "stakeholders": (1.0 if stakeholders else 0.0) * 0.5
                        + (1.0 if any(s["raci"] == "Accountable" for s in stakeholders) else 0.0) * 0.5,
        "capability_map": 1.0 if capabilities else 0.0,
        "system_context": min(1.0, (counts["l2_children"] * 0.5) + (0.5 if counts["diagrams"] else 0.0)),
        "risk_funding": (1.0 if risks else 0.0) * 0.5 + (1.0 if funded_risks else 0.0) * 0.5,
        "traceability": 1.0 if counts["l2_children"] >= 1 else 0.0,
        "approval": 1.0 if vision["status"] in ("approved", "baselined") else 0.0,
    }
    score = round(sum(areas[key] * AREA_WEIGHTS[key] for key in AREA_WEIGHTS))
    complete = all(done for _, done in checklist)
    if score >= 80:
        label = "Ready for L2 architecture review"
    elif score >= 50:
        label = "In progress — key gaps remain"
    else:
        label = "Early draft — foundational artifacts missing"

    gaps = [item for item, done in checklist if not done]
    # Deterministic, targeted recommendations for the biggest weighted gaps.
    rec_for = {
        "vision_okrs": "Capture a vision statement and at least one OKR with a measurable target.",
        "stakeholders": "Identify the key stakeholders and mark one as Accountable (RACI).",
        "capability_map": "Map the core business capabilities the system supports.",
        "system_context": "Model L2 containers and a system-context view on the C4 canvas.",
        "risk_funding": "Log the top risks with a mitigation and a funding source.",
        "traceability": "Link this L1 to at least one L2 epic on the C4 canvas.",
        "approval": "Complete the approval sign-off chain to baseline the L1.",
    }
    recommendations = [
        rec_for[key]
        for key in sorted(AREA_WEIGHTS, key=lambda k: AREA_WEIGHTS[k], reverse=True)
        if areas[key] < 1.0
    ]

    return {
        "score": score,
        "status_label": label,
        "complete": complete,
        "areas": [{"area": key, "weight": AREA_WEIGHTS[key], "score": round(areas[key] * 100)} for key in AREA_WEIGHTS],
        "checklist": [{"item": item, "done": done} for item, done in checklist],
        "gaps": gaps,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------- executive summary (MD + Mermaid)

def _slug(text: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text)[:14]
    return f"{cleaned or 'cap'}{index}"


def _capability_mermaid(l1_name: str, capabilities: list[dict[str, Any]]) -> str:
    lines = ["flowchart TD", f'  root["{l1_name}"]']
    ids = {}
    for index, cap in enumerate(capabilities):
        node = _slug(cap["name"], index)
        ids[cap["id"]] = node
        lines.append(f'  {node}["{cap["name"]}"]')
    for index, cap in enumerate(capabilities):
        node = ids[cap["id"]]
        parent = ids.get(cap["parent_id"]) if cap.get("parent_id") else "root"
        lines.append(f"  {parent} --> {node}")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join((str(cell).replace("|", "\\|") or "—") for cell in row) + " |")
    return "\n".join(out)


def executive_summary(project_id: str, l1_element_id: str) -> dict[str, str]:
    from backend.l1arch import store

    baseline = store.get_baseline(project_id, l1_element_id)
    element = baseline["element"]
    vision = baseline["vision"]
    okrs = baseline["okrs"]
    stakeholders = baseline["stakeholders"]
    capabilities = baseline["capabilities"]
    risks = baseline["risks"]
    readiness_data = baseline["readiness"]
    name = element["name"]

    md: list[str] = []
    md.append(f"# {name} — L1 Architecture Baseline\n")
    md.append(f"> **Readiness: {readiness_data['score']}%** · {readiness_data['status_label']}\n")

    md.append("## Vision\n")
    md.append((vision["vision_statement"] or "_No vision captured yet._") + "\n")
    if vision["business_problem"]:
        md.append(f"**Business problem:** {vision['business_problem']}\n")
    if vision["target_users"]:
        md.append(f"**Target users:** {vision['target_users']}\n")

    md.append("## Objectives & Key Results\n")
    if okrs:
        md.append(_table(
            ["Objective", "Key result", "Metric", "Target", "Current", "Owner", "Status"],
            [[o["objective"], o["key_result"], o["metric_name"], o["target_value"], o["current_value"], o["owner"], o["status"]] for o in okrs],
        ) + "\n")
    else:
        md.append("_No OKRs captured yet._\n")

    md.append("## Business Capability Map\n")
    if capabilities:
        md.append("```mermaid\n" + _capability_mermaid(name, capabilities) + "\n```\n")
    else:
        md.append("_No capabilities mapped yet._\n")

    md.append("## Stakeholders & RACI\n")
    active = [s for s in stakeholders if s["status"] == "active"]
    if active:
        md.append(_table(
            ["Name", "Role", "Type", "Influence", "Interest", "RACI"],
            [[s["name"], s["role"], s["stakeholder_type"], s["influence"], s["interest"], s["raci"]] for s in active],
        ) + "\n")
    else:
        md.append("_No stakeholders identified yet._\n")

    md.append("## Portfolio Risk & Funding\n")
    if risks:
        md.append(_table(
            ["Risk", "Category", "Level", "Owner", "Funding", "Approved", "Actual", "Status"],
            [[r["title"], r["category"], r["risk_level"], r["owner"], r["funding_source"], f"{r['approved_budget']:,.0f}", f"{r['actual_spend']:,.0f}", r["status"]] for r in risks],
        ) + "\n")
        total_budget = sum(r["approved_budget"] for r in risks)
        total_actual = sum(r["actual_spend"] for r in risks)
        md.append(f"\n**Total approved:** {total_budget:,.0f} · **Actual:** {total_actual:,.0f}\n")
    else:
        md.append("_No risks or funding captured yet._\n")

    md.append("## Readiness Breakdown\n")
    md.append(_table(
        ["Area", "Weight", "Score"],
        [[a["area"].replace("_", " ").title(), f"{a['weight']}%", f"{a['score']}%"] for a in readiness_data["areas"]],
    ) + "\n")

    return {"markdown": "\n".join(md), "readiness_score": readiness_data["score"]}


# ---------------------------------------------------------------- traceability & impact

def _element_names(conn: Any, project_id: str) -> dict[str, dict[str, str]]:
    rows = conn.execute("SELECT id, name, level FROM c4_elements WHERE project_id = ?", (project_id,)).fetchall()
    return {row["id"]: {"name": row["name"], "level": row["level"]} for row in rows}


def traceability(project_id: str, l1_element_id: str) -> dict[str, Any]:
    """Links from L1 artifacts to the C4 model (initiatives/epics), for traceability."""
    from backend.l1arch import store

    with connect() as conn:
        elements = _element_names(conn, project_id)
    links = []
    for kind, items in (("okr", store.list_okrs(l1_element_id)),
                        ("capability", store.list_capabilities(l1_element_id)),
                        ("risk", store.list_risks(l1_element_id))):
        for item in items:
            target = item.get("linked_element_id")
            links.append({
                "artifact_type": kind,
                "artifact_id": item["id"],
                "artifact_name": item.get("objective") or item.get("name") or item.get("title"),
                "linked_element_id": target,
                "linked_element_name": elements.get(target, {}).get("name") if target else None,
                "linked_level": elements.get(target, {}).get("level") if target else None,
                "orphaned": bool(target) and target not in elements,
            })
    linked = [link for link in links if link["linked_element_id"] and not link["orphaned"]]
    return {"links": links, "linked_count": len(linked), "total": len(links)}


def impact_analysis(project_id: str, l1_element_id: str) -> dict[str, Any]:
    """Deterministic change-impact / consistency findings (requirement workflow 9.2)."""
    from datetime import date

    from backend.l1arch import store

    baseline = store.get_baseline(project_id, l1_element_id)
    trace = traceability(project_id, l1_element_id)
    findings: list[dict[str, str]] = []

    def add(severity: str, message: str) -> None:
        findings.append({"severity": severity, "message": message})

    # Broken traceability links (target element removed).
    for link in trace["links"]:
        if link["orphaned"]:
            add("high", f"{link['artifact_type'].title()} '{link['artifact_name']}' links to a C4 element that no longer exists.")

    # Stakeholders inactive but still Accountable.
    for s in baseline["stakeholders"]:
        if s["status"] != "active" and s["raci"] == "Accountable":
            add("high", f"Accountable stakeholder '{s['name']}' is {s['status']} — reassign accountability.")

    # Capabilities with no owner.
    for c in baseline["capabilities"]:
        if not (c["business_owner"] or "").strip() and not (c["technology_owner"] or "").strip():
            add("medium", f"Capability '{c['name']}' has no business or technology owner.")

    # Risks past target date and not completed.
    today = date.today().isoformat()
    for r in baseline["risks"]:
        if r.get("target_date") and r["target_date"] < today and r["status"] != "completed":
            add("medium", f"Risk '{r['title']}' is past its target date ({r['target_date']}) and still {r['status']}.")

    # OKRs off track.
    for o in baseline["okrs"]:
        if o["status"] == "off_track":
            add("medium", f"Objective '{o['objective']}' is off track.")

    # A baselined vision with new open comments (potential drift).
    open_comments = [c for c in baseline["comments"] if c["status"] == "open"]
    if baseline["vision"]["status"] == "baselined" and open_comments:
        add("low", f"{len(open_comments)} open review comment(s) on a baselined L1 — consider re-review.")

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: severity_rank.get(f["severity"], 3))
    return {
        "findings": findings,
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "clean": len(findings) == 0,
    }
