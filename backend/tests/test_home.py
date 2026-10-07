"""Personal home dashboard: summary, tasks inbox, and pending actions."""

from __future__ import annotations

import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.home import service
from backend.storage import db


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="karya-home-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("KARYA_DB", str(work_dir / "test.db"))
    db._initialized.clear()
    yield


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def _scenario(*, staff_allocation=80):
    """Manager Dana; report Evan on a squad with at-risk / overdue / due-soon work,
    plus an off-track OKR, a blocked risk and an open comment he authored."""
    ids = {k: db.new_id() for k in ("proj", "l1", "s1", "s2", "tribe", "squad", "dana", "evan")}
    now = db.utc_now()
    with db.connect() as conn:
        conn.execute("INSERT INTO projects (id, name, created_at) VALUES (?, 'Payments', ?)", (ids["proj"], now))
        conn.execute("INSERT INTO c4_elements (id, project_id, level, name, created_at) VALUES (?, ?, 'L1', 'Payments', ?)",
                     (ids["l1"], ids["proj"], now))
        for key, name, path in [("s1", "Refund", "src/refund.py"), ("s2", "Payout", "src/payout.py")]:
            conn.execute("INSERT INTO c4_elements (id, project_id, level, name, parent_id, code_path, created_at) "
                         "VALUES (?, ?, 'L3', ?, ?, ?, ?)", (ids[key], ids["proj"], name, ids["l1"], path, now))
            conn.execute("INSERT INTO artifact_links (id, element_id, artifact_type, points) VALUES (?, ?, 'story', 5)",
                         (db.new_id(), ids[key]))
        conn.execute("INSERT INTO l1_agile_units (id, project_id, l1_element_id, unit_type, name, created_at) "
                     "VALUES (?, ?, ?, 'tribe', 'Core', ?)", (ids["tribe"], ids["proj"], ids["l1"], now))
        conn.execute("INSERT INTO l1_agile_units (id, project_id, l1_element_id, unit_type, parent_unit_id, name, created_at) "
                     "VALUES (?, ?, ?, 'squad', ?, 'Refund Squad', ?)", (ids["squad"], ids["proj"], ids["l1"], ids["tribe"], now))
        for sid, first, last, mgr in [(ids["dana"], "Dana", "Lead", None), (ids["evan"], "Evan", "Dev", ids["dana"])]:
            conn.execute("INSERT INTO resource_staff (id, staff_code, staff_first_name, staff_last_name, staff_name, "
                         "reporting_manager_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (sid, f"STF-{sid[:4]}", first, last, f"{first} {last}", mgr, now, now))
        conn.execute("INSERT INTO l1_team_members (id, unit_id, resource_staff_id, name, role, allocation_percent, monthly_cost, created_at) "
                     "VALUES (?, ?, ?, 'Evan Dev', 'Engineer', ?, 9000, ?)", (db.new_id(), ids["squad"], ids["evan"], staff_allocation, now))
        work = [("Build refund", _iso(40), "at_risk", "s1"), ("Payout API", _iso(-3), "in_progress", "s2"),
                ("Reconcile", _iso(2), "planned", "s1"), ("Archive", _iso(90), "done", "s2")]
        for title, end, status, story in work:
            conn.execute("INSERT INTO l1_work_items (id, project_id, l1_element_id, squad_id, linked_element_id, title, "
                         "start_date, end_date, status, created_at) VALUES (?, ?, ?, ?, ?, ?, '2026-01-01', ?, ?, ?)",
                         (db.new_id(), ids["proj"], ids["l1"], ids["squad"], ids[story], title, end, status, now))
        conn.execute("INSERT INTO l1_okrs (id, l1_element_id, objective, status, owner, created_at) "
                     "VALUES (?, ?, 'Cut latency', 'off_track', 'Evan Dev', ?)", (db.new_id(), ids["l1"], now))
        conn.execute("INSERT INTO l1_risks (id, l1_element_id, title, risk_level, status, owner, created_at) "
                     "VALUES (?, ?, 'Vendor SLA', 'high', 'blocked', 'Evan Dev', ?)", (db.new_id(), ids["l1"], now))
        conn.execute("INSERT INTO l1_comments (id, l1_element_id, body, author, status, created_at) "
                     "VALUES (?, ?, 'Confirm rollback', 'Evan Dev', 'open', ?)", (db.new_id(), ids["l1"], now))
    return ids


def test_summary_counts_are_user_scoped():
    ids = _scenario()
    dash = service.personal_dashboard(ids["evan"])
    s = dash["summary"]
    assert dash["user"]["name"] == "Evan Dev"
    assert s["tasks_total"] == 4
    assert s["tasks_open"] == 3          # the "done" item is excluded
    assert s["at_risk"] == 1
    assert s["overdue"] == 1
    assert s["squads"] == 1 and s["projects"] == 1
    assert s["allocation"] == 80.0
    assert s["reports"] == 0             # Evan manages nobody


def test_tasks_inbox_orders_by_urgency_and_flags_overdue():
    ids = _scenario()
    tasks = service.personal_dashboard(ids["evan"])["tasks"]
    assert [t["title"] for t in tasks][:3] == ["Build refund", "Payout API", "Reconcile"]
    overdue = next(t for t in tasks if t["title"] == "Payout API")
    assert overdue["overdue"] is True and overdue["due_in_days"] < 0
    assert next(t for t in tasks if t["title"] == "Archive")["overdue"] is False


def test_actions_include_work_okr_risk_and_comment_sorted_by_severity():
    ids = _scenario()
    actions = service.personal_dashboard(ids["evan"])["actions"]
    types = {a["type"] for a in actions}
    assert {"at_risk_work", "overdue_work", "due_soon_work", "okr_off_track", "risk_open", "open_comment"} <= types
    severities = [a["severity"] for a in actions]
    order = {"high": 0, "medium": 1, "low": 2}
    assert severities == sorted(severities, key=lambda s: order[s])
    assert severities[0] == "high" and severities[-1] == "low"


def test_manager_sees_bench_report_action():
    ids = _scenario(staff_allocation=0)  # Evan now unallocated -> on the bench
    dash = service.personal_dashboard(ids["dana"])
    assert dash["summary"]["reports"] == 1
    assert dash["summary"]["bench_reports"] == 1
    bench = [a for a in dash["actions"] if a["type"] == "unstaffed_report"]
    assert len(bench) == 1 and bench[0]["title"] == "Evan Dev"


def test_fully_allocated_report_is_not_on_the_bench():
    ids = _scenario(staff_allocation=100)
    dash = service.personal_dashboard(ids["dana"])
    assert dash["summary"]["bench_reports"] == 0
    assert not [a for a in dash["actions"] if a["type"] == "unstaffed_report"]


def test_missing_staff_raises():
    _scenario()
    with pytest.raises(LookupError):
        service.personal_dashboard("nope")


def test_organization_dashboard_is_portfolio_wide():
    _scenario(staff_allocation=0)  # leaves Evan on the bench too
    dash = service.organization_dashboard()
    assert dash["scope"] == "organization"
    assert dash["user"]["staff_id"] is None
    s = dash["summary"]
    assert s["projects"] == 1
    assert s["squads"] == 1
    assert s["resources"] == 2          # Dana + Evan, both active
    assert s["on_bench"] == 2           # neither is allocated in this scenario
    # Portfolio work inbox surfaces every open item regardless of who owns it.
    assert s["tasks_open"] == 3
    assert s["at_risk"] == 1 and s["overdue"] == 1
    # Off-track OKR and blocked risk show up even though no personal identity owns them.
    types = {a["type"] for a in dash["actions"]}
    assert "okr_off_track" in types and "risk_open" in types
    # The bench is a single aggregate action, not one row per person.
    bench = [a for a in dash["actions"] if a["type"] == "bench_pool"]
    assert len(bench) == 1 and "2 resources" in bench[0]["title"]


def test_organization_actions_name_the_owner():
    _scenario()
    dash = service.organization_dashboard()
    okr = next(a for a in dash["actions"] if a["type"] == "okr_off_track")
    assert "owner Evan Dev" in okr["detail"]


def test_tasks_and_actions_carry_their_l1_initiative_for_deep_links():
    ids = _scenario()
    dash = service.personal_dashboard(ids["evan"])
    assert all(t["l1_id"] == ids["l1"] for t in dash["tasks"])
    payout = next(t for t in dash["tasks"] if t["title"] == "Payout API")
    assert payout["element_id"] == ids["s2"]
    linked = [a for a in dash["actions"] if a["category"] in {"work", "okr", "risk", "comment"}]
    assert linked and all(a["l1_id"] == ids["l1"] for a in linked)
