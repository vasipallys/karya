# Design: Project Workspace with C4 Model and Estimation Roll-ups

Status: implemented (2026-07-05) — all four phases landed in one pass; this document is the design rationale. Usage lives in the README ("Project workspace flow").

## Idea in one paragraph

Story Pointer today estimates one story (or a batch) with no memory of the project it belongs to. This design turns it into a **project workspace**: a user creates or opens a project, links it to a code repo and a Jira project, and builds (or imports) a **C4 model** of the system in an interactive canvas. Every C4 element maps to an Agile artifact per the standard ladder — L1 System context → Theme/Initiative, L2 Container → Epic, L3 Component → Story/Feature, L4 Code → Task/Sub-task/PR — and the existing LangGraph estimation pipeline runs on the L3/L4 leaves with architecture context injected as evidence. Points roll up the tree so an epic and an initiative always show a justified aggregate. The UI moves to a Material Design 3 ("Google") theme.

## C4 ↔ Agile artifact mapping

| C4 level | Element kinds | Agile artifact | Estimation behavior |
|---|---|---|---|
| L1 System context | systems, actors | Theme / Initiative | Never estimated directly; roll-up of child epics |
| L2 Container | apps, services, DBs | Epic | Roll-up of child stories + an LLM-assessed integration overhead |
| L3 Component | modules in a container | Story / Feature | **The existing pipeline unit** — estimated directly via the LangGraph graph |
| L4 Code | classes, functions, PRs | Task / Sub-task / PR | Optional; seeded automatically from the pipeline's `hidden_tasks` and `recommend_split` outputs |

Cross-cutting artifacts attach to multiple levels instead of one parent:

- **Bug** → tagged L3 + L4 (component it lives in, code it touches)
- **Tech debt item** → tagged L2 + L3 (container whose health it affects, component to change)
- **Architecture flow** → tagged L2 + L3 (a relation-centric artifact: a path of `C4Relation` edges, e.g. "checkout → payment-service → ledger DB")

There is a natural synergy with the existing graph: `detect_hidden_tasks` output becomes proposed L4 tasks under the estimated L3 element, and `recommend_split` (mandatory for a 13) becomes proposed sibling L3 elements. The pipeline already produces the decomposition; today it is only displayed and thrown away.

## Data model (new — requires persistence)

The app currently has zero durable storage (`MemorySaver` is in-process). Projects and C4 models must survive restarts, so this feature introduces **SQLite via SQLModel/SQLAlchemy** (single file, no server, fits the current deployment shape). The graph checkpointer moves from `MemorySaver` to `SqliteSaver` in the same change so refinement sessions also survive restarts.

```
Project        (id, name, description, created_at)
RepoLink       (id, project_id, url, provider, mode: existing|new, default_branch)
JiraLink       (id, project_id, instance_name, project_key)     # instance_name references the existing JiraRegistry
C4Element      (id, project_id, level: L1|L2|L3|L4, kind, name, description,
                parent_id, tech, code_path, status)
C4Relation     (id, project_id, source_id, target_id, label, kind: sync|async|data)
ArtifactLink   (id, element_id, artifact_type: initiative|epic|story|task|bug|tech_debt|arch_flow,
                jira_issue_key?, points?, estimate_session_id?, estimated_at?)
```

Rules the model enforces:

