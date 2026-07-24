"""Resource-view reporting: org graph + per-resource drill-down aggregation."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.reporting import service
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="karya-reporting-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("KARYA_DB", str(work_dir / "test.db"))
    db._initialized.clear()
    yield


def _staff(conn, staff_id, first, last, manager_id=None, tech_unit=""):
    now = db.utc_now()
    conn.execute(
        """INSERT INTO resource_staff
           (id, staff_code, staff_first_name, staff_last_name, staff_name, tech_unit,
            reporting_manager_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (staff_id, f"STF-{staff_id[:4]}", first, last, f"{first} {last}", tech_unit, manager_id, now, now),
    )


def _build_org():
    """Manager Dana with report Evan; Evan sits on a squad that owns a 5-point story."""
    ids = {k: db.new_id() for k in ("proj", "l1", "l3", "tribe", "squad", "dana", "evan")}
    now = db.utc_now()
    with db.connect() as conn:
        conn.execute("INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)", (ids["proj"], "Payments", now))
        conn.execute(
            "INSERT INTO c4_elements (id, project_id, level, name, created_at) VALUES (?, ?, 'L1', 'Payments Initiative', ?)",
            (ids["l1"], ids["proj"], now),
        )
        conn.execute(
            "INSERT INTO c4_elements (id, project_id, level, name, parent_id, code_path, created_at) "
            "VALUES (?, ?, 'L3', 'Refund story', ?, 'src/refund.py', ?)",
            (ids["l3"], ids["proj"], ids["l1"], now),
        )
        conn.execute(
            "INSERT INTO artifact_links (id, element_id, artifact_type, points) VALUES (?, ?, 'story', 5)",
            (db.new_id(), ids["l3"]),
        )
        conn.execute(
            "INSERT INTO l1_agile_units (id, project_id, l1_element_id, unit_type, name, created_at) "
            "VALUES (?, ?, ?, 'tribe', 'Core Tribe', ?)",
            (ids["tribe"], ids["proj"], ids["l1"], now),
        )
        conn.execute(
            "INSERT INTO l1_agile_units (id, project_id, l1_element_id, unit_type, parent_unit_id, name, created_at) "
            "VALUES (?, ?, ?, 'squad', ?, 'Refund Squad', ?)",
            (ids["squad"], ids["proj"], ids["l1"], ids["tribe"], now),
        )
        _staff(conn, ids["dana"], "Dana", "Lead", tech_unit="ENG")
        _staff(conn, ids["evan"], "Evan", "Dev", manager_id=ids["dana"], tech_unit="ENG")
        conn.execute(
            "INSERT INTO l1_team_members (id, unit_id, resource_staff_id, name, role, allocation_percent, monthly_cost, created_at) "
            "VALUES (?, ?, ?, 'Evan Dev', 'Engineer', 80, 9000, ?)",
            (db.new_id(), ids["squad"], ids["evan"], now),
        )
        conn.execute(
            "INSERT INTO l1_work_items (id, project_id, l1_element_id, squad_id, linked_element_id, title, start_date, end_date, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'Build refund', '2026-01-01', '2026-02-01', 'in_progress', ?)",
            (db.new_id(), ids["proj"], ids["l1"], ids["squad"], ids["l3"], now),
        )
    return ids


def test_resource_graph_builds_reporting_forest():
    ids = _build_org()
    graph = service.resource_graph()

    assert graph["totals"] == {"resources": 2, "managers": 1, "roots": 1, "squads": 1}
    # A single root (Dana) whose subtree weight counts both people.
    assert len(graph["tree"]) == 1
    root = graph["tree"][0]
    assert root["id"] == ids["dana"]
    assert root["weight"] == 2
    assert root["reports_count"] == 1
    # One manager -> report edge.
    assert graph["edges"] == [{"source": ids["dana"], "target": ids["evan"]}]

    evan = next(n for n in graph["nodes"] if n["id"] == ids["evan"])
    assert evan["squad_count"] == 1
    assert evan["tribe_count"] == 1
    assert evan["project_count"] == 1
    assert evan["story_count"] == 1
    assert evan["points"] == 5


def test_resource_profile_aggregates_teams_stories_and_code():
    ids = _build_org()
    profile = service.resource_profile(ids["evan"])

    assert profile["profile"]["name"] == "Evan Dev"
    assert profile["manager_chain"] == [{"id": ids["dana"], "name": "Dana Lead", "code": profile["manager_chain"][0]["code"]}]
    assert profile["summary"]["story_count"] == 1
    assert profile["summary"]["points"] == 5
    assert profile["summary"]["allocation"] == 80.0

    assert len(profile["teams"]) == 1
    team = profile["teams"][0]
    assert team["unit_name"] == "Refund Squad"
    assert team["unit_type"] == "squad"
    assert team["tribe_name"] == "Core Tribe"
    assert team["project_name"] == "Payments"
    assert team["role"] == "Engineer"

    assert len(profile["stories"]) == 1
    assert profile["stories"][0]["code_path"] == "src/refund.py"
    assert profile["code_paths"] == ["src/refund.py"]


def test_resource_profile_reports_direct_reports():
    ids = _build_org()
    profile = service.resource_profile(ids["dana"])
    assert [r["id"] for r in profile["reports"]] == [ids["evan"]]
    assert profile["summary"]["reports_count"] == 1
    assert profile["manager_chain"] == []


def test_resource_profile_missing_staff_raises():
    _build_org()
    with pytest.raises(LookupError):
        service.resource_profile("does-not-exist")
