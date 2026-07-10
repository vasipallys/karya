"""CRUD and validation for C4 elements, relations, and artifact links."""

from __future__ import annotations

from typing import Any

from backend.c4.models import (
    ARTIFACT_FOR_LEVEL,
    CROSS_CUTTING_LEVELS,
    LEVELS,
    C4ElementCreate,
    C4ElementUpdate,
    C4RelationCreate,
)
from backend.projects.store import NotFoundError, get_project
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class C4ValidationError(ValueError):
    pass


def _check_parent(conn: Any, project_id: str, level: str, parent_id: str | None) -> None:
    if parent_id is None:
        return
    parent = conn.execute(
        "SELECT level, project_id FROM c4_elements WHERE id = ?", (parent_id,)
    ).fetchone()
    if parent is None or parent["project_id"] != project_id:
        raise C4ValidationError("parent_id does not reference an element in this project")
    if LEVELS.index(parent["level"]) != LEVELS.index(level) - 1:
        raise C4ValidationError(f"A {level} element's parent must be one level up ({LEVELS[LEVELS.index(level) - 1]})")


def create_element(project_id: str, payload: C4ElementCreate) -> dict[str, Any]:
    get_project(project_id)
    with connect() as conn:
        _check_parent(conn, project_id, payload.level, payload.parent_id)
        record = {"id": new_id(), "project_id": project_id, "created_at": utc_now(), **payload.model_dump()}
        conn.execute(
            """INSERT INTO c4_elements (id, project_id, level, kind, name, description, parent_id, tech, code_path, status, pos_x, pos_y, created_at)
               VALUES (:id, :project_id, :level, :kind, :name, :description, :parent_id, :tech, :code_path, :status, :pos_x, :pos_y, :created_at)""",
            record,
        )
    return get_element(project_id, record["id"])


def get_element(project_id: str, element_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM c4_elements WHERE id = ? AND project_id = ?", (element_id, project_id)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"C4 element '{element_id}' was not found")
        element = dict(row)
        element["artifacts"] = rows_to_dicts(
            conn.execute("SELECT * FROM artifact_links WHERE element_id = ?", (element_id,)).fetchall()
        )
    return element


def update_element(project_id: str, element_id: str, payload: C4ElementUpdate) -> dict[str, Any]:
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    element = get_element(project_id, element_id)
    if "parent_id" in changes:
        with connect() as conn:
            _check_parent(conn, project_id, element["level"], changes["parent_id"])
    if changes:
        assignments = ", ".join(f"{key} = :{key}" for key in changes)
        with connect() as conn:
            conn.execute(
                f"UPDATE c4_elements SET {assignments} WHERE id = :id AND project_id = :project_id",
                {**changes, "id": element_id, "project_id": project_id},
            )
    return get_element(project_id, element_id)


def delete_element(project_id: str, element_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM c4_elements WHERE id = ? AND project_id = ?", (element_id, project_id)
        ).rowcount
    if not deleted:
        raise NotFoundError(f"C4 element '{element_id}' was not found")


def list_graph(project_id: str) -> dict[str, Any]:
    get_project(project_id)
    with connect() as conn:
        elements = rows_to_dicts(
            conn.execute(
                "SELECT * FROM c4_elements WHERE project_id = ? ORDER BY created_at", (project_id,)
            ).fetchall()
        )
        artifacts = rows_to_dicts(
            conn.execute(
                """SELECT artifact_links.* FROM artifact_links
                   JOIN c4_elements ON c4_elements.id = artifact_links.element_id
                   WHERE c4_elements.project_id = ?""",
                (project_id,),
            ).fetchall()
        )
        relations = rows_to_dicts(
            conn.execute("SELECT * FROM c4_relations WHERE project_id = ?", (project_id,)).fetchall()
        )
    by_element: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        by_element.setdefault(artifact["element_id"], []).append(artifact)
    for element in elements:
        element["artifacts"] = by_element.get(element["id"], [])
    return {"elements": elements, "relations": relations}


def create_relation(project_id: str, payload: C4RelationCreate) -> dict[str, Any]:
    get_project(project_id)
    with connect() as conn:
        for element_id in (payload.source_id, payload.target_id):
            row = conn.execute(
                "SELECT id FROM c4_elements WHERE id = ? AND project_id = ?", (element_id, project_id)
            ).fetchone()
            if row is None:
                raise C4ValidationError(f"Relation endpoint '{element_id}' is not an element in this project")
        record = {"id": new_id(), "project_id": project_id, **payload.model_dump()}
        conn.execute(
            "INSERT INTO c4_relations (id, project_id, source_id, target_id, label, kind) VALUES (:id, :project_id, :source_id, :target_id, :label, :kind)",
            record,
        )
    return record


def delete_relation(project_id: str, relation_id: str) -> None:
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM c4_relations WHERE id = ? AND project_id = ?", (relation_id, project_id)
        ).rowcount
    if not deleted:
        raise NotFoundError(f"Relation '{relation_id}' was not found")


