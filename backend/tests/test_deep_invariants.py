"""Deep cross-module invariants: FK cascade, level rules, estimation, integrations, resources."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from backend.c4 import service as c4_service
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db
from backend.storage.db import connect


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="storypointer-deep-inv-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("STORYPOINTER_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    db._initialized.clear()
    yield


def _chain():
    pid = create_project(ProjectCreate(name="Deep"))["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="Init"))["id"]
    l2 = c4_store.create_element(pid, C4ElementCreate(level="L2", name="Cont", parent_id=l1))["id"]
    l3 = c4_store.create_element(pid, C4ElementCreate(level="L3", name="Comp", parent_id=l2))["id"]
    l4 = c4_store.create_element(pid, C4ElementCreate(level="L4", name="Task", parent_id=l3))["id"]
    return pid, l1, l2, l3, l4


def _count(table: str, column: str, value: str) -> int:
    with connect() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?", (value,)).fetchone()["n"]


# ---- FK cascade delete reaches children and every attached arch table --------

def test_deleting_l2_cascades_to_descendants_and_arch_tables():
    from backend.l2arch import store as l2s
    from backend.l2arch.models import ContainerCreate, L2Update
    from backend.l3arch import store as l3s
    from backend.l3arch.models import ComponentCreate, L3Update
    from backend.l4arch import store as l4s
    from backend.l4arch.models import CodeUnitCreate, L4Update

    pid, l1, l2, l3, l4 = _chain()
    l2s.update_l2(pid, l2, L2Update(summary="x"))
    l2s.create_container(pid, l2, ContainerCreate(name="svc"))
    l3s.update_l3(pid, l3, L3Update(summary="x"))
    l3s.create_component(pid, l3, ComponentCreate(name="ctrl"))
    l4s.update_l4(pid, l4, L4Update(summary="x"))
    l4s.create_code_unit(pid, l4, CodeUnitCreate(name="Class"))

    # sanity: rows exist
    assert _count("l2_arch", "l2_element_id", l2) == 1
    assert _count("l3_components", "l3_element_id", l3) == 1
    assert _count("l4_code_units", "l4_element_id", l4) == 1

    c4_store.delete_element(pid, l2)  # deletes L2 and, via FK cascade, everything under it

    with connect() as conn:
        remaining = {r["id"] for r in conn.execute("SELECT id FROM c4_elements WHERE project_id = ?", (pid,)).fetchall()}
    assert remaining == {l1}  # L2/L3/L4 all gone
    # every attached arch row cascaded away
    assert _count("l2_arch", "l2_element_id", l2) == 0
    assert _count("l2_containers", "l2_element_id", l2) == 0
    assert _count("l3_arch", "l3_element_id", l3) == 0
    assert _count("l3_components", "l3_element_id", l3) == 0
    assert _count("l4_arch", "l4_element_id", l4) == 0
    assert _count("l4_code_units", "l4_element_id", l4) == 0


def test_deleting_project_cascades_all_elements():
    pid, *_ = _chain()
    from backend.projects.store import delete_project
    delete_project(pid)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM c4_elements WHERE project_id = ?", (pid,)).fetchone()["n"] == 0


# ---- C4 level rules ----------------------------------------------------------

def test_level_rules_reject_wrong_parent():
    pid = create_project(ProjectCreate(name="P"))["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="I"))["id"]
    with pytest.raises(c4_store.C4ValidationError):
        c4_store.create_element(pid, C4ElementCreate(level="L3", name="skip", parent_id=l1))  # L3 under L1
    with pytest.raises(c4_store.C4ValidationError):
        c4_store.create_element(pid, C4ElementCreate(level="L1", name="child", parent_id=l1))  # L1 under L1


def test_parent_from_other_project_rejected():
    p1 = create_project(ProjectCreate(name="A"))["id"]
    p2 = create_project(ProjectCreate(name="B"))["id"]
    foreign = c4_store.create_element(p1, C4ElementCreate(level="L1", name="X"))["id"]
    with pytest.raises(c4_store.C4ValidationError):
        c4_store.create_element(p2, C4ElementCreate(level="L2", name="Y", parent_id=foreign))


# ---- estimation + roll-up ----------------------------------------------------

def test_rollup_counts_estimated_and_excludes_proposed():
    pid = create_project(ProjectCreate(name="E"))["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="I"))["id"]
    l2 = c4_store.create_element(pid, C4ElementCreate(level="L2", name="E", parent_id=l1))["id"]
    done = c4_store.create_element(pid, C4ElementCreate(level="L3", name="done", parent_id=l2))["id"]
    c4_store.create_element(pid, C4ElementCreate(level="L3", name="todo", parent_id=l2))
    c4_store.create_element(pid, C4ElementCreate(level="L3", name="ghost", parent_id=l2, status="proposed"))
    c4_store.upsert_artifact(done, "story", points=8)

    totals = c4_service.rollup(pid)["totals"]
    assert totals["estimated_stories"] == 1
    assert totals["unestimated_stories"] == 1  # the proposed one is excluded
    assert totals["rolled_up_points"] == 8


# ---- integration connector invariants ---------------------------------------

def test_every_configurable_connector_has_a_secret_field():
    from backend.integrations import connectors
    keys = list(connectors.CONNECTOR_ARCHETYPE) + ["some_unmapped_tool"]
    for key in keys:
        if not connectors.is_configurable(key):
            continue
        assert connectors.secret_keys(key), f"{key} should collect at least one secret"
        assert connectors.required_keys(key), f"{key} should have required fields"


def test_integration_test_flags_bad_url_and_disconnect_missing():
    from backend.integrations import store as istore
    istore.save_config("github", {"base_url": "ftp://nope", "api_token": "t"}, enabled=False)
    assert istore.test_config("github")["ok"] is False  # bad URL scheme
    istore.save_config("github", {"base_url": "https://api.github.com", "api_token": "t"}, enabled=True)
    assert istore.test_config("github")["ok"] is True
    with pytest.raises(istore.NotFoundError):
        istore.clear_config("gitlab")  # never configured


# ---- resource directory invariants ------------------------------------------

def test_manager_must_exist_and_not_be_self_and_delete_nulls_reports():
    from backend.resources import store as rstore
    from backend.resources.models import StaffCreate, StaffUpdate

    boss = rstore.create_staff(StaffCreate(staff_first_name="Boss", staff_last_name="One"))
    with pytest.raises(rstore.ValidationError):
        rstore.create_staff(StaffCreate(staff_first_name="Bad", staff_last_name="Ref", reporting_manager_id="nope"))
    report = rstore.create_staff(StaffCreate(staff_first_name="Rep", staff_last_name="Ort", reporting_manager_id=boss["id"]))
    with pytest.raises(rstore.ValidationError):
        rstore.update_staff(report["id"], StaffUpdate(reporting_manager_id=report["id"]))  # self-manager
    rstore.delete_staff(boss["id"])  # deleting the manager nulls the report's link
    assert rstore.get_staff(report["id"])["reporting_manager_id"] is None


def test_rejecting_a_stage_reverts_a_baselined_l2():
    from backend.l2arch import store as l2s
    pid, l1, l2, l3, l4 = _chain()
    l2s.submit_for_review(pid, l2)
    for stage in ("engineering", "security", "nfr", "data", "architecture", "sponsor"):
        l2s.decide_approval(pid, l2, stage, True, "Ann", "")
    assert l2s.get_l2(pid, l2)["status"] == "baselined"
    # a later rejection on the final stage un-baselines the L2 back to 'reviewed'
    state = l2s.decide_approval(pid, l2, "sponsor", False, "Ann", "changed mind")
    assert state["complete"] is False and state["rejected"] is True
    assert l2s.get_l2(pid, l2)["status"] == "reviewed"


def test_rejecting_a_stage_reverts_a_baselined_l3():
    from backend.l3arch import store as l3s
    pid, l1, l2, l3, l4 = _chain()
    l3s.submit_for_review(pid, l3)
    for stage in ("design", "interfaces", "security", "testing", "architecture", "tech_lead"):
        l3s.decide_approval(pid, l3, stage, True, "Ann", "")
    assert l3s.get_l3(pid, l3)["status"] == "baselined"
    l3s.decide_approval(pid, l3, "tech_lead", False, "Ann", "reopen")
    assert l3s.get_l3(pid, l3)["status"] == "reviewed"


def test_lookup_in_use_cannot_be_deleted():
    from backend.resources import store as rstore
    from backend.resources.models import LookupCreate, StaffCreate

    unit = rstore.create_lookup("tech_unit", LookupCreate(code="PAY", label="Payments"))
    # staff.tech_unit is validated against the lookup *code*; an unknown code is rejected...
    with pytest.raises(rstore.ValidationError):
        rstore.create_staff(StaffCreate(staff_first_name="Bad", staff_last_name="Unit", tech_unit="NOPE"))
    rstore.create_staff(StaffCreate(staff_first_name="Uses", staff_last_name="Unit", tech_unit="PAY"))
    with pytest.raises(rstore.ValidationError):
        rstore.delete_lookup(unit["id"])  # can't delete a lookup that's assigned
