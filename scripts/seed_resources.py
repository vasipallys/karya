"""Seed the global resource directory with sample staff, lookups, and custom fields.

Run from the repository root:  python scripts/seed_resources.py

Re-running is safe: extra lookups and custom fields are created only if absent,
and staff always get fresh auto-generated codes (so you may end up with
duplicates of the people if you run it repeatedly).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.resources import store  # noqa: E402
from backend.resources.models import (  # noqa: E402
    CustomFieldCreate,
    LookupCreate,
    StaffCreate,
)

# Extra reference values beyond the defaults init_db seeds (Platform/Data/Mobile/Cloud,
# Analyst…Manager, Engineer…Architect). Ignored if they already exist.
EXTRA_LOOKUPS = {
    "tech_unit": [("AI", "AI & ML"), ("SEC", "Security")],
    "rank": [("D", "Director")],
    "hr_role": [("SM", "Scrum Master"), ("UX", "UX Designer")],
}

CUSTOM_FIELDS = [
    CustomFieldCreate(key="cost_center", label="Cost Center", field_type="text"),
    CustomFieldCreate(key="remote", label="Remote Worker", field_type="boolean"),
    CustomFieldCreate(
        key="clearance", label="Security Clearance", field_type="select", options=["None", "SC", "DV"]
    ),
]

# (first, last, type, status, sub_status, tech_unit, citizenship, rank, hr_role,
#  start, end, manager_key, custom_values). manager_key indexes an earlier person.
PEOPLE = [
    ("Diana", "Prince", "Perm", "Active", "Allocated", "PLATFORM", "US", "D", "PM",
     date(2019, 3, 4), None, None, {"cost_center": "CC-100", "remote": False, "clearance": "DV"}),
    ("Marcus", "Chen", "Perm", "Active", "Allocated", "PLATFORM", "SG", "M", "ARCH",
     date(2020, 6, 15), None, 0, {"cost_center": "CC-110", "remote": False, "clearance": "SC"}),
    ("Priya", "Nair", "Perm", "Active", "Allocated", "DATA", "IN", "M", "PM",
     date(2021, 1, 11), None, 0, {"cost_center": "CC-120", "remote": True, "clearance": "SC"}),
    ("Tom", "Baker", "Perm", "Active", "Allocated", "PLATFORM", "GB", "SC", "ENG",
     date(2021, 9, 1), None, 1, {"cost_center": "CC-110", "remote": True, "clearance": "SC"}),
    ("Aisha", "Khan", "Perm", "Active", "PartiallyAllocated", "PLATFORM", "GB", "C", "ENG",
     date(2022, 2, 14), None, 1, {"cost_center": "CC-110", "remote": True, "clearance": "None"}),
    ("Leo", "Martins", "Contract", "Active", "Allocated", "CLOUD", "BR", "SC", "ENG",
     date(2023, 4, 3), date(2026, 12, 31), 1, {"cost_center": "CC-110", "remote": True, "clearance": "None"}),
    ("Yuki", "Tanaka", "Perm", "Active", "Allocated", "DATA", "JP", "SA", "BA",
     date(2022, 7, 18), None, 2, {"cost_center": "CC-120", "remote": False, "clearance": "None"}),
    ("Sofia", "Rossi", "Perm", "Active", "PartiallyAllocated", "AI", "IT", "SC", "ENG",
     date(2023, 1, 9), None, 2, {"cost_center": "CC-120", "remote": True, "clearance": "SC"}),
    ("Omar", "Haddad", "Contract", "Active", "UnAllocated", "SEC", "AE", "C", "SM",
     date(2024, 5, 20), date(2026, 10, 1), 2, {"cost_center": "CC-120", "remote": True, "clearance": "None"}),
    ("Grace", "Osei", "Perm", "Active", "Allocated", "MOBILE", "GH", "C", "UX",
     date(2023, 11, 6), None, 1, {"cost_center": "CC-110", "remote": True, "clearance": "None"}),
    ("Ivan", "Petrov", "Perm", "Active", "UnAllocated", "PLATFORM", "BG", "A1", "QA",
     date(2025, 2, 3), None, 3, {"cost_center": "CC-110", "remote": True, "clearance": "None"}),
    ("Elena", "Vargas", "Contract", "Inactive", "UnAllocated", "DATA", "ES", "SA", "ENG",
     date(2022, 8, 15), date(2025, 8, 14), 2, {"cost_center": "CC-120", "remote": True, "clearance": "None"}),
]


def ensure_lookups() -> None:
    for category, entries in EXTRA_LOOKUPS.items():
        for code, label in entries:
            try:
                store.create_lookup(category, LookupCreate(code=code, label=label))
            except store.ValidationError:
                pass  # already present


def ensure_custom_fields() -> None:
    for field in CUSTOM_FIELDS:
        try:
            store.create_custom_field(field)
        except store.ValidationError:
            pass  # already present


def main() -> None:
    ensure_lookups()
    ensure_custom_fields()

    created: list[dict] = []
    for row in PEOPLE:
        (first, last, staff_type, status, sub_status, tech_unit, citizenship,
         rank, hr_role, start, end, manager_index, custom_values) = row
        manager_id = created[manager_index]["id"] if manager_index is not None else None
        staff = store.create_staff(StaffCreate(
            staff_first_name=first,
            staff_last_name=last,
            staff_type=staff_type,
            staff_status=status,
            sub_status=sub_status,
            tech_unit=tech_unit,
            citizenship=citizenship,
            rank=rank,
            hr_role=hr_role,
            staff_start_date=start,
            staff_end_date=end,
            reporting_manager_id=manager_id,
            custom_values=custom_values,
        ))
        created.append(staff)

    print(f"Seeded {len(created)} staff into the global resource directory.")
    print(f"  codes: {created[0]['staff_code']} … {created[-1]['staff_code']}")
    print("  extra lookups + custom fields (cost_center, remote, clearance) ensured.")
    print("Open the app and click Resources in the top bar to see them.")


if __name__ == "__main__":
    main()