def upsert_artifact(
    element_id: str,
    artifact_type: str,
    *,
    jira_issue_key: str | None = None,
    points: int | None = None,
    spike_recommended: bool | None = None,
    split_recommended: bool | None = None,
    estimate_session_id: str | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM artifact_links WHERE element_id = ? AND artifact_type = ?",
            (element_id, artifact_type),
        ).fetchone()
        if existing is None:
            record = {
                "id": new_id(),
                "element_id": element_id,
                "artifact_type": artifact_type,
                "jira_issue_key": jira_issue_key,
                "points": points,
                "spike_recommended": int(bool(spike_recommended)),
                "split_recommended": int(bool(split_recommended)),
                "estimate_session_id": estimate_session_id,
                "estimated_at": utc_now() if points is not None else None,
            }
            conn.execute(
                """INSERT INTO artifact_links (id, element_id, artifact_type, jira_issue_key, points, spike_recommended, split_recommended, estimate_session_id, estimated_at)
                   VALUES (:id, :element_id, :artifact_type, :jira_issue_key, :points, :spike_recommended, :split_recommended, :estimate_session_id, :estimated_at)""",
                record,
            )
            return record
        record = dict(existing)
        if jira_issue_key is not None:
            record["jira_issue_key"] = jira_issue_key
        if points is not None:
            record["points"] = points
            record["estimated_at"] = utc_now()
        if spike_recommended is not None:
            record["spike_recommended"] = int(spike_recommended)
        if split_recommended is not None:
            record["split_recommended"] = int(split_recommended)
        if estimate_session_id is not None:
            record["estimate_session_id"] = estimate_session_id
        conn.execute(
            """UPDATE artifact_links SET jira_issue_key = :jira_issue_key, points = :points,
               spike_recommended = :spike_recommended, split_recommended = :split_recommended,
               estimate_session_id = :estimate_session_id, estimated_at = :estimated_at
               WHERE id = :id""",
            record,
        )
    return record


def tag_cross_cutting(project_id: str, element_id: str, artifact_type: str, jira_issue_key: str | None) -> dict[str, Any]:
    element = get_element(project_id, element_id)
    allowed = CROSS_CUTTING_LEVELS[artifact_type]
    if element["level"] not in allowed:
        raise C4ValidationError(f"A {artifact_type} artifact tags {' or '.join(sorted(allowed))} elements only")
    return upsert_artifact(element_id, artifact_type, jira_issue_key=jira_issue_key)


def default_artifact_type(level: str) -> str:
    return ARTIFACT_FOR_LEVEL[level]


def find_child_by_name(project_id: str, parent_id: str | None, name: str) -> dict[str, Any] | None:
    with connect() as conn:
        query = "SELECT * FROM c4_elements WHERE project_id = ? AND name = ? AND parent_id "
        params: tuple[Any, ...] = (project_id, name)
        query += "IS NULL" if parent_id is None else "= ?"
        if parent_id is not None:
            params += (parent_id,)
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None
