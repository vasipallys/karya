"""Connector configuration: field schemas, secret masking, enable rules, catalog status, RBAC."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.integrations import catalog, connectors, store
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-integrations-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def test_field_schema_and_configurability():
    assert [f["key"] for f in connectors.fields_for("jira")] == ["base_url", "email", "api_token"]
    assert connectors.secret_keys("jira") == {"api_token"}
    assert connectors.fields_for("slack")[0]["key"] == "webhook_url"
    assert connectors.is_configurable("github") is True
    assert connectors.is_configurable("document_import") is False  # in-app adapter
    assert connectors.fields_for("document_import") == []


def test_enable_requires_all_required_fields():
    with pytest.raises(store.IntegrationValidationError):
        store.save_config("jira", {"base_url": "https://x.atlassian.net"}, enabled=True)
    # Saving as a disabled draft is allowed with partial fields.
    cfg = store.save_config("jira", {"base_url": "https://x.atlassian.net"}, enabled=False)
    assert cfg["enabled"] is False


def test_secrets_are_write_only_and_masked():
    store.save_config("jira", {"base_url": "https://acme.atlassian.net", "email": "a@acme.com", "api_token": "SECRET"}, enabled=True)
    cfg = store.get_config("jira")
    assert "SECRET" not in str(cfg)  # never returned to the caller
    assert "api_token" not in cfg["values"]
    assert cfg["secrets_set"] == ["api_token"]
    assert cfg["values"]["base_url"] == "https://acme.atlassian.net"
    # Re-saving with a blank secret keeps the stored one; non-secret fields update.
    store.save_config("jira", {"base_url": "https://acme2.atlassian.net", "email": "a@acme.com", "api_token": ""}, enabled=True)
    assert store._stored_values("jira")["api_token"] == "SECRET"
    assert store._stored_values("jira")["base_url"] == "https://acme2.atlassian.net"


def test_catalog_status_reflects_configuration():
    before = {t["key"]: t for g in catalog.list_catalog()["groups"] for t in g["tools"]}
    assert before["github"]["status"] == "available"
    assert before["document_import"]["status"] == "adapter" and before["document_import"]["configurable"] is False
    store.save_config("github", {"base_url": "https://api.github.com", "api_token": "ghp_x"}, enabled=True)
    after = {t["key"]: t for g in catalog.list_catalog()["groups"] for t in g["tools"]}
    assert after["github"]["status"] == "connected"


def test_validate_and_clear():
    store.save_config("slack", {"webhook_url": "not-a-url"}, enabled=False)
    assert store.test_config("slack")["ok"] is False  # bad URL
    store.save_config("slack", {"webhook_url": "https://hooks.slack.com/x"}, enabled=True)
    assert store.test_config("slack")["ok"] is True
    store.clear_config("slack")
    assert store.get_config("slack")["enabled"] is False
    with pytest.raises(store.NotFoundError):
        store.clear_config("slack")  # nothing to remove


def test_endpoints_and_rbac():
    with TestClient(app) as client:
        assert client.get("/integrations/catalog", headers={"X-User-Role": "viewer"}).status_code == 200
        # config read/write is admin-only.
        assert client.get("/integrations/jira/config", headers={"X-User-Role": "viewer"}).status_code == 403
        assert client.get("/integrations/jira/config", headers={"X-User-Role": "admin"}).status_code == 200
        body = {"values": {"base_url": "https://a.atlassian.net", "email": "a@a.com", "api_token": "T"}, "enabled": True}
        assert client.patch("/integrations/jira/config", json=body, headers={"X-User-Role": "contributor"}).status_code == 403
        saved = client.patch("/integrations/jira/config", json=body, headers={"X-User-Role": "admin"})
        assert saved.status_code == 200 and saved.json()["enabled"] is True
        assert client.get("/integrations/unknown/config", headers={"X-User-Role": "admin"}).status_code == 404
        assert client.post("/integrations/jira/test", headers={"X-User-Role": "admin"}).json()["ok"] is True
