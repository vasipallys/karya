"""Conversational assistant: query/report execute, writes propose→apply, RBAC on apply."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.ai import agents
from backend.api.main import app
from backend.c4 import store as c4_store
from backend.c4.models import C4ElementCreate
from backend.projects.models import ProjectCreate
from backend.projects.store import create_project
from backend.storage import db
from backend.config import get_settings
from backend.llm.factory import get_llm
from backend.l2arch import store as l2_store
from backend.l2arch.models import L2Update
from backend.planning import store as planning_store
from backend.planning.models import AgileUnitCreate


@pytest.fixture
def work_dir():
    path = Path(tempfile.mkdtemp(prefix="karya-chat-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_db(work_dir, monkeypatch):
    monkeypatch.setenv("KARYA_DB", str(work_dir / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    get_llm.cache_clear()
    db._initialized.clear()
    yield
    get_settings.cache_clear()
    get_llm.cache_clear()


def _scope():
    project = create_project(ProjectCreate(name="Digital banking"))
    pid = project["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="Digital banking"))
    l2 = c4_store.create_element(pid, C4ElementCreate(level="L2", name="onboarding-web", parent_id=l1["id"]))
    return pid, l1["id"], l2["id"]


ADMIN = {"X-User-Role": "admin"}
VIEWER = {"X-User-Role": "viewer"}


def _chat(client, pid, message, headers=ADMIN):
    return client.post(f"/projects/{pid}/chat", json={"message": message}, headers=headers)


def test_query_and_report_execute():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        overview = _chat(client, pid, "what's the project status?").json()
        assert overview["action"] == "overview" and "%" in overview["reply"]
        listing = _chat(client, pid, "list L2 containers").json()
        assert listing["action"] == "list"
        assert any(i["name"] == "onboarding-web" for i in listing["data"]["items"])
        assert all(i["id"] for i in listing["data"]["items"])  # ids power UI deep links
        report = _chat(client, pid, "what should I do next?").json()
        assert report["action"] == "report" and report["mutation"] is None


def test_complete_project_status_reads_overview_not_readiness():
    """“give me complete project status” must answer from the DB as an overview —
    the word “complete” must not divert it into readiness (which then asks for an
    element name) or into a free-form model answer."""
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "give me complete project status").json()
        assert res["action"] == "overview"
        assert res["mutation"] is None and "%" in res["reply"]


def test_named_status_questions_are_grounded_to_the_current_turn():
    """An unknown name must never fall back to the open project's cached-looking overview."""
    pid, _, _ = _scope()
    with TestClient(app) as client:
        exact = _chat(client, pid, "what is the status of Digital banking").json()
        assert exact["action"] == "overview"
        assert exact["reply"].startswith("Digital banking is")

        first = client.post(
            f"/projects/{pid}/chat",
            json={"message": "what is the status of Digital banking"},
            headers=ADMIN,
        ).json()
        unknown = client.post(
            f"/projects/{pid}/chat",
            json={
                "message": "what is the status of no banking",
                "conversation_id": first["conversation_id"],
            },
            headers=ADMIN,
        ).json()
        assert unknown["action"] == "answer"
        assert unknown["reply"].startswith("I don't know the status of **no banking**")
        assert "Digital banking is" not in unknown["reply"]
        assert "Did you mean" not in unknown["reply"]

        typo = _chat(client, pid, "what is the status of Digitol banking").json()
        assert typo["action"] == "answer"
        assert "Did you mean **Digital banking**?" in typo["reply"]


def test_unknown_status_stream_uses_lookup_evidence_not_project_rollup():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        response = client.post(
            f"/projects/{pid}/chat/stream",
            json={"message": "what is the status of no banking"},
            headers=ADMIN,
        )
        assert response.status_code == 200
        assert "I don't know the status of **no banking**" in response.text
        assert '"tool": "entity_lookup"' in response.text
        assert '"tool": "workflow_guide"' not in response.text
        assert '"tool": "rollup"' not in response.text


