"""Versioned L1 requirements, collaborative review, and immutable audit events."""

from __future__ import annotations

import json
from typing import Any

from backend.planning.models import (
    RequirementCommentAction,
    RequirementCommentCreate,
    RequirementDocumentCreate,
    RequirementDocumentUpdate,
    RequirementReviewAction,
)
from backend.planning.store import PlanningValidationError, _require_l1
from backend.projects.store import NotFoundError, get_project
from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class PlanningConflictError(RuntimeError):
    """Raised when an editor tries to overwrite a newer document version."""


def _require_document(conn: Any, project_id: str, document_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM l1_requirement_documents WHERE id = ? AND project_id = ?",
        (document_id, project_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Requirement document '{document_id}' was not found")
    return dict(row)


def _audit(
    conn: Any,
    document_id: str,
    event_type: str,
    actor: str,
    version: int,
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """INSERT INTO l1_requirement_audit
           (id, document_id, event_type, actor, document_version, detail_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (new_id(), document_id, event_type, actor, version, json.dumps(detail or {}), utc_now()),
    )


def list_documents(project_id: str, l1_element_id: str) -> list[dict[str, Any]]:
    get_project(project_id)
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        rows = conn.execute(
            """SELECT d.*,
                      SUM(CASE WHEN c.status = 'open' THEN 1 ELSE 0 END) AS open_comments,
                      COUNT(c.id) AS comment_count
               FROM l1_requirement_documents d
               LEFT JOIN l1_requirement_comments c ON c.document_id = d.id
               WHERE d.project_id = ? AND d.l1_element_id = ?
               GROUP BY d.id
               ORDER BY d.updated_at DESC, d.title""",
            (project_id, l1_element_id),
        ).fetchall()
    return rows_to_dicts(rows)


def create_document(
    project_id: str,
    l1_element_id: str,
    payload: RequirementDocumentCreate,
) -> dict[str, Any]:
    now = utc_now()
    document_id = new_id()
    with connect() as conn:
        _require_l1(conn, project_id, l1_element_id)
        conn.execute(
            """INSERT INTO l1_requirement_documents
               (id, project_id, l1_element_id, title, content, status, version, created_by, updated_by,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'draft', 1, ?, ?, ?, ?)""",
            (
                document_id,
                project_id,
                l1_element_id,
                payload.title,
                payload.content,
                payload.actor,
                payload.actor,
                now,
                now,
            ),
        )
        conn.execute(
            """INSERT INTO l1_requirement_versions
               (id, document_id, version, title, content, changed_by, change_summary, created_at)
               VALUES (?, ?, 1, ?, ?, ?, ?, ?)""",
            (new_id(), document_id, payload.title, payload.content, payload.actor, "Initial version", now),
        )
        _audit(conn, document_id, "document_created", payload.actor, 1, {"title": payload.title})
    return get_document(project_id, document_id)


def get_document(project_id: str, document_id: str) -> dict[str, Any]:
    with connect() as conn:
        document = _require_document(conn, project_id, document_id)
        comments = rows_to_dicts(
            conn.execute(
                """SELECT * FROM l1_requirement_comments
                   WHERE document_id = ? ORDER BY created_at, id""",
                (document_id,),
            ).fetchall()
        )
        versions = rows_to_dicts(
            conn.execute(
                """SELECT id, document_id, version, title, changed_by, change_summary, created_at
                   FROM l1_requirement_versions WHERE document_id = ? ORDER BY version DESC""",
                (document_id,),
            ).fetchall()
        )
        audit = rows_to_dicts(
            conn.execute(
                """SELECT * FROM l1_requirement_audit
                   WHERE document_id = ? ORDER BY created_at DESC, id DESC""",
                (document_id,),
            ).fetchall()
        )
    for event in audit:
        event["detail"] = json.loads(event.pop("detail_json") or "{}")
    document["comments"] = comments
    document["versions"] = versions
    document["audit"] = audit
    return document


def get_version(project_id: str, document_id: str, version: int) -> dict[str, Any]:
    with connect() as conn:
        _require_document(conn, project_id, document_id)
        row = conn.execute(
            "SELECT * FROM l1_requirement_versions WHERE document_id = ? AND version = ?",
            (document_id, version),
        ).fetchone()
    if row is None:
        raise NotFoundError(f"Version {version} of requirement document '{document_id}' was not found")
    return dict(row)


def update_document(
    project_id: str,
    document_id: str,
    payload: RequirementDocumentUpdate,
) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        current = _require_document(conn, project_id, document_id)
        if current["version"] != payload.expected_version:
            raise PlanningConflictError(
                f"This document is now at version {current['version']}. Refresh before saving your changes."
            )
        if current["title"] == payload.title and current["content"] == payload.content:
            raise PlanningValidationError("There are no content changes to save")
        next_version = current["version"] + 1
        conn.execute(
            """UPDATE l1_requirement_documents
               SET title = ?, content = ?, status = 'draft', version = ?, updated_by = ?,
                   approved_by = NULL, approved_at = NULL, updated_at = ?
               WHERE id = ?""",
            (payload.title, payload.content, next_version, payload.actor, now, document_id),
        )
        conn.execute(
            """INSERT INTO l1_requirement_versions
               (id, document_id, version, title, content, changed_by, change_summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id(),
                document_id,
                next_version,
                payload.title,
                payload.content,
                payload.actor,
                payload.change_summary,
                now,
            ),
        )
        _audit(
            conn,
            document_id,
            "document_updated",
            payload.actor,
            next_version,
            {
                "change_summary": payload.change_summary,
                "previous_version": current["version"],
                "approval_invalidated": current["status"] == "approved",
            },
        )
    return get_document(project_id, document_id)


def add_comment(
    project_id: str,
    document_id: str,
    payload: RequirementCommentCreate,
) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        document = _require_document(conn, project_id, document_id)
        if payload.parent_comment_id:
            parent = conn.execute(
                "SELECT id FROM l1_requirement_comments WHERE id = ? AND document_id = ?",
                (payload.parent_comment_id, document_id),
            ).fetchone()
            if parent is None:
                raise PlanningValidationError("The parent comment does not belong to this document")
        record = {
            "id": new_id(),
            "document_id": document_id,
            "document_version": document["version"],
            "parent_comment_id": payload.parent_comment_id,
            "body": payload.body,
            "author": payload.actor,
            "status": "open",
            "acted_by": None,
            "acted_at": None,
            "created_at": now,
        }
        conn.execute(
            """INSERT INTO l1_requirement_comments
               (id, document_id, document_version, parent_comment_id, body, author, status, created_at)
               VALUES (:id, :document_id, :document_version, :parent_comment_id, :body, :author, :status, :created_at)""",
            record,
        )
        _audit(
            conn,
            document_id,
            "comment_added",
            payload.actor,
            document["version"],
            {"comment_id": record["id"], "parent_comment_id": payload.parent_comment_id},
        )
    return record


def act_on_comment(
    project_id: str,
    comment_id: str,
    payload: RequirementCommentAction,
) -> dict[str, Any]:
    status_for_action = {"approve": "approved", "resolve": "resolved", "reopen": "open"}
    now = utc_now()
    with connect() as conn:
        row = conn.execute(
            """SELECT c.*, d.project_id FROM l1_requirement_comments c
               JOIN l1_requirement_documents d ON d.id = c.document_id
               WHERE c.id = ? AND d.project_id = ?""",
            (comment_id, project_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Requirement comment '{comment_id}' was not found")
        next_status = status_for_action[payload.action]
        conn.execute(
            """UPDATE l1_requirement_comments
               SET status = ?, acted_by = ?, acted_at = ? WHERE id = ?""",
            (next_status, payload.actor, now, comment_id),
        )
        _audit(
            conn,
            row["document_id"],
            f"comment_{next_status}",
            payload.actor,
            row["document_version"],
            {"comment_id": comment_id, "previous_status": row["status"]},
        )
        updated = conn.execute("SELECT * FROM l1_requirement_comments WHERE id = ?", (comment_id,)).fetchone()
    return dict(updated)


def review_document(
    project_id: str,
    document_id: str,
    payload: RequirementReviewAction,
) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        document = _require_document(conn, project_id, document_id)
        if payload.action == "submit":
            next_status, approved_by, approved_at = "in_review", None, None
        elif payload.action == "approve":
            next_status, approved_by, approved_at = "approved", payload.actor, now
        else:
            next_status, approved_by, approved_at = "draft", None, None
        if document["status"] == next_status and payload.action != "revoke":
            raise PlanningValidationError(f"The document is already {next_status.replace('_', ' ')}")
        conn.execute(
            """UPDATE l1_requirement_documents
               SET status = ?, approved_by = ?, approved_at = ?, updated_by = ?, updated_at = ?
               WHERE id = ?""",
            (next_status, approved_by, approved_at, payload.actor, now, document_id),
        )
        _audit(
            conn,
            document_id,
            f"review_{payload.action}",
            payload.actor,
            document["version"],
            {"note": payload.note, "previous_status": document["status"], "status": next_status},
        )
    return get_document(project_id, document_id)
