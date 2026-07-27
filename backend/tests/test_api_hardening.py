"""Production HTTP boundary: safe errors, request correlation, and upload limits."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

import backend.api.main as api_main
from backend.l1arch.router import ExecExportRequest


def test_api_responses_include_correlation_and_security_headers():
    with TestClient(api_main.app) as client:
        response = client.get(
            "/projects",
            headers={"X-Request-Id": "test-request-123", "Origin": "http://localhost:5173"},
        )

    assert response.status_code == 401
    assert response.headers["X-Request-Id"] == "test-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "X-Request-Id" in response.headers["Access-Control-Expose-Headers"]


def test_invalid_request_uses_serializable_error_envelope():
    with TestClient(api_main.app) as client:
        response = client.post(
            "/projects",
            headers={"X-User-Role": "admin"},
            json={"name": "", "sensitivity": "not-a-valid-value"},
        )

    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == "validation_error"
    assert isinstance(payload["details"], list)
    assert all("ctx" not in item for item in payload["details"])


def test_unhandled_error_is_redacted_and_correlated(monkeypatch):
    class BrokenRegistry:
        async def health(self):
            raise RuntimeError("secret implementation detail")

    monkeypatch.setattr(api_main, "get_jira_registry", lambda: BrokenRegistry())
    with TestClient(api_main.app, raise_server_exceptions=False) as client:
        response = client.get("/health", headers={"X-Request-Id": "failure-42"})

    assert response.status_code == 500
    assert response.headers["X-Request-Id"] == "failure-42"
    payload = response.json()["error"]
    assert payload["code"] == "internal_error"
    assert payload["details"]["request_id"] == "failure-42"
    assert "secret implementation detail" not in response.text


def test_story_upload_rejects_over_limit_without_parsing():
    oversized = b"x" * (15 * 1024 * 1024 + 1)
    with TestClient(api_main.app) as client:
        response = client.post(
            "/upload/parse",
            headers={"X-User-Role": "admin"},
            files={"file": ("large.csv", oversized, "text/csv")},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parse_error"


def test_executive_export_payload_is_bounded():
    with pytest.raises(ValidationError, match="28 MB"):
        ExecExportRequest(diagram_images=["x" * 28_000_001])
