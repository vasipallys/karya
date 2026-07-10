"""Seed a demo project with a small C4 model so the workspace has sample data.

Run from the repository root:  python scripts/seed_demo.py
Re-running is safe; it creates a new project each time.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.c4.models import C4ElementCreate, C4RelationCreate  # noqa: E402
from backend.c4.store import create_element, create_relation, find_child_by_name, upsert_artifact  # noqa: E402
from backend.projects.models import ProjectCreate, RepoLinkCreate  # noqa: E402
from backend.projects.store import add_repo_link, create_project  # noqa: E402


def element(project_id: str, level: str, name: str, *, parent: dict | None = None, **extra) -> dict:
    return create_element(project_id, C4ElementCreate(level=level, name=name, parent_id=parent["id"] if parent else None, **extra))


def main() -> None:
    project = create_project(ProjectCreate(
        name="Payments platform (demo)",
        description="Card payment initiation and ledger posting for retail banking. Regulated: PSD2, SOX audit trail.",
    ))
    add_repo_link(project["id"], RepoLinkCreate(url="https://github.com/example/payments-platform.git", local_path=str(Path(__file__).resolve().parents[1])))

    system = element(project["id"], "L1", "Payments platform", kind="system",
                     description="Lets retail customers initiate card payments; posts to the general ledger; audited end to end.",
                     pos_x=280, pos_y=120)

    web = element(project["id"], "L2", "payments-web", parent=system, kind="container", tech="React 19 micro-frontend",
                  description="Customer-facing payment initiation UI on the bank portal shell.", pos_x=60, pos_y=60)
    service = element(project["id"], "L2", "payment-service", parent=system, kind="container", tech="Spring Boot 3, OpenShift",
                      description="Validates, enriches, and routes payment instructions; owns the payment state machine.", pos_x=340, pos_y=60)
    ledger = element(project["id"], "L2", "ledger-db", parent=system, kind="container", tech="PostgreSQL 16",
                     description="System of record for posted transactions; append-only audit schema.", pos_x=620, pos_y=60)
    create_relation(project["id"], C4RelationCreate(source_id=web["id"], target_id=service["id"], label="submits payment", kind="sync"))
    create_relation(project["id"], C4RelationCreate(source_id=service["id"], target_id=ledger["id"], label="posts entries", kind="data"))

    stories = [
        ("Payment initiation form", "As a customer I can enter payee, amount, and date, with field-level validation and accessibility to WCAG 2.2 AA.",
         "React form in the portal shell; reuses the design-system components; server-side validation echo.", web),
        ("Payment initiation API", "As the web app I can submit a validated payment instruction and receive a payment id and initial status.",
         "New REST endpoint on payment-service; idempotency keys; request enrichment from the customer profile service.", service),
        ("Limits and sanctions check", "As compliance I need every instruction screened against daily limits and the sanctions list before routing.",
         "Synchronous call to the screening engine with a 300 ms budget; deny-by-default on timeout; full audit event.", service),
        ("Ledger posting worker", "As finance I need confirmed payments posted to the ledger exactly once within 5 seconds.",
         "Outbox pattern from payment-service; consumer writes double-entry rows; reconciliation job for gaps.", ledger),
    ]
    for name, user_story, tech_notes, parent in stories:
        element(project["id"], "L3", name, parent=parent, kind="component",
                description=f"{user_story}\n\nTechnical notes: {tech_notes}")

    # One story arrives pre-linked to a Jira issue key (reference only, no points).
    graph_stories = [name for name, *_ in stories]
    linked = find_child_by_name(project["id"], service["id"], "Payment initiation API")
    if linked:
        upsert_artifact(linked["id"], "story", jira_issue_key="PAY-101")

    print(f"Seeded demo project: {project['name']}")
    print(f"  id: {project['id']}")
    print(f"  elements: 1 system, 3 containers, {len(graph_stories)} stories")
    print("Open the app, pick the demo project, and estimate the stories from the C4 canvas.")


if __name__ == "__main__":
    main()