def test_pending_items_lists_proposed_from_db():
    """“give me pending items in L1” lists proposed L1 elements from the DB —
    it must not fall through to a free-form (hallucinated) answer."""
    pid, l1_id, _ = _scope()
    # A proposed L1 sibling and an active one; only the proposed should show.
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Payments platform", status="proposed"))
    with TestClient(app) as client:
        res = _chat(client, pid, "give me pending items in L1").json()
        assert res["action"] == "list"
        assert res["data"]["level"] == "L1" and res["data"]["status"] == "proposed"
        names = {i["name"] for i in res["data"]["items"]}
        assert "Payments platform" in names and "Digital banking" not in names
        assert "pending" not in res["reply"].lower() or "proposed" in res["reply"].lower()


def test_summary_of_all_l2_lists_from_db():
    """“give me summary of all L2” must enumerate real L2 elements, not produce a
    free-form (hallucinated) answer."""
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "give me summary of all L2").json()
        assert res["action"] == "list"
        assert res["data"]["level"] == "L2"
        assert any(i["name"] == "onboarding-web" for i in res["data"]["items"])


def test_screen_context_defaults_bare_readiness_to_open_element():
    """On the L2 screen with an element open, a bare “readiness?” checks that
    element — the agent uses the current screen instead of asking which one."""
    pid, l1_id, l2_id = _scope()
    with TestClient(app) as client:
        res = client.post(f"/projects/{pid}/chat", json={
            "message": "how ready is it?",
            "screen_context": {"tab": "l2arch", "tab_label": "L2 arch", "level": "L2", "element_id": l2_id},
        }, headers=ADMIN).json()
        assert res["action"] == "readiness"
        assert res["data"]["name"] == "onboarding-web"


def test_screen_context_defaults_bare_list_to_open_level():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = client.post(f"/projects/{pid}/chat", json={
            "message": "show me everything here",
            "screen_context": {"tab": "l2arch", "tab_label": "L2 arch", "level": "L2"},
        }, headers=ADMIN).json()
        assert res["action"] == "list" and res["data"]["level"] == "L2"


def test_readiness_of_named_element():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "readiness of onboarding-web").json()
        assert res["action"] == "readiness"
        assert res["data"]["name"] == "onboarding-web" and "score" in res["data"]


def test_status_of_each_level_item_returns_per_item_readiness(monkeypatch):
    """A level-scoped status question is not a project overview: every element
    at that level must carry its own deterministic readiness percentage."""
    async def unexpected_llm(*args, **kwargs):
        pytest.fail("grounded level status must not call the LLM")

    monkeypatch.setattr(agents, "_invoke", unexpected_llm)
    pid, _, _ = _scope()
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Core CRM"))

    with TestClient(app) as client:
        res = _chat(client, pid, "what is status of each L1 item").json()
        assert res["action"] == "readiness"
        assert res["data"]["level"] == "L1"
        assert {item["name"] for item in res["data"]["items"]} == {"Digital banking", "Core CRM"}
        assert all(isinstance(item["score"], int) and item["status_label"] for item in res["data"]["items"])
        assert "readiness by item" in res["reply"]

        streamed = client.post(
            f"/projects/{pid}/chat/stream",
            json={"message": "what is status of each L1 item"},
            headers=ADMIN,
        )
        assert '"action": "readiness"' in streamed.text
        assert '"tool": "l1_readiness"' in streamed.text
        assert '"tool": "rollup"' not in streamed.text


@pytest.mark.parametrize("question", [
    "what is L2 Client-service about",
    "what is L2 Client-service about, give me description",
    "tell me about the L2 Client service",
])
def test_element_description_uses_persisted_model_and_architecture_context(monkeypatch, question):
    async def unexpected_llm(*args, **kwargs):
        pytest.fail("a resolved element description must not call the LLM")

    monkeypatch.setattr(agents, "_invoke", unexpected_llm)
    pid, l1_id, _ = _scope()
    l2 = c4_store.create_element(pid, C4ElementCreate(
        level="L2",
        name="client-service",
        kind="container",
        description="Manages client profiles and servicing workflows.",
        parent_id=l1_id,
        tech="Spring Boot",
        code_path="services/client-service",
    ))
    c4_store.create_element(pid, C4ElementCreate(
        level="L3", name="profile-api", parent_id=l2["id"], description="Exposes client profile operations."
    ))
    l2_store.update_l2(pid, l2["id"], L2Update(
        summary="The client domain boundary for profile, preferences, and servicing capabilities."
    ))

    with TestClient(app) as client:
        response = _chat(client, pid, question)
        assert response.status_code == 200
        result = response.json()
        assert result["action"] == "describe"
        assert "Manages client profiles and servicing workflows" in result["reply"]
        assert "client domain boundary" in result["reply"]
        assert "Digital banking" in result["reply"] and "profile-api" in result["reply"]
        assert "Spring Boot" in result["reply"] and "services/client-service" in result["reply"]
        assert result["data"]["element"]["id"] == l2["id"]
        assert result["data"]["parent"]["name"] == "Digital banking"

        streamed = client.post(f"/projects/{pid}/chat/stream", json={"message": question}, headers=ADMIN)
        assert '"action": "describe"' in streamed.text
        assert '"tool": "element_context"' in streamed.text
        assert '"tool": "rollup"' not in streamed.text


