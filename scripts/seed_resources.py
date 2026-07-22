"""Seed a realistic sample organization into the global resource directory.

Run from the repository root with ``npm run api:seed:resources`` or
``python scripts/seed_resources.py``.

The seed is idempotent. Records created by this script carry a stable employee
number and ``sample_seed`` marker, so subsequent runs update those records and
their reporting lines instead of creating duplicate people. User-created staff
are never matched or modified by name alone.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.access import store as access_store  # noqa: E402
from backend.access.models import AccessUpdate  # noqa: E402
from backend.resources import store  # noqa: E402
from backend.resources.models import (  # noqa: E402
    CustomFieldCreate,
    LookupCreate,
    StaffCreate,
    StaffUpdate,
)
from backend.storage.db import db_path  # noqa: E402

ORGANIZATION = "Northstar Digital"
SEED_MARKER = "northstar_sample_organization_v1"


# Codes are intentionally stable because resource records, imports and filters
# persist them. Existing application defaults remain available alongside these.
LOOKUPS = {
    "tech_unit": [
        ("EXEC", "Executive Office"),
        ("PRODUCT", "Product Management"),
        ("ENGINEERING", "Software Engineering"),
        ("ARCH", "Enterprise Architecture"),
        ("DELIVERY", "Delivery & PMO"),
        ("SEC", "Cybersecurity"),
        ("OPS", "Cloud & Technology Operations"),
        ("PEOPLE", "People Operations"),
    ],
    "rank": [
        ("EXEC", "C-Suite"),
        ("VP", "Vice President"),
        ("DIR", "Director / Head"),
        ("PRINC", "Principal"),
        ("MGR", "Manager"),
        ("LEAD", "Lead"),
        ("SENIOR", "Senior Professional"),
        ("PRO", "Professional"),
    ],
    "hr_role": [
        ("CTO", "Chief Technology Officer"),
        ("PROD", "Product Management"),
        ("ENG_MGR", "Engineering Manager"),
        ("SWE", "Software Engineer"),
        ("ARCHITECT", "Architect"),
        ("DELIVERY", "Program / Delivery Manager"),
        ("SCRUM", "Scrum Master / Agile Coach"),
        ("DATA_ENG", "Data Engineer"),
        ("DATA_SCI", "Data Scientist / ML Engineer"),
        ("SECURITY", "Security Professional"),
        ("SRE", "Site Reliability / DevOps Engineer"),
        ("SUPPORT", "Technology Support"),
        ("PEOPLE_OPS", "People Operations"),
        ("UX", "UX Designer"),
    ],
}

CUSTOM_FIELDS = [
    CustomFieldCreate(key="email", label="Work email", field_type="text"),
    CustomFieldCreate(key="username", label="Directory username", field_type="text"),
    CustomFieldCreate(key="employee_number", label="Employee number", field_type="text"),
    CustomFieldCreate(key="phone", label="Work phone", field_type="text"),
    CustomFieldCreate(
        key="location",
        label="Office location",
        field_type="select",
        options=["Bengaluru", "Hyderabad", "London", "New York", "Singapore", "Toronto", "Remote"],
    ),
    CustomFieldCreate(key="cost_center", label="Cost center", field_type="text"),
    CustomFieldCreate(key="skills", label="Primary skills", field_type="text"),
    CustomFieldCreate(
        key="work_arrangement",
        label="Work arrangement",
        field_type="select",
        options=["Hybrid", "Remote", "On-site"],
    ),
    CustomFieldCreate(key="sample_seed", label="Sample data source", field_type="text"),
]


def person(
    key: str,
    first: str,
    last: str,
    *,
    manager: str | None,
    unit: str,
    rank: str,
    hr_role: str,
    app_role: str = "contributor",
    location: str = "Bengaluru",
    citizenship: str = "IN",
    skills: str = "",
    allocation: str = "Allocated",
    staff_type: str = "Perm",
    start: date = date(2022, 1, 10),
    end: date | None = None,
    active: bool = True,
    page_permissions: dict[str, bool] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "first": first,
        "last": last,
        "manager": manager,
        "unit": unit,
        "rank": rank,
        "hr_role": hr_role,
        "app_role": app_role,
        "location": location,
        "citizenship": citizenship,
        "skills": skills,
        "allocation": allocation,
        "staff_type": staff_type,
        "start": start,
        "end": end,
        "active": active,
        "page_permissions": page_permissions or {},
    }


# Parents precede reports. This lets the normal store validation enforce every
# reporting-manager relationship while the organization is being constructed.
PEOPLE = [
    person("cto", "Aisha", "Raman", manager=None, unit="EXEC", rank="EXEC", hr_role="CTO",
           app_role="admin", location="New York", skills="Technology strategy, portfolio governance",
           start=date(2018, 4, 2)),

    # Product management
    person("vp_product", "Daniel", "Brooks", manager="cto", unit="PRODUCT", rank="VP", hr_role="PROD",
           app_role="manager", location="London", citizenship="GB", skills="Product strategy, P&L",
           start=date(2019, 6, 3)),
    person("group_pm", "Maya", "Patel", manager="vp_product", unit="PRODUCT", rank="DIR", hr_role="PROD",
           app_role="manager", skills="Digital channels, product discovery", start=date(2020, 2, 17)),
    person("senior_pm", "Omar", "Hassan", manager="vp_product", unit="PRODUCT", rank="MGR", hr_role="PROD",
           app_role="manager", location="Toronto", citizenship="CA", skills="Core CRM, roadmap management",
           start=date(2021, 5, 10)),
    person("business_analyst", "Chloe", "Martin", manager="group_pm", unit="PRODUCT", rank="SENIOR", hr_role="BA",
           location="London", citizenship="GB", skills="Business analysis, process modelling",
           allocation="PartiallyAllocated", start=date(2022, 8, 1)),
    person("ux_lead", "Lucas", "Silva", manager="group_pm", unit="PRODUCT", rank="LEAD", hr_role="UX",
           location="Remote", citizenship="BR", skills="Service design, accessibility, Figma",
           start=date(2021, 11, 8)),
    person("product_owner", "Ananya", "Iyer", manager="senior_pm", unit="PRODUCT", rank="SENIOR", hr_role="PROD",
           location="Hyderabad", skills="Backlog management, customer journeys", start=date(2023, 1, 9)),

    # Software engineering
    person("vp_engineering", "Priya", "Nair", manager="cto", unit="ENGINEERING", rank="VP", hr_role="ENG_MGR",
           app_role="manager", location="Bengaluru", skills="Engineering strategy, platform modernization",
           start=date(2019, 9, 16)),
    person("client_eng_mgr", "Sophia", "Chen", manager="vp_engineering", unit="ENGINEERING", rank="MGR", hr_role="ENG_MGR",
           app_role="manager", location="Singapore", citizenship="SG", skills="Web and mobile engineering",
           start=date(2020, 7, 13)),
    person("core_eng_mgr", "Marcus", "Lee", manager="vp_engineering", unit="ENGINEERING", rank="MGR", hr_role="ENG_MGR",
           app_role="manager", location="Toronto", citizenship="CA", skills="Distributed systems, APIs",
           start=date(2020, 10, 5)),
    person("client_lead", "Ethan", "Brown", manager="client_eng_mgr", unit="ENGINEERING", rank="LEAD", hr_role="SWE",
           location="London", citizenship="GB", skills="React, TypeScript, frontend architecture",
           start=date(2021, 4, 12)),
    person("frontend_eng", "Kavya", "Reddy", manager="client_lead", unit="ENGINEERING", rank="PRO", hr_role="SWE",
           location="Hyderabad", skills="React, TypeScript, design systems", start=date(2023, 6, 19)),
    person("backend_eng", "Mateo", "Alvarez", manager="client_lead", unit="ENGINEERING", rank="SENIOR", hr_role="SWE",
           location="Remote", citizenship="ES", skills="Python, FastAPI, event-driven services",
           start=date(2022, 3, 7)),
    person("qa_lead", "Zoe", "Johnson", manager="client_eng_mgr", unit="ENGINEERING", rank="LEAD", hr_role="QA",
           location="London", citizenship="GB", skills="Quality strategy, test automation",
           start=date(2021, 8, 23)),
    person("qa_eng", "Ravi", "Shah", manager="qa_lead", unit="ENGINEERING", rank="PRO", hr_role="QA",
           skills="Playwright, API testing, performance testing", start=date(2023, 9, 4)),
    person("mobile_eng", "Nina", "Petrov", manager="client_eng_mgr", unit="ENGINEERING", rank="SENIOR", hr_role="SWE",
           location="Remote", citizenship="BG", skills="React Native, iOS, Android",
           allocation="PartiallyAllocated", start=date(2022, 5, 16)),
    person("core_lead", "Jack", "Wilson", manager="core_eng_mgr", unit="ENGINEERING", rank="LEAD", hr_role="SWE",
           location="New York", citizenship="US", skills="Java, Spring Boot, domain-driven design",
           start=date(2020, 11, 2)),
    person("java_eng", "Meera", "Krishnan", manager="core_lead", unit="ENGINEERING", rank="SENIOR", hr_role="SWE",
           skills="Java, Spring, PostgreSQL", start=date(2022, 9, 12)),
    person("api_contractor", "Ahmed", "El-Sayed", manager="core_lead", unit="ENGINEERING", rank="SENIOR", hr_role="SWE",
           location="Remote", citizenship="AE", skills="API design, Kafka, integration",
           staff_type="Contract", start=date(2025, 1, 6), end=date(2027, 1, 5)),

    # Architecture
    person("chief_architect", "Elena", "Garcia", manager="cto", unit="ARCH", rank="DIR", hr_role="ARCHITECT",
           app_role="manager", location="New York", citizenship="US", skills="Enterprise architecture, C4, governance",
           start=date(2019, 3, 11), page_permissions={"admin_integrations": True}),
    person("solution_arch", "Fatima", "Zahra", manager="chief_architect", unit="ARCH", rank="PRINC", hr_role="ARCHITECT",
           location="London", citizenship="GB", skills="Solution architecture, cloud, integration",
           start=date(2020, 12, 7)),
    person("data_arch", "Kenji", "Tanaka", manager="chief_architect", unit="ARCH", rank="PRINC", hr_role="ARCHITECT",
           location="Singapore", citizenship="JP", skills="Data architecture, governance, analytics",
           start=date(2021, 6, 14)),
    person("security_arch", "Samuel", "Okafor", manager="chief_architect", unit="ARCH", rank="PRINC", hr_role="ARCHITECT",
           location="Toronto", citizenship="CA", skills="Zero trust, threat modelling, IAM",
           start=date(2021, 2, 8)),

    # Delivery and portfolio management
    person("delivery_director", "Grace", "Kim", manager="cto", unit="DELIVERY", rank="DIR", hr_role="DELIVERY",
           app_role="manager", location="New York", citizenship="US", skills="Portfolio delivery, financial governance",
           start=date(2019, 10, 21)),
    person("program_mgr", "Rachel", "Green", manager="delivery_director", unit="DELIVERY", rank="MGR", hr_role="DELIVERY",
           app_role="manager", location="London", citizenship="GB", skills="Program management, dependency planning",
           start=date(2021, 1, 18)),
    person("delivery_mgr", "Arjun", "Rao", manager="delivery_director", unit="DELIVERY", rank="MGR", hr_role="DELIVERY",
           app_role="manager", location="Hyderabad", skills="Delivery management, risk management",
           start=date(2021, 7, 5)),
    person("scrum_master", "Sofia", "Costa", manager="program_mgr", unit="DELIVERY", rank="SENIOR", hr_role="SCRUM",
           location="Remote", citizenship="PT", skills="Scrum, facilitation, team coaching",
           start=date(2022, 10, 10)),
    person("agile_coach", "Ben", "Carter", manager="delivery_director", unit="DELIVERY", rank="LEAD", hr_role="SCRUM",
           location="Toronto", citizenship="CA", skills="Agile coaching, flow metrics",
           allocation="PartiallyAllocated", start=date(2020, 5, 4)),

    # Data and AI
    person("data_director", "Liam", "O'Connor", manager="cto", unit="DATA", rank="DIR", hr_role="DATA_ENG",
           app_role="manager", location="London", citizenship="IE", skills="Data strategy, AI governance",
           start=date(2020, 1, 13)),
    person("data_lead", "Yuki", "Tanaka", manager="data_director", unit="DATA", rank="LEAD", hr_role="DATA_ENG",
           location="Singapore", citizenship="JP", skills="Data platforms, Spark, streaming",
           start=date(2021, 9, 20)),
    person("data_engineer", "Sara", "Ahmed", manager="data_lead", unit="DATA", rank="PRO", hr_role="DATA_ENG",
           location="Hyderabad", skills="Python, dbt, data quality", start=date(2023, 3, 6)),
    person("ml_engineer", "Leo", "Martins", manager="data_director", unit="DATA", rank="SENIOR", hr_role="DATA_SCI",
           location="Remote", citizenship="BR", skills="Machine learning, MLOps, NLP",
           staff_type="Contract", start=date(2024, 2, 5), end=date(2027, 2, 4)),
    person("bi_analyst", "Imani", "Osei", manager="data_director", unit="DATA", rank="SENIOR", hr_role="BA",
           location="London", citizenship="GH", skills="Power BI, portfolio analytics",
           allocation="PartiallyAllocated", start=date(2022, 6, 27)),

    # Cybersecurity
    person("security_director", "Isabella", "Rossi", manager="cto", unit="SEC", rank="DIR", hr_role="SECURITY",
           app_role="manager", location="Toronto", citizenship="IT", skills="Security strategy, risk and compliance",
           start=date(2020, 4, 6), page_permissions={"admin_integrations": True}),
    person("security_lead", "Victor", "Nguyen", manager="security_director", unit="SEC", rank="LEAD", hr_role="SECURITY",
           location="Singapore", citizenship="SG", skills="Application security, DevSecOps",
           start=date(2021, 10, 11)),
    person("iam_engineer", "Noor", "Khan", manager="security_lead", unit="SEC", rank="SENIOR", hr_role="SECURITY",
           location="London", citizenship="GB", skills="IAM, OAuth, directory services",
           start=date(2022, 12, 5)),
    person("grc_analyst", "Elena", "Petrova", manager="security_director", unit="SEC", rank="PRO", hr_role="SECURITY",
           app_role="viewer", location="Remote", citizenship="BG", skills="GRC, controls assurance",
           allocation="PartiallyAllocated", start=date(2023, 7, 3), page_permissions={"ask_ai": False}),

    # Cloud and technology operations
    person("ops_director", "Noah", "Williams", manager="cto", unit="OPS", rank="DIR", hr_role="SRE",
           app_role="manager", location="New York", citizenship="US", skills="Cloud operations, reliability governance",
           start=date(2019, 12, 2)),
    person("sre_lead", "Oliver", "Smith", manager="ops_director", unit="OPS", rank="LEAD", hr_role="SRE",
           location="Toronto", citizenship="CA", skills="SRE, observability, incident management",
           start=date(2021, 3, 15)),
    person("devops_eng", "Mia", "Wong", manager="sre_lead", unit="OPS", rank="SENIOR", hr_role="SRE",
           location="Singapore", citizenship="SG", skills="Kubernetes, Terraform, CI/CD",
           start=date(2022, 4, 18)),
    person("service_desk_lead", "David", "Mensah", manager="ops_director", unit="OPS", rank="MGR", hr_role="SUPPORT",
           app_role="manager", location="London", citizenship="GH", skills="ITSM, service operations",
           start=date(2020, 8, 24)),
    person("support_analyst", "Lily", "Evans", manager="service_desk_lead", unit="OPS", rank="PRO", hr_role="SUPPORT",
           app_role="viewer", location="London", citizenship="GB", skills="Service desk, user support",
           allocation="UnAllocated", start=date(2024, 1, 8), page_permissions={"ask_ai": False}),

    # People operations owns the resource directory and access lifecycle.
    person("people_head", "Hannah", "Muller", manager="cto", unit="PEOPLE", rank="DIR", hr_role="PEOPLE_OPS",
           app_role="manager", location="London", citizenship="DE", skills="Workforce strategy, organization design",
           start=date(2020, 6, 1), page_permissions={"admin_access": True}),
    person("people_ops_mgr", "Amelia", "Clark", manager="people_head", unit="PEOPLE", rank="MGR", hr_role="PEOPLE_OPS",
           app_role="manager", location="Toronto", citizenship="CA", skills="People operations, onboarding",
           start=date(2021, 11, 15), page_permissions={"admin_access": True}),
    person("resource_analyst", "Jacob", "Stein", manager="people_ops_mgr", unit="PEOPLE", rank="SENIOR", hr_role="PEOPLE_OPS",
           app_role="manager", location="Remote", citizenship="DE", skills="Capacity planning, resource analytics",
           start=date(2023, 5, 22)),

    # Inactive records exercise status filtering and disabled-login behavior.
    person("former_ux", "Eva", "Novak", manager="group_pm", unit="PRODUCT", rank="SENIOR", hr_role="UX",
           app_role="viewer", location="Remote", citizenship="CZ", skills="UX research",
           allocation="UnAllocated", staff_type="Contract", start=date(2023, 2, 6), end=date(2025, 12, 19), active=False),
    person("former_data", "Carlos", "Mendes", manager="data_lead", unit="DATA", rank="SENIOR", hr_role="DATA_ENG",
           app_role="viewer", location="Remote", citizenship="PT", skills="Data migration",
           allocation="UnAllocated", staff_type="Contract", start=date(2022, 7, 4), end=date(2025, 9, 30), active=False),
]


def ensure_lookups() -> None:
    existing = {
        category: {item["code"] for item in store.list_lookups(category)}
        for category in LOOKUPS
    }
    for category, entries in LOOKUPS.items():
        for code, label in entries:
            if code not in existing[category]:
                store.create_lookup(category, LookupCreate(code=code, label=label))


def ensure_custom_fields() -> None:
    existing = {field["key"]: field for field in store.list_custom_fields()}
    for field in CUSTOM_FIELDS:
        if field.key not in existing:
            store.create_custom_field(field)


def _slug(first: str, last: str) -> str:
    return "".join(char for char in f"{first[0]}{last}".lower() if char.isalnum())


def _cost_center(unit: str) -> str:
    codes = {
        "EXEC": "CC-1000", "PRODUCT": "CC-2000", "ENGINEERING": "CC-3000",
        "ARCH": "CC-4000", "DELIVERY": "CC-5000", "DATA": "CC-6000",
        "SEC": "CC-7000", "OPS": "CC-8000", "PEOPLE": "CC-9000",
    }
    return codes[unit]


def _custom_values(item: dict[str, Any], index: int) -> dict[str, Any]:
    username = _slug(item["first"], item["last"])
    return {
        "email": f"{item['first'].lower().replace(' ', '')}.{item['last'].lower().replace(' ', '').replace(chr(39), '')}@northstardigital.example",
        "username": username,
        "employee_number": f"NS-{1000 + index:04d}",
        "phone": f"+1-202-555-{1000 + index:04d}",
        "location": item["location"],
        "cost_center": _cost_center(item["unit"]),
        "skills": item["skills"],
        "work_arrangement": "Remote" if item["location"] == "Remote" else "Hybrid",
        "sample_seed": SEED_MARKER,
    }


def _seeded_by_employee_number() -> dict[str, dict[str, Any]]:
    seeded: dict[str, dict[str, Any]] = {}
    for staff in store.list_staff():
        custom = staff.get("custom_values") or {}
        if custom.get("sample_seed") == SEED_MARKER and custom.get("employee_number"):
            seeded[str(custom["employee_number"])] = staff
    return seeded


def main() -> None:
    ensure_lookups()
    ensure_custom_fields()

    existing = _seeded_by_employee_number()
    by_key: dict[str, dict[str, Any]] = {}
    created = 0
    updated = 0

    for index, item in enumerate(PEOPLE, start=1):
        employee_number = f"NS-{1000 + index:04d}"
        manager_id = by_key[item["manager"]]["id"] if item["manager"] else None
        values = _custom_values(item, index)
        payload = {
            "staff_first_name": item["first"],
            "staff_last_name": item["last"],
            "staff_name": f"{item['first']} {item['last']}",
            "staff_type": item["staff_type"],
            "staff_status": "Active" if item["active"] else "Inactive",
            "sub_status": item["allocation"],
            "tech_unit": item["unit"],
            "citizenship": item["citizenship"],
            "rank": item["rank"],
            "hr_role": item["hr_role"],
            "staff_start_date": item["start"],
            "staff_end_date": item["end"],
            "reporting_manager_id": manager_id,
            "custom_values": values,
        }

        current = existing.get(employee_number)
        if current:
            staff = store.update_staff(current["id"], StaffUpdate(**payload))
            updated += 1
        else:
            staff = store.create_staff(StaffCreate(**payload))
            created += 1

        access_store.set_access(
            staff["id"],
            AccessUpdate(role=item["app_role"], enabled=item["active"]),
        )
        if item["app_role"] != "admin" and item["page_permissions"]:
            access_store.set_page_permissions(staff["id"], item["page_permissions"])
        by_key[item["key"]] = staff

    active_count = sum(1 for item in PEOPLE if item["active"])
    units = len({item["unit"] for item in PEOPLE})
    role_counts = access_store.role_counts()
    print(f"Seeded {ORGANIZATION} into {db_path()}.")
    print(f"  people: {len(PEOPLE)} total ({active_count} active, {len(PEOPLE) - active_count} inactive)")
    print(f"  changes: {created} created, {updated} updated")
    print(f"  organization: {units} functions with validated reporting lines")
    print(
        "  access: "
        + ", ".join(f"{role}={role_counts[role]}" for role in ("admin", "manager", "contributor", "viewer"))
        + f", disabled={role_counts['disabled']}"
    )
    print("Refresh Admin > Resources to view the directory.")


if __name__ == "__main__":
    main()