- `parent_id` must point one level up (L3's parent is an L2, etc.); cross-cutting artifacts use `ArtifactLink` rows against multiple elements instead of a parent.
- `estimate_session_id` stores the LangGraph `thread_id`, so "refine this estimate" from the canvas reuses the existing checkpointed-refinement mechanism unchanged.
- `code_path` on an element (e.g. `backend/graph/`) is what links C4 to the repo — clickable in the UI, and included as evidence in estimation prompts.

## Backend additions

New router modules, following the existing boundary style (`backend/projects/`, `backend/c4/`):

| Method | Route | Purpose |
|---|---|---|
| POST/GET | `/projects` | Create / list projects (create = "start new"; open = "add to existing") |
| GET | `/projects/{id}` | Project detail incl. links and roll-up summary |
| POST | `/projects/{id}/repos` | Link an existing repo URL or register a new one |
| POST | `/projects/{id}/jira` | Bind a registry instance + project key |
| CRUD | `/projects/{id}/c4/elements`, `/relations` | C4 model editing |
| POST | `/projects/{id}/c4/import/jira` | Pull epics/stories from the bound Jira project and propose L2/L3 elements |
| POST | `/projects/{id}/c4/import/repo-scan` | Propose L2/L3/L4 elements from repo structure (LLM-assisted summarization of the module tree) |
| POST | `/projects/{id}/elements/{eid}/estimate` | SSE — wraps the existing graph with `c4_context` added to the story |
| POST | `/projects/{id}/elements/{eid}/artifact` | Create/link the mapped Jira issue (same triple gating as today's write-back) |
| GET | `/projects/{id}/rollup` | Initiative → epic → story tree with points, spike flags, unestimated counts |

**Estimation context change (the only touch to the graph):** `EstimationState.story` gains an optional `c4_context` dict — the element, its parent chain, its relations, and its `code_path`. Nodes already serialize the story into prompts via `_context`, so the pipeline picks this up as evidence with no node rewiring. Prompt text in `score_parameters` gets one added instruction: weigh dependencies/NFRs using the supplied architecture relations when present.

**Roll-up service** is deterministic (not LLM): sum of child story points per epic, plus flags (any spike recommended below, any unestimated leaf, any 13 pending split). L2 integration overhead is the one LLM-assisted step and is cached per epic until its children change.

**Boundaries preserved:** provider names stay only in `backend/llm/factory.py`; Jira HTTP stays in `backend/jira/`; all writes remain gated by `JIRA_WRITE_ENABLED` + explicit `confirm=true` + per-item UI confirmation.

## Frontend: interactive C4 canvas

- **Library:** React Flow (`@xyflow/react`) — custom nodes, pan/zoom, edge routing; the standard choice for interactive node canvases in React 19.
- **Levels = zoom/drill:** breadcrumb `L1 › payment-platform › payment-service`; double-click a node to drill into its children; the level palette matches the reference image (indigo L1, green L2, rust L3, grey L4).
- **Node anatomy:** name, kind, tech chips, artifact badge (e.g. `Epic · PAY-42`), and a points badge once estimated; unestimated leaves show a dashed outline.
- **Inspector panel (right):** selected element's description, code path (clickable to repo URL), linked Jira issue, last estimate (reusing the existing `Scorecard`, `EffortBar`, `ResultCard` components), and actions: *Estimate* (streams SSE into the panel), *Refine*, *Create Jira artifact*, *Link code path*.
- **Cross-cutting artifacts** render as pill overlays attached to their tagged elements, filterable from a toolbar (Bugs / Tech debt / Flows).

## UI/UX base flow — Material Design 3

Adopt MD3 tokens and components (recommendation: **MUI v6** with a Material-You token theme — mature React 19 support; `@material/web` web components are the alternative if framework-agnostic components are preferred). Roboto/Google Sans type scale, MD3 color roles derived from a seed color, dark scheme as default to match the current app.

Screen flow:

1. **Projects home** — top app bar, grid of project `Card`s (name, repo chip, Jira chip, % estimated), FAB **＋ New project**.
2. **New Project wizard** (MD3 stepper, every step skippable):
   `Basics` (name, description) → `Code repo` (paste existing URL / mark as new / skip) → `Jira` (pick instance from registry dropdown + project key / skip) → `Seed C4` (blank canvas | scan repo | import Jira epics).
3. **Project workspace** — navigation rail: *Overview · C4 Canvas · Estimates · Upload · Settings*. Canvas center, inspector right, estimation progress in an MD3 bottom sheet showing the existing SSE node-by-node pipeline view.
4. **Roll-up dashboard** — expandable tree (Initiative → Epic → Story → Task) with points, person-day ranges, spike/split flags, and a "estimate all unestimated" batch action that reuses the sequential batch SSE flow.

The current single-story form, Jira browser, and Excel upload remain available inside a project workspace (Upload tab) and as a standalone "Quick estimate" entry from the home screen — nothing existing is removed.

## Phasing

1. **Persistence + projects** — SQLite, `SqliteSaver`, project CRUD, repo/Jira link records, MD3 theme shell (app bar, rail, home, wizard).
2. **C4 model** — element/relation CRUD, React Flow canvas with drill-down, manual editing.
3. **Estimation integration** — `c4_context` in the story payload, per-element estimate + refine from the inspector, hidden-tasks → L4 seeding, roll-up endpoint + dashboard.
4. **Imports + Jira artifact creation** — Jira import, repo scan proposals, gated artifact write-back, cross-cutting artifacts.

Each phase is shippable; phase 1 alone already delivers "add new project, start new or add to existing, link repo and Jira".