def test_unknown_element_is_a_clean_400():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "readiness of does-not-exist")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "chat_invalid"


def test_create_proposes_then_applies_and_rbac():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        proposal = _chat(client, pid, "create an L2 container called payments under Digital banking").json()
        assert proposal["action"] == "create_element"
        mutation = proposal["mutation"]
        assert mutation["level"] == "L2" and mutation["name"] == "payments"
        # nothing created yet
        assert not any(e["name"] == "payments" for e in c4_store.list_graph(pid)["elements"])
        # viewer may propose (query) but not apply
        assert _chat(client, pid, "list L2", VIEWER).status_code == 200
        assert client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=VIEWER).status_code == 403
        # admin applies -> element exists
        applied = client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=ADMIN)
        assert applied.status_code == 200
        assert any(e["name"] == "payments" and e["level"] == "L2" for e in c4_store.list_graph(pid)["elements"])


def test_tribe_request_routes_to_operating_plan_not_c4(monkeypatch):
    """Regression for the production failure where "add a tribe" became an L2."""
    async def unexpected_llm(*args, **kwargs):
        pytest.fail("explicit tribe/squad intent must be provider-independent")

    monkeypatch.setattr(agents, "_invoke", unexpected_llm)
    pid, l1_id, _ = _scope()
    with TestClient(app) as client:
        proposal = client.post(f"/projects/{pid}/chat", json={
            "message": "Create a tribe for the Digital banking system",
            "screen_context": {
                "tab": "planning", "tab_label": "L1 plan", "level": "L1", "element_id": l1_id,
            },
        }, headers=ADMIN)
        assert proposal.status_code == 200
        result = proposal.json()
        assert result["action"] == "create_agile_unit"
        assert result["mutation"]["unit_type"] == "tribe"
        assert result["mutation"]["scope"] == "Digital banking"
        assert result["mutation"]["name"] == "Digital banking Tribe"
        assert not any(e["name"] == "Tribe" for e in c4_store.list_graph(pid)["elements"])

        applied = client.post(
            f"/projects/{pid}/chat/apply",
            json={"mutation": result["mutation"]},
            headers=ADMIN,
        )
        assert applied.status_code == 200
        plan = planning_store.get_plan(pid, l1_id)
        assert [(unit["unit_type"], unit["name"]) for unit in plan["units"]] == [
            ("tribe", "Digital banking Tribe"),
        ]
        assert all(element["level"] != "L2" or element["name"] != "Tribe"
                   for element in c4_store.list_graph(pid)["elements"])
        replay = client.post(
            f"/projects/{pid}/chat/apply",
            json={"mutation": result["mutation"]},
            headers=ADMIN,
        )
        assert replay.status_code == 400
        assert "already exists" in replay.json()["error"]["message"]


def test_squad_is_attached_to_named_tribe_and_can_be_listed():
    pid, l1_id, _ = _scope()
    tribe = planning_store.create_unit(
        pid, l1_id,
        AgileUnitCreate(unit_type="tribe", name="Growth Tribe"),
    )
    with TestClient(app) as client:
        proposal = _chat(client, pid, "Create a squad called Checkout under Growth Tribe").json()
        assert proposal["action"] == "create_agile_unit"
        assert proposal["mutation"]["unit_type"] == "squad"
        assert proposal["mutation"]["parent"] == "Growth Tribe"
        applied = client.post(
            f"/projects/{pid}/chat/apply",
            json={"mutation": proposal["mutation"]},
            headers=ADMIN,
        )
        assert applied.status_code == 200
        squad = next(unit for unit in planning_store.get_plan(pid, l1_id)["units"]
                     if unit["name"] == "Checkout")
        assert squad["parent_unit_id"] == tribe["id"]

        listing = _chat(client, pid, "list squads").json()
        assert listing["action"] == "list_agile_units"
        assert listing["data"]["items"][0]["name"] == "Checkout"

        scoped = _chat(client, pid, "Create a squad called Mobile in Digital banking").json()
        assert scoped["mutation"]["scope"] == "Digital banking"
        assert scoped["mutation"]["parent"] == "Growth Tribe"


