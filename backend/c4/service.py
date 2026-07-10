"""C4 domain services: story assembly, estimate persistence, roll-ups, imports."""

from __future__ import annotations

from typing import Any

from backend.c4 import scan, store
from backend.c4.models import ARTIFACT_FOR_LEVEL, C4ElementCreate
from backend.models import Story
from backend.projects.store import get_project
from backend.storage.db import connect, rows_to_dicts


def element_to_story(project_id: str, element: dict[str, Any]) -> Story:
    """Build the estimation story for an element, with the C4 tree as evidence."""
    project = get_project(project_id)
    chain = _parent_chain(project_id, element)
    relations = _element_relations(project_id, element["id"])
    repo_urls = [repo["url"] or repo["local_path"] for repo in project["repos"]]
    return Story(
        title=element["name"],
        user_story=element["description"],
        technical_breakdown=element["tech"] or None,
        components=[item["name"] for item in chain],
        source="manual",
        c4_context={
            "level": element["level"],
            "kind": element["kind"],
            "artifact_type": ARTIFACT_FOR_LEVEL[element["level"]],
            "parent_chain": [
                {"level": item["level"], "name": item["name"], "description": item["description"]}
                for item in chain
            ],
            "relations": relations,
            "code_path": element["code_path"] or None,
            "repositories": [url for url in repo_urls if url],
        },
    )


def _parent_chain(project_id: str, element: dict[str, Any]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    current = element
    while current.get("parent_id"):
        current = store.get_element(project_id, current["parent_id"])
        chain.insert(0, current)
    return chain


def _element_relations(project_id: str, element_id: str) -> list[dict[str, str]]:
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """SELECT r.label, r.kind, s.name AS source, t.name AS target
                   FROM c4_relations r
                   JOIN c4_elements s ON s.id = r.source_id
                   JOIN c4_elements t ON t.id = r.target_id
                   WHERE r.project_id = ? AND (r.source_id = ? OR r.target_id = ?)""",
                (project_id, element_id, element_id),
            ).fetchall()
        )
    return rows


def persist_estimate(project_id: str, element: dict[str, Any], session_id: str, result: dict[str, Any]) -> None:
    """Save the estimate on the element's artifact and seed proposed children/siblings."""
    split = result.get("split_recommendation") or {}
    store.upsert_artifact(
        element["id"],
        ARTIFACT_FOR_LEVEL[element["level"]],
        points=result.get("points"),
        spike_recommended=bool(result.get("spike_recommended")),
        split_recommended=bool(split.get("split_recommended")),
        estimate_session_id=session_id,
    )
    if element["level"] == "L3":
        for task in result.get("hidden_tasks") or []:
            name = (task.get("task") or "").strip()[:200]
            if name and store.find_child_by_name(project_id, element["id"], name) is None:
                store.create_element(project_id, C4ElementCreate(
                    level="L4", name=name, kind="task", status="proposed",
                    description=f"Hidden work detected during estimation (weight: {task.get('weight', 'unknown')}).",
                    parent_id=element["id"],
                ))
        if split.get("split_recommended"):
            for proposed in split.get("proposed_stories") or []:
                name = str(proposed).strip()[:200]
                if name and store.find_child_by_name(project_id, element["parent_id"], name) is None:
                    store.create_element(project_id, C4ElementCreate(
                        level="L3", name=name, kind="component", status="proposed",
                        description="Proposed by the split recommendation of a 13-point estimate.",
                        parent_id=element["parent_id"],
                    ))


