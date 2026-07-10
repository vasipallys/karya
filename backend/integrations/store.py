"""Persistence for connector configuration (app-global, one row per connector).

Secrets are write-only: `get_config` never returns stored secret values — only a
`secrets_set` list naming which secret fields have a saved value. `save_config`
merges, updating a secret field only when a new non-empty value is supplied, so
re-saving a form without re-typing the secret keeps the existing one.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.integrations import connectors
from backend.storage.db import connect, utc_now


class NotFoundError(LookupError):
    pass


class IntegrationValidationError(ValueError):
    pass


_URL_RE = re.compile(r"^(https?|ldaps?)://", re.IGNORECASE)


def _row(key: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM integration_configs WHERE connector_key = ?", (key,)).fetchone()
    return dict(row) if row else None


def _stored_values(key: str) -> dict[str, Any]:
    row = _row(key)
    if not row:
        return {}
    try:
        return json.loads(row["settings"] or "{}")
    except json.JSONDecodeError:
        return {}


def get_config(key: str) -> dict[str, Any]:
    """Connector config view: field schema + non-secret values + which secrets are set."""
    if not connectors.is_configurable(key):
        return {
            "connector_key": key, "configurable": False, "fields": [],
            "values": {}, "secrets_set": [], "enabled": False, "updated_at": None, "updated_by": "",
        }
    fields = connectors.fields_for(key)
    secret_keys = connectors.secret_keys(key)
    stored = _stored_values(key)
    row = _row(key)
    values = {k: v for k, v in stored.items() if k not in secret_keys}
    secrets_set = [k for k in secret_keys if str(stored.get(k, "")).strip()]
    return {
        "connector_key": key,
        "configurable": True,
        "fields": fields,
        "values": values,
        "secrets_set": secrets_set,
        "enabled": bool(row["enabled"]) if row else False,
        "updated_at": row["updated_at"] if row else None,
        "updated_by": row["updated_by"] if row else "",
    }


def _merge_values(key: str, provided: dict[str, Any]) -> dict[str, Any]:
    stored = _stored_values(key)
    field_keys = connectors.field_keys(key)
    secret_keys = connectors.secret_keys(key)
    merged = dict(stored)
    for field_key in field_keys:
        if field_key not in provided:
            continue
        value = provided.get(field_key)
        text = "" if value is None else str(value)
        if field_key in secret_keys:
            if text.strip():  # secrets are write-only — blank means "leave unchanged"
                merged[field_key] = text
        else:
            merged[field_key] = text
    return merged


def save_config(key: str, provided: dict[str, Any], enabled: bool, user: str = "") -> dict[str, Any]:
    if not connectors.is_configurable(key):
        raise IntegrationValidationError(f"'{key}' is an in-app adapter and needs no configuration")
    merged = _merge_values(key, provided)
    if enabled:
        missing = [k for k in connectors.required_keys(key) if not str(merged.get(k, "")).strip()]
        if missing:
            labels = {f["key"]: f["label"] for f in connectors.fields_for(key)}
            raise IntegrationValidationError("Cannot enable — missing required fields: " + ", ".join(labels.get(m, m) for m in missing))
    with connect() as conn:
        conn.execute(
            """INSERT INTO integration_configs (connector_key, enabled, settings, updated_at, updated_by)
               VALUES (:connector_key, :enabled, :settings, :updated_at, :updated_by)
               ON CONFLICT(connector_key) DO UPDATE SET
                 enabled=excluded.enabled, settings=excluded.settings,
                 updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
            {
                "connector_key": key, "enabled": 1 if enabled else 0,
                "settings": json.dumps(merged), "updated_at": utc_now(), "updated_by": user or "",
            },
        )
    return get_config(key)


def clear_config(key: str) -> None:
    with connect() as conn:
        deleted = conn.execute("DELETE FROM integration_configs WHERE connector_key = ?", (key,)).rowcount
    if not deleted:
        raise NotFoundError(f"No configuration to remove for '{key}'")


def test_config(key: str) -> dict[str, Any]:
    """Deterministic configuration validation (required present + URL fields well-formed).

    This validates the saved settings; it does not open live connections to the
    external tool (that is connector-specific and, for Jira, uses jira.registry).
    """
    if not connectors.is_configurable(key):
        raise IntegrationValidationError(f"'{key}' is an in-app adapter and is always available")
    stored = _stored_values(key)
    fields = connectors.fields_for(key)
    problems: list[str] = []
    for field in fields:
        value = str(stored.get(field["key"], "")).strip()
        if field["required"] and not value:
            problems.append(f"{field['label']} is required")
        elif value and field["type"] == "url" and not _URL_RE.match(value):
            problems.append(f"{field['label']} must be a valid URL")
    if problems:
        return {"ok": False, "message": "; ".join(problems)}
    return {"ok": True, "message": "Configuration looks valid. Saved settings are complete and well-formed."}


def configured_keys() -> set[str]:
    """Connector keys with an enabled configuration (drives catalog 'connected' status)."""
    with connect() as conn:
        rows = conn.execute("SELECT connector_key FROM integration_configs WHERE enabled = 1").fetchall()
    return {row["connector_key"] for row in rows}


def is_configured(key: str) -> bool:
    return key in configured_keys()
