"""Persistent project-scoped assistant conversations and attachment metadata."""

from __future__ import annotations

import json
from typing import Any

from backend.storage.db import connect, new_id, rows_to_dicts, utc_now


class ChatStoreError(LookupError):
    pass


def create_conversation(project_id: str, user_id: str = "", title: str = "New chat") -> dict[str, Any]:
    now = utc_now()
    record = {"id": new_id(), "project_id": project_id, "user_id": user_id or "", "title": title[:120] or "New chat",
              "created_at": now, "updated_at": now}
    with connect() as conn:
        conn.execute("""INSERT INTO chat_conversations (id, project_id, user_id, title, created_at, updated_at)
                        VALUES (:id, :project_id, :user_id, :title, :created_at, :updated_at)""", record)
    return record


def list_conversations(project_id: str, user_id: str = "") -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("""SELECT c.*, COUNT(m.id) AS message_count
                               FROM chat_conversations c LEFT JOIN chat_messages m ON m.conversation_id = c.id
                               WHERE c.project_id = ? AND c.user_id = ? GROUP BY c.id
                               ORDER BY c.updated_at DESC LIMIT 100""", (project_id, user_id or "")).fetchall()
    return rows_to_dicts(rows)


def get_conversation(project_id: str, conversation_id: str, user_id: str = "") -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM chat_conversations WHERE id=? AND project_id=? AND user_id=?",
                           (conversation_id, project_id, user_id or "")).fetchone()
        if row is None:
            raise ChatStoreError("Conversation not found")
        messages = rows_to_dicts(conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id=? ORDER BY created_at, rowid", (conversation_id,)).fetchall())
        attachments = rows_to_dicts(conn.execute(
            "SELECT id, message_id, filename, media_type, size_bytes, created_at FROM chat_attachments WHERE conversation_id=? ORDER BY created_at",
            (conversation_id,)).fetchall())
    by_message: dict[str, list[dict[str, Any]]] = {}
    for attachment in attachments:
        by_message.setdefault(attachment.get("message_id") or "", []).append(attachment)
    for message in messages:
        try:
            message["payload"] = json.loads(message.get("payload") or "{}")
        except json.JSONDecodeError:
            message["payload"] = {}
        message["attachments"] = by_message.get(message["id"], [])
    return {**dict(row), "messages": messages}


def delete_conversation(project_id: str, conversation_id: str, user_id: str = "") -> None:
    with connect() as conn:
        result = conn.execute("DELETE FROM chat_conversations WHERE id=? AND project_id=? AND user_id=?",
                              (conversation_id, project_id, user_id or ""))
        if not result.rowcount:
            raise ChatStoreError("Conversation not found")


def add_message(conversation_id: str, role: str, text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    now = utc_now()
    record = {"id": new_id(), "conversation_id": conversation_id, "role": role, "text": text,
              "payload": json.dumps(payload or {}, ensure_ascii=False, default=str), "created_at": now}
    with connect() as conn:
        conn.execute("""INSERT INTO chat_messages (id, conversation_id, role, text, payload, created_at)
                        VALUES (:id, :conversation_id, :role, :text, :payload, :created_at)""", record)
        count = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        title = text.strip().replace("\n", " ")[:80] if role == "user" and count <= 1 else None
        if title:
            conn.execute("UPDATE chat_conversations SET title=?, updated_at=? WHERE id=?", (title, now, conversation_id))
        else:
            conn.execute("UPDATE chat_conversations SET updated_at=? WHERE id=?", (now, conversation_id))
    return {**record, "payload": payload or {}}


def add_attachment(conversation_id: str, filename: str, media_type: str, size_bytes: int, extracted_text: str) -> dict[str, Any]:
    record = {"id": new_id(), "conversation_id": conversation_id, "message_id": None, "filename": filename[:255],
              "media_type": media_type[:120], "size_bytes": size_bytes, "extracted_text": extracted_text, "created_at": utc_now()}
    with connect() as conn:
        conn.execute("""INSERT INTO chat_attachments (id, conversation_id, message_id, filename, media_type, size_bytes, extracted_text, created_at)
                        VALUES (:id, :conversation_id, :message_id, :filename, :media_type, :size_bytes, :extracted_text, :created_at)""", record)
    return {k: v for k, v in record.items() if k != "extracted_text"}


def attachment_context(conversation_id: str, attachment_ids: list[str]) -> tuple[str, list[dict[str, Any]]]:
    if not attachment_ids:
        return "", []
    marks = ",".join("?" for _ in attachment_ids)
    with connect() as conn:
        rows = rows_to_dicts(conn.execute(
            f"SELECT * FROM chat_attachments WHERE conversation_id=? AND id IN ({marks})",
            (conversation_id, *attachment_ids)).fetchall())
    text = "\n\n".join(f"FILE: {r['filename']}\n{r['extracted_text'][:12000]}" for r in rows)
    return text[:30000], [{k: v for k, v in r.items() if k != "extracted_text"} for r in rows]


def attach_to_message(attachment_ids: list[str], message_id: str) -> None:
    if not attachment_ids:
        return
    marks = ",".join("?" for _ in attachment_ids)
    with connect() as conn:
        conn.execute(f"UPDATE chat_attachments SET message_id=? WHERE id IN ({marks})", (message_id, *attachment_ids))