def rollup(project_id: str) -> dict[str, Any]:
    """Deterministic points roll-up: initiative <- epics <- stories, with flags."""
    graph = store.list_graph(project_id)
    elements = graph["elements"]
    children: dict[str | None, list[dict[str, Any]]] = {}
    for element in elements:
        children.setdefault(element["parent_id"], []).append(element)

    def node(element: dict[str, Any]) -> dict[str, Any]:
        own = next(
            (a for a in element["artifacts"] if a["artifact_type"] == ARTIFACT_FOR_LEVEL[element["level"]]),
            None,
        )
        kids = [node(child) for child in children.get(element["id"], [])]
        summary = {
            "estimated_stories": sum(k["summary"]["estimated_stories"] for k in kids),
            "unestimated_stories": sum(k["summary"]["unestimated_stories"] for k in kids),
            "rolled_up_points": sum(k["summary"]["rolled_up_points"] for k in kids),
            "spikes": sum(k["summary"]["spikes"] for k in kids),
            "pending_splits": sum(k["summary"]["pending_splits"] for k in kids),
        }
        if element["level"] == "L3":
            points = own["points"] if own and own["points"] is not None else None
            summary["estimated_stories"] += int(points is not None)
            summary["unestimated_stories"] += int(points is None and element["status"] != "proposed")
            summary["rolled_up_points"] += points or 0
            summary["spikes"] += int(bool(own and own["spike_recommended"]))
            summary["pending_splits"] += int(bool(own and own["split_recommended"]))
        return {
            "element": {key: element[key] for key in ("id", "level", "kind", "name", "status", "code_path")},
            "artifact": own,
            "summary": summary,
            "children": kids,
        }

    roots = [node(element) for element in children.get(None, [])]
    totals = {
        "estimated_stories": sum(r["summary"]["estimated_stories"] for r in roots),
        "unestimated_stories": sum(r["summary"]["unestimated_stories"] for r in roots),
        "rolled_up_points": sum(r["summary"]["rolled_up_points"] for r in roots),
        "spikes": sum(r["summary"]["spikes"] for r in roots),
        "pending_splits": sum(r["summary"]["pending_splits"] for r in roots),
    }
    return {"tree": roots, "totals": totals}


def apply_scan(project_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
    """Create proposed elements from a repo scan, skipping names that already exist."""
    created = 0
    system = store.find_child_by_name(project_id, None, proposal["system"]["name"])
    if system is None:
        system = store.create_element(project_id, C4ElementCreate(
            level="L1", name=proposal["system"]["name"], kind="system", status="proposed",
            description="Seeded from repo scan.",
        ))
        created += 1
    for container in proposal["containers"]:
        existing = store.find_child_by_name(project_id, system["id"], container["name"])
        if existing is None:
            existing = store.create_element(project_id, C4ElementCreate(
                level="L2", name=container["name"], kind="container", status="proposed",
                tech=container["tech"], code_path=container["code_path"], parent_id=system["id"],
                description="Seeded from repo scan.",
            ))
            created += 1
        for component in container["components"]:
            if store.find_child_by_name(project_id, existing["id"], component["name"]) is None:
                store.create_element(project_id, C4ElementCreate(
                    level="L3", name=component["name"], kind="component", status="proposed",
                    tech=component["tech"], code_path=component["code_path"], parent_id=existing["id"],
                    description="Seeded from repo scan.",
                ))
                created += 1
    return {"created": created}


def scan_project_repo(project_id: str, local_path: str | None) -> dict[str, Any]:
    project = get_project(project_id)
    path = local_path or next((repo["local_path"] for repo in project["repos"] if repo["local_path"]), None)
    if not path:
        raise FileNotFoundError("No local repo path is linked to this project; pass local_path explicitly")
    return scan.scan_repo(path, project["name"])


def import_jira_stories(project_id: str, stories: list[Story], container_name: str = "Imported from Jira") -> dict[str, Any]:
    """Create L3 story elements (under one L2 container) from fetched Jira issues."""
    system = _first_element_at_level(project_id, "L1")
    container = store.find_child_by_name(project_id, system["id"] if system else None, container_name)
    if container is None:
        container = store.create_element(project_id, C4ElementCreate(
            level="L2", name=container_name, kind="container", status="proposed",
            description="Holding container for issues imported from Jira; re-parent them onto real containers.",
            parent_id=system["id"] if system else None,
        ))
    created = 0
    for story in stories:
        if store.find_child_by_name(project_id, container["id"], story.title[:200]) is not None:
            continue
        element = store.create_element(project_id, C4ElementCreate(
            level="L3", name=story.title[:200], kind="component", status="proposed",
            description=story.user_story, parent_id=container["id"],
        ))
        # Existing Jira points stay reference-only; a rolled-up point always needs a justified estimate.
        store.upsert_artifact(element["id"], "story", jira_issue_key=story.key)
        created += 1
    return {"created": created, "container_id": container["id"]}


def _first_element_at_level(project_id: str, level: str) -> dict[str, Any] | None:
    graph = store.list_graph(project_id)
    return next((element for element in graph["elements"] if element["level"] == level), None)