def test_team_member_assignment_is_proposed_and_applied():
    pid, l1_id, _ = _scope()
    squad = planning_store.create_unit(
        pid, l1_id,
        AgileUnitCreate(unit_type="squad", name="Checkout Squad"),
    )
    with TestClient(app) as client:
        proposal = _chat(client, pid, "Add Priya to Checkout Squad as QA at 50%").json()
        assert proposal["action"] == "assign_team_member"
        assert proposal["mutation"]["unit"] == "Checkout Squad"
        assert proposal["mutation"]["allocation_percent"] == 50
        client.post(
            f"/projects/{pid}/chat/apply",
            json={"mutation": proposal["mutation"]},
            headers=ADMIN,
        )
        member = planning_store.get_plan(pid, l1_id)["units"][0]["members"][0]
        assert member["unit_id"] == squad["id"]
        assert member["name"] == "Priya"
        assert member["role"] == "QA"
        assert member["allocation_percent"] == 50

        update = _chat(client, pid, "Set Priya's allocation to 70% in Checkout Squad").json()
        assert update["action"] == "update_team_member"
        client.post(
            f"/projects/{pid}/chat/apply",
            json={"mutation": update["mutation"]},
            headers=ADMIN,
        )
        member = planning_store.get_plan(pid, l1_id)["units"][0]["members"][0]
        assert member["allocation_percent"] == 70

        removal = _chat(client, pid, "Remove Priya from Checkout Squad").json()
        assert removal["action"] == "remove_team_member"
        client.post(
            f"/projects/{pid}/chat/apply",
            json={"mutation": removal["mutation"]},
            headers=ADMIN,
        )
        assert planning_store.get_plan(pid, l1_id)["units"][0]["members"] == []


def test_tribe_rename_delete_and_combined_list_are_not_c4_mutations():
    pid, l1_id, _ = _scope()
    planning_store.create_unit(pid, l1_id, AgileUnitCreate(unit_type="tribe", name="Growth Tribe"))
    planning_store.create_unit(pid, l1_id, AgileUnitCreate(unit_type="squad", name="Independent Squad"))
    with TestClient(app) as client:
        listing = _chat(client, pid, "show tribes and squads").json()
        assert listing["action"] == "list_agile_units"
        assert {item["unit_type"] for item in listing["data"]["items"]} == {"tribe", "squad"}

        rename = _chat(client, pid, "rename Growth Tribe to Digital Tribe").json()
        assert rename["action"] == "update_agile_unit"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": rename["mutation"]}, headers=ADMIN)
        assert any(unit["name"] == "Digital Tribe" for unit in planning_store.get_plan(pid, l1_id)["units"])

        deletion = _chat(client, pid, "delete Digital Tribe").json()
        assert deletion["action"] == "delete_agile_unit"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": deletion["mutation"]}, headers=ADMIN)
        assert all(unit["name"] != "Digital Tribe" for unit in planning_store.get_plan(pid, l1_id)["units"])


def test_generic_team_create_asks_for_domain_instead_of_guessing_level():
    pid, l1_id, _ = _scope()
    with TestClient(app) as client:
        response = client.post(f"/projects/{pid}/chat", json={
            "message": "Add a team",
            "screen_context": {
                "tab": "planning", "tab_label": "L1 plan", "level": "L1", "element_id": l1_id,
            },
        }, headers=ADMIN)
        assert response.status_code == 200
        result = response.json()
        assert result["action"] == "answer"
        assert "tribe" in result["reply"].lower() and "squad" in result["reply"].lower()
        assert result["mutation"] is None


def test_malformed_chat_mutation_is_a_clean_400():
    pid, l1_id, _ = _scope()
    planning_store.create_unit(pid, l1_id, AgileUnitCreate(unit_type="squad", name="Checkout Squad"))
    with TestClient(app) as client:
        response = client.post(f"/projects/{pid}/chat/apply", json={"mutation": {
            "action": "assign_team_member",
            "scope": "Digital banking",
            "unit": "Checkout Squad",
            "name": "Priya",
            "allocation_percent": None,
        }}, headers=ADMIN)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "chat_invalid"


