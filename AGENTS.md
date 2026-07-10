# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project

Story Pointer: an evidence-led story-point estimator (modified Fibonacci 1/2/3/5/8/13) for React/Spring teams. FastAPI backend runs a checkpointed LangGraph pipeline and streams progress over SSE; React 19 + Vite frontend (Material 3 shell) consumes the stream. Stories come from a form, Jira, a spreadsheet upload, or — via the project workspace — from L3 components of an interactive C4 model whose points roll up to epics and initiatives. Each L1 initiative can also carry an operating plan (teams, cost, schedule, architecture diagrams).

## Commands

Run everything from the repository root. Python 3.11+, Node 20+.

```powershell
# setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item backend\.env.example backend\.env   # then fill in LLM_* keys
npm install
Copy-Item frontend\.env.example frontend\.env

# run
npm run dev:all                               # API on :8000 + Vite on :5173
npm run api:dev                               # backend only
npm run web:dev                               # frontend only
.\scripts\run-monorepo.ps1 dev                # PowerShell wrapper for API + web

npm run api:seed:demo                         # small demo project + C4 model
npm run api:seed:banking                      # richer multi-level banking sample

# tests
.venv\Scripts\python.exe -m pytest backend/tests -q   # backend
pytest backend/tests/test_mapping.py -q        # one file
pytest backend/tests/test_l1_planning.py::test_full_operating_plan_and_cost_metrics -q   # one test
npm run web:test                               # frontend (vitest run, all files)
npm run web:test -- InspectorPanel             # frontend, one file by name
npm run test:all                               # backend + frontend
npm run build                                  # production build to dist/

# desktop (Electron) — see the Desktop section below
npm run desktop:dev                            # hot-reload Vite + Electron shell, backend runs from source
python -m pip install -r requirements-desktop.txt   # adds PyInstaller for bundling
npm run desktop:build:win                      # NSIS installer + portable exe into release/
npm run desktop:build:mac                      # dmg + zip
```

This is a monorepo. The root `package.json` orchestrates project commands; `frontend/package.json` owns the React/Vite workspace, `desktop/package.json` owns Electron packaging, and Python backend dependencies stay in `requirements.txt`. See `docs/monorepo.md` for the boundary map and runner commands.

`LLM_PROVIDER=mock` in `backend/.env` runs the full pipeline offline with no API key (deterministic, hash-based points) — use it for local UI work and demos.

`AGENTS.md` is a near-verbatim mirror of this file for Codex; keep the two in sync when editing architecture notes.

## Architecture

### Estimation pipeline (the core)

- `backend/graph/build.py` — wires the LangGraph `StateGraph`: score_parameters → identify_drivers → compare_to_anchors → derive_points → (conditional `spike_split_branch` when points == 13 or uncertainty is High) → write_plain_language_reasoning → detect_hidden_tasks → assess_risks → recommend_split. Compiled with `MemorySaver`; the caller's `session_id` becomes the `thread_id`, which is what makes refinements ("re-estimate assuming X") work against a prior run.
- `backend/graph/state.py` — the `EstimationState` TypedDict plus one Pydantic output schema per node (`ScorecardOutput`, `PointsOutput`, etc.). These schemas are the contract between prompts and state.
- `backend/graph/nodes.py` — all node prompts and implementations. Contains `_parse_structured_result`, which tolerates provider quirks (raw/parsed envelopes, markdown-fenced JSON, Groq list echoes) — structured-output bugs are usually fixed there, not in the nodes.

### Project workspace and C4 model

