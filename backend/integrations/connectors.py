"""Per-connector configuration field schemas.

Each connector in the catalog is mapped to an *archetype* describing the fields a
user must supply to configure it (base URL, credentials, connector-specific
options). Secret fields are flagged so the store can mask them on read and treat
them as write-only. In-app adapters (document import, mermaid, resource
directory) need no configuration and are not configurable.
"""

from __future__ import annotations

from typing import Any


def _field(key: str, label: str, ftype: str = "text", required: bool = True, secret: bool = False, placeholder: str = "") -> dict[str, Any]:
    return {"key": key, "label": label, "type": ftype, "required": required, "secret": secret, "placeholder": placeholder}


# Reusable field sets keyed by archetype.
ARCHETYPE_FIELDS: dict[str, list[dict[str, Any]]] = {
    "atlassian": [
        _field("base_url", "Base URL", "url", placeholder="https://yourorg.atlassian.net"),
        _field("email", "Account email", "text", placeholder="you@company.com"),
        _field("api_token", "API token", "password", secret=True),
    ],
    "token": [
        _field("base_url", "Base URL", "url", placeholder="https://api.example.com"),
        _field("api_token", "Access token", "password", secret=True),
    ],
    "apikey": [
        _field("base_url", "Base URL", "url", placeholder="https://api.example.com"),
        _field("api_key", "API key", "password", secret=True),
    ],
    "basic": [
        _field("base_url", "Instance URL", "url", placeholder="https://instance.example.com"),
        _field("username", "Username", "text"),
        _field("password", "Password", "password", secret=True),
    ],
    "webhook": [
        _field("webhook_url", "Incoming webhook URL", "url", secret=True, placeholder="https://hooks.example.com/services/…"),
    ],
    "directory": [
        _field("server_url", "Server URL", "url", placeholder="ldaps://ad.company.com:636"),
        _field("bind_dn", "Bind DN", "text", placeholder="CN=svc,OU=Service,DC=company,DC=com"),
        _field("bind_password", "Bind password", "password", secret=True),
        _field("base_dn", "Base DN", "text", placeholder="DC=company,DC=com"),
    ],
    "oauth": [
        _field("base_url", "Base URL", "url", placeholder="https://api.example.com"),
        _field("client_id", "Client ID", "text"),
        _field("client_secret", "Client secret", "password", secret=True),
        _field("tenant_id", "Tenant ID", "text", required=False),
    ],
}

# connector key -> archetype. Anything catalogued but absent here uses DEFAULT.
CONNECTOR_ARCHETYPE: dict[str, str] = {
    # Product & delivery
    "jira": "atlassian", "azure_devops": "token", "rally": "apikey", "aha": "apikey", "jira_align": "atlassian",
    # Documentation
    "confluence": "atlassian", "sharepoint": "oauth", "google_drive": "oauth", "notion": "token",
    # Architecture
    "structurizr": "token", "plantuml": "token", "drawio": "token", "lucidchart": "apikey",
    "leanix": "apikey", "ardoq": "apikey", "sparx": "basic",
    # People
    "ldap": "directory", "active_directory": "directory", "workday": "apikey", "successfactors": "apikey",
    "teams": "webhook", "slack": "webhook",
    # Engineering
    "github": "token", "bitbucket": "atlassian", "gitlab": "token", "sonarqube": "token",
    "snyk": "token", "jenkins": "basic", "github_actions": "token",
    # Risk & operations
    "servicenow_grc": "basic", "servicenow_itsm": "basic", "archer": "basic", "pagerduty": "apikey",
    "opsgenie": "apikey", "splunk": "token", "elk": "apikey", "grafana": "token",
    "prometheus": "token", "appdynamics": "apikey",
}

DEFAULT_ARCHETYPE = "token"

# In-app adapters need no external configuration.
NON_CONFIGURABLE = {"document_import", "mermaid", "resource_directory"}


def is_configurable(key: str) -> bool:
    return key not in NON_CONFIGURABLE


def archetype_for(key: str) -> str:
    return CONNECTOR_ARCHETYPE.get(key, DEFAULT_ARCHETYPE)


def fields_for(key: str) -> list[dict[str, Any]]:
    """The list of configuration fields for a connector (empty if not configurable)."""
    if not is_configurable(key):
        return []
    return [dict(field) for field in ARCHETYPE_FIELDS[archetype_for(key)]]


def field_keys(key: str) -> set[str]:
    return {field["key"] for field in fields_for(key)}


def secret_keys(key: str) -> set[str]:
    return {field["key"] for field in fields_for(key) if field["secret"]}


def required_keys(key: str) -> set[str]:
    return {field["key"] for field in fields_for(key) if field["required"]}
