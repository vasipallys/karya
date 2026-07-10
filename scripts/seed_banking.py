"""Seed a detailed retail-banking sample project with a full C4 structure.

Run from the repository root:  python scripts/seed_banking.py
Creates a new project each run. Descriptions are written as estimation
evidence, so every L3 story is immediately estimable from the canvas.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.c4.models import C4ElementCreate, C4RelationCreate  # noqa: E402
from backend.c4.store import create_element, create_relation, tag_cross_cutting, upsert_artifact  # noqa: E402
from backend.projects.models import ProjectCreate, RepoLinkCreate  # noqa: E402
from backend.projects.store import add_repo_link, create_project  # noqa: E402


def element(project_id, level, name, *, parent=None, x=None, y=None, **extra):
    return create_element(project_id, C4ElementCreate(
        level=level, name=name, parent_id=parent["id"] if parent else None,
        pos_x=x, pos_y=y, **extra,
    ))


def relate(project_id, source, target, label, kind="sync"):
    create_relation(project_id, C4RelationCreate(
        source_id=source["id"], target_id=target["id"], label=label, kind=kind,
    ))


def main() -> None:
    project = create_project(ProjectCreate(
        name="Retail banking (sample)",
        description=(
            "Digital retail banking for a regulated European bank: onboarding, accounts, "
            "payments, and fraud monitoring. PSD2/SCA, GDPR, and SOX audit obligations apply. "
            "React micro-frontends and Spring Boot microservices on OpenShift; Kafka event backbone."
        ),
    ))
    pid = project["id"]
    add_repo_link(pid, RepoLinkCreate(url="https://github.com/example/retail-banking.git", mode="existing"))

    # ---- L1 · System context (theme / initiative) -------------------------
    bank = element(pid, "L1", "Digital retail banking", kind="system", x=340, y=150,
                   description="The bank-owned digital platform this initiative delivers: onboarding, daily banking, and payments for retail customers.")
    customer = element(pid, "L1", "Retail customer", kind="person", x=40, y=150,
                       description="Account holder using web and mobile; authenticated with SCA (PSD2).")
    core = element(pid, "L1", "Core banking system", kind="external system", x=660, y=40,
                   description="Vendor core (ledger, product engine). Fixed nightly batch windows; SOAP/ISO 20022 interfaces; change requests take a full release cycle.")
    bureau = element(pid, "L1", "Credit bureau & eKYC provider", kind="external system", x=660, y=170,
                     description="External identity verification and credit scoring. Rate-limited REST API, PII residency constraints (GDPR).")
    scheme = element(pid, "L1", "Payment schemes (SEPA/SWIFT)", kind="external system", x=660, y=300,
                     description="Clearing and settlement rails. Cut-off times, mandatory sanctions screening before submission.")
    relate(pid, customer, bank, "banks via web/mobile")
    relate(pid, bank, core, "posts and reads ledger", "sync")
    relate(pid, bank, bureau, "verifies identity", "sync")
    relate(pid, bank, scheme, "clears payments", "async")

    # ---- L2 · Containers (epics) inside the platform ----------------------
    def container(name, tech, description, x, y):
        return element(pid, "L2", name, parent=bank, kind="container", tech=tech, description=description, x=x, y=y)

    onboarding_web = container("onboarding-web", "React 19 micro-frontend",
                               "Customer acquisition journey: identity capture, eKYC, product selection, account opening. WCAG 2.2 AA.", 40, 40)
    portal_web = container("banking-portal-web", "React 19 micro-frontend",
                           "Authenticated daily banking: balances, statements, transfers, standing orders, notifications preferences.", 40, 190)
    gateway = container("api-gateway", "Spring Cloud Gateway",
                        "Single entry point: OAuth2/OIDC token relay, SCA step-up triggers, rate limiting, request audit headers.", 340, 40)
    customer_svc = container("customer-service", "Spring Boot 3",
                             "Customer profile, consents (PSD2), and preference management. GDPR data-subject requests originate here.", 340, 190)
    account_svc = container("account-service", "Spring Boot 3",
                            "Accounts, balances, statements; reads core banking; caches positions with strict staleness rules.", 340, 340)
    payment_svc = container("payment-service", "Spring Boot 3",
                            "Payment initiation state machine: validation, enrichment, sanctions screening, routing to schemes via the core.", 340, 490)
    fraud = container("fraud-engine", "Kafka Streams",
                      "Real-time transaction monitoring: velocity rules, device fingerprint signals, case creation for analysts.", 640, 340)
    notify = container("notification-service", "Spring Boot 3",
                       "Transactional email/SMS/push with consent checks and template governance.", 640, 190)
    events = container("event-bus", "Kafka", "Event backbone: payment lifecycle, fraud signals, audit trail topics (append-only, 7-year retention).", 640, 490)
    cust_db = container("customer-db", "PostgreSQL 16", "Customer and consent data. Encrypted at rest, field-level PII controls.", 40, 340)
    txn_db = container("transaction-db", "PostgreSQL 16", "Payment instructions and status history. Append-only audit schema.", 40, 490)

    relate(pid, onboarding_web, gateway, "REST via BFF")
    relate(pid, portal_web, gateway, "REST via BFF")
    relate(pid, gateway, customer_svc, "routes")
    relate(pid, gateway, account_svc, "routes")
    relate(pid, gateway, payment_svc, "routes")
    relate(pid, customer_svc, cust_db, "reads/writes", "data")
    relate(pid, payment_svc, txn_db, "persists instructions", "data")
    relate(pid, payment_svc, events, "publishes lifecycle events", "async")
    relate(pid, events, fraud, "streams transactions", "async")
    relate(pid, fraud, events, "emits fraud signals", "async")
    relate(pid, events, notify, "triggers notifications", "async")

    # ---- L3 · Components (stories) ----------------------------------------
    def story(parent, name, user_story, tech_notes, x, y, tech=""):
        return element(pid, "L3", name, parent=parent, kind="component", tech=tech, x=x, y=y,
                       description=f"{user_story}\n\nTechnical notes: {tech_notes}")

    doc_capture = story(onboarding_web, "Identity document capture",
                        "As an applicant I can photograph my ID and see instant quality feedback so my application is not rejected later.",
                        "Camera/file capture with client-side blur/glare checks; uploads via pre-signed URL; retries on flaky mobile networks; accessibility for assistive tech.", 40, 40)
    ekyc_screen = story(onboarding_web, "eKYC status and retry screen",
                        "As an applicant I can see my verification status and complete missing steps without restarting the journey.",
                        "Polls verification status; resumable journey state; distinct flows for refer/reject outcomes with human-readable reasons.", 40, 190)
    product_wizard = story(onboarding_web, "Product selection wizard",
                           "As an applicant I can compare current accounts and select one with clear fee disclosure (regulatory requirement).",
                           "Config-driven product catalogue; fee disclosure PDFs generated server-side; analytics events for funnel drop-off.", 40, 340)

    consent_api = story(customer_svc, "Consent management API (PSD2)",
                        "As a TPP or internal channel I can create, read, and revoke customer consents with a full audit trail.",
                        "Consent state machine with expiry; every transition audited to the event bus; GDPR erasure interacts with retention rules.", 40, 40)
    profile_api = story(customer_svc, "Customer profile API",
                        "As a channel I can read and update contact details with strong validation and change notifications.",
                        "Optimistic locking; address validation service integration; PII field-level encryption; emits profile-changed events.", 40, 190)

    balances_api = story(account_svc, "Balance and statement API",
                         "As a customer I can see near-real-time balances and download statements for any period.",
                         "Core banking read adapter with cache and staleness budget of 60s; statement PDFs rendered async; pagination over 7 years of history.", 40, 40)
    accrual_job = story(account_svc, "Interest accrual reconciliation job",
                        "As finance I need daily verification that platform balances match core banking accruals.",
                        "Nightly batch inside core's window; discrepancy report with tolerance thresholds; alerting into ops channel.", 40, 190)

    transfer_api = story(payment_svc, "Domestic transfer API",
                         "As a customer I can send a SEPA transfer and receive a payment id and status immediately.",
                         "Idempotency keys; synchronous sanctions screening budget 300ms; outbox pattern to the event bus; SCA challenge integration via gateway.", 40, 40)
    standing_orders = story(payment_svc, "Standing order scheduler",
                            "As a customer I can create, amend, and cancel standing orders that execute reliably on schedule.",
                            "Cron-like scheduler with calendar rules (TARGET2 holidays); retries with dead-letter handling; amendments versioned for audit.", 40, 190)
    sanctions_adapter = story(payment_svc, "Sanctions screening adapter",
                              "As compliance I need every instruction screened against the sanctions list before routing, deny-by-default on timeout.",
                              "Vendor API with 300ms budget and circuit breaker; deny-by-default; full audit event per decision; list-update reconciliation.", 40, 340)
    payment_webhooks = story(payment_svc, "Payment status webhooks",
                             "As a partner system I can subscribe to payment status changes with guaranteed at-least-once delivery.",
                             "Webhook registry with HMAC signing; retry/backoff with DLQ; replay endpoint for consumers that lost events.", 40, 490)

    velocity_rules = story(fraud, "Velocity rules evaluator",
                           "As a fraud analyst I need configurable velocity rules (amount/count per window) evaluated in-stream under 50ms.",
                           "Kafka Streams state stores; rule config hot-reload; shadow-mode evaluation before enforcement.", 40, 40)
    fraud_cases = story(fraud, "Fraud case creation adapter",
                        "As a fraud analyst I get a case with full transaction context whenever a rule fires.",
                        "Case-management REST integration; dedup within correlation window; PII minimization in case payloads.", 40, 190)

    token_relay = story(gateway, "OAuth2 token relay and SCA step-up",
                        "As a channel I get seamless token relay, with SCA step-up triggered for high-risk operations (PSD2 RTS).",
                        "Token exchange; risk-based step-up policy config; session binding; audit headers propagated to all services.", 40, 40)

    # A few stories arrive pre-linked to Jira issue keys (reference only).
    upsert_artifact(transfer_api["id"], "story", jira_issue_key="RB-201")
    upsert_artifact(consent_api["id"], "story", jira_issue_key="RB-115")
    upsert_artifact(doc_capture["id"], "story", jira_issue_key="RB-42")

    # ---- L4 · Code-level tasks under one story (example decomposition) ----
    def task(parent, name, description, x, y):
        return element(pid, "L4", name, parent=parent, kind="task", description=description, x=x, y=y)

    task(transfer_api, "TransferController + request validation",
         "REST controller, bean validation, problem-details error mapping, SCA challenge propagation.", 40, 40)
    task(transfer_api, "Outbox publisher",
         "Transactional outbox table + poller publishing lifecycle events to Kafka exactly-once.", 40, 170)
    task(transfer_api, "Idempotency key store",
         "Persistent idempotency keys with TTL; replay returns the original response.", 40, 300)

    # ---- Cross-cutting artifacts ------------------------------------------
    tag_cross_cutting(pid, payment_webhooks["id"], "bug", "RB-388")          # bug lives on L3 (+L4 in Jira)
    tag_cross_cutting(pid, account_svc["id"], "tech_debt", "RB-260")         # cache layer rewrite debt on the container
    tag_cross_cutting(pid, balances_api["id"], "tech_debt", "RB-260")        # and the component it touches
    tag_cross_cutting(pid, payment_svc["id"], "arch_flow", "RB-300")         # payment initiation flow spans containers
    tag_cross_cutting(pid, sanctions_adapter["id"], "arch_flow", "RB-300")

    stories = 14
    print(f"Seeded: {project['name']}")
    print(f"  id: {pid}")
    print(f"  L1: 5 (1 system, 1 person, 3 external)  L2: 11  L3: {stories}  L4: 3")
    print("  relations: 15 · Jira-linked: RB-42, RB-115, RB-201 · cross-cutting: 1 bug, 1 tech debt, 1 arch flow")
    print("Open the app > 'Retail banking (sample)' > C4 canvas. Double-click 'Digital retail banking' to enter the platform.")


if __name__ == "__main__":
    main()