- Persistence is stdlib SQLite ([backend/storage/db.py](backend/storage/db.py)) at `data/storypointer.db` (override: `STORYPOINTER_DB` env var); LangGraph checkpoints go to `data/checkpoints.db` via `AsyncSqliteSaver`, installed in the API lifespan through [backend/graph/checkpoint.py](backend/graph/checkpoint.py) — tests and bare imports fall back to `MemorySaver`.
- `backend/projects/` (CRUD + repo/Jira links) and `backend/c4/` (elements, relations, artifact links, imports, roll-up) follow store/service/router layering. Level rules: an element's parent must be exactly one level up; L1→initiative, L2→epic, L3→story, L4→task (`ARTIFACT_FOR_LEVEL` in [backend/c4/models.py](backend/c4/models.py)); cross-cutting bug/tech_debt/arch_flow artifacts tag elements at allowed levels.
- Estimation of an element (L3/L4 only) builds a `Story` with `c4_context` (parent chain, relations, code path — see `element_to_story` in [backend/c4/service.py](backend/c4/service.py)) and reuses `stream_story` from [backend/api/streaming.py](backend/api/streaming.py) with an `on_result` callback that persists points and seeds proposed L4 tasks (from `hidden_tasks`) and sibling L3 stories (from split recommendations). Roll-ups are deterministic sums — never LLM output; `proposed` elements are excluded.
- SSE helpers live in `backend/api/streaming.py` (not `main.py`) so the C4 router can import them without a circular import.

### L1 operating plans (`backend/planning/`)

- Each **L1 element** can carry an operating plan: agile units (tribes → squads), team members, scheduled/costed work items, and mermaid architecture/infrastructure diagrams — all in the `l1_*` tables in [backend/storage/db.py](backend/storage/db.py). Same store/router layering as the other modules; the router mounts under `/projects/{id}/l1/...` in [backend/planning/router.py](backend/planning/router.py).
- Invariants enforced in [backend/planning/store.py](backend/planning/store.py): a plan attaches only to an L1 element; a squad's parent must be a tribe in the same plan; a work item's `linked_element_id` must be an L2–L4 descendant of that L1, and its `squad_id` a squad in the same plan; `end_date >= start_date`.
- `get_plan` returns the plan plus **deterministically computed** `metrics` (people, allocated FTE, monthly run-rate, planned/actual cost + variance, at-risk work) — no LLM involvement. Money is presentation-only; the stored `currency_code` (per-L1 `l1_plan_settings`) just labels it.

### Global resource directory (`backend/resources/`)

- App-global (not project-scoped) staff pool any module can reference — served under `/resources/...`, same store/service/router layering. Tables `resource_staff`, `resource_lookups`, `resource_custom_fields` live in [backend/storage/db.py](backend/storage/db.py); default Tech Unit / Rank / HR Role lookups are seeded once in `init_db`.
- Fixed staff columns mirror the standard schema (name, type, status, sub_status, dates, `reporting_manager_id`); `staff_code` is generated (`STF-0001`, …). The three "…defined in X Table" fields (`tech_unit`/`rank`/`hr_role`) are validated against the `resource_lookups` category on write. Anything beyond the fixed columns is user-defined: **custom field definitions** (`resource_custom_fields`, typed text/number/date/select/boolean) whose values live in each staff row's `custom_values` JSON — validated in [backend/resources/store.py](backend/resources/store.py) (unknown keys rejected, required present, select options enforced).
- Invariants in `store.py`: a lookup can't be deleted while assigned to staff; a manager must exist and not be self; deleting a person nulls reports' `reporting_manager_id`. Frontend is the global **Resources** screen ([frontend/src/screens/ResourceDirectory.jsx](frontend/src/screens/ResourceDirectory.jsx)), reached from the top-bar nav; its "Lists & fields" dialog manages lookups and custom-field definitions.

### Admin, auth & access control (`backend/access/`, `backend/reporting/`)