def test_create_without_parent_attaches_to_the_system_l1():
    """“create an L2 container called payments” (no ‘under …’) must not create
    an orphan on the system landscape — it attaches to the only suitable L1."""
    pid, l1_id, _ = _scope()
    # Persons/externals must not be picked as container parents.
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Retail customer", kind="person"))
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Core banking", kind="external system"))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "create an L2 container called payments").json()
        assert proposal["mutation"]["parent"] == "Digital banking"
        assert "under “Digital banking”" in proposal["mutation"]["summary"]
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=ADMIN)
        created = next(e for e in c4_store.list_graph(pid)["elements"] if e["name"] == "payments")
        assert created["parent_id"] == l1_id


def test_create_with_ambiguous_parent_asks_instead_of_guessing():
    pid, _, _ = _scope()
    c4_store.create_element(pid, C4ElementCreate(level="L1", name="Payments platform", kind="system"))
    with TestClient(app) as client:
        res = _chat(client, pid, "create an L2 container called payments")
        assert res.status_code == 400
        message = res.json()["error"]["message"]
        assert "Which L1" in message and "Digital banking" in message and "Payments platform" in message


def test_create_rejects_wrong_level_parent():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = _chat(client, pid, "create an L4 task called cleanup under Digital banking")
        assert res.status_code == 400
        assert "needs an L3 parent" in res.json()["error"]["message"]


def test_compound_create_and_route_in_one_message():
    """“create a L2 payments container and route it to the api-gateway” must
    extract the inline name, attach to the L1, and create the relation."""
    pid, l1_id, _ = _scope()
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1_id))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "create a L2 payments container and route it to the api gateway").json()
        mutation = proposal["mutation"]
        assert mutation["action"] == "create_element"
        assert mutation["name"] == "payments"
        assert mutation["target"] == "api-gateway"
        assert "api-gateway" in mutation["summary"]
        applied = client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=ADMIN)
        assert applied.status_code == 200
        assert "connected it to “api-gateway”" in applied.json()["reply"]
        graph = c4_store.list_graph(pid)
        payments = next(e for e in graph["elements"] if e["name"] == "payments")
        assert payments["parent_id"] == l1_id
        assert any(r["source_id"] == payments["id"] and r["target_id"] == gw["id"] for r in graph["relations"])


def test_standalone_relation_between_existing_elements():
    pid, l1_id, l2_id = _scope()
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1_id))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "route onboarding-web to api-gateway").json()
        assert proposal["mutation"]["action"] == "create_relation"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=ADMIN)
        relations = c4_store.list_graph(pid)["relations"]
        assert any(r["source_id"] == l2_id and r["target_id"] == gw["id"] for r in relations)


def test_route_to_target_through_intermediary_sets_direction():
    """“add route to payments through api-gateway” connects api-gateway → payments:
    the element named after through/via is the source, not the target."""
    pid, l1_id, _ = _scope()
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1_id))
    pay = c4_store.create_element(pid, C4ElementCreate(level="L2", name="payments", parent_id=l1_id))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "add route to payments through api-gateway").json()
        mutation = proposal["mutation"]
        assert mutation["action"] == "create_relation"
        assert mutation["name"] == "api-gateway" and mutation["target"] == "payments"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=ADMIN)
        relations = c4_store.list_graph(pid)["relations"]
        assert any(r["source_id"] == gw["id"] and r["target_id"] == pay["id"] for r in relations)


def test_route_between_two_elements():
    pid, l1_id, l2_id = _scope()
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1_id))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "add a connection between onboarding-web and api-gateway").json()
        mutation = proposal["mutation"]
        assert mutation["action"] == "create_relation"
        assert mutation["name"] == "onboarding-web" and mutation["target"] == "api-gateway"


