"""The catalog of integrations (requirement section 10), grouped by category.

`status` is computed at request time: `connected` when the app can actually
reach it now (Jira with configured instances), `adapter` when there is a working
in-app adapter (document import → AI extraction), else `available` (catalogued,
connection is a configuration/roadmap step).
"""

from __future__ import annotations

from typing import Any

# category -> [(key, name, purpose)]
CATALOG: dict[str, list[tuple[str, str, str]]] = {
    "Product & delivery": [
        ("jira", "Jira", "Initiatives, epics, stories, dependencies, delivery status"),
        ("azure_devops", "Azure DevOps", "Boards, repos, pipelines and work items"),
        ("rally", "Rally", "Agile portfolio and team planning"),
        ("aha", "Aha!", "Product roadmap and strategy"),
        ("jira_align", "Jira Align", "Portfolio, themes, objectives and funding"),
    ],
    "Documentation": [
        ("document_import", "Document import", "Paste strategy/architecture docs — AI extracts L1 artifacts"),
        ("confluence", "Confluence", "Strategy, architecture and design documents"),
        ("sharepoint", "SharePoint", "Enterprise documents, approvals and governance evidence"),
        ("google_drive", "Google Drive", "Documents, spreadsheets and diagrams"),
        ("notion", "Notion", "Lightweight product and architecture content"),
    ],
    "Architecture": [
        ("mermaid", "Mermaid", "Lightweight diagrams as code"),
        ("structurizr", "Structurizr", "Create, update and publish C4 models"),
        ("plantuml", "PlantUML", "UML and architecture diagrams"),
        ("drawio", "Draw.io", "Visual diagrams"),
        ("lucidchart", "Lucidchart", "Enterprise diagrams"),
        ("leanix", "LeanIX", "Enterprise architecture and capability mapping"),
        ("ardoq", "Ardoq", "Enterprise architecture and dependency mapping"),
        ("sparx", "Sparx EA", "Detailed enterprise modelling"),
    ],
    "People": [
        ("resource_directory", "Resource directory", "The app's own staff pool"),
        ("ldap", "LDAP", "Users, teams and groups"),
        ("active_directory", "Active Directory", "Users, roles and reporting lines"),
        ("workday", "Workday", "People, roles and departments"),
        ("successfactors", "SuccessFactors", "HR and reporting structure"),
        ("teams", "Microsoft Teams", "Notifications and approvals"),
        ("slack", "Slack", "Notifications and collaboration"),
    ],
    "Engineering": [
        ("github", "GitHub", "Repositories, PRs and code ownership"),
        ("bitbucket", "Bitbucket", "Repositories, PRs and branch activity"),
        ("gitlab", "GitLab", "Repositories, CI/CD and merge requests"),
        ("sonarqube", "SonarQube", "Code quality and security findings"),
        ("snyk", "Snyk", "Dependency and container vulnerabilities"),
        ("jenkins", "Jenkins", "Pipeline and build status"),
        ("github_actions", "GitHub Actions", "Workflow and build status"),
    ],
    "Risk & operations": [
        ("servicenow_grc", "ServiceNow GRC", "Risks, controls and compliance records"),
        ("servicenow_itsm", "ServiceNow ITSM", "Incidents, changes and problems"),
        ("archer", "Archer", "Enterprise risk register"),
        ("pagerduty", "PagerDuty", "On-call and incident response"),
        ("opsgenie", "Opsgenie", "Alert and incident response"),
        ("splunk", "Splunk", "Logs and runtime events"),
        ("elk", "ELK", "Logs and runtime events"),
        ("grafana", "Grafana", "Dashboards and SLO data"),
        ("prometheus", "Prometheus", "Metrics and alert data"),
        ("appdynamics", "AppDynamics", "Application performance data"),
    ],
}

# Integrations that have a working in-app adapter today.
_ADAPTERS = {"document_import", "mermaid", "resource_directory"}


def list_catalog() -> dict[str, Any]:
    from backend.integrations import connectors, store
    from backend.jira.registry import get_jira_registry

    jira_connected = bool(get_jira_registry().list_instances())
    configured = store.configured_keys()
    groups = []
    counts = {"connected": 0, "adapter": 0, "available": 0}
    for category, tools in CATALOG.items():
        items = []
        for key, name, purpose in tools:
            if key in _ADAPTERS:
                status = "adapter"
            elif key in configured or (key == "jira" and jira_connected):
                status = "connected"
            else:
                status = "available"
            counts[status] += 1
            items.append({
                "key": key, "name": name, "purpose": purpose, "status": status,
                "configurable": connectors.is_configurable(key),
            })
        groups.append({"category": category, "tools": items})
    total = sum(len(tools) for tools in CATALOG.values())
    return {"groups": groups, "total": total, "counts": counts}