- **Local demo auth** (no passwords/tokens). Application users *are* people in the resource directory; `app_access` (in [backend/storage/db.py](backend/storage/db.py)) assigns each a role (`admin > manager > contributor > viewer`) + enabled flag. [backend/access/store.py](backend/access/store.py) `_bootstrap_admin` promotes the earliest-created staff to admin so the app is never locked out; `/access/login-users` lists enabled+active identities for the login screen, `/access/users` drives the role editor.
- **Reporting** ([backend/reporting/service.py](backend/reporting/service.py), `/reporting/overview`) is deterministic cross-module aggregation (portfolio, resource utilisation, allocation status, app-role counts) — no LLM.
- **Frontend auth is client-side**: [frontend/src/auth/AuthContext.jsx](frontend/src/auth/AuthContext.jsx) holds the signed-in `{staff_id, name, role}` in localStorage; [permissions.js](frontend/src/auth/permissions.js) maps roles → capabilities via `can(role, cap)`. `App.jsx` renders [Login](frontend/src/screens/Login.jsx) when signed out, otherwise gates the **Admin** nav + actions by capability. The [AdminConsole](frontend/src/screens/AdminConsole.jsx) hosts Access management, Reporting, and the **Resources directory (moved here from the top-level nav)**. Global feedback uses the [Toast](frontend/src/ui/Toast.jsx) snackbar provider (wired in `main.jsx` alongside `AuthProvider`). Shared UX styles live in [frontend/src/ux.css](frontend/src/ux.css).
- **Backend RBAC is enforced** by an HTTP middleware in [backend/api/main.py](backend/api/main.py): the frontend client sends `X-User-Id` (role looked up authoritatively via `access.store.effective_role`) or `X-User-Role` (bootstrap admin without a directory id); [backend/auth/deps.py](backend/auth/deps.py) `route_policy` maps method+path → required capability ([backend/auth/permissions.py](backend/auth/permissions.py) mirrors the frontend map). Reads need auth; writes need `platform.edit`; `/access`→`admin.access`, `/reporting`→`admin.reporting`, `/resources` writes→`admin.resources`; `/health`, `/config`, `/access/login-users` are public. This map **must stay in sync with the frontend permissions**.

### Agentic AI (`backend/ai/`)

- Four LLM-backed services, each gathering context → structured output via the factory (never touching provider names) → returning a *proposal* the user reviews before anything persists. Mounted by [backend/ai/router.py](backend/ai/router.py); all require a configured LLM (503 otherwise, like estimation). `LLM_PROVIDER=mock` returns deterministic proposals via `_build_agentic` in [backend/llm/mock.py](backend/llm/mock.py) (parses the **human** message only — labels also appear in system prompts).
  - **Auto-staffing** (`/projects/{id}/l1/{l1}/ai/staffing`): proposes squad↔resource assignments respecting each person's remaining allocation (re-clamped defensively in `agents.propose_staffing`); apply reuses `planning.create_member` so the 100% cap still holds. UI: "AI staffing" in [TeamPlanning](frontend/src/planning/TeamPlanning.jsx).
  - **Reporting narrative** (`/reporting/narrative`): summarises the deterministic overview into an executive briefing. UI: "AI summary" in [Reporting](frontend/src/screens/admin/Reporting.jsx).
  - **Story decomposition** (`/projects/{id}/c4/elements/{eid}/ai/decompose`): proposes child stories; apply creates them one level down as `status='proposed'`. UI: "AI: suggest stories" in [InspectorPanel](frontend/src/c4/InspectorPanel.jsx).
  - **C4 scaffold** (`/projects/{id}/c4/ai/scaffold`): turns a description into an L1/L2/L3 model + relations (temporary `ref`s resolved to ids on apply, all `proposed`). UI: "AI scaffold" on the [C4Canvas](frontend/src/c4/C4Canvas.jsx) toolbar.

### L1 architecture baseline (`backend/l1arch/`)