def test_route_to_target_from_source_with_level_qualifier():
    """“add new route to L2 payments from api-gateway” connects api-gateway →
    payments: `from` names the source, and the `L2` qualifier on the target is
    stripped during name resolution (this must not be read as create_element)."""
    pid, l1_id, _ = _scope()
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1_id))
    pay = c4_store.create_element(pid, C4ElementCreate(level="L2", name="payments", parent_id=l1_id))
    with TestClient(app) as client:
        proposal = _chat(client, pid, "add new route to L2 payments from api-gateway").json()
        mutation = proposal["mutation"]
        assert mutation["action"] == "create_relation"
        assert mutation["name"] == "api-gateway" and mutation["target"] == "payments"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=ADMIN)
        relations = c4_store.list_graph(pid)["relations"]
        assert any(r["source_id"] == gw["id"] and r["target_id"] == pay["id"] for r in relations)


def test_quoted_name_create_with_connect_route_in_one_message():
    """“Add a "Payments" as a new L3 Container and connect the route through
    api-gateway…” must extract the quoted inline name (not ask for it) and wire
    the new element to api-gateway on apply. Single L2 so the L3 parent is
    unambiguous, isolating the name+relation extraction."""
    project = create_project(ProjectCreate(name="Digital banking"))
    pid = project["id"]
    l1 = c4_store.create_element(pid, C4ElementCreate(level="L1", name="Digital banking"))
    gw = c4_store.create_element(pid, C4ElementCreate(level="L2", name="api-gateway", parent_id=l1["id"]))
    with TestClient(app) as client:
        proposal = _chat(client, pid, 'Add a "Payments" as a new L3 Container and connect the route through api-gateway, name the route as Payments').json()
        mutation = proposal["mutation"]
        assert mutation["action"] == "create_element"
        assert mutation["level"] == "L3" and mutation["name"] == "Payments"
        assert mutation["target"] == "api-gateway"
        applied = client.post(f"/projects/{pid}/chat/apply", json={"mutation": mutation}, headers=ADMIN)
        assert applied.status_code == 200
        graph = c4_store.list_graph(pid)
        payments = next(e for e in graph["elements"] if e["name"] == "Payments")
        assert payments["level"] == "L3" and payments["parent_id"] == gw["id"]
        assert any(r["source_id"] == payments["id"] and r["target_id"] == gw["id"] for r in graph["relations"])


def test_add_new_element_as_level_extracts_name():
    """“add a new L2 container called Payments” and the name-before-level form both
    resolve the name rather than asking for it."""
    pid, _, _ = _scope()
    with TestClient(app) as client:
        a = _chat(client, pid, 'add a new L2 container called Payments').json()
        assert a["mutation"]["name"] == "Payments" and a["mutation"]["level"] == "L2"
        b = _chat(client, pid, 'add "Reporting" as a new L2 container').json()
        assert b["mutation"]["name"] == "Reporting" and b["mutation"]["level"] == "L2"


def test_followup_answer_uses_conversation_history():
    """After the assistant asks for a name, a bare answer like “payments”
    must complete the pending create instead of falling back to help."""
    pid, l1_id, _ = _scope()
    with TestClient(app) as client:
        first = _chat(client, pid, "create an L2 container")
        assert first.status_code == 400  # asks for the name
        history = [
            {"role": "user", "text": "create an L2 container"},
            {"role": "assistant", "text": "What should the new element be called?"},
        ]
        followup = client.post(f"/projects/{pid}/chat", json={"message": "payments", "history": history}, headers=ADMIN).json()
        mutation = followup["mutation"]
        assert mutation["action"] == "create_element" and mutation["name"] == "payments"
        assert mutation["parent"] == "Digital banking"


def test_chat_stream_runs_branches_concurrently_then_judges():
    """The agent graph fans out planner/retrieval/tools, streams a `branch`
    event per branch, a `judge` verdict, then the final `result` in the same
    shape as POST /chat (so the Apply flow is shared)."""
    pid, _, _ = _scope()
    with TestClient(app) as client:
        res = client.post(f"/projects/{pid}/chat/stream", json={"message": "list L2 containers"}, headers=ADMIN)
        assert res.status_code == 200
        body = res.text
        assert body.count("event: branch") == 3
        for branch in ("planner", "retrieval", "tools"):
            assert f'"branch": "{branch}"' in body
        assert "event: judge" in body and '"sufficient": true' in body
        assert "event: result" in body and '"action": "list"' in body
        assert '"evidence"' in body  # retrieval/tools attached to the final payload
        # branch partials must arrive before the verdict, which precedes the result
        assert body.index("event: branch") < body.index("event: judge") < body.index("event: result")