- Extends each **L1 element** with strategy/governance artifacts beyond the operating plan: vision + OKRs, stakeholder map with RACI, hierarchical business-capability map, and a portfolio risk & funding register — tables `l1_vision`/`l1_okrs`/`l1_stakeholders`/`l1_capabilities`/`l1_risks` in [backend/storage/db.py](backend/storage/db.py), same store/router layering, mounted under `/projects/{id}/l1/{l1}/arch/...`.
- [backend/l1arch/service.py](backend/l1arch/service.py) computes a **deterministic readiness score** (weighted per the requirement's 7 areas) + a completeness checklist, and renders the **executive summary as a single Markdown document with embedded Mermaid** (`executive_summary`) — deliberately *the PowerPoint replacement*: the app's own [MarkdownViewer](frontend/src/components/MarkdownEditor.jsx) renders it (capability map as a live Mermaid diagram). No LLM in scoring or rendering.
- AI: `agents.generate_l1_baseline` / `apply_l1_baseline` (schema `L1BaselineDraft`) drafts vision/OKRs/stakeholders/capabilities/risks from a brief and applies accepted sections; mock builder makes it work offline. UI: the **L1 baseline** tab (default) in [L1Architecture](frontend/src/planning/L1Architecture.jsx) — readiness gauge + checklist, per-artifact tables/dialogs, "AI generate baseline", and the rendered executive summary.
- API note: the executive-summary route returns `{markdown, readiness_score}` — `readiness_score` is an int, so the route is typed `dict[str, Any]`, not `dict[str, str]` (a `dict[str, str]` annotation triggers `ResponseValidationError`). Covered by `test_l1arch.py::test_executive_summary_endpoint_returns_200`.
- **Governance**: `l1_approvals` (in [db.py](backend/storage/db.py)) drives a sequential sign-off chain (product→architecture→security→risk→finance→sponsor); `store.decide_approval` enforces order and baselines the vision when all approve, reverting to `draft` on a rejection. UI: the **Governance** tab in [L1Architecture](frontend/src/planning/L1Architecture.jsx).
- **Exports**: [backend/l1arch/exports.py](backend/l1arch/exports.py) renders the exec summary to Markdown / Word / PowerPoint by reusing the requirements exporter's Markdown+Mermaid helpers (`_blocks`, `_diagram_bytes`); the frontend renders Mermaid to PNGs (`renderMermaidImages`) and POSTs them so Word/PPTX embed the diagram. The MD/Mermaid view stays the source of truth — exports are just renderings.

### L2 container architecture (`backend/l2arch/`)

- A living **container-architecture workspace attached to each L2 element** (a child of an L1 initiative) — mirrors the l1arch pattern one C4 level down. Tables `l2_arch` (summary + `container_diagram` mermaid + status), `l2_containers` (service boundaries + ownership), `l2_apis` (API/data contracts), `l2_nfrs`, `l2_integrations` in [db.py](backend/storage/db.py); store/service/router layering, mounted under `/projects/{id}/l2/{l2}/arch/...` (`store._require_l2` rejects non-L2 elements).
- [backend/l2arch/service.py](backend/l2arch/service.py): deterministic **readiness score** (the requirement's 9 weighted areas) + checklist + gaps/recommendations, and the **engineering summary as Markdown + embedded Mermaid** (container diagram embedded, or auto-built from the containers when none) — the PowerPoint replacement, rendered by [MarkdownViewer](frontend/src/components/MarkdownEditor.jsx).
- AI: `agents.generate_l2_baseline` / `apply_l2_baseline` (schema `L2Draft`) drafts a container diagram + containers/APIs/NFRs/integrations from the L1 context + a brief; mock builder works offline. UI: the **L2 arch** nav-rail tab ([L2Architecture](frontend/src/planning/L2Architecture.jsx)) — L2-element picker, readiness gauge, a split Mermaid editor+live preview (reuses [MermaidView](frontend/src/components/MermaidView.jsx) + "Open studio" → [DiagramStudio](frontend/src/planning/DiagramStudio.jsx)), per-artifact tables/dialogs, "AI generate L2", and the rendered engineering summary.
- **Governance**: `l2_approvals` (in [db.py](backend/storage/db.py)) drives a sequential sign-off chain (engineering→security→nfr→data→architecture→sponsor); `store.decide_approval` enforces order and baselines `l2_arch.status` when all approve, reverting a baselined L2 to `reviewed` on a rejection. `store.approval_state` is the shape the frontend `GovernancePanel` renders. UI: the **Governance** tab.
- **RACI matrix**: `l2_arch.raci` is a JSON `{artifact:role → R|A|C|I}` map; `store.set_raci` validates against `RACI_ARTIFACTS` × `RACI_ROLES` (both surfaced in `get_workspace`) and read-modify-writes the JSON. UI: the **RACI** tab grid of `<select>` cells.
- **Traceability**: `service.traceability` returns the L1→L2→L3 link graph + a Mermaid flowchart (also embedded as a "## Traceability" section in the engineering summary). UI: the **Traceability** tab.
- **Live imports** ([backend/l2arch/imports.py](backend/l2arch/imports.py)): `parse_openapi` (one API record per path+method) and `parse_kubernetes` (a container per Deployment/StatefulSet/Service/etc.) accept JSON or YAML (PyYAML, multi-doc), raising `ImportError_`→400; `run_import` persists via the store. UI: the header **Import** dialog (OpenAPI → APIs, Kubernetes manifest → containers).

### L3 component architecture (`backend/l3arch/`)

- A **component-design workspace attached to each L3 element** (a child of an L2 container) — mirrors l2arch one C4 level down (full parity). Tables `l3_arch` (summary + `component_diagram` mermaid + `raci` JSON + status), `l3_approvals`, `l3_components` (internal building blocks: controller/service/repository/gateway/… with responsibilities, tech, pattern, owner), `l3_interfaces` (provided/consumed + contract + auth), `l3_dependencies` (internal/container/external/library), `l3_concerns` (cross-cutting: logging/caching/validation/security/…) in [db.py](backend/storage/db.py); store/service/router layering, mounted under `/projects/{id}/l3/{l3}/arch/...` (`store._require_l3` rejects non-L3 elements).
- [backend/l3arch/service.py](backend/l3arch/service.py): deterministic **readiness score** (9 weighted areas summing 100) + checklist + gaps/recommendations, and the **component summary as Markdown + embedded Mermaid** (component diagram embedded, or auto-built from the components) — the PowerPoint replacement, rendered by [MarkdownViewer](frontend/src/components/MarkdownEditor.jsx).
- **Governance** (`l3_approvals`): sequential sign-off design→interfaces→security→testing→architecture→tech_lead; `store.decide_approval` enforces order and baselines `l3_arch.status`. **RACI** (`l3_arch.raci`, `RACI_ARTIFACTS` × `RACI_ROLES`) and **traceability** (`service.traceability` → L2→L3→L4 graph + Mermaid, also embedded in the summary) match the l2arch pattern.
- AI: `agents.generate_l3_baseline` / `apply_l3_baseline` (schema `L3Draft`) drafts a component diagram + components/interfaces/dependencies/concerns from the L2 context + a brief; mock builder works offline. UI: the **L3 arch** nav-rail tab ([L3Architecture](frontend/src/planning/L3Architecture.jsx)) — element picker, readiness gauge, split Mermaid editor+preview, per-artifact tables/dialogs, RACI + Governance + Traceability tabs, "AI generate L3", and the rendered component summary.

### L4 implementation detail (`backend/l4arch/`)

- A **code / implementation-detail workspace attached to each L4 task element** (a child of an L3 component) — deliberately **lean** (no approval chain/RACI at task level). Tables `l4_arch` (summary + `code_diagram` mermaid + status), `l4_code_units` (classes/interfaces/functions/modules with responsibility, tech, path, complexity), `l4_test_cases` (unit/integration/e2e with scenario + expected), `l4_checklist` (Definition-of-Done items, `done` INTEGER hydrated to bool) in [db.py](backend/storage/db.py); store/service/router under `/projects/{id}/l4/{l4}/arch/...` (`store._require_l4`).
- [backend/l4arch/service.py](backend/l4arch/service.py): deterministic **implementation-readiness score** (5 weighted areas summing 100: l3_alignment/code_units/test_coverage/dod_checklist/diagram) + checklist, the **implementation summary as Markdown + Mermaid** (class/sequence diagram, or auto-built classDiagram from code units; DoD rendered as `- [x]` task lists), and **upward traceability** (`service.traceability` → L2→L3→L4 chain + Mermaid).
- AI: `agents.generate_l4_baseline` / `apply_l4_baseline` (schema `L4Draft`) drafts a class/sequence diagram + code units/test cases/DoD checklist from the L3 context + a brief; mock builder works offline. UI: the **L4 detail** nav-rail tab ([L4Architecture](frontend/src/planning/L4Architecture.jsx)) — element picker, readiness gauge, split Mermaid editor+preview, code-unit/test-case tables, a toggleable **Definition of Done** list, Traceability, "AI generate L4", and the rendered implementation summary.
- Note: `TestCaseCreate`/`TestCaseUpdate` in [backend/l4arch/models.py](backend/l4arch/models.py) set `__test__ = False` so pytest doesn't try to collect the Pydantic models as test classes.

### Cross-level workflow guide (`backend/workflow/`)

- A deterministic **next-best-action guide** across the whole top-down flow (L1 strategy → L2 containers → L3 components → L4 implementation → estimation & roll-up). [backend/workflow/service.py](backend/workflow/service.py) `guide(project_id)` assembles, per level: active element count, average readiness (from each level's own `readiness` scorer), a `status` (not_started / in_progress / ready), whether the level is `expected` yet (a level becomes expected once its parent exists), and a list of `actions` each carrying a target frontend `tab`. Estimation progress comes from the deterministic `c4.service.rollup`. It also derives an overall %, the current `stage`, and the single most impactful `next_action`. No LLM. Route: `GET /projects/{id}/workflow` ([router.py](backend/workflow/router.py), mounted in [main.py](backend/api/main.py)).
- UI: the **Workflow guide** button in the [ProjectWorkspace](frontend/src/screens/ProjectWorkspace.jsx) page header opens a stepper modal ([WorkflowWizard](frontend/src/screens/WorkflowWizard.jsx)) — overall progress + stage, an L1→L4→Est stepper, per-stage stats/readiness/recommended actions, and a "Next best step" CTA; acting on any recommendation calls `onNavigate(tab)` to jump straight to the relevant workspace tab and closes the wizard.

### Conversational assistant (`backend/chat/`)

- A chat assistant that can **query, report on, and modify** the C4 model in natural language. [backend/ai/agents.py](backend/ai/agents.py) `interpret_chat` turns a message (+ a compact element listing for name resolution, PII-masked) into a `ChatCommand` (schema in [ai/schemas.py](backend/ai/schemas.py)); [backend/chat/service.py](backend/chat/service.py) `dispatch` then **executes reads immediately** (overview → workflow guide, list, readiness of a named element/level, report → roll-up + next step) and **returns writes as a proposal** (`create_element` / `update_element` / `delete_element`) rather than persisting. `apply` performs a confirmed write by **re-resolving names** through `c4.store` (so C4 level rules + RBAC hold). Reads use the deterministic services' own computed replies (accurate numbers), not LLM prose.
- Routes ([backend/chat/router.py](backend/chat/router.py), mounted in [main.py](backend/api/main.py)): `POST /projects/{id}/chat` (needs a configured LLM) and `POST /projects/{id}/chat/apply`. RBAC ([deps.py](backend/auth/deps.py)): `…/chat` reads/proposes so **any signed-in user** may use it; `…/chat/apply` writes so it needs **`platform.edit`**. `LLM_PROVIDER=mock` gives a deterministic keyword parser (`ChatCommand` builder in [llm/mock.py](backend/llm/mock.py)) so the whole flow works offline and in tests.
- UI: a floating **Assistant** dock ([frontend/src/components/ChatDock.jsx](frontend/src/components/ChatDock.jsx)) mounted in the ProjectWorkspace — conversation bubbles, structured data (element lists, readiness chips, per-level chips), and proposed writes rendered with **Apply / Dismiss** (Apply hidden without `platform.edit`); applying calls `chatApply` then the workspace's refresh.

### Integrations, orchestrator & ABAC

- **Integration catalog** ([backend/integrations/catalog.py](backend/integrations/catalog.py), `/integrations/catalog`): the ~42 tools from the requirement, grouped by category with a computed `status` — `adapter` (a live in-app adapter: document import, mermaid, resource directory), `connected` (a saved+enabled config, or Jira with env-configured instances), else `available`. Each tool carries a `configurable` flag (adapters aren't). It's a **framework + catalog**, not 42 live connectors. UI: **Admin → Integrations**.
- **Connector configuration** ([backend/integrations/connectors.py](backend/integrations/connectors.py) + [store.py](backend/integrations/store.py), `integration_configs` table): each connector maps to a field-schema *archetype* (atlassian / token / apikey / basic / webhook / directory / oauth) describing the URL/credential fields to collect. `store.get_config` returns the field schema + non-secret values + a `secrets_set` list — **secrets are write-only and never returned to the client**; `save_config` merges (a secret is updated only when a new non-blank value is supplied) and requires all required fields before it will `enable`. Routes `GET/PATCH/DELETE /integrations/{key}/config` + `POST /integrations/{key}/test` (deterministic validation — required present + URLs well-formed; not a live connection). RBAC: the catalog is readable by any signed-in user, but config read/write needs the **`admin.integrations`** capability (admin-only; see [permissions.py](backend/auth/permissions.py) and [deps.py](backend/auth/deps.py)). UI: a **Configure/Manage** dialog per card in [Integrations](frontend/src/screens/admin/Integrations.jsx) that renders the connector's fields, masks saved secrets, toggles enabled, and Validate/Disconnect.
- **AI orchestrator** (`agents.orchestrate`, `/ai/orchestrate`): routes a natural-language request to one specialized agent (`generate_l1_baseline`/`auto_staffing`/`decompose_story`/`scaffold_c4`/`reporting_narrative`/`review_readiness`). Shown as the "AI command router" on the Integrations screen. **Document import** reuses `aiL1Baseline(brief=<pasted text>)`.
- **PII masking** ([backend/ai/masking.py](backend/ai/masking.py) `mask_pii`) redacts emails/phones/ids from user free-text before it reaches the LLM — applied to baseline briefs, decompose guidance, scaffold descriptions and the orchestrator request.
- **ABAC**: projects carry a `sensitivity` (`standard`|`restricted`); the RBAC middleware's `restricted_block` ([backend/auth/deps.py](backend/auth/deps.py)) 403s viewers/contributors on any `/projects/{id}/...` path of a restricted workspace (managers/admins pass). Set at creation in the New-platform wizard.

### L1 traceability, change-impact, comments & live Jira

- **Traceability**: OKRs, capabilities and risks each carry a nullable `linked_element_id` (FK → `c4_elements`, `ON DELETE SET NULL` — deleting the target *nulls* the link, so orphans can't exist). `service.traceability` returns the link graph; the frontend edit dialogs expose a C4-element dropdown (field `type: 'element'`).
- **Change-impact analysis** ([service.impact_analysis](backend/l1arch/service.py), `/arch/impact`): deterministic consistency findings (inactive-but-Accountable stakeholders, owner-less capabilities, overdue risks, off-track OKRs, open comments on a baselined L1), severity-sorted. Shown atop the **Governance** tab alongside the readiness review + approval chain.
- **Comments / review threads**: `l1_comments` table + CRUD (`/arch/comments`); the **Discussion** tab posts/resolves/deletes review feedback.
- **Live Jira import** (`/arch/import/jira`): uses the existing `jira.registry` client to fetch a project's issues and map them into the L1 as capabilities or OKRs. Returns a clear `jira_not_configured` 400 when the instance isn't set up (covered by `test_l1arch.py::test_jira_import_requires_configured_instance`); real import needs `JIRA_*` env config.

### Desktop app (`desktop/`, Electron + PyInstaller)

- The same web build and FastAPI backend ship as a self-contained desktop app; no code forks. `desktop/electron/main.cjs` is the Electron main process: it starts the backend, waits on `/health`, then loads the UI (dev server URL when `ELECTRON_DEV_SERVER_URL` is set, otherwise `dist/index.html`).
- **Backend launch is dual-mode** ([main.cjs](desktop/electron/main.cjs) `backendCommand`): packaged builds run the bundled PyInstaller exe from `process.resourcesPath/backend`; unpackaged (`desktop:dev`) runs `python -m desktop.backend_launcher` from the repo. `backend_launcher.py` just calls `uvicorn.run(..., reload=False)` on host/port from `STORYPOINTER_API_*`.
- **Port handling**: prefers `8765`, reuses an already-healthy instance on it, else picks a random free port — so a dev backend and the desktop app coexist. A single-instance lock prevents duplicate windows.
- **The UI never bakes in the API URL.** Electron injects the resolved base via `additionalArguments`; `preload.cjs` exposes it as `window.storyPointer.apiBaseUrl`, and [client.js](frontend/src/api/client.js) prefers that over `VITE_API_BASE_URL`. Desktop data is per-user: `STORYPOINTER_DB` and the backend env file live under Electron's `userData` dir, seeded from `desktop/backend.env.example` on first run.
- **Bundling** ([scripts/build-backend-bundle.mjs](scripts/build-backend-bundle.mjs)) runs PyInstaller against `desktop/pyinstaller/storypointer-api.spec` → `desktop/backend-dist/`; the spec lists provider/langgraph/docx/pptx packages as `hiddenimports` (PyInstaller can't see dynamic imports, so **a new LLM provider or optional dep must be added there** or it's missing at runtime). `desktop:prepare` chains icon gen + web build + backend bundle before `electron-builder` (config in `package.json` `build`).

### Strict module boundaries

- `backend/llm/factory.py` is the **only** module allowed to know provider names. Native LangChain providers go in `NATIVE_PROVIDERS` (via `init_chat_model`); OpenAI-compatible endpoints (Moonshot, DeepSeek, Ollama, …) share `ChatOpenAI(base_url=...)` via `OPENAI_COMPATIBLE`. Groq gets `json_mode` structured output. `LLM_PROVIDER=mock` (`OFFLINE_PROVIDERS`) needs no API key and routes structured calls to the deterministic [backend/llm/mock.py](backend/llm/mock.py) — points come from a hash of the story title, so tests and demos are stable and offline. The API-key requirement is provider-specific and lives in `validate_factory_config`, not `config.py`. Adding a provider means editing the factory only.
- `backend/jira/registry.py` mirrors that boundary for Jira: `JIRA_INSTANCES=prod,sandbox` env names expand to `JIRA_<NAME>_*` variables parsed in `backend/config.py`. Cloud instances use REST v3 + Basic auth (email + token); Server/DC uses REST v2 + Bearer PAT (`backend/jira/client.py`). Instance names/auth are validated at startup, credentials lazily on first use.
- `backend/anchors.py` holds six fixed calibration stories injected into every comparison prompt — no embeddings or retrieval. Calibration changes are edits to this file plus an API restart.

### API behavior (`backend/api/main.py`)

- All estimation routes stream SSE. `node` events are progress-only; the final `result` event is emitted atomically and the server raises if `plain_language_why` or `tldr` is missing — a point value must never appear without its explanation.
- Startup config errors don't crash the app: `lifespan` stashes them in `app.state.configuration_errors`, `/health` reports them, and estimation routes return 503 via `require_llm_config`.
- All errors (HTTP and in-stream) use the shape `{ "error": { code, message, details, retryable } }`.
- Jira write-back is triple-gated: `JIRA_WRITE_ENABLED=true` env, `confirm=true` on the request, and per-issue confirmation in the UI.

### Configuration

All backend config comes from `backend/.env` (loaded by `backend/config.py`, typed via pydantic-settings). Frontend reads only `VITE_API_BASE_URL` from `frontend/.env`. Provider/model strings must not appear in application code outside the LLM factory.

### Frontend

- `frontend/src/App.jsx` is a small state-based router (no router lib): `home` → `wizard` → `project`, plus a standalone `quick`. [ProjectWorkspace](frontend/src/screens/ProjectWorkspace.jsx) hosts the nav-rail tabs — **canvas / L1 plan / L2 arch / L3 arch / L4 detail / rollup / quick / overview** (the L2–L4 architecture tabs are lazy-loaded) plus a header **Workflow guide** launcher ([WorkflowWizard](frontend/src/screens/WorkflowWizard.jsx)) that navigates between those tabs. Top-level screens live in `frontend/src/screens/`.
- The C4 canvas (`frontend/src/c4/`) is React Flow (`@xyflow/react`): [C4Canvas.jsx](frontend/src/c4/C4Canvas.jsx) with an [InspectorPanel](frontend/src/c4/InspectorPanel.jsx) side panel. Estimation runs in a **modal** ([EstimateDialog.jsx](frontend/src/c4/EstimateDialog.jsx)), not inline — it streams the pipeline then shows the full `ResultCard`; results are cached per element so "View reasoning" reopens without re-running.
- L1 planning UI is in `frontend/src/planning/` (teams, work/cost, mermaid diagram studio), opened from the L1 plan tab or the inspector's "More details" on an L1 node.
- The original single-story flow (form / Jira browser / Excel upload) is now the **Quick estimate** screen ([QuickEstimate.jsx](frontend/src/screens/QuickEstimate.jsx)); its building blocks stay in `frontend/src/components/`.
- `frontend/src/api/client.js` wraps every endpoint plus `consumeSSE` for streaming. Material 3 styling lives in [frontend/src/md3.css](frontend/src/md3.css) (the workspace shell) alongside the older `styles.css` (estimation components). Tests colocate as `*.test.jsx` (jsdom + Testing Library, setup in `frontend/src/test-setup.js`).