def test_chat_stream_write_proposal_and_error_paths():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        # A write streams the same proposal mutation the non-streaming path builds.
        res = client.post(f"/projects/{pid}/chat/stream",
                          json={"message": "create an L2 container called payments"}, headers=ADMIN)
        assert '"mutation"' in res.text and '"parent": "Digital banking"' in res.text
        # A dispatch failure becomes a clean in-stream error event.
        res = client.post(f"/projects/{pid}/chat/stream",
                          json={"message": "readiness of does-not-exist"}, headers=ADMIN)
        assert "event: error" in res.text and '"code": "chat_invalid"' in res.text


def test_hosted_llm_failure_has_json_and_stream_error_contracts(monkeypatch):
    """Provider SDK failures must be visible to the UI, never raw ASGI 500s."""
    from backend.llm.factory import LLMInvocationError

    async def fail(*args, **kwargs):
        raise LLMInvocationError("The configured LLM request failed. quota exceeded", retryable=True)

    monkeypatch.setattr(agents, "interpret_chat", fail)
    pid, _, _ = _scope()
    with TestClient(app) as client:
        response = _chat(client, pid, "list L2")
        assert response.status_code == 502
        assert response.json()["error"] == {
            "code": "llm_provider_error",
            "message": "The configured LLM request failed. quota exceeded",
            "details": None,
            "retryable": True,
        }

        streamed = client.post(f"/projects/{pid}/chat/stream", json={"message": "list L2"}, headers=ADMIN)
        assert streamed.status_code == 200
        assert "event: error" in streamed.text
        assert '"code": "llm_provider_error"' in streamed.text
        assert '"retryable": true' in streamed.text


def test_update_status_via_chat():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        proposal = _chat(client, pid, "set onboarding-web status to reviewed").json()
        assert proposal["action"] == "update_element"
        client.post(f"/projects/{pid}/chat/apply", json={"mutation": proposal["mutation"]}, headers=ADMIN)
        status = next(e["status"] for e in c4_store.list_graph(pid)["elements"] if e["name"] == "onboarding-web")
        assert status == "reviewed"


def test_conversations_persist_and_are_user_scoped():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        result = _chat(client, pid, "what's the project status?").json()
        conversation_id = result["conversation_id"]
        listing = client.get(f"/projects/{pid}/chat/conversations", headers=ADMIN).json()
        assert listing[0]["id"] == conversation_id
        assert listing[0]["message_count"] == 2
        loaded = client.get(f"/projects/{pid}/chat/conversations/{conversation_id}", headers=ADMIN).json()
        assert [message["role"] for message in loaded["messages"]] == ["user", "assistant"]
        assert client.get(f"/projects/{pid}/chat/conversations/{conversation_id}", headers=VIEWER).status_code == 404


def test_text_attachment_is_saved_and_linked_to_message():
    pid, _, _ = _scope()
    with TestClient(app) as client:
        conversation = client.post(f"/projects/{pid}/chat/conversations", headers=ADMIN).json()
        uploaded = client.post(
            f"/projects/{pid}/chat/conversations/{conversation['id']}/attachments",
            files={"file": ("notes.md", b"# Release notes\nPayments launch is at risk.", "text/markdown")},
            headers=ADMIN,
        )
        assert uploaded.status_code == 200
        response = client.post(f"/projects/{pid}/chat", json={
            "message": "summarize this file", "conversation_id": conversation["id"],
            "attachment_ids": [uploaded.json()["id"]],
        }, headers=ADMIN)
        assert response.status_code == 200
        loaded = client.get(f"/projects/{pid}/chat/conversations/{conversation['id']}", headers=ADMIN).json()
        assert loaded["messages"][0]["attachments"][0]["filename"] == "notes.md"


@pytest.mark.parametrize(("mode", "action"), [
    ("chat", "answer"), ("code", "code"), ("research", "web_search"),
    ("image", "image"), ("document", "document"),
])
def test_explicit_chat_modes_override_keyword_routing(mode, action):
    pid, _, _ = _scope()
    with TestClient(app) as client:
        response = client.post(f"/projects/{pid}/chat", json={
            "message": "create an L2 container called should-not-be-created",
            "mode": mode,
        }, headers=ADMIN)
        assert response.status_code == 200
        assert response.json()["action"] == action
        assert response.json()["mutation"] is None
