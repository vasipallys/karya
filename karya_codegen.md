# Karya — Full Code-Generation Specification (`karya_codegen.md`)

> This document is an exhaustive regeneration spec for the **Karya** application. It captures every module,
> database table, API route, algorithm, invariant, prompt, and frontend structure in enough detail that a
> competent engineer (or LLM) can recreate the entire codebase without loss of functionality.
> Verbatim-critical assets (SQL schema, anchors, permission maps, prompts, mock builders, readiness weights)
> are reproduced literally; the rest is specified precisely at function level.
>
> **Implementation baseline: 22 July 2026.** This revision includes grounded chat description/status reads,
> provider-tolerant `ChatCommand` parsing, Excel/CSV and LDAP/Active Directory resource imports, inline lead
> creation, per-user page permissions enforced in UI and API, full user-profile drill-down, the idempotent
> Northstar Digital organization seed, and the Smart Banking sample-data rename.

---

## 1. Product overview

Karya is an **evidence-led story-point estimator** (modified Fibonacci 1/2/3/5/8/13) for React/Spring teams,
grown into a full portfolio/architecture workspace:

- **FastAPI backend** runs a checkpointed **LangGraph** estimation pipeline and streams progress over **SSE**.
- **React 19 + Vite frontend** (Material 3 shell, no router library) consumes the stream.
- Stories come from a form, Jira, a spreadsheet upload, or — via the **project workspace** — from L3
  components of an interactive **C4 model** whose points roll up to epics and initiatives.
- Each **L1 initiative** can carry an operating plan (teams, cost, schedule, mermaid diagrams), an
  **architecture baseline** (vision/OKRs/stakeholders/capabilities/risks + governance), requirement documents;
  **L2/L3/L4** elements carry container/component/implementation architecture workspaces mirroring the same
  pattern one C4 level down each.
- Cross-cutting: global **resource directory**, local demo **auth + RBAC/ABAC**, **reporting**, **agentic AI**
  services (proposal-based), a **conversational assistant**, an **integration catalog/connector config**
  framework, a deterministic **workflow guide**, and an **Electron desktop** packaging of the same app.

**Tech stack**: Python 3.11+ (FastAPI, LangGraph, LangChain, pydantic v2, pydantic-settings, pandas,
openpyxl, httpx, PyYAML, python-docx, python-pptx), stdlib `sqlite3` persistence; Node 20+ (React 19, Vite,
`@xyflow/react`, mermaid, vitest + Testing Library); LDAP/Active Directory via `ldap3`; Electron +
PyInstaller for desktop.

---

## 2. Repository layout (monorepo)

```
karya/
├─ package.json               # root orchestrator scripts (npm run dev:all, api:dev, web:*, test:all, desktop:*)
├─ requirements.txt           # backend Python deps
├─ requirements-local.txt     # optional local HF runtime (torch, transformers, sentencepiece, tiktoken…)
├─ requirements-desktop.txt   # + PyInstaller
├─ pytest.ini
├─ .claude/launch.json        # dev-server launch config
├─ CLAUDE.md / AGENTS.md      # architecture notes (AGENTS.md mirrors CLAUDE.md)
├─ backend/                   # FastAPI app (module layout below)
├─ frontend/                  # React/Vite workspace (own package.json)
├─ desktop/                   # Electron shell + PyInstaller spec (own package.json)
├─ scripts/                   # seeders, monorepo runners, desktop build helpers
├─ docs/                      # monorepo.md, local-llm.md, user-guide, design docs
└─ data/                      # runtime SQLite files (karya.db, checkpoints.db) — gitignored
```

Backend module layout (each feature module follows **store / service / router** layering; every package has
an `__init__.py`):

```
backend/
├─ config.py        anchors.py       models.py
├─ api/             main.py, streaming.py
├─ auth/            deps.py, permissions.py
├─ access/          models.py, pages.py, store.py, router.py
├─ projects/        models.py, store.py, router.py
├─ c4/              models.py, store.py, service.py, router.py, scan.py
├─ graph/           build.py, state.py, nodes.py, checkpoint.py
├─ llm/             factory.py, mock.py, local.py
├─ ingest/          excel.py
├─ jira/            registry.py, client.py, mapping.py
├─ planning/        models.py, store.py, router.py, requirements.py, diagram_ai.py, exports.py
├─ l1arch/          models.py, store.py, service.py, router.py, exports.py
├─ l2arch/          models.py, store.py, service.py, router.py, imports.py
├─ l3arch/          models.py, store.py, service.py, router.py
├─ l4arch/          models.py, store.py, service.py, router.py
├─ resources/       models.py, imports.py, store.py, router.py
├─ reporting/       service.py, router.py
├─ ai/              agents.py, schemas.py, masking.py, nl.py, router.py
├─ chat/            service.py, store.py, router.py, graph.py
├─ workflow/        service.py, router.py
├─ integrations/    catalog.py, connectors.py, store.py, router.py
├─ storage/         db.py
└─ tests/           conftest.py + ~25 test files
```

---

## 3. Configuration — `backend/config.py`

Loads `backend/.env` (path overridable via `KARYA_ENV_FILE`) using `dotenv` + `pydantic-settings`
(`SettingsConfigDict(env_file=ENV_FILE, extra="ignore")`).

- `class ConfigurationError(RuntimeError)` — carries `errors: list[str]`, message is `"; ".join(errors)`.
- `class LLMSettings(BaseModel)` — consumed exclusively by the LLM factory:
  - `provider: str`, `model: str` (validator: non-empty, stripped)
  - `api_key: SecretStr`, `base_url: str|None`
  - `temperature: float = 0.2 (ge=0, le=2)`, `max_tokens: int = 3000 (ge=128, le=100_000)`
  - `local_device: str = "auto"` (validator: auto|cpu|mps|cuda|cuda:<idx>)
  - `local_dtype: str = "auto"` (validator: auto|float32|float16|bfloat16, lower-cased)
  - `local_revision: str = "main"`, `local_cache_dir: str|None`
  - `local_context_window: int = 8192 (ge=512, le=131_072)`
  - `local_trust_remote_code: bool = False`, `local_files_only: bool = False`
  - `local_preload: bool = True` (warm model at API startup on a background thread)
- `class JiraInstanceSettings(BaseModel)` — `name`, `base_url` (validator strips + rstrips `/`),
  `auth_type: Literal["cloud","server"]`, `api_token: SecretStr`, `email: str|None`,
  `story_points_field: str|None`, `ac_field: str|None`.
- `class Settings(BaseSettings)` — env fields (all prefixed `LLM_` / `JIRA_` in the env file):
  `llm_provider=""`, `llm_model=""`, `llm_api_key=SecretStr("")`, `llm_base_url=None`,
  `llm_temperature=0.2`, `llm_max_tokens=3000`, `llm_local_device="auto"`, `llm_local_dtype="auto"`,
  `llm_local_revision="main"`, `llm_local_cache_dir=None`, `llm_local_context_window=8192`,
  `llm_local_trust_remote_code=False`, `llm_local_files_only=False`, `llm_local_preload=True`,
  `jira_instances=""`, `jira_write_enabled=False`,
  `cors_origins="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"`.
  - `@property llm -> LLMSettings` — maps fields; wraps `ValidationError` into
    `ConfigurationError(["LLM_<LOC>: <msg>", …])`.
  - `@property cors_origin_list` — comma-split, stripped, non-empty.
  - `jira_configs() -> dict[name, JiraInstanceSettings]` — `JIRA_INSTANCES=prod,sandbox` expands to
    `JIRA_<NAME>_BASE_URL / _AUTH_TYPE (default "cloud") / _EMAIL / _API_TOKEN / _STORY_POINTS_FIELD / _AC_FIELD`
    env vars read via `os.getenv`; collects validation errors into one `ConfigurationError`.
  - `validate_startup()` — validates `llm` shape and `jira_configs()`; **API-key requirement is NOT here**
    (it is provider-specific and lives in the factory).
- `@lru_cache get_settings() -> Settings`.

`backend/.env.example` documents: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`,
`LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, the `LLM_LOCAL_*` knobs, `JIRA_INSTANCES` + per-instance vars,
`JIRA_WRITE_ENABLED`, `CORS_ORIGINS`. Frontend `.env.example`: only `VITE_API_BASE_URL=http://localhost:8000`.

---

## 4. Shared domain models — `backend/models.py`

```python
class Story(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    user_story: str = ""
    acceptance_criteria: list[str] = []       # before-validator: None→[]; str→split on ';' and newlines, strip blanks
    technical_breakdown: str | None = None
    existing_points: float | None = None
    key: str | None = None                     # Jira issue key
    status: str | None = None
    labels: list[str] = []
    components: list[str] = []
    source: Literal["manual", "jira", "upload"] = "manual"
    jira_instance: str | None = None
    c4_context: dict[str, Any] | None = None

class EstimateRequest(BaseModel):        story: Story; session_id: str|None; refinement: str|None
class BatchEstimateRequest(BaseModel):   stories: list[Story] (1..100); session_id: str|None
class UploadEstimateRequest(BaseModel):  rows: list[dict] (1..100); mapping: dict[str, str|None]; session_id: str|None
class JiraWriteRequest(BaseModel):       points: int; confirm: bool = False
class ErrorPayload(BaseModel):           code: str; message: str; details: Any|None; retryable: bool = False
```

All errors (HTTP and in-stream) use the shape `{"error": {code, message, details, retryable}}`.

---

## 5. Calibration anchors — `backend/anchors.py` (verbatim data)

Six fixed calibration stories injected into every comparison prompt — no embeddings/retrieval. Each is a dict
`{title, full_text, acceptance_criteria: [..], points, rationale}`:

1. **"Inline validation on a React payment form"** — 3 pts. AC: Validate four existing fields / Focus the first
   error / Add component tests. Rationale: React-only, established patterns, no service or data changes, modest testing.
2. **"Add an entitlement-protected account preference"** — 5 pts. AC: Hide control without entitlement / Persist
   and retrieve value / Audit the change. Rationale: small cross-stack change, known patterns, entitlement + audit.
3. **"Search and filter an existing transaction endpoint"** — 5 pts. AC: Combine filters / Preserve pagination /
   Test query performance. Rationale: cross-stack but bounded; some DB/perf work, little domain uncertainty.
4. **"Cross-market eKYC status integration"** — 8 pts. AC: Map vendor states / Apply market residency rules /
   Audit transitions / Handle timeouts. Rationale: integration-heavy, regulatory rules, failure handling, multi-market tests.
5. **"Transaction-wide AI summary with audit"** — 8 pts. AC: Write atomically / Record full audit metadata /
   Redact sensitive data / Support retry. Rationale: broad Spring + data work, transactional consistency, compliance.
6. **"New multi-market payment orchestration journey"** — 13 pts. AC: Support three markets / Compensate partial
   failures / Enforce entitlements / Full audit trail. Rationale: multiple new layers + external dependencies,
   high uncertainty; should be split before delivery.

---

## 6. SQLite persistence — `backend/storage/db.py`

Stdlib `sqlite3`; short-lived connections (one per operation), WAL mode, `PRAGMA foreign_keys=ON` per
connection, commit-on-success/rollback-on-exception context manager.

- `db_path()` → `KARYA_DB` env var else `<repo>/data/karya.db`; `checkpoint_path()` → sibling `checkpoints.db`.
- `init_db(path=None)` — mkdir parents, WAL, `executescript(_SCHEMA)`, then forward-migrations via
  `_ensure_columns` (PRAGMA table_info + ALTER TABLE ADD COLUMN for missing columns):
  - `l1_diagrams.metadata`, rebuild of `l1_diagrams` if the CHECK constraint predates the full diagram-type list
    (`_ensure_l1_diagram_type_check` renames to `_old`, recreates, copies, drops, re-indexes)
  - `projects.leads` / `projects.sensitivity`
  - `l1_team_members.resource_staff_id`
  - `linked_element_id` on `l1_okrs`, `l1_capabilities`, `l1_risks`
  - `l1_vision.{vision_statement_details,business_problem_details,target_users_details}`
  - `l2_arch.raci`
  - then `_seed_resource_lookups` (only if `resource_lookups` empty).
- `connect()` contextmanager — lazy `init_db` per path (`_initialized` set), `row_factory = sqlite3.Row`.
- `new_id()` = `uuid4().hex`; `utc_now()` = ISO-8601 UTC seconds; `rows_to_dicts(rows)`.

Default resource lookups seeded once:
```python
_DEFAULT_RESOURCE_LOOKUPS = {
  "tech_unit": [("PLATFORM","Platform"),("DATA","Data & Analytics"),("MOBILE","Mobile"),("CLOUD","Cloud & Infra")],
  "rank": [("A1","Analyst"),("SA","Senior Analyst"),("C","Consultant"),("SC","Senior Consultant"),("M","Manager")],
  "hr_role": [("ENG","Engineer"),("QA","QA Engineer"),("BA","Business Analyst"),("PM","Project Manager"),("ARCH","Architect")],
}
```

Allowed `l1_diagrams.diagram_type` values (`_DIAGRAM_TYPES`):
`architecture, infrastructure, architecture_beta, block, kanban, packet, sequence, class, state, er,
requirement, c4, gantt, journey, timeline, mindmap, quadrant, gitgraph, pie, xychart, sankey, radar, treemap, venn`.

### 6.1 Complete schema (verbatim)

```sql
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  leads TEXT NOT NULL DEFAULT '[]',
  sensitivity TEXT NOT NULL DEFAULT 'standard' CHECK (sensitivity IN ('standard','restricted')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repo_links (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  url TEXT NOT NULL DEFAULT '',
  local_path TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT 'git',
  mode TEXT NOT NULL DEFAULT 'existing',
  default_branch TEXT NOT NULL DEFAULT 'main'
);
CREATE TABLE IF NOT EXISTS jira_links (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  instance_name TEXT NOT NULL,
  project_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS c4_elements (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  level TEXT NOT NULL CHECK (level IN ('L1','L2','L3','L4')),
  kind TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  parent_id TEXT REFERENCES c4_elements(id) ON DELETE CASCADE,
  tech TEXT NOT NULL DEFAULT '',
  code_path TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  pos_x REAL, pos_y REAL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS c4_relations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  target_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  label TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'sync'
);
CREATE TABLE IF NOT EXISTS artifact_links (
  id TEXT PRIMARY KEY,
  element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL,
  jira_issue_key TEXT,
  points INTEGER,
  spike_recommended INTEGER NOT NULL DEFAULT 0,
  split_recommended INTEGER NOT NULL DEFAULT 0,
  estimate_session_id TEXT,
  estimated_at TEXT,
  UNIQUE (element_id, artifact_type)
);
CREATE TABLE IF NOT EXISTS l1_agile_units (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  unit_type TEXT NOT NULL CHECK (unit_type IN ('tribe','squad')),
  parent_unit_id TEXT REFERENCES l1_agile_units(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  mission TEXT NOT NULL DEFAULT '',
  lead_name TEXT NOT NULL DEFAULT '',
  capacity_fte REAL NOT NULL DEFAULT 0 CHECK (capacity_fte >= 0),
  target_velocity REAL NOT NULL DEFAULT 0 CHECK (target_velocity >= 0),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_plan_settings (
  l1_element_id TEXT PRIMARY KEY REFERENCES c4_elements(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  currency_code TEXT NOT NULL DEFAULT 'USD',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_team_members (
  id TEXT PRIMARY KEY,
  unit_id TEXT NOT NULL REFERENCES l1_agile_units(id) ON DELETE CASCADE,
  resource_staff_id TEXT REFERENCES resource_staff(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT '',
  skills TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  allocation_percent REAL NOT NULL DEFAULT 100 CHECK (allocation_percent >= 0 AND allocation_percent <= 100),
  monthly_cost REAL NOT NULL DEFAULT 0 CHECK (monthly_cost >= 0),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_work_items (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  squad_id TEXT REFERENCES l1_agile_units(id) ON DELETE SET NULL,
  linked_element_id TEXT REFERENCES c4_elements(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','in_progress','at_risk','done')),
  allocation_percent REAL NOT NULL DEFAULT 100 CHECK (allocation_percent >= 0 AND allocation_percent <= 100),
  budget_cost REAL NOT NULL DEFAULT 0 CHECK (budget_cost >= 0),
  actual_cost REAL NOT NULL DEFAULT 0 CHECK (actual_cost >= 0),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_diagrams (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  diagram_type TEXT NOT NULL CHECK (diagram_type IN (/* the 24 _DIAGRAM_TYPES above */)),
  title TEXT NOT NULL,
  mermaid_source TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_requirement_documents (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_review','approved')),
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  approved_by TEXT,
  approved_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_requirement_versions (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES l1_requirement_documents(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  changed_by TEXT NOT NULL,
  change_summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (document_id, version)
);
CREATE TABLE IF NOT EXISTS l1_requirement_comments (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES l1_requirement_documents(id) ON DELETE CASCADE,
  document_version INTEGER NOT NULL,
  parent_comment_id TEXT REFERENCES l1_requirement_comments(id) ON DELETE SET NULL,
  body TEXT NOT NULL,
  author TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','approved','resolved')),
  acted_by TEXT,
  acted_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_requirement_audit (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES l1_requirement_documents(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  document_version INTEGER NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resource_staff (
  id TEXT PRIMARY KEY,
  staff_code TEXT NOT NULL UNIQUE,
  staff_first_name TEXT NOT NULL,
  staff_last_name TEXT NOT NULL,
  staff_name TEXT NOT NULL DEFAULT '',
  staff_type TEXT NOT NULL DEFAULT 'Perm' CHECK (staff_type IN ('Perm','Contract')),
  staff_status TEXT NOT NULL DEFAULT 'Active' CHECK (staff_status IN ('Active','Inactive')),
  sub_status TEXT NOT NULL DEFAULT 'UnAllocated' CHECK (sub_status IN ('Allocated','UnAllocated','PartiallyAllocated')),
  tech_unit TEXT NOT NULL DEFAULT '',
  citizenship TEXT NOT NULL DEFAULT '',
  rank TEXT NOT NULL DEFAULT '',
  hr_role TEXT NOT NULL DEFAULT '',
  staff_start_date TEXT,
  staff_end_date TEXT,
  reporting_manager_id TEXT REFERENCES resource_staff(id) ON DELETE SET NULL,
  custom_values TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resource_lookups (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL CHECK (category IN ('tech_unit','rank','hr_role')),
  code TEXT NOT NULL,
  label TEXT NOT NULL,
  UNIQUE (category, code)
);
CREATE TABLE IF NOT EXISTS resource_custom_fields (
  id TEXT PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  field_type TEXT NOT NULL DEFAULT 'text' CHECK (field_type IN ('text','number','date','select','boolean')),
  required INTEGER NOT NULL DEFAULT 0,
  options TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_access (
  staff_id TEXT PRIMARY KEY REFERENCES resource_staff(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin','manager','contributor','viewer')),
  enabled INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_page_permissions (
  staff_id TEXT NOT NULL REFERENCES resource_staff(id) ON DELETE CASCADE,
  page_key TEXT NOT NULL,
  allowed INTEGER NOT NULL CHECK (allowed IN (0,1)),
  updated_at TEXT NOT NULL,
  PRIMARY KEY (staff_id, page_key)
);
-- l1arch strategy tables
CREATE TABLE IF NOT EXISTS l1_vision (
  l1_element_id TEXT PRIMARY KEY REFERENCES c4_elements(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  vision_statement TEXT NOT NULL DEFAULT '',
  business_problem TEXT NOT NULL DEFAULT '',
  target_users TEXT NOT NULL DEFAULT '',
  vision_statement_details TEXT NOT NULL DEFAULT '',
  business_problem_details TEXT NOT NULL DEFAULT '',
  target_users_details TEXT NOT NULL DEFAULT '',
  strategic_theme TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','baselined','archived')),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_okrs (
  id TEXT PRIMARY KEY,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  linked_element_id TEXT REFERENCES c4_elements(id) ON DELETE SET NULL,
  objective TEXT NOT NULL,
  key_result TEXT NOT NULL DEFAULT '',
  metric_name TEXT NOT NULL DEFAULT '',
  baseline_value TEXT NOT NULL DEFAULT '',
  target_value TEXT NOT NULL DEFAULT '',
  current_value TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'on_track' CHECK (status IN ('on_track','at_risk','off_track','done')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_stakeholders (
  id TEXT PRIMARY KEY,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  resource_staff_id TEXT REFERENCES resource_staff(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  department TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT '',
  stakeholder_type TEXT NOT NULL DEFAULT 'internal' CHECK (stakeholder_type IN ('internal','external','vendor','regulator')),
  influence TEXT NOT NULL DEFAULT 'medium' CHECK (influence IN ('high','medium','low')),
  interest TEXT NOT NULL DEFAULT 'medium' CHECK (interest IN ('high','medium','low')),
  raci TEXT NOT NULL DEFAULT 'Informed' CHECK (raci IN ('Responsible','Accountable','Consulted','Informed')),
  owns TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','replaced')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_capabilities (
  id TEXT PRIMARY KEY,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  parent_id TEXT REFERENCES l1_capabilities(id) ON DELETE CASCADE,
  linked_element_id TEXT REFERENCES c4_elements(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  cap_level TEXT NOT NULL DEFAULT 'L1' CHECK (cap_level IN ('L1','L2','L3')),
  business_owner TEXT NOT NULL DEFAULT '',
  technology_owner TEXT NOT NULL DEFAULT '',
  criticality TEXT NOT NULL DEFAULT 'medium' CHECK (criticality IN ('high','medium','low')),
  current_maturity INTEGER NOT NULL DEFAULT 1 CHECK (current_maturity BETWEEN 1 AND 5),
  target_maturity INTEGER NOT NULL DEFAULT 3 CHECK (target_maturity BETWEEN 1 AND 5),
  strategic_priority TEXT NOT NULL DEFAULT 'medium' CHECK (strategic_priority IN ('high','medium','low')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','planned','retired')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_risks (
  id TEXT PRIMARY KEY,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  linked_element_id TEXT REFERENCES c4_elements(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'delivery' CHECK (category IN ('delivery','architecture','security','compliance','operational','financial')),
  risk_level TEXT NOT NULL DEFAULT 'medium' CHECK (risk_level IN ('high','medium','low')),
  owner TEXT NOT NULL DEFAULT '',
  mitigation TEXT NOT NULL DEFAULT '',
  funding_source TEXT NOT NULL DEFAULT '',
  approved_budget REAL NOT NULL DEFAULT 0 CHECK (approved_budget >= 0),
  forecast_spend REAL NOT NULL DEFAULT 0 CHECK (forecast_spend >= 0),
  actual_spend REAL NOT NULL DEFAULT 0 CHECK (actual_spend >= 0),
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','active','blocked','completed')),
  target_date TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l1_approvals (
  id TEXT PRIMARY KEY,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  stage TEXT NOT NULL CHECK (stage IN ('product','architecture','security','risk','finance','sponsor')),
  ordinal INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_by TEXT, decided_at TEXT,
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (l1_element_id, stage)
);
CREATE TABLE IF NOT EXISTS l1_comments (
  id TEXT PRIMARY KEY,
  l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL DEFAULT 'baseline',
  artifact_id TEXT,
  body TEXT NOT NULL,
  author TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
  created_at TEXT NOT NULL
);
-- l2arch
CREATE TABLE IF NOT EXISTS l2_arch (
  l2_element_id TEXT PRIMARY KEY REFERENCES c4_elements(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  summary TEXT NOT NULL DEFAULT '',
  container_diagram TEXT NOT NULL DEFAULT '',
  raci TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','baselined','archived')),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l2_approvals (
  id TEXT PRIMARY KEY,
  l2_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  stage TEXT NOT NULL CHECK (stage IN ('engineering','security','nfr','data','architecture','sponsor')),
  ordinal INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_by TEXT, decided_at TEXT,
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (l2_element_id, stage)
);
CREATE TABLE IF NOT EXISTS l2_containers (
  id TEXT PRIMARY KEY,
  l2_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  capability TEXT NOT NULL DEFAULT '',
  responsibilities TEXT NOT NULL DEFAULT '',
  owns_data TEXT NOT NULL DEFAULT '',
  owner_team TEXT NOT NULL DEFAULT '',
  security_classification TEXT NOT NULL DEFAULT 'internal' CHECK (security_classification IN ('public','internal','confidential','restricted')),
  nfr_criticality TEXT NOT NULL DEFAULT 'medium' CHECK (nfr_criticality IN ('high','medium','low')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','planned','retired')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l2_apis (
  id TEXT PRIMARY KEY,
  l2_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT '',
  consumer TEXT NOT NULL DEFAULT '',
  endpoint TEXT NOT NULL DEFAULT '',
  api_type TEXT NOT NULL DEFAULT 'REST' CHECK (api_type IN ('REST','GraphQL','gRPC','Event','Batch','File')),
  data_classification TEXT NOT NULL DEFAULT 'internal' CHECK (data_classification IN ('public','internal','confidential','restricted')),
  authentication TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT 'v1',
  owner TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','active','deprecated')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l2_nfrs (
  id TEXT PRIMARY KEY,
  l2_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'performance' CHECK (category IN ('performance','security','availability','scalability','privacy','resilience')),
  scenario TEXT NOT NULL DEFAULT '',
  metric TEXT NOT NULL DEFAULT '',
  baseline TEXT NOT NULL DEFAULT '',
  target TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT '',
  risk_level TEXT NOT NULL DEFAULT 'medium' CHECK (risk_level IN ('high','medium','low')),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','met','at_risk')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l2_integrations (
  id TEXT PRIMARY KEY,
  l2_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  source_system TEXT NOT NULL DEFAULT '',
  target_system TEXT NOT NULL DEFAULT '',
  integration_type TEXT NOT NULL DEFAULT 'API' CHECK (integration_type IN ('API','Event','Batch','File','UI','Manual')),
  data_exchanged TEXT NOT NULL DEFAULT '',
  security_method TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','blocked','done')),
  created_at TEXT NOT NULL
);
-- l3arch
CREATE TABLE IF NOT EXISTS l3_arch (
  l3_element_id TEXT PRIMARY KEY REFERENCES c4_elements(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  summary TEXT NOT NULL DEFAULT '',
  component_diagram TEXT NOT NULL DEFAULT '',
  raci TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','baselined','archived')),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l3_approvals (
  id TEXT PRIMARY KEY,
  l3_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  stage TEXT NOT NULL CHECK (stage IN ('design','interfaces','security','testing','architecture','tech_lead')),
  ordinal INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_by TEXT, decided_at TEXT,
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (l3_element_id, stage)
);
CREATE TABLE IF NOT EXISTS l3_components (
  id TEXT PRIMARY KEY,
  l3_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  component_type TEXT NOT NULL DEFAULT 'service' CHECK (component_type IN ('controller','service','repository','gateway','model','client','config','ui','other')),
  responsibilities TEXT NOT NULL DEFAULT '',
  tech TEXT NOT NULL DEFAULT '',
  pattern TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','planned','retired')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l3_interfaces (
  id TEXT PRIMARY KEY,
  l3_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  direction TEXT NOT NULL DEFAULT 'provided' CHECK (direction IN ('provided','consumed')),
  interface_type TEXT NOT NULL DEFAULT 'REST' CHECK (interface_type IN ('REST','GraphQL','gRPC','Event','Function','Message')),
  contract TEXT NOT NULL DEFAULT '',
  counterpart TEXT NOT NULL DEFAULT '',
  authentication TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','active','deprecated')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l3_dependencies (
  id TEXT PRIMARY KEY,
  l3_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  dependency_type TEXT NOT NULL DEFAULT 'internal' CHECK (dependency_type IN ('internal','container','external','library')),
  target TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  criticality TEXT NOT NULL DEFAULT 'medium' CHECK (criticality IN ('high','medium','low')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','planned','retired')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l3_concerns (
  id TEXT PRIMARY KEY,
  l3_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'security' CHECK (category IN ('logging','caching','validation','security','error_handling','config','observability','resilience')),
  approach TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','implemented','gap')),
  created_at TEXT NOT NULL
);
-- l4arch
CREATE TABLE IF NOT EXISTS l4_arch (
  l4_element_id TEXT PRIMARY KEY REFERENCES c4_elements(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  summary TEXT NOT NULL DEFAULT '',
  code_diagram TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','done','archived')),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l4_code_units (
  id TEXT PRIMARY KEY,
  l4_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  unit_type TEXT NOT NULL DEFAULT 'class' CHECK (unit_type IN ('class','interface','function','module','config','migration','test')),
  responsibility TEXT NOT NULL DEFAULT '',
  tech TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  complexity TEXT NOT NULL DEFAULT 'medium' CHECK (complexity IN ('high','medium','low')),
  status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in_progress','done')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l4_test_cases (
  id TEXT PRIMARY KEY,
  l4_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  test_type TEXT NOT NULL DEFAULT 'unit' CHECK (test_type IN ('unit','integration','e2e','contract','manual')),
  scenario TEXT NOT NULL DEFAULT '',
  expected TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','passing','failing')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l4_checklist (
  id TEXT PRIMARY KEY,
  l4_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  item TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'code' CHECK (category IN ('code','tests','docs','security','review','deploy')),
  done INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
-- integrations
CREATE TABLE IF NOT EXISTS integration_configs (
  connector_key TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 0,
  settings TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT,
  updated_by TEXT NOT NULL DEFAULT ''
);
-- chat persistence
CREATE TABLE IF NOT EXISTS chat_conversations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT 'New chat',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
  text TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_attachments (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  message_id TEXT REFERENCES chat_messages(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  media_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  size_bytes INTEGER NOT NULL DEFAULT 0,
  extracted_text TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
```

Indexes: `idx_resource_staff_manager(reporting_manager_id)`, `idx_resource_lookups_category(category)`,
`idx_elements_project`, `idx_elements_parent`, `idx_relations_project`, `idx_artifacts_element`,
`idx_l1_units_element`, `idx_l1_members_unit`, `idx_l1_work_element`, `idx_l1_diagrams_element`,
`idx_l1_requirements_element`, `idx_l1_requirement_versions_doc`, `idx_l1_requirement_comments_doc`,
`idx_l1_requirement_audit_doc`, `idx_l1_comments_element`, `idx_l1_approvals_element`,
`idx_l2_approvals_element`, `idx_l2_containers_element`, `idx_l2_apis_element`, `idx_l2_nfrs_element`,
`idx_l2_integrations_element`, `idx_l3_approvals_element`, `idx_l3_components_element`,
`idx_l3_interfaces_element`, `idx_l3_dependencies_element`, `idx_l3_concerns_element`,
`idx_l4_code_units_element`, `idx_l4_test_cases_element`, `idx_l4_checklist_element`,
`idx_l1_okrs_element`, `idx_l1_stakeholders_element`, `idx_l1_capabilities_element`, `idx_l1_risks_element`,
`idx_chat_conversations_project_user(project_id,user_id,updated_at)`,
`idx_chat_messages_conversation(conversation_id,created_at)`, `idx_chat_attachments_conversation`.

---

## 7. Estimation pipeline — `backend/graph/`

### 7.1 `state.py`

`ScoreLevel = Literal["Low","Medium","High"]`. The 12 scored parameters (`PARAMETERS`, order preserved):
`complexity, volume, uncertainty, react_scope, spring_scope, existing_code_scope, dependencies, nfrs,
testing, compliance_audit, familiarity, dod_overhead`.

Node output schemas (Pydantic — the contract between prompts and state):
- `ParameterScore{parameter: Literal[<the 12>], score: ScoreLevel, reason: str (5..240)}`
- `ScorecardOutput{scores: list[ParameterScore]}`
- `DriversOutput{drivers: list[str] (2..3), explanation: str}`
- `AnchorComparisonOutput{comparison: str, anchor_titles: list[str] (min 1)}` — after-validator truncates
  `anchor_titles` to the first 3 (small models echo every anchor; keep the closest three rather than fail).
- `PointsOutput{points: Literal[1,2,3,5,8,13], derivation: str}`
- `EffortRange{optimistic, likely, pessimistic: float (ge=0)}`
- `LayerEffort{react: str, spring: str, existing_code: str, person_days: EffortRange}`
- `PlainLanguageOutput{plain_language_why: str, tldr: str, effort: LayerEffort}`
- `HiddenTask{task: str, weight: str}`; `HiddenTasksOutput{hidden_tasks: list[HiddenTask]}`
- `Risk{risk: str, mitigation_or_assumption: str}`;
  `RisksOutput{risks: list[Risk] (1..3), assumptions: list[str], spike_recommended: bool, spike_reason: str|None}`
- `SplitOutput{split_recommended: bool, rationale: str, proposed_stories: list[str] = []}`

`EstimationState(TypedDict, total=False)` keys: `story, anchors, scorecard, drivers, drivers_explanation,
anchor_comparison, anchor_titles, points, points_derivation, plain_language_why, tldr, effort, hidden_tasks,
risks, assumptions, spike_recommended, spike_reason, split_recommendation, escalation_required, refinement,
messages: Annotated[list[AnyMessage], add_messages]`.

### 7.2 `build.py`

`@lru_cache get_estimation_graph()` builds a `StateGraph(EstimationState)` with nodes:
`score_parameters → identify_drivers → compare_to_anchors → derive_points` then conditional edges via
`route_after_points` → `{"escalate": "spike_split_branch", "continue": "write_plain_language_reasoning"}`;
`spike_split_branch → write_plain_language_reasoning → detect_hidden_tasks → assess_risks → recommend_split → END`.
Compiled with `checkpointer=get_checkpointer()`. The caller's `session_id` becomes `thread_id`, which makes
refinements ("re-estimate assuming X") work against a prior run.

### 7.3 `checkpoint.py`

Process-wide registry: `set_checkpointer(saver|None)` / `get_checkpointer()` (defaults to `MemorySaver()`
lazily). The API lifespan swaps in `AsyncSqliteSaver` when `langgraph-checkpoint-sqlite` is installed.

### 7.4 `nodes.py` — prompts and helpers

System prompt (verbatim):
```
You are a senior full-stack agile estimator for a regulated bank.
The team builds React micro-frontends and Spring Boot microservices on OpenShift.
Be concrete, cautious, concise, and explain every judgment from the supplied evidence.
Never invent requirements. Use plain language and modified Fibonacci only.
```

Helpers:
- `_context(state, fields)` — `json.dumps({field: state.get(field)}, indent=2, default=str)`.
- `_parse_structured_result(schema, result)` — tolerant parser (fix structured-output bugs HERE, not in nodes):
  handles the `{"raw","parsed","parsing_error"}` include-raw envelope (prefer `parsed`, fall back to
  `raw.content`); strings: strip ```json fences then `json.loads`, else scan for the first `{` where
  `JSONDecoder.raw_decode` succeeds (models wrapping JSON in a sentence); lists: push items reversed (Groq
  returns `[echoed_schema, actual_result]` — prefer last); dicts: `schema.model_validate`, else descend into
  `text`/`content`/`output` keys. Raises `ValueError(detail[:500])` when exhausted.
- `_annotation_contract` / `_schema_contract` — render the Pydantic schema as **plain-text field
  instructions** ("Return one JSON object for `X`. Do not return the schema itself. Fields: - `name`
  (required): …") instead of an echoable JSON Schema; includes min/max length constraints from field metadata.
- `_retry_delay(error, attempt)` — parse "try again in Ns" hints (`min(n+0.5, 65)`), else `2**attempt`.
- `_invoke(schema, prompt, state, context_fields)` — builds `[SystemMessage(SYSTEM), HumanMessage(prompt +
  "\n\nReturn only one valid JSON object matching the contract exactly. The response root must be an object,
  never an array. Do not use markdown or function-call tags.\nOUTPUT CONTRACT:\n<contract>\n\nCONTEXT:\n<json>")]`;
  2 attempts; on failure sleeps `_retry_delay` then appends
  `HumanMessage("The prior output was invalid. Return only schema-valid JSON with every required field.")`;
  finally raises `RuntimeError(f"The model could not produce valid {schema.__name__} output: …")`.
- `_trace(node, summary)` — returns `[AIMessage(content=summary, name=node)]` appended to `messages`.

Node prompts (verbatim task text; each node passes the listed context fields):

| Node | Schema | Prompt | Context fields |
|---|---|---|---|
| `score_parameters` | ScorecardOutput | "Score exactly these 12 parameters once each as Low, Medium, or High, with a one-line evidence-based reason: <PARAMETERS joined>." Post-check: raise `RuntimeError(f"Scorecard omitted parameters: …")` if the returned set ≠ the 12. | story, refinement |
| `identify_drivers` | DriversOutput | "Name the 2-3 scorecard parameters that genuinely decide the estimate. Explain why they dominate." | story, scorecard |
| `compare_to_anchors` | AnchorComparisonOutput | "Compare explicitly with named fixed anchors and their points. Say bigger than, smaller than, or similar to each selected anchor and why." | story, scorecard, drivers, anchors |
| `derive_points` | PointsOutput | "Conclude 1, 2, 3, 5, 8, or 13 strictly as a consequence of the scorecard, drivers, and anchor comparison. Defend the conclusion; do not guess." Sets `escalation_required = points==13 or uncertainty score == "High"`. | story, scorecard, drivers, anchor_comparison |
| `escalation_branch` (node name `spike_split_branch`) | — | No LLM. Sets `spike_recommended=True`, `spike_reason="The estimate is 13 or uncertainty is high; reduce uncertainty before commitment."` | — |
| `write_plain_language_reasoning` | PlainLanguageOutput | "Write a 3-5 sentence 'Why this is an N' explanation for a product owner, naming drivers and an anchor in everyday terms. Also write a one-line TL;DR beginning with 'N -'. Provide React, Spring, existing-code effort and optimistic/likely/pessimistic person-days." | story, drivers, anchor_comparison, points, points_derivation |
| `detect_hidden_tasks` | HiddenTasksOutput | "Surface sub-tasks implied by the acceptance criteria but easy to miss, especially audit, entitlement, data residency, cross-market, deployment, and testing work. For each, say why it adds weight. Return none when evidence does not imply any." | story, scorecard, points |
| `assess_risks` | RisksOutput | "Give the top 3 concrete risks or unknowns and explicit assumptions. Recommend a spike when uncertainty is high. Preserve an already-triggered spike recommendation." Merges: `spike = state.spike_recommended or result.spike_recommended`; keeps prior `spike_reason` if set. | story, scorecard, points, hidden_tasks, spike_recommended |
| `recommend_split` | SplitOutput | "Recommend whether to split. A 13 must be split and must include proposed independently valuable sub-stories with suggested Fibonacci sizes in their text. Avoid splitting merely by technical layer." Forces `split_recommended=True` when points==13. | story, points, drivers, risks, spike_recommended |

`route_after_points(state)` returns `"escalate"` if `state.get("escalation_required")` else `"continue"`.

---

## 8. LLM layer — `backend/llm/`

### 8.1 `factory.py` — the ONLY module that knows provider names

```python
OPENAI_COMPATIBLE = {"moonshot","deepseek","openrouter","ollama","vllm","compatible"}
NATIVE_PROVIDERS  = {"anthropic","google_genai","openai","groq","mistral"}
OFFLINE_PROVIDERS = {"mock"}
LOCAL_PROVIDERS   = {"local","localpath"}   # in-process Transformers runtime
PATH_PROVIDERS    = {"localpath"}           # LLM_MODEL is a physical directory; strictly offline
```

- `validate_factory_config()` — unsupported provider error; `LLM_BASE_URL` required for OPENAI_COMPATIBLE;
  `LLM_API_KEY` required unless provider ∈ OFFLINE|LOCAL; for `localpath`, `LLM_MODEL` must be an existing
  directory. Raises `ConfigurationError`.
- `LLMInvocationError(message, retryable=True)` is the stable hosted-provider failure contract.
  `_invocation_error` extracts HTTP status/detail without leaking SDK exception types; retryable is True for
  no-status failures, 408/409/425/429 and 5xx. `main.py` maps it to HTTP 502 `llm_provider_error` and the chat
  SSE route emits the same code/retryability rather than an unhandled 500.
- `@lru_cache get_llm()` — mock → `FakeListChatModel(responses=["Mock mode is active; …"])`;
  local/localpath → `LocalHuggingFaceChatModel(...)` (with `local_files_only` forced True for `localpath`);
  OPENAI_COMPATIBLE → `ChatOpenAI(model, temperature, max_tokens, api_key, max_retries=1, base_url)`;
  else `init_chat_model(model_provider=provider, **common)`.
- `get_structured_llm(schema)` — mock → `MockStructuredLLM(schema)`; local → a `RunnableLambda` that
  prepends `SystemMessage("Return only one valid JSON object matching this JSON Schema. No markdown or
  commentary.\n<compact schema json>")` and returns `{"raw": raw, "parsed": None, "parsing_error": None}`;
  groq → `_hosted_structured_runnable(..., json_mode=True)`; else the same helper without json_mode. The
  helper normalizes setup/invocation failures and prepends a system message explicitly requesting one JSON
  object for Groq (Groq rejects `response_format=json_object` when no message says JSON).
- `preload_llm()` — no-op unless provider is local and `local_preload`; then `start_background_load(get_llm())`.
- `llm_runtime_status()` — `{"status":"ready"}` for non-local; else `local.runtime_status()`.
- `prefers_text_routing()` — True for LOCAL_PROVIDERS (small local models are unreliable emitters of the big
  ChatCommand schema, so chat routing goes deterministic).

### 8.2 `local.py` — in-process Hugging Face runtime

`LocalHuggingFaceChatModel(BaseChatModel)` fields: `model_name, token (repr=False), temperature=0.2,
max_new_tokens=3000, device="auto", dtype="auto", revision="main", cache_dir, context_window=8192,
trust_remote_code=False, local_files_only=False`. `_llm_type="local-huggingface"`.

Key behaviors to reproduce:
- Module-level `_load_lock` + `_load_state` dict (`status: not_started|loading|ready|error`, `started_at`,
  `loaded_at`, `error`). `start_background_load(model)` runs one daemon thread ("karya-local-llm-loader")
  that builds `_runtime_cached(...)` (an `@lru_cache(maxsize=2)` around `_TransformersRuntime`), calls
  best-effort `warmup()` (1 token generation), and updates the state; logs via `logging.getLogger("uvicorn.error")`.
- `_runtime(...)` raises `LocalModelLoadingError` while loading / when kicking off a lazy load, and
  `RuntimeError` when the load failed; returns the cached runtime when ready.
- `_TransformersRuntime.__init__`: import torch/transformers (actionable ImportError → "install
  requirements-local.txt"); `_reject_unsupported_model_dir` fails fast on a GGUF folder (message points to
  LLM_PROVIDER=compatible + LM Studio/Ollama) or a folder without `config.json`; enable transformers progress
  bars; `AutoTokenizer.from_pretrained` with fast→slow fallback (slow-failure message mentions
  sentencepiece/tiktoken extras); resolve device (auto→cuda→mps→cpu; explicit cuda/mps validated available)
  and dtype (auto→fp16 on cuda/mps else fp32); `AutoModelForCausalLM.from_pretrained(torch_dtype=…,
  low_cpu_mem_usage=True, device_map="auto"` when device auto`)`; `.eval()`; remember `input_device`.
- `generate(messages, *, temperature, max_new_tokens, context_window, stop)`: under an instance lock +
  `torch.inference_mode()`, `tokenizer.apply_chat_template(..., add_generation_prompt=True,
  return_tensors="pt", return_dict=True)`, truncate ids/attention to the last `context_window` tokens,
  `do_sample = temperature > 0`, pad = pad or eos token, decode only the new tokens, apply stop markers
  (split at first occurrence), strip.
- `_normalize_messages`: convert to `{role, content}` (human→user, ai→assistant), flatten list content;
  merge ALL leading system messages into one (Gemma templates reject consecutive system messages), then merge
  any adjacent equal roles by concatenating with a blank line.
- `_generate` wraps runtime errors as `LocalModelInferenceError("Local model inference failed. Check /health
  and the API log …")`, letting `LocalModelLoadingError` propagate.
- `runtime_status()` returns `{status, load_seconds (rounded 1dp), error}`.

### 8.3 `mock.py` — deterministic offline LLM (LLM_PROVIDER=mock)

`class MockStructuredLLM` — `__init__(schema)`; `async ainvoke(messages)` sleeps 0.15s (lets the streaming
pipeline view animate), then dispatches:
- `DiagramAIOutput` → `_build_diagram_ai(messages)`
- schema name ∈ `_AGENTIC_SCHEMAS = {StaffingProposal, NarrativeOutput, StoryDecomposition, C4Scaffold,
  L1BaselineDraft, OrchestratorPlan, FieldSummary, L2Draft, L3Draft, L4Draft, ChatCommand}` → `_build_agentic`
- else `_build(schema, _title(messages))`.

**Estimation builders (`_build`)** — determinism source:
- `_seed(text) = zlib.crc32(utf8)`; `FIBONACCI=[2,3,5,8,13]`; `LEVELS=["Low","Medium","High"]`
- `_title(messages)`: regex `"title":\s*"([^"]+)"` over joined message contents, default "the story".
- `_points(title) = FIBONACCI[_seed(title) % 5]`; `_score(title,param) = LEVELS[_seed(f"{title}:{param}") % 3]`.
- ScorecardOutput: one `ParameterScore` per parameter, reason `"Mock assessment of <param> from the supplied evidence."`
- DriversOutput: first two of `sorted(PARAMETERS, key=seed(title:param))`, explanation "Mock mode: X and Y dominate…".
- AnchorComparisonOutput: uses first two anchor titles; "…judged bigger/similar or smaller…" (bigger when points>=8).
- PointsOutput: "Mock derivation: hashed scope of '<title>' maps to N on the modified Fibonacci scale."
- PlainLanguageOutput: fixed sentences; tldr `"{points} - Mock estimate: scope and dependencies decide it."`;
  effort person_days = (points*0.5, points, points*1.6).
- HiddenTasksOutput: audit-logging (medium) + regression-tests (small) mock tasks.
- RisksOutput: spike when points>=8; two fixed risks; assumption "Mock mode is active; no real analysis was performed."
- SplitOutput: split only when points==13, proposed `["<title> — happy path (5)", "<title> — edge cases and audit (5)"]`.

**Diagram builder (`_build_diagram_ai`)**: parses `DIAGRAM TYPE:`, `INSTRUCTION:` (first line), and
`CURRENT DIAGRAM:` (```mermaid fenced) out of the joined messages. Rules: existing non-flowchart diagram →
returned unchanged ("kept the current non-flowchart diagram for text editing"); existing flowchart → append a
node named after the first keyword of the instruction and connect it to the first anchor node found by regex;
`sequence` type → canned sequenceDiagram (User/Web/API estimate flow); type in `_MOCK_DIAGRAMS` (canned
snippets for architecture_beta, block, packet, class, state, er, requirement, c4, gantt, journey, timeline,
mindmap, quadrant, gitgraph, pie, xychart, sankey, treemap, venn) → that snippet; `kanban` and `radar` have
their own canned bodies; else a `flowchart LR` chaining up to 5 keywords. Keyword extraction `_keywords`:
regex words, drop `_STOPWORDS` (the, a, an, and, or, of, for, to, with, that, this, add, create, new,
diagram, show, make, into, from, using, please, our, then, when, flow, between, should, which, node, connect,
change, update, modify) and words <3 chars, capitalize first letter, dedupe, cap at limit, fallback
`["System","Service","Data"]`. `_node_id(label,i)` strips non-alphanumerics (14 chars max) + index.

**Agentic builders (`_build_agentic`)** — parse the **human** message only (labels also appear in system
prompts). `_json_after(text, label)` extracts the bracket-balanced JSON array/object after a label.
- `StaffingProposal`: reads `RESOURCE POOL` and `SQUADS:` JSON; round-robins people onto squads with
  `allocation = min(remaining_percent, 50)`, skipping ≤0; reason string mentions free % and squad fit.
- `NarrativeOutput`: reads `METRICS:` JSON; headline `"{projects} platforms · {estimated_pct}% estimated"`;
  fixed summary/highlights/risks/recommendations from portfolio + resources numbers.
- `StoryDecomposition`: element name from `ELEMENT ([^)]*):`; 4 seeded slices (Happy path/core flow,
  Validation & errors/edge cases, Persistence & audit/data and traceability, Tests & observability/quality gates).
- `C4Scaffold`: keywords from `DESCRIPTION:`; emits refs sys(L1 system) / web,svc,db(L2 React, Spring Boot,
  PostgreSQL) / cmp1,cmp2(L3 modules under svc) + relations web→svc "calls" sync, svc→db "reads/writes" data.
- `L1BaselineDraft`: name from `L1 INITIATIVE:`; canned vision/problem/users, 2 OKRs, 4 stakeholders
  (Business Sponsor/Accountable, Product Owner/Responsible, Enterprise Architect/Consulted, Security
  Architect/Consulted), 3 capabilities (Customer Experience, Core Processing, Data & Analytics), 2 risks.
- `FieldSummary`: text after `DETAIL NOTES:` up to `\n\nSummarize`; strips markdown; first sentence,
  ≤200 chars, appends " (mock summary)".
- `L2Draft` / `L3Draft` / `L4Draft`: names parsed from `L2 EPIC/CONTAINER SLICE:` / `L3 COMPONENT/STORY:` /
  `L4 TASK:`; canned flowchart/classDiagram + containers/APIs/NFRs/integrations, components/interfaces/
  dependencies/concerns, code units/test cases/5-item DoD checklist respectively (see mock.py for exact
  canned rows — reproduce the same names/categories for test stability).
- `ChatCommand`: a real deterministic keyword parser (used by tests and mock mode). Parses out of the prompt:
  `USER MESSAGE:` (up to `\n\nInterpret`), `REQUEST MODE:` (chat|code|research|image|document → forces
  actions answer/code/web_search/image/document), `CURRENT SCREEN:` (`level=Lx`, `element=…`), and element
  names anchored to lines `- L[1-4] · <name> (` (sorted longest-first). Rules in order: `rename X to Y` →
  update_element(new_name); "status … to <word>" → update_element(status); delete/remove → delete_element;
  `match_relation` (both endpoints known) → create_relation; `parse_create` → create_element; route/connect/
  link/wire X to/through/via/with Y → create_relation(label "routes"); `classify_read` → overview/list/
  readiness/report (with `list_status_filter`); help → help; search/browse/internet/web/latest → web_search;
  code/function/class/component/script/implement/generate → code (mock disclaimer reply). Follow-up handling:
  if nothing parsed and message ≤60 chars, retry the last user turn containing create/add/new/rename with
  `"… called <msg>"`. Fallback: `answer` with the "Mock mode is active…" reply.
- `OrchestratorPlan`: keyword table (auto_staffing: staff/assign/squad/team/allocat; scaffold_c4: c4/context
  diagram/scaffold/architecture model; decompose_story: decompose/break/split/stories/story;
  generate_l1_baseline: vision/okr/baseline/stakeholder/capabilit/risk; reporting_narrative:
  report/summary/executive/portfolio; review_readiness: ready/readiness/complete/govern) — first match wins,
  else action "none"; `suggested_prompt = text[:200]`.

---

## 9. API app — `backend/api/`

### 9.1 `main.py`

- `error_response(code, message, status, details=None, retryable=False)` → JSONResponse of `ErrorPayload`.
- Lifespan: `init_db()`; `AsyncExitStack`; `_install_durable_checkpointer` (import
  `langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver`, subclass `JsonSafeMetadataSaver` whose `aput` does
  `json.loads(json.dumps(metadata, default=str))` — stdlib json crashes on LangChain message objects in
  metadata; checkpoint blob uses the real serializer so this is lossless), then `set_checkpointer(saver)` +
  `get_estimation_graph.cache_clear()`; then `validate_startup()` + `validate_factory_config()` with errors
  stashed in `app.state.configuration_errors` (startup config errors NEVER crash the app; `/health` reports
  them and estimation routes 503 via `require_llm_config`); on success `preload_llm()`.
- `FastAPI(title="Karya API", version="2.0.0", lifespan=lifespan)`.
- **RBAC middleware** (`@app.middleware("http")`): skip OPTIONS; `route_policy(method, path)` →
  `(requires_auth, capability)`; if auth required: `resolve_role(request)` (None → 401 "Sign in required."),
  capability check via `can(role, capability)` (fail → 403 "Your role does not permit this action (<cap>)."),
  then `restricted_block(path, role)` (fail → 403 "This workspace is restricted to managers and admins.").
- CORS: configured origins, credentials, methods GET/POST/PATCH/DELETE/OPTIONS, all headers,
  `expose_headers=["Content-Disposition"]`.
- Routers mounted: projects, c4, planning, resources, access, reporting, ai, l1arch, l2arch, l3arch, l4arch,
  workflow, chat, integrations.
- Exception handlers: RequestValidationError → 422 `validation_error` ("The request contains invalid
  fields.") with `exc.errors()` details; HTTPException → uses `detail` dict `{code, message, details}` else
  wraps string; JiraError → 502 if status None/>=500 else 400, code `jira_error`, `retryable=exc.retryable`;
  UploadError → 400 `parse_error`.
- Routes:
  - `GET /health` → `{status: "degraded"|"ok", llm: {status: "configuration_error", errors} |
    {**llm_runtime_status(), errors: []}, jira: await registry.health()}`
  - `GET /config` → `{llm: {provider, model}, jira_instances, jira_write_enabled}`
  - `GET /jira/instances`
  - `GET /jira/{instance}/project/{code}/issues?status&sprint&page_size(1..100,50)&max_issues(1..1000,500)`
  - `POST /upload/parse` (multipart file; >15MB → UploadError "File exceeds the 15 MB upload limit") →
    `dataframe_payload(read_upload(content, filename))`
  - `GET /upload/template` → xlsx bytes, `Content-Disposition: attachment; filename="karya-template.xlsx"`
  - `POST /estimate` → SSE `stream_story(story, session, refinement)`; session = payload.session_id or uuid4
  - `POST /estimate/batch` → SSE `stream_batch(stories, session)`
  - `POST /upload/estimate` → `rows_to_stories(rows, mapping)`; empty → UploadError "No valid rows remain
    after mapping"; SSE `stream_batch(stories, session, skipped)`
  - `POST /jira/{instance}/{issue_key}/points` — gates: `jira_write_enabled` else 403 `write_disabled`;
    `payload.confirm` else 400 `confirmation_required`; then `write_points`; returns
    `{status:"updated", issue_key, points}`.

### 9.2 `streaming.py` (separate module so the C4 router can import without circular imports)

- `require_llm_config(request)` — raises 503 `configuration_error` "LLM configuration is incomplete." when
  `app.state.configuration_errors` is non-empty.
- `sse(event, data)` → `f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()`.
- `public_result(values)` — strips `{anchors, messages, escalation_required, refinement}` from state.
- `stream_story(story, session_id, refinement=None, on_result=None)` (async generator of bytes):
  emits `started {session_id, title}`; initial state `{story: story.model_dump(), anchors: ANCHORS,
  refinement, messages: [HumanMessage(refinement or f"Estimate: {title}")]}`; iterates
  `graph.astream(initial, config={"configurable": {"thread_id": session_id}}, stream_mode="updates")`
  emitting `node {node, status:"completed"}` per update (progress-only); then `aget_state` snapshot →
  `public_result`; **raises if `plain_language_why` or `tldr` missing** ("The model returned points without
  the required explanation" — a point value must never appear without its explanation); awaits `on_result(result)`
  callback if given; emits atomic `result`. Exceptions → `error {code:"estimation_error", message, retryable:true}`.
- `stream_batch(stories, root_session, skipped=None)`: emits `batch_started {count, session_id, skipped}`;
  per story with `item_session = f"{root}:{index}"`: `item_started {index,title}` then re-emits inner events
  as `item_node` / `item_result` / `item_error` (parses the inner SSE text); finally
  `batch_result {results, skipped}`.

---

## 10. Auth — `backend/auth/`

### 10.1 `permissions.py` (kept in sync with `frontend/src/auth/permissions.js`)

```python
ROLE_CAPS = {
  "admin": ["*"],
  "manager": ["admin", "admin.reporting", "admin.resources", "page.platforms", "page.workspace",
              "page.ask_ai", "page.guide", "platform.create", "platform.edit"],
  "contributor": ["page.platforms", "page.workspace", "page.ask_ai", "page.guide",
                  "platform.create", "platform.edit"],
  "viewer": ["page.platforms", "page.workspace", "page.ask_ai", "page.guide"],
}
def can(role, capability): caps = ROLE_CAPS.get(role or "", []); return "*" in caps or capability in caps
```

### 10.2 `deps.py`

- `PUBLIC_PATHS = {"/health","/config","/access/login-users","/access/roles","/jira/instances","/docs","/openapi.json"}`
- ABAC: `_RESTRICTED_ROLES = {"admin","manager"}`; `_PROJECT_PATH = re.compile(r"^/projects/([0-9a-f]+)")`;
  `restricted_block(path, role)` → True when role not in restricted set AND the path's project has
  `sensitivity='restricted'` (SQL lookup).
- `resolve_role(request)` — `X-User-Id` header → `effective_role(staff_id)` (authoritative DB lookup);
  else `X-User-Role` header accepted only if it is a known role (bootstrap admin without directory id).
- `capability_allowed(request, role, capability)` — admin always True; otherwise consult
  `app_page_permissions` via `page_permission_override(X-User-Id, capability)` first, then fall back to the
  role map. This is the authoritative counterpart of the frontend's effective page-permission map.
- `route_policy(method, path) -> (requires_auth, capability|string-tuple|None)`:
  public paths → unauthenticated; `/access/me` → authenticated self; other `/access*` → `admin.access`;
  `/reporting*` → `admin.reporting`; integration catalog → signed-in, connector config →
  `admin.integrations`; resource reads → signed-in and resource writes/imports → `admin.resources`;
  `/ai/*` → `page.ask_ai`; `GET /projects` → `page.platforms`; project creation →
  (`page.platforms`, `platform.create`); project chat reads/proposals → `page.workspace`; project writes
  including chat apply → (`page.workspace`, `platform.edit`); other project reads → `page.workspace`.
  Tuple requirements mean **all** capabilities must pass.

---

## 11. Access management — `backend/access/`

- `models.py`: `Role = Literal["admin","manager","contributor","viewer"]`; `ROLES` tuple in that order;
  `DEFAULT_ROLE = "viewer"`; `AccessUpdate{role?, enabled?}`; `AccessCreate{staff_id, role=viewer,
  enabled=True}`; `PagePermissionsUpdate{permissions: dict[str,bool|None]}` where null removes an override.
- `pages.py`: the canonical page registry (`PAGE_DEFINITIONS`, `PAGE_KEYS`, `CAPABILITY_TO_PAGE`):
  `platforms→page.platforms`, `workspace→page.workspace`, `ask_ai→page.ask_ai`, `guide→page.guide`,
  `admin_access→admin.access`, `admin_reporting→admin.reporting`, `admin_resources→admin.resources`,
  `admin_integrations→admin.integrations`. Each definition includes its UI label and description.
- `store.py`:
  - `_bootstrap_admin(conn)` — if no enabled admin exists, promote the earliest-created staff. Admin page
    overrides are deleted because administrators are the break-glass identity and cannot be denied a page.
  - `_permission_overrides` reads explicit decisions; `_permission_bundle` returns both effective page
    decisions and overrides, using role defaults unless an override exists.
  - `list_users(enabled_only=False)` — all staff LEFT JOIN access, ordered by name; every returned user has
    `role`, boolean `enabled`, `page_permissions` (effective) and `page_permission_overrides` (explicit).
    `enabled_only` also requires `staff_status == "Active"`.
  - `set_access` upserts while preserving omitted fields and clears overrides on promotion to admin;
    `get_user`; `effective_role` (None when unknown/disabled); `page_permission_override(staff_id,
    capability)`; `role_counts`.
  - `set_page_permissions(staff_id, permissions)` rejects unknown keys, rejects any override for an admin,
    deletes rows for null values, and upserts boolean choices in `app_page_permissions`.
- `router.py` (prefix `/access`): `GET /roles`, `GET /users`, `GET /pages`, authenticated `GET /me`, public
  `GET /login-users`, `PATCH /users/{staff_id}`, and `PATCH /users/{staff_id}/page-permissions`.

---

## 12. Projects — `backend/projects/`

- `models.py`: `Lead{name (1..120), role ("" ..120)}`; `ProjectCreate{name (1..200), description="",
  leads: list[Lead] (max 20), sensitivity: Literal["standard","restricted"]="standard"}`; `ProjectUpdate`
  (all optional); `RepoLinkCreate{url="", local_path="", provider="git", mode: Literal["existing","new"]
  ="existing", default_branch="main"}`; `JiraLinkCreate{instance_name (min 1), project_key (1..50)}`.
- `store.py`: leads stored as JSON string, hydrated to list on read (`_hydrate_project` tolerates bad JSON).
  `list_projects()` orders `created_at DESC` and computes per-project `story_count` (# L3 elements) and
  `estimated_count` (# L3 with an artifact_links row having points NOT NULL) via one SQL per project, plus
  `repos` and `jira` link lists. `add_jira_link` lower-cases instance_name. `NotFoundError(LookupError)`.
- `router.py` (prefix `/projects`): `POST ""`, `GET ""`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`
  (→ `{"status":"deleted"}`), `POST /{id}/repos`, `POST /{id}/jira`. NotFoundError → 404 `not_found`.

---

## 13. C4 model — `backend/c4/`

### 13.1 `models.py`

- `LEVELS = ["L1","L2","L3","L4"]`; `ARTIFACT_FOR_LEVEL = {L1: initiative, L2: epic, L3: story, L4: task}`;
  `CROSS_CUTTING_LEVELS = {bug: {L3,L4}, tech_debt: {L2,L3}, arch_flow: {L2,L3}}`.
- `C4ElementCreate{level, name (1..200), kind="", description="", parent_id=None, tech="", code_path="",
  status="active", pos_x/pos_y: float|None}`; `C4ElementUpdate` (all optional);
  `C4RelationCreate{source_id, target_id, label="", kind: Literal["sync","async","data"]="sync"}`;
  `ArtifactTagRequest{artifact_type: Literal["bug","tech_debt","arch_flow"], jira_issue_key?}`;
  `ElementEstimateRequest{refinement?, session_id?}`; `JiraArtifactRequest{confirm=False, link_existing_key?}`;
  `JiraImportRequest{instance_name?, project_key?, status?, max_issues=100 (1..500)}`;
  `RepoScanRequest{local_path?, apply=False}`.

### 13.2 `store.py`

- `C4ValidationError(ValueError)`. `_check_parent`: parent must exist in the same project AND be exactly one
  level up (`LEVELS.index(parent.level) == LEVELS.index(level) - 1`), messages:
  "parent_id does not reference an element in this project" / "A {level} element's parent must be one level up (Lx)".
- `create_element` / `get_element` (includes its `artifacts` list) / `update_element` (re-checks parent when
  changed; only non-None fields updated) / `delete_element` (404 style NotFoundError when rowcount 0).
- `list_graph(project_id)` → `{elements: [... each with artifacts[]], relations: [...]}` ordered by created_at.
- `create_relation` (both endpoints must be project elements) / `delete_relation`.
- `upsert_artifact(element_id, artifact_type, *, jira_issue_key, points, spike_recommended,
  split_recommended, estimate_session_id)` — insert or field-wise update; sets `estimated_at=utc_now()`
  whenever points is provided.
- `tag_cross_cutting` — level must be in `CROSS_CUTTING_LEVELS[type]` else C4ValidationError
  ("A {type} artifact tags L2 or L3 elements only").
- `default_artifact_type(level)`; `find_child_by_name(project_id, parent_id|None, name)`.

### 13.3 `service.py`

- `element_to_story(project_id, element) -> Story` — title=name, user_story=description,
  technical_breakdown=tech or None, components=[parent-chain names], source="manual", and `c4_context =
  {level, kind, artifact_type, parent_chain: [{level,name,description}…], relations: [{label,kind,source,target}…],
  code_path, repositories: [repo url or local_path, non-empty]}`. Parent chain walks `parent_id` upward
  (root first). Relations = all relations touching the element (joined to names).
- `persist_estimate(project_id, element, session_id, result)` — upserts the level's artifact with points /
  spike_recommended / split_recommended / session id. **If element is L3**: for each `hidden_tasks[]` creates
  a **proposed L4 child** (kind "task", name = task text[:200], description "Hidden work detected during
  estimation (weight: X)."), skipping existing names; if split recommended, creates **proposed L3 siblings**
  (kind "component", description "Proposed by the split recommendation of a 13-point estimate.") under the
  same parent, skipping existing names.
- `rollup(project_id)` — deterministic recursive sum (never LLM). Per node summary keys:
  `estimated_stories, unestimated_stories, rolled_up_points, spikes, pending_splits` — child sums, plus for
  L3 elements their own artifact contribution (`unestimated` counts only non-`proposed` L3s without points).
  Node shape `{element: {id,level,kind,name,status,code_path}, artifact, summary, children}`. Returns
  `{tree: roots(parent_id None), totals}`.
- `apply_scan(project_id, proposal)` — creates proposed L1 system / L2 containers / L3 components from a scan
  proposal, skipping existing names; returns `{created: n}`.
- `scan_project_repo(project_id, local_path|None)` — path from arg or first repo link with local_path, else
  `FileNotFoundError("No local repo path is linked to this project; pass local_path explicitly")`.
- `import_jira_stories(project_id, stories, container_name="Imported from Jira")` — ensures a holding L2
  container (proposed, under the first L1 if any; description "Holding container for issues imported from
  Jira; re-parent them onto real containers."), creates proposed L3 elements per story (skip duplicates by
  name), linking `jira_issue_key` on the story artifact but NEVER copying existing points (a rolled-up point
  always needs a justified estimate). Returns `{created, container_id}`.

### 13.4 `scan.py` — deterministic repo scan

`SKIP_DIRS = {.git,.hg,.svn,node_modules,venv,.venv,__pycache__,dist,build,target,.idea,.vscode,coverage,
.pytest_cache,data,docs}`; `TECH_BY_EXTENSION = {.py: Python, .java: Java, .kt: Kotlin, .js: JavaScript,
.jsx: React, .ts: TypeScript, .tsx: React, .go: Go, .cs: C#, .sql: SQL}`.
`scan_repo(local_path, project_name)` — proposes `{system: {name=project_name, L1, kind system},
containers: [top-level dirs containing code (recursive extension scan to depth 3), each with tech label
(joined sorted unique tech names) + code_path + components: [their code subdirs likewise]]}`. Raises
FileNotFoundError when path isn't a directory. Paths use forward slashes.

### 13.5 `router.py` (prefix `/projects/{project_id}`)

`_run` maps NotFoundError→404 `not_found`, C4ValidationError→400 `c4_validation`, FileNotFoundError→400 `scan_error`.

- `GET /c4/graph`; `POST /c4/elements`; `GET|PATCH|DELETE /c4/elements/{id}`; `POST /c4/relations`;
  `DELETE /c4/relations/{id}`; `POST /c4/elements/{id}/tag` (cross-cutting artifacts).
- `GET /rollup`.
- `POST /c4/import/repo-scan` — scan; when `apply` also `apply_scan`; returns `{proposal, applied[, created]}`.
- `POST /c4/import/jira` — instance/key from payload or the project's first jira link; missing → 400
  `jira_link_missing`; fetches issues then `import_jira_stories`.
- `POST /elements/{id}/estimate` — `require_llm_config`; **only L3/L4** (else 400 `not_estimable`,
  "Lx elements aggregate child estimates; estimate the L3 stories beneath them."); session = payload.session_id
  or (stored artifact estimate_session_id when refining) or `f"c4-{element_id}-{uuid4.hex[:8]}"`; streams
  `stream_story(element_to_story(...), session, refinement, on_result=persist_estimate)`.
- `POST /elements/{id}/artifact` — link existing Jira key (`{status:"linked", artifact}`) OR create a Jira
  issue (triple-gated: `jira_write_enabled` else 403; `confirm` else 400; project jira link else 400).
  Issue type map: initiative→Epic, epic→Epic, story→Story, task→Task. Returns `{status:"created", issue_key, artifact}`.

---

## 14. Spreadsheet ingest — `backend/ingest/excel.py`

- `TARGET_ALIASES` (fuzzy header matching):
  - title: title, summary, story title, issue, name
  - user_story: user story, description, story, details, requirement
  - acceptance_criteria: acceptance criteria, acs, ac, criteria, conditions of satisfaction
  - technical_breakdown: technical breakdown, technical notes, implementation, dev notes
  - existing_points: existing points, story points, points, sp, estimate
- `UploadError(ValueError)`.
- `_score(header, alias)` — normalize header (`[^a-z0-9]+` to space, lower, strip): exact = 1.0; substring
  either way = 0.9; else `SequenceMatcher.ratio()`.
- `suggest_mapping(columns)` — per target, best (score, column) among unused columns; accept if score >= 0.55
  else None; a chosen column can't be reused. Title is the only required mapping (enforced later).
- `read_upload(content, filename)` — by suffix: `.csv` -> `pd.read_csv(dtype=object).fillna("")`;
  `.xlsx` (engine openpyxl) / `.xls` (engine xlrd) -> `pd.read_excel`; parse failure ->
  UploadError `"Could not parse {filename}: {exc}"`; other suffix -> "Use a .csv, .xlsx, or .xls file".
- `dataframe_payload(frame, preview_rows=20)` -> `{columns, suggested_mapping, preview (first 20), rows
  (all, None->""), row_count}` (rows via `frame.to_json(orient="records", date_format="iso")`).
- `rows_to_stories(rows, mapping) -> (stories, skipped)` — requires mapping["title"] else UploadError
  "Map a source column to Title before estimating"; enumerates from row 2 (spreadsheet numbering); blank
  title -> skipped `{row, reason: "Title is blank"}`; existing_points parsed as float, non-numeric -> None;
  builds `Story(source="upload")` (acceptance_criteria goes through the Story validator that splits on ;/newlines).
- `template_workbook()` — one sample row (Title "Add beneficiary confirmation", User Story "As a customer, I
  want to confirm beneficiary details before payment.", AC "Show beneficiary name\nRecord confirmation in
  audit trail", Technical Breakdown "React confirmation panel; Spring audit event", Existing Points ""),
  sheet "Stories", freeze panes A2, bold header, column widths A:34 B:60 C:60 D:50 E:18. Returns xlsx bytes.

---

## 15. Jira — `backend/jira/`

### 15.1 `registry.py`
`JiraRegistry(configs)`: `list_instances()` -> `[{name, auth_type}]`; `get_client(name)` — unknown instance ->
`JiraError("Unknown Jira instance 'X'")`; validates BASE_URL/API_TOKEN present (+EMAIL for cloud) ->
`JiraError("Jira instance 'X' is missing: <fields>")`; caches one `JiraClient` per instance. `health()` ->
per-instance client health, JiraError -> `{status:"error", message, retryable:false}`. `@lru_cache get_jira_registry()`.

### 15.2 `client.py`
`JiraError(RuntimeError)` with `status: int|None`, `retryable: bool`.
`JiraClient(config)`:
- Cloud -> REST **v3**, `httpx.BasicAuth(email, token)`; Server/DC -> REST **v2**, `Authorization: Bearer <token>`.
- `_request(method, path, **kwargs)` — url `f"{base_url}/rest/api/{v}/{path}"`; 2 attempts; timeout 30;
  status >=400 -> JiraError `"Jira returned {code}: {detail}"` (detail JSON if content-type json else text),
  retryable for {429,502,503,504} (one silent retry first); network/timeout -> retry once then
  `JiraError("Could not reach Jira: ...", retryable=True)`; empty body -> `{}`.
- `health()` — GET `myself` -> `{status:"ok", message:"Connected"}` or error dict.
- `fetch_project_issues(project_code, *, status, sprint, page_size=50, max_issues=500)` — project code must
  match `[A-Za-z][A-Za-z0-9_-]{0,49}` else JiraError "Project code contains invalid characters"; JQL
  `project = "X" [AND status = "..."] [AND sprint = "..."] ORDER BY created DESC` (double quotes in filter
  values are backslash-escaped); fields: summary, description, status, labels, components + configured
  story_points_field/ac_field. Pagination: cloud uses `GET search/jql` + `nextPageToken` (stop on
  isLast/no token/no issues); server uses `GET search` + `startAt`/`total`. Maps each issue via `issue_to_story`.
- `create_issue(project_key, issue_type, summary, description="")` — summary[:255]; description for cloud is
  wrapped in Atlassian Document Format (`{type:"doc",version:1,content:[{type:"paragraph",content:[{type:"text",text}]}]}`),
  plain string for server; POST `issue`; missing key in response -> JiraError "Jira accepted the issue but returned no key".
- `write_points(issue_key, points)` — requires `story_points_field` configured else JiraError "Story Points
  field is not configured for this Jira instance"; PUT `issue/{key}` `{fields: {field: points}}`.

### 15.3 `mapping.py`
- `adf_to_text(value)` — flatten Atlassian Document Format (recursive dict/list walk collecting `text` +
  `content`, newline-joined), pass through strings, str() fallback.
- `split_acceptance_criteria(value, description)` — text from the AC field; if empty, regex the description
  for `(?:acceptance criteria|given\s.+?when\s.+?then)\s*:?\s*(.+)` (IGNORECASE|DOTALL); split on
  newlines/semicolons, strip list markers (`^[\s*\-\d.)]+`).
- `issue_to_story(issue, config) -> Story` — title = summary or key or "Untitled Jira issue";
  user_story = adf description; acceptance_criteria via splitter; existing_points from configured field;
  key, status.name, labels, component names; `source="jira"`, `jira_instance=config.name`.

---

## 16. L1 operating plans — `backend/planning/`

### 16.1 `models.py`
- `DIAGRAM_TYPES` / `DiagramType` Literal — the same 24 types as the DB CHECK (see section 6).
- `AgileUnitCreate{unit_type: Literal["tribe","squad"], name (1..160), parent_unit_id?, mission (..1200),
  lead_name (..160), capacity_fte (0..10000), target_velocity (0..100000)}`; `AgileUnitUpdate` all optional.
- `PlanSettingsUpdate{currency_code: pattern ^[A-Z]{3}$}`.
- `TeamMemberCreate{name (1..160), resource_staff_id? (link to global directory), role (..160),
  skills (..1000), location (..160), allocation_percent (0..100, default 100), monthly_cost (0..1e8)}`;
  `TeamMemberUpdate` all optional.
- `WorkItemCreate{title (1..240), description (..2400), squad_id?, linked_element_id?, start_date: date,
  end_date: date, status: planned|in_progress|at_risk|done = planned, allocation_percent (0..100),
  budget_cost (0..1e10), actual_cost (0..1e10)}` + model_validator `end_date >= start_date`
  ("end_date must be on or after start_date"); `WorkItemUpdate` all optional.
- `DiagramCreate{diagram_type, title (1..200), mermaid_source (1..50000), metadata: dict = {}}` — metadata is
  free-form JSON keyed by mermaid node id (per-node annotations: explanation, custom properties, links,
  documents; the frontend owns its shape); `DiagramUpdate` all optional.
- `DiagramChatTurn{role: user|assistant, content (1..4000)}`;
  `DiagramGenerateRequest{prompt (1..4000), diagram_type="architecture", title? (..200)}`;
  `DiagramAssistRequest{prompt, current_source (..50000)="", diagram_type="architecture",
  history: list[DiagramChatTurn] (..20)}`; `DiagramAIOutput{mermaid (min 1), message=""}`.
- Requirements: `RequirementDocumentCreate{title (1..240), content (..500000)="", actor (1..160)}`;
  `RequirementDocumentUpdate{title, content, actor, change_summary (..500)="", expected_version (ge 1)}`;
  `RequirementCommentCreate{body (1..10000), actor, parent_comment_id?}`;
  `RequirementCommentAction{action: approve|resolve|reopen, actor}`;
  `RequirementReviewAction{action: submit|approve|revoke, actor, note (..2000)=""}`;
  `RequirementExportRequest{diagram_images: list[str] (..50)}` + validator: total image chars <= 28,000,000
  ("Rendered diagram images must not exceed 28 MB in total").

### 16.2 `store.py` — invariants
- `PlanningValidationError(ValueError)`.
- `_require_l1` — element must exist in project AND be level L1
  ("Operating plans can only be attached to L1 elements").
- `_check_parent_unit` — a tribe cannot be nested ("A tribe cannot be nested under another agile unit");
  a squad's parent (when given) must be a **tribe in the same L1 plan** ("A squad parent must be a tribe in
  the same L1 plan").
- `get_plan(project_id, l1_element_id)` — returns `{element, units (each with members[]), work_items
  (each with squad_name + linked_element_name via LEFT JOINs, ordered start_date,title), diagrams
  (metadata JSON hydrated, ordered updated_at DESC), settings ({currency_code:"USD",updated_at:None} default),
  metrics}` where **metrics are deterministically computed** (no LLM):
  `tribes`, `squads`, `people`, `allocated_fte = sum(alloc%/100) (2dp)`,
  `monthly_run_rate = sum(monthly_cost*alloc%/100) (2dp)`, `planned_cost = sum(budget_cost)`,
  `actual_cost = sum(actual_cost)`, `cost_variance = planned - actual`, `at_risk_work = count(status=='at_risk')`.
  Money is presentation-only; `currency_code` just labels it.
- `update_settings` — upsert `l1_plan_settings`.
- Units: `create_unit` / `update_unit` (honors explicit `parent_unit_id=None` via `model_fields_set`;
  re-validates parent) / `delete_unit`.
- Members: `_require_resource` (directory person must exist: "Resource 'X' was not found in the directory");
  `_assert_allocation_within_cap(conn, staff_id, allocation, exclude_member_id=None)` — **a directory
  person's total allocation_percent across ALL team memberships must stay <= 100%** — error
  `"{name} would be allocated {t}% across teams (already {e}%); the total cannot exceed 100%."`;
  `create_member` / `update_member` (recheck with merged values, excluding self) / `delete_member`
  (scoped to project's units).
- Work items: `_check_work_links` — `squad_id` must be a squad in the same L1 plan ("Work must be assigned
  to a squad in the same L1 plan"); `linked_element_id` must be an L2-L4 element of this project
  ("linked_element_id must reference an L2-L4 element in this project") whose ancestor chain reaches this
  L1 ("The linked C4 element must belong to this L1 initiative"). `create_work_item` /
  `update_work_item` (merges row+changes then re-validates dates and links; nullable links honored via
  `model_fields_set`) / `delete_work_item`. Dates serialized via isoformat.
- Diagrams: `create_diagram` / `update_diagram` (metadata JSON-serialized; sets updated_at) / `delete_diagram`;
  `_hydrate_diagram` parses metadata back to dict (bad JSON -> {}).

### 16.3 `requirements.py` — versioned docs + review + audit
- `PlanningConflictError(RuntimeError)` — optimistic concurrency (router maps to 409 `planning_conflict`).
- `list_documents` — with `open_comments` and `comment_count` aggregates, ordered updated_at DESC, title.
- `create_document` — status 'draft', version 1, snapshot row in `l1_requirement_versions`
  (change_summary "Initial version"), audit `document_created`.
- `get_document` — document + `comments` (ordered created_at,id) + `versions` (metadata only, no content,
  DESC) + `audit` (detail_json parsed into `detail`, DESC).
- `get_version` — full version row (with content) or NotFound.
- `update_document` — **expected_version must equal current version** else PlanningConflictError
  ("This document is now at version N. Refresh before saving your changes."); no-op change ->
  PlanningValidationError "There are no content changes to save"; bumps version, resets status to 'draft'
  and clears approved_by/approved_at; writes version snapshot + audit `document_updated`
  `{change_summary, previous_version, approval_invalidated: was-approved}`.
- `add_comment` — parent comment must belong to the same document ("The parent comment does not belong to
  this document"); records `document_version`; audit `comment_added`.
- `act_on_comment` — approve->approved / resolve->resolved / reopen->open; sets acted_by/acted_at;
  audit `comment_<new_status>` with previous_status.
- `review_document` — submit->in_review, approve->approved (+approved_by/at), revoke->draft; same-status
  (except revoke) -> "The document is already <status>"; audit `review_<action>` `{note, previous_status, status}`.

### 16.4 `diagram_ai.py` — LLM diagram authoring
- System prompt: "You are a senior software architect who expresses systems as Mermaid diagrams." + rules:
  single diagram matching requested type and starter header; only Mermaid 11.x renderable syntax; short
  alphanumeric node ids with clear labels; flowchart shape vocabulary (["rectangle"], (["stadium"]),
  (("circle")), [("database")], {"decision"}, {{"hexagon"}}, [/"data"/], and v11 object shapes like
  `Node@{ shape: doc, label: "Document" }`); edge vocabulary (`A --> B` dependency, `A -. label .-> B`
  event/async, `A ==> B` primary flow, `A --- B` association, `A -- text --> B` labels); subgraphs for
  grouping; prefer 4-15 nodes; when modifying keep existing node ids/labels and return the FULL updated
  diagram, never a diff; put diagram in `mermaid` and a 1-2 sentence summary in `message`.
- `DEFAULT_HEADERS` — diagram_type -> mermaid header (architecture -> `flowchart LR`,
  infrastructure -> `flowchart TB`, architecture_beta -> `architecture-beta`, block -> `block-beta`, kanban,
  packet, sequence -> `sequenceDiagram`, class -> `classDiagram`, state -> `stateDiagram-v2`,
  er -> `erDiagram`, requirement -> `requirementDiagram`, c4 -> `C4Context`, gantt, journey, timeline,
  mindmap, quadrant -> `quadrantChart`, gitgraph -> `gitGraph`, pie -> `pie showData`,
  xychart -> `xychart-beta`, sankey -> `sankey-beta`, radar -> `radar-beta`, treemap -> `treemap-beta`,
  venn -> `venn-beta`).
- `TYPE_GUIDANCE` — one usage sentence per type (e.g. architecture: "Use a readable flowchart for services,
  boundaries, data stores, events, and dependencies."; see source list for all 24).
- `_sanitize_mermaid(text, type)` — strip code fences; if the first line doesn't match the known-header regex
  (flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(-v2)?|erDiagram|journey|gantt|pie|mindmap|
  timeline|gitGraph|quadrantChart|C4Context|requirementDiagram|architecture-beta|block-beta|packet|kanban|
  radar-beta|treemap-beta|venn-beta|xychart-beta|sankey-beta, case-insensitive), prepend the default header;
  cap at 50000 chars.
- `_build_human(prompt, type, current_source, history)` — sections: `CONVERSATION SO FAR:` (last 8 turns as
  `ROLE: content`), `CURRENT DIAGRAM:` (mermaid-fenced; when present the task line is "Modify the current
  diagram according to the instruction. Return the full updated diagram.", else "Create a new diagram that
  satisfies the instruction."), `DIAGRAM TYPE:`, `STARTER HEADER:`, `TYPE GUIDANCE:`, `INSTRUCTION:`, task.
  These labels are load-bearing — the mock diagram parser matches them.
- `assist_diagram(*, prompt, diagram_type="architecture", current_source="", history=None)` ->
  `{mermaid (sanitized), message (default "Updated the diagram." when editing / "Here is a first draft.")}`
  via `get_structured_llm(DiagramAIOutput)` + `_parse_structured_result`.
- `title_from_prompt(prompt)` — first 8 words of the first line, stripped of ` .,:;-`, <=80 chars, fallback
  "Generated diagram".

### 16.5 `exports.py` — Word/PowerPoint requirement exports
- `MarkdownBlock{kind: heading|paragraph|bullet|number|quote|code|mermaid, text, level}`;
  `_blocks(markdown)` — fence-aware line parser (```mermaid -> kind "mermaid", other fences -> "code");
  headings #x1-6; bullets `- * +`; numbered `\d+[.)]`; `>` quotes; blank lines flush paragraphs; unclosed
  fence flushed at end.
- `_plain(text)` — strip images/links (keep text), bold/italic markers, backticks.
- `_diagram_bytes(images)` — validate each data URL: must be `image/png` base64, PNG magic bytes, running
  total <= 20 MB, PIL `verify()`; invalid -> PlanningValidationError "Rendered Mermaid images must be valid
  PNG data URLs". Empty entries -> None placeholders.
- `word_export(project_id, document_id, diagram_images)` — python-docx: margins 0.7/0.8 inch, Normal font
  Aptos 10.5pt, heading 0 title colored RGB(11,87,208), italic meta line
  "L1 requirements  •  Version N  •  Status", optional "Approved by X on Y" Caption; renders blocks
  (headings capped at level 4, List Bullet / List Number, Quote with 0.25" indent, code/mermaid in Consolas
  8.5pt with a "Mermaid diagram" heading + embedded PNG at 6.4" width + "Editable Mermaid definition"
  caption); new-page section "Review record" with an export note + one bullet per comment
  ("author — Status: body" with bold prefix). Returns `(bytes, filename)`.
- `powerpoint_export(...)` — python-pptx 13.333x7.5 inches; title slide (layout 0) with meta subtitle;
  content slides (layout 1) accumulate blocks per H1/H2 section, splitting on >=6 blocks or >850 chars
  ("<title> (continued)"); mermaid blocks get their own slide (layout 5) with the PNG centered and scaled
  into 11.3x5.45" (or the raw source in Consolas 16pt when no image), footer "Version N • status" 8pt
  right-aligned; final "Review comments" slide with up to 10 comments. Returns `(bytes, filename)`.
- `_filename(title, ext)` — slugify `[^A-Za-z0-9_-]+` -> `-`, lower, fallback "l1-requirements".

### 16.6 `router.py` (prefix `/projects/{project_id}`, tag l1-planning)
Error mapping `_run`: NotFoundError->404, PlanningValidationError->400 `planning_validation`,
PlanningConflictError->409 `planning_conflict`. AI failures (`_run_ai`) -> 502 `diagram_ai_error`
(message[:400], retryable=True).

Routes: `GET|PATCH /l1/{l1}/plan`; `POST /l1/{l1}/units`; `PATCH|DELETE /l1/units/{unit_id}`;
`POST /l1/units/{unit_id}/members`; `PATCH|DELETE /l1/members/{member_id}`;
`POST /l1/{l1}/work`; `PATCH|DELETE /l1/work/{work_item_id}`;
`POST /l1/{l1}/diagrams`; `PATCH|DELETE /l1/diagrams/{diagram_id}`;
`POST /l1/{l1}/diagrams/generate` (require_llm_config; assist then persist with title from payload or
`title_from_prompt`); `POST /l1/{l1}/diagrams/assist` (returns `{mermaid, message}` without persisting);
`GET|POST /l1/{l1}/requirements`; `GET|PATCH /l1/requirements/{document_id}`;
`GET /l1/requirements/{document_id}/versions/{version}`;
`POST /l1/requirements/{document_id}/comments`; `PATCH /l1/requirements/comments/{comment_id}`;
`POST /l1/requirements/{document_id}/review`;
`POST /l1/requirements/{document_id}/export/{docx|pptx}` (other format -> 400; returns attachment with
Content-Disposition filename and the right Office media type).

---

## 17. Global resource directory — `backend/resources/`

### 17.1 `models.py`
`StaffType=Perm|Contract`; `StaffStatus=Active|Inactive`; `SubStatus=Allocated|UnAllocated|PartiallyAllocated`;
`LookupCategory/LOOKUP_CATEGORIES=(tech_unit,rank,hr_role)`; `CustomFieldType=text|number|date|select|boolean`.
- `LdapImportRequest{connector_key: ldap|active_directory="ldap", scope: bulk|single="bulk", identifier?
  (..320), search_filter="(objectClass=person)" (3..1000), max_results=500 (1..5000),
  update_existing=False}`; model validator requires `identifier` for single-user scope.
- `StaffBase{staff_first_name (1..120), staff_last_name (1..120), staff_name (..240, auto-generated from
  first+last when blank via model_validator), staff_type=Perm, staff_status=Active, sub_status=UnAllocated,
  tech_unit/citizenship/rank/hr_role (..120)="", staff_start_date/staff_end_date: date|None (validator:
  end >= start -> "staff_end_date must be on or after staff_start_date"), reporting_manager_id?,
  custom_values: dict = {}}`; `StaffCreate(StaffBase)`; `StaffUpdate` all-optional variant.
- `LookupCreate{code (1..80), label (1..160)}`; `LookupUpdate{label}`.
- `CustomFieldCreate{key (1..60, pattern ^[a-zA-Z][a-zA-Z0-9_]*$), label (1..160), field_type=text,
  required=False, options: list[str] (..100)}` + validator: select fields require >=1 option;
  `CustomFieldUpdate` all optional.

### 17.2 `imports.py` — Excel/CSV and directory ingestion

- `ResourceImportError(ValueError)` maps to HTTP 400 `resource_import_error`.
- `_ALIASES` maps human/LDAP-style headings to fixed fields (First/Given Name, Last/Surname/sn, Display
  Name, employment type/status, allocation, department, citizenship, grade, job title, start/end dates).
  `_payload_from_row` accepts First+Last or splits Display Name, normalizes enum aliases, recognizes
  `Custom: <key>` columns, and returns both the payload and set of fields actually present.
- `_apply(rows, update_existing, source)` is the shared row engine. Matching is case-insensitive display
  name; existing people are skipped unless update_existing; updates contain only present fields; all rows
  pass through normal resource-store validation. Result is `{source, created, updated, skipped, errors,
  counts}` with row-scoped error messages, so valid rows survive a partial import.
- `import_excel(content, filename, update_existing=False)` supports CSV, XLSX and XLS (`pandas`, `openpyxl`,
  `xlrd`), max 5,000 rows, and requires First+Last or Display Name. `template_workbook()` produces a styled
  `karya-resource-import.xlsx` sample with frozen headings.
- LDAP helpers RFC-4515-escape identifiers. Single-user scope combines the base filter with uid,
  sAMAccountName, userPrincipalName, mail, employeeNumber and displayName alternatives and limits to one.
- `import_ldap` accepts only configured `ldap`/`active_directory` connectors; calls
  `integrations.store.runtime_config` so required values and enabled state are enforced; uses `ldap3` with
  15s connect/30s query timeouts and always unbinds. It maps givenName/sn/displayName, employeeType,
  department/title/country/disabled state and conditionally maps mail/username/employeeNumber/phone into
  same-named custom fields when those definitions exist. Department/title only populate lookup-backed fields
  when their exact codes exist.

### 17.3 `store.py` — invariants
- `NotFoundError(LookupError)`; `ValidationError(ValueError)` (HTTP 400).
- `_LOOKUP_COLUMN = {tech_unit, rank, hr_role}` map to same-named columns; `_validate_lookups` — a non-blank
  value must be a code in the category's lookup table ("{column} '{value}' is not defined in the {category}
  lookup table").
- `_validate_manager` — manager must exist and not be self ("A staff member cannot report to themselves" /
  "reporting_manager_id 'X' does not exist").
- `_validate_custom_values` — unknown keys rejected ("Unknown custom field(s): …"); required fields must be
  non-blank ("Custom field '<label>' is required"); select values must be a defined option.
- `_next_staff_code` — max existing `STF-%` numeric suffix + 1, formatted `STF-{n:04d}` (STF-0001, ...).
- `create_staff` — validates, generates id + staff_code, dates iso-serialized, custom_values JSON.
- `list_staff(filters)` — equality filters on staff_status/sub_status/staff_type/tech_unit/rank/hr_role,
  `search` LIKE on staff_name or staff_code; ordered staff_name NOCASE; hydrates custom_values JSON.
- `get_staff`; `update_staff` — merges provided (exclude_unset) over current; regenerates display name only
  when the caller cleared it; revalidates lookups/manager/date order; custom_values replaced wholesale when
  provided (validated); sets updated_at.
- `delete_staff` — first NULLs `reporting_manager_id` of reports, then deletes.
- Lookups: `list_lookups(category)` (unknown category -> NotFound "Unknown lookup category 'X'"),
  `list_all_lookups()` (dict by category), `create_lookup` (duplicate code -> "'{code}' already exists in the
  {category} table"), `update_lookup` (label only), `delete_lookup` — **refused while any staff row uses the
  code** ("'{code}' is assigned to staff and cannot be deleted").
- Custom fields: `list_custom_fields` (ordered created_at), `create_custom_field` (duplicate key ->
  "A custom field with key 'X' already exists"), `update_custom_field`, `delete_custom_field`;
  `_hydrate_custom_field` parses options JSON + bool required.

### 17.4 `router.py` (prefix `/resources`)
`_guard`: NotFoundError->404 `not_found`, ValidationError->400 `invalid_resource`.
Routes: `GET /staff` (query filters incl. `search` max_length 160), `POST /staff`;
`GET /import/template`; `POST /import/excel?update_existing=` (multipart, non-empty, max 15 MB, threadpool);
`POST /import/ldap` (threadpool, request schema above);
`GET|PATCH|DELETE /staff/{staff_id}`; `GET /lookups` (all), `GET|POST /lookups/{category}`,
`PATCH|DELETE /lookups/{lookup_id}`; `GET|POST /custom-fields`, `PATCH|DELETE /custom-fields/{field_id}`.
RBAC: GET is any signed-in user (planning/profile dropdowns need it); POST/PATCH/DELETE, including both
imports, require effective `admin.resources` page permission.

---

## 18. Reporting — `backend/reporting/`

`service.overview()` — all deterministic SQL, no LLM. Returns:
```
{
  access: role_counts(),           # admin/manager/contributor/viewer/disabled counts
  portfolio: {
    projects, stories (# L3), estimated (# L3 with points), estimated_pct (rounded %),
    squads (# l1_agile_units squad), members (# l1_team_members),
    at_risk_work_items (# l1_work_items status=at_risk),
    platforms: [{id, name, stories, estimated, estimated_pct} per project, created_at DESC],
  },
  resources: {
    total, active,                 # resource_staff counts
    on_bench,                      # active staff with 0 summed allocation across l1_team_members
    fully_allocated,               # summed allocation >= 100
    partially_allocated,           # 0 < allocation < 100
    avg_utilisation,               # mean of min(allocated,100) over active staff, 1dp
    by_sub_status / by_type: [{label, value}],   # GROUP BY counts, DESC
    by_tech_unit: [{label, value}],              # labels resolved via resource_lookups, fallback code, "—" for empty
  },
}
```
`router.py` (prefix `/reporting`): `GET /overview`. RBAC: whole prefix needs `admin.reporting`.

---

## 19. Agentic AI — `backend/ai/`

### 19.1 `schemas.py` (structured-output contracts; the mock builds valid instances of each)
- `StaffingAssignment{staff_id, staff_name="", squad_id, squad_name="", role="", allocation_percent (0..100),
  reason (..400)}`; `StaffingProposal{summary (..1200), assignments[]}`.
- `NarrativeOutput{headline (..200), summary (..2000), highlights/risks/recommendations: list[str] (..8)}`.
- `ProposedStory{name (1..200), description (..2000), rationale (..400)}`;
  `StoryDecomposition{summary (..1200), stories (..20)}`.
- `ScaffoldElement{ref, level: L1|L2|L3, name (1..200), kind (..60), description (..1200), tech (..200),
  parent_ref?}`; `ScaffoldRelation{source_ref, target_ref, label (..120), kind="sync" (..40)}`;
  `C4Scaffold{summary, elements (..40), relations (..60)}`.
- `DraftOkr{objective (1..400), key_result (..600), metric_name (..200), target_value (..100), owner (..160)}`;
  `DraftStakeholder{name (1..160), role, stakeholder_type=internal, influence/interest=medium, raci=Informed}`;
  `DraftCapability{name (1..200), description (..1000), criticality=medium}`;
  `DraftRisk{title (1..300), category=delivery, risk_level=medium, mitigation (..1000), funding_source (..200)}`;
  `L1BaselineDraft{summary, vision_statement (..2000), business_problem (..2000), target_users (..1000),
  okrs (..12), stakeholders (..20), capabilities (..20), risks (..15)}`.
- `OrchestratorAction = generate_l1_baseline|auto_staffing|decompose_story|scaffold_c4|reporting_narrative|
  review_readiness|none`; `OrchestratorPlan{action="none", rationale (..600), suggested_prompt (..1000)}`.
- `FieldSummary{summary (..2000)}`.
- `DraftContainer{name, capability, responsibilities, owner_team, security_classification=internal}`;
  `DraftApi{name, provider, consumer, api_type=REST, data_classification=internal, authentication}`;
  `DraftNfr{name, category=performance, metric, target}`; `DraftIntegration{name, source_system,
  target_system, integration_type=API}`; `L2Draft{summary (..1600), container_diagram (..8000),
  containers (..20), apis (..20), nfrs (..15), integrations (..15)}`.
- `DraftComponent{name, component_type=service, responsibilities, tech, pattern}`;
  `DraftInterface{name, direction=provided, interface_type=REST, contract (..600), authentication}`;
  `DraftDependency{name, dependency_type=internal, target, criticality=medium}`;
  `DraftConcern{name, category=security, approach (..600)}`; `L3Draft{summary, component_diagram,
  components/interfaces/dependencies (..20), concerns (..15)}`.
- `DraftCodeUnit{name, unit_type=class, responsibility (..600), tech, complexity=medium}`;
  `DraftTestCase{name, test_type=unit, scenario (..600), expected (..600)}`;
  `DraftChecklistItem{item (1..400), category=code}`; `L4Draft{summary, code_diagram, code_units (..25),
  test_cases (..25), checklist (..20)}`.
- `ChatCommand{action: overview|list|describe|readiness|report|create_element|update_element|delete_element|
  create_relation|answer|code|web_search|image|document|help|none = "help", level (..4), name (..200),
  parent (..200), new_name (..200), status (..40), description (..2000), target (..200), label (..120),
  reply (..12000)}` — reads execute immediately; *_element writes surface as a proposal. A before-validator
  on `status` converts None or provider-returned booleans to `""`; guessing that True means a lifecycle
  status would silently filter reads or create an unsafe mutation. This specifically tolerates providers
  that return `{"action":"list","level":"L1","status":true}`.

### 19.2 `masking.py`
`mask_pii(text)` — regex-redacts emails -> `[email]`, SSN `\d{3}-\d{2}-\d{4}` -> `[id]`, phones
(`\+?\d[\d\s().-]{7,}\d`) -> `[phone]`. Applied to briefs, guidance, descriptions, chat messages/history/
attachments, orchestrator requests before they reach the LLM.

### 19.3 `nl.py` — deterministic NL helpers (shared by mock + local routing; keep both in sync via this module)
- `is_write_intent(text)` recognizes create/add/rename/delete/remove/set/update/change/connect/route/link/wire
  so mutation language reaches write routing before deterministic read classification.
- `resolve_element_name(fragment, names)` — strip leading filler (the/a/an/new/L1-4), squash to [a-z0-9];
  longest names first; forward containment OR (fragment >= 4 chars) reverse containment.
- `match_relation(text, names) -> (source, target, label)|None` — trigger words route/connect/link/wire/
  connection; label "routes" if "rout" in text, "links to" if "link", else "connects to"; BOTH endpoints must
  resolve to existing elements. Direction rules: `between A and B` -> A->B; `from A to B` -> A->B;
  `to B from A` -> A->B; `to X through/via Y` -> **Y->X** (the through/via hop is the source);
  `route/connect/link/wire/call A to/into/with/through/via B` -> A->B.
- `parse_create(text, names) -> {level, name, parent, target, label}|None` — trigger create/add/new; level
  from `\bl([1-4])\b`; name via `_new_element_name` patterns (called/named X; any quoted literal; "create X
  as a new L#"; "L# <name> <type>"; "create <name> <type>", where type-tail = container|component|service|
  module|task|story|system|element|node|initiative|epic), cleaned of quotes/articles/type-tail; parent from
  `under <name>`; optional compound relation tail `and routes/connects/links/wires/publishes/calls …` sets
  target (resolved) and a `name the route as X` label.
- `classify_read(text, names, screen_level, screen_element) -> (action, level, name)|None`, checked in order:
  report regex (`next|what should i|recommend|roll.?up|report|estimat`) -> ("report","","");
  resolved element + describe/details/purpose/responsibilities/"what is … about"/"what does … do" →
  `describe`; an explicit level plus lifecycle word (active/proposed/reviewed/baselined) → filtered `list`;
  status/progress with a resolved element or explicit level → scoped `readiness` (so “status of each L1
  item” cannot become whole-project overview);
  readiness regex -> ("readiness", level-or-screen_level when no name, found-or-screen_element);
  enumerate regex (`list|show|display|enumerate|summar…|how many|which|items|everything`) + (level or a
  type word) -> ("list", level, ""); overview regex (`overview|project status|status|progress|where am i|
  how are we|health|state of|summar…`) -> ("overview","",""); bare enumerate on a level screen ->
  ("list", screen_level, "").
- `list_status_filter(text)` — pending/proposed/draft -> "proposed"; active; reviewed; baselined; else "".

### 19.4 `agents.py` — the agentic services (gather context -> structured output -> return a PROPOSAL)
Common: `_invoke(schema, system, human)` = `get_structured_llm(schema).ainvoke([System, Human])` ->
`_parse_structured_result`.

**Auto-staffing** — system prompt: delivery lead composing squads; only assign from RESOURCE POOL by exact
staff_id; never exceed remaining capacity; prefer skill/rank/role fit; leave unassigned rather than overload;
concrete reason per assignment. `_staffing_context` builds: squads of the plan, active staff with
`remaining = 100 - SUM(l1_team_members.allocation_percent)` (only >0 included, with rank/hr_role/tech_unit),
open work items (planned/in_progress/at_risk), human message with sections INITIATIVE / SQUADS: / OPEN WORK
ITEMS: / RESOURCE POOL (with remaining capacity): (all JSON) + instruction. `propose_staffing` — empty
pool/squads -> early return "No available resources or squads to staff."; **defensively re-clamps** every
returned assignment: unknown staff/squad dropped, `allocation = min(requested, remaining)` decremented per
person, <=0 dropped; fills staff_name/squad_name. `apply_staffing` — creates team members via
`planning_store.create_member` (so the 100% cap still holds); partial apply OK, per-item errors collected
-> `{created, errors}`.

**Reporting narrative** — system: portfolio analyst, quantitative, no invented data. Human: "Write an
executive summary of this delivery portfolio snapshot.\n\nMETRICS:\n<overview JSON>" -> `NarrativeOutput`.

**Story decomposition** — system: senior BA/tech-lead; vertically sliced, testable, sprint-sized; user story
+ AC; 3-8 stories, no overlap. Human labels: PARENT / ELEMENT (<level>): / DESCRIPTION: / TECH: /
EXTRA GUIDANCE (masked). `apply_decomposition` — child level map L1->L2, L2->L3, L3->L4 (default L3); creates
`status='proposed'` children (kind component for L3 else task), name[:200] -> `{created, level}`.

**C4 scaffold** — system: exactly one L1 system, a handful of L2 containers, L3 components; use `ref` +
parent_ref; add relations; 8-20 elements; realistic tech. Human: "Turn this description into a C4 model …
DESCRIPTION:\n<masked>". `apply_scaffold` — sorts elements L1->L2->L3, creates each as `proposed` resolving
parent_ref via a ref->id map, then relations (skip unresolved refs; kind coerced to sync|async|data) ->
`{created_elements, created_relations}`.

**L1 baseline** — system: enterprise architect; vision, business problem, target users, 2-4 OKRs with
measurable KRs, stakeholders with RACI (exactly one Accountable), top capabilities, risks with mitigations +
funding source. Human labels: `L1 INITIATIVE:` / EXISTING DESCRIPTION / BRIEF (masked, "(use the initiative
name and description)" fallback). `apply_l1_baseline(project, l1, draft, sections)` — sections filter
(default all of vision/okrs/stakeholders/capabilities/risks); vision applied via `l1_store.update_vision`
only when statement/problem present; each list applied via the l1arch create functions; returns counts.

**L2 baseline** — system: container architecture for one epic/slice: summary, C4-style Mermaid container
diagram (flowchart LR), containers (capability/responsibilities/owner team/security classification), API
contracts, NFRs (metric+target), integrations; mark unknowns. Human labels `L2 EPIC/CONTAINER SLICE:` /
PARENT L1 INITIATIVE / EXISTING DESCRIPTION / BRIEF. `apply_l2_baseline` — sections default
summary/containers/apis/nfrs/integrations; summary+diagram via `l2_store.update_l2`, lists via creates.

**L3 baseline** — analogous; system mentions flowchart TB, component types controller/service/repository/
gateway/model/client, interfaces with contract+auth, dependencies, cross-cutting concerns. Label
`L3 COMPONENT/STORY:` / PARENT L2 CONTAINER. `apply_l3_baseline` sections summary/components/interfaces/
dependencies/concerns.

**L4 baseline** — analogous; Mermaid class or sequence diagram, code units, test cases, DoD checklist.
Label `L4 TASK:` / PARENT L3 COMPONENT. `apply_l4_baseline` sections summary/code_units/test_cases/checklist.

**Orchestrator** — system lists the 6 routable actions + none, one-line rationale. Human: "USER REQUEST:\n
<masked>\n\nChoose the single best action." -> `OrchestratorPlan`.

**Field summarizer** — `_SUMMARIZE_STYLES = {vision: "a single crisp vision sentence (who it's for, what it
provides, the outcome)", problem: "a one-to-two sentence business-problem statement", users: "a short
comma-separated list of the primary user segments", default: "one concise, executive-ready sentence"}`;
system: distil notes, no preamble/markdown/bullets; human `DETAIL NOTES:\n<masked>\n\nSummarize into <style>.`

**Conversational assistant `interpret_chat(project_id, message, history, attachment_context, mode, screen)`**
- `_CHAT_SYSTEM` (long prompt; reproduce from source): interpret into ONE ChatCommand; describes every action
  incl. the relation direction rule ("add route to payments through api-gateway" means api-gateway -> payments),
  compound create+route as ONE create_element with target/label, follow-up resolution from CONVERSATION,
  REQUEST MODE is authoritative when not auto (chat->answer, code->code, research->web_search, image->image,
  document->document), image mode is text-only (never claim bitmap generation), web_search sets description
  to a focused query, never invent elements, prefer grounded reads (overview/report/list/readiness), ground
  every claim in PROJECT SNAPSHOT + PLATFORM GUIDE, default omitted level/element from CURRENT SCREEN.
- `_PLATFORM_GUIDE` — fixed paragraph describing Karya (estimator + C4 workspace, readiness, governance,
  Fibonacci roll-up, proposal-first assistant).
- `_project_snapshot(project_id, elements)` — deterministic status lines: per-level element counts (+proposed),
  roll-up "X/Y stories estimated · N points", workflow "P% complete (stage S) · next: …"; best-effort
  (exceptions swallowed).
- `_resolve_screen(screen, elements)` -> (level, element_name, label) from `{level, element_id, tab/tab_label}`.
- Human message sections in order: `REQUEST MODE: <mode>`, PLATFORM GUIDE, `PROJECT SNAPSHOT (deterministic,
  from the database):`, optional `CURRENT SCREEN: view=… | level=… | element=…` (+ "Use this only to fill a
  level or element the message leaves implicit."), `PROJECT ELEMENTS:` (up to 100 lines `- L2 · name (status)`),
  optional `CONVERSATION SO FAR:` (last 8 turns, `ROLE: masked-text[:300]`), optional `ATTACHED FILE CONTENT:`
  (masked), `USER MESSAGE:` (masked), "Interpret into one command."
- Routing: if `prefers_text_routing()` (local providers) -> `_interpret_local_chat` (deterministic regex
  routing using nl.py helpers — writes first: rename / status-to / delete / match_relation / parse_create /
  follow-up replay from history (<=60 chars) / web-search keywords / classify_read; open-ended modes get a
  Gemma Markdown reply via `_local_markdown_reply` with `max_new_tokens=256` and mode-specific system suffix);
  else `_invoke(ChatCommand, _CHAT_SYSTEM, human)` with forced-mode override applied after.
- `_apply_screen_defaults(command, screen_level, screen_element)` — fills omitted list.level /
  readiness.name-or-level from the screen.
- Before provider routing, Auto-mode messages without write intent run through `classify_read` for **every
  provider**. Recognizable overview/report/list/describe/readiness questions become deterministic
  `ChatCommand`s immediately; the LLM remains responsible for writes and genuinely open-ended modes. This
  prevents a hosted model from widening a scoped request such as “status of each L1 item.”

### 19.5 `router.py` (tag "ai") — all generation routes `require_llm_config` (503 when unconfigured)
Error guard: NotFound from any store -> 404; validation errors (planning/c4/l2/l3/l4) -> 400 `invalid`.
- `POST /projects/{id}/ai/diagram` — shared diagram assistant for all levels (DiagramAssistRequest ->
  `{mermaid, message}`; failures 502 `diagram_ai_error` retryable).
- `POST /projects/{id}/l1/{l1}/ai/staffing` -> StaffingProposal; `POST /projects/{id}/ai/staffing/apply`
  (`{assignments: [StaffingAssignment]}`).
- `POST /reporting/narrative` -> NarrativeOutput of `reporting_service.overview()`.
- `POST /projects/{id}/c4/elements/{eid}/ai/decompose` (`{guidance ..2000}`; L4 -> 400 `not_decomposable`
  "L4 tasks are already the lowest level.") + `/apply` (`{stories: [ProposedStory] (..30)}`).
- `POST /projects/{id}/c4/ai/scaffold` (`{description 1..8000}`) + `/apply`
  (`{elements (..60), relations (..80)}`).
- `POST /projects/{id}/l1/{l1}/ai/baseline` (`{brief ..8000}`) + `/apply` (`{draft: L1BaselineDraft, sections?}`).
- `POST /projects/{id}/l2/{l2}/ai/l2` + `/apply`; `POST …/l3/{l3}/ai/l3` + `/apply`;
  `POST …/l4/{l4}/ai/l4` + `/apply` (same shape with L2Draft/L3Draft/L4Draft).
- `POST /ai/orchestrate` (`{request 1..2000}`); `POST /ai/summarize` (`{text 1..20000, field ..40}`).

---

## 20. Conversational assistant — `backend/chat/`

### 20.1 `service.py`
- `ChatError(ValueError)` (router -> 400 `chat_invalid`).
- `_find(project_id, name)` — case-insensitive exact name match; none -> "I couldn't find an element named
  “X”." + "Did you mean: …?" hint from substring matches (up to 5); multiple -> "matches N elements — please
  be more specific."; blank -> "Which element? Please name it."
- `_resolve_parent(project_id, level, parent_name)` — the C4 one-level-up rule must always hold: explicit
  parent must be at the expected level; without one, candidates = non-proposed elements at the expected level
  (for L2, prefer kinds that aren't person/external); zero -> "A {level} element needs an {expected} parent —
  create the {expected} first."; multiple -> asks "Which {expected} should it live under? Say e.g. '… under
  X'. Options: …" ; exactly one -> inferred. L1 with an explicit parent -> "L1 elements are top-level…".
- `dispatch(project_id, command)` — reads run immediately: `overview` (workflow guide -> reply
  "<name> is **P%** through the workflow (stage: S). Next best step: …"), `list` (level+status filters;
  default hides proposed unless a status filter or nothing else matches; data
  `{level, status, items: [{id,level,name,status}]}`), `describe`, `readiness`, `report` (roll-up + next step
  sentence), `web_search`, and
  answer/code/image/document echo `command.reply`. Writes -> `_propose`. Anything else -> help text
  (bullet list of example commands).
- `_describe(project_id, command)` resolves one element and loads its level workspace via
  `l1_store.get_baseline` / `l2_store.get_workspace` / `l3_store.get_workspace` /
  `l4_store.get_workspace`. The deterministic Markdown answer combines level/kind/status, parent, stored C4
  description (fallback architecture summary/vision), tech/code path, children, artifact counts, relations
  and readiness. Structured data returns the element, parent, children, relations, architecture/vision text,
  artifact counts and `{score,status_label}`. It never asks the model to invent a description.
- `_readiness`: named element → its level scorer; level-wide → score **every element** at that level, sort by
  name, and return `{level,count,ready,avg_readiness,items:[{id,name,level,status,score,status_label}]}`.
  This is the contract for “status of each L1 item”; the project workflow percentage is deliberately not
  substituted for individual scores.
- `_web_search(command)` — GET `https://html.duckduckgo.com/html/?q=<quote_plus(query[:500])>` with UA
  "Karya/2.0 research assistant", timeout 10, follow_redirects; regex `class="result__a" href` anchors, up to
  6 sources; strips tags, unescapes, fixes `//` URLs, unwraps DDG `uddg` redirect params; reply is a Markdown
  list of `[title](url)`; HTTP failure or no results return graceful replies (never fabricate).
- `_propose` — builds a human `summary` + a `mutation` dict per action: create_element (resolves parent NOW
  so the summary names it; optional target relation "…, <label> “target”", default label "uses"),
  update_element (collects rename/status/description changes; none -> "What should I change? …"),
  create_relation (resolves both), delete_element ("Delete Lx “name” (and its children)"). Returns
  `{reply: "<summary>? Review and Apply to confirm.", action, data: None, mutation}`.
- `apply(project_id, mutation)` — **re-resolves names** through the store (RBAC + level rules hold):
  create_element (re-resolves parent + optional target, creates relation with label default "uses"),
  create_relation, update_element (C4ElementUpdate with None for blanks), delete_element. Unknown action ->
  ChatError. Returns `{reply, result}`.

### 20.2 `graph.py` — concurrent chat-agent graph (used by `/chat/stream`)
`ChatAgentState` TypedDict: project_id, message, history, attachment_context, mode, screen, plan, facts,
tool_runs, verdict, final. Nodes:
- `planner` (async) — `agents.interpret_chat` -> `{plan: command.model_dump()}`.
- `retrieval` — normally element counts by level, proposed count, first-12 names and summary. For a scoped
  `describe`, it instead returns that element's stored fields, parent and children so evidence does not get
  diluted by whole-project counts.
- `tools` — for scoped `describe`, returns only `element_context`; for named/level readiness, returns only the
  relevant readiness result(s), including every item for a level. Other requests run roll-up and workflow
  guide plus readiness of a named element. This keeps the Agent evidence aligned with the actual question.
- `judge` — `sufficient = action not in (help, none) and >=1 evidence branch`; verdict includes reason.
- `respond` — rebuilds `ChatCommand(**plan)` and calls `chat_service.dispatch` (same proposal-first contract
  as the non-streaming path); attaches `evidence = {retrieval, tools, verdict}`.
`get_chat_graph()` (lru_cache) — START fans out to planner+retrieval+tools in parallel, all join at judge,
then respond -> END. Compiled WITHOUT a checkpointer.

### 20.3 `store.py` — persistent conversations
`create_conversation` (title[:120] default "New chat"); `list_conversations` (per project+user, message_count,
updated_at DESC, LIMIT 100); `get_conversation` (messages ordered created_at,rowid with parsed payload JSON +
attachments grouped per message) or `ChatStoreError("Conversation not found")`; `delete_conversation`;
`add_message` (payload JSON with ensure_ascii=False/default=str; the FIRST user message sets the conversation
title to text[:80]; always bumps updated_at); `add_attachment` (returns record without extracted_text);
`attachment_context(conversation_id, ids) -> (text, meta)` — "FILE: name\n<text[:12000]>" joined, capped
30000; `attach_to_message(ids, message_id)`.

### 20.4 `router.py` (prefix `/projects/{project_id}`, tag chat)
- `ChatRequest{message (1..2000), history (..12) [{role, text}], conversation_id?, attachment_ids (..10),
  mode: auto|chat|code|research|image|document = auto, screen_context?}`; `ChatApplyRequest{mutation}`.
- `_user_id(request)` = `X-User-Id` header or `f"role:{X-User-Role or 'unknown'}"`.
- `_extract_file(filename, content)` — text/code suffixes (txt md markdown csv json yaml yml xml html css js
  jsx ts tsx py java kt sql sh ps1 c cpp h go rs) -> utf-8 decode (errors=replace); docx -> python-docx
  paragraph text; xlsx/xls -> pandas all sheets, `SHEET: name` + head(200) CSV; images -> placeholder note
  ("Visual OCR is not available in this local runtime"); else ChatError "Unsupported attachment type…".
- Routes: `GET|POST /chat/conversations`, `GET|DELETE /chat/conversations/{id}`,
  `POST /chat/conversations/{id}/attachments` (empty -> 400 `empty_file`; >10MB -> 413 `file_too_large`;
  extracted text stored capped at 100_000 chars).
- `POST /chat` — require_llm_config; 404 if project unknown; loads/creates conversation; stored history
  (last 12 messages) preferred over payload history; attachment context assembled; persists the user message
  (with attachment meta) and links attachments; `interpret_chat` errors map: LocalModelLoadingError -> 503
  `model_loading`, LocalModelInferenceError -> 502 `local_inference_error`, ValueError -> 502
  `invalid_model_output`; `service.dispatch`; persists the assistant message with the full result payload;
  returns `{**result, conversation_id}`.
- `POST /chat/stream` — SSE over `get_chat_graph().astream(state, stream_mode="updates")`: `branch` event per
  parallel branch as it lands, `judge` event, final `result` (exact same shape as POST /chat, persisted);
  errors emitted as `error` events with the same code mapping (+`chat_invalid`); hosted failures emit
  `llm_provider_error` with factory-derived retryability.
- `POST /chat/apply` — `service.apply` (RBAC: needs `platform.edit`; all other chat routes are any-signed-in).

---

## 21. Workflow guide — `backend/workflow/`

`READY_THRESHOLD = 80`. `_LEVELS` metadata: L1 "Strategy & initiatives" tab `planning` child L2 (purpose:
vision/OKRs/stakeholders/capabilities/risks), L2 "Container architecture" tab `l2arch` child L3, L3
"Component design" tab `l3arch` child L4, L4 "Implementation detail" tab `l4arch` child None — each with its
level service's `readiness` scorer.

`guide(project_id)` returns:
- `levels`: per level `{level, label, purpose, tab, count (non-proposed), proposed, ready (score>=80),
  avg_readiness (rounded mean; scorer exceptions count as 0), status: not_started|in_progress|ready,
  expected (L1 always; else parent level count > 0), actions: [{text, tab, tone: primary|normal|done}]}`.
  Action rules: L1 empty -> "Create an initiative (L1) on the C4 canvas" (tab canvas); non-L1 with no parent
  -> "Add a parent Lx first"; level empty -> "Add Lx elements under the level above on the canvas"; below
  threshold -> "Open the <label> workspace and raise readiness" + "Use “AI generate Lx” to bootstrap, then
  review"; ready -> "<label> looks ready — review governance / traceability"; plus "Decompose into <child>
  elements on the canvas" when the child level is empty.
- `estimation`: `{label: "Estimation & roll-up", tab: rollup, estimated, unestimated, total, pct, points,
  spikes, pending_splits, status, actions}` from the deterministic roll-up (actions: add L3 stories / estimate
  the N remaining (+ "Or run a one-off Quick estimate") / all estimated; plus spike + split notices).
- `overall_pct` = rounded mean of expected levels' avg_readiness + est_pct (when stories exist).
- `stage` + `next_action`: first expected non-ready level (stage labels Strategy/Architecture/Component
  design/Implementation) -> its first action (+level+label); else estimation; else stage "Complete" with a
  "keep governance current" done action.
Route: `GET /projects/{id}/workflow`.

---

## 22. Integrations — `backend/integrations/`

### 22.1 `catalog.py`
`CATALOG`: 6 categories -> ~42 `(key, name, purpose)` tools:
- Product & delivery: jira, azure_devops, rally, aha, jira_align
- Documentation: document_import, confluence, sharepoint, google_drive, notion
- Architecture: mermaid, structurizr, plantuml, drawio, lucidchart, leanix, ardoq, sparx
- People: resource_directory, ldap, active_directory, workday, successfactors, teams, slack
- Engineering: github, bitbucket, gitlab, sonarqube, snyk, jenkins, github_actions
- Risk & operations: servicenow_grc, servicenow_itsm, archer, pagerduty, opsgenie, splunk, elk, grafana,
  prometheus, appdynamics
`_ADAPTERS = {document_import, mermaid, resource_directory}` (live in-app adapters).
`list_catalog()` — per tool computed `status`: `adapter` | `connected` (saved+enabled config, or jira with
env-configured instances) | `available`; each carries `configurable` flag; returns `{groups: [{category,
tools}], total, counts: {connected, adapter, available}}`. It's a framework + catalog, NOT 42 live connectors.

### 22.2 `connectors.py`
`ARCHETYPE_FIELDS` — field lists per archetype (each field `{key,label,type,required,secret,placeholder}`):
- atlassian: base_url(url), email, api_token(password,secret)
- token: base_url(url), api_token(password,secret)
- apikey: base_url(url), api_key(password,secret)
- basic: base_url("Instance URL"), username, password(secret)
- webhook: webhook_url(url, secret)
- directory: server_url(url), bind_dn, bind_password(secret), base_dn
- oauth: base_url(url), client_id, client_secret(secret), tenant_id(optional)
`CONNECTOR_ARCHETYPE` map (jira/jira_align/confluence/bitbucket -> atlassian; azure_devops/notion/structurizr/
plantuml/drawio/github/gitlab/sonarqube/snyk/github_actions/splunk/grafana/prometheus -> token; rally/aha/
lucidchart/leanix/ardoq/workday/successfactors/pagerduty/opsgenie/elk/appdynamics -> apikey; sparx/jenkins/
servicenow_grc/servicenow_itsm/archer -> basic; ldap/active_directory -> directory; teams/slack -> webhook;
sharepoint/google_drive -> oauth). `DEFAULT_ARCHETYPE="token"`. `NON_CONFIGURABLE = adapters`.
Helpers: `is_configurable`, `archetype_for`, `fields_for` (copies; [] when not configurable), `field_keys`,
`secret_keys`, `required_keys`.

### 22.3 `store.py`
- `get_config(key)` -> `{connector_key, configurable, fields, values (non-secret only), secrets_set (names of
  secret fields with a saved value — **secret values are never returned**), enabled, updated_at, updated_by}`.
- `save_config(key, provided, enabled, user)` — non-configurable -> IntegrationValidationError "'{key}' is an
  in-app adapter and needs no configuration"; `_merge_values` keeps only known field keys and updates a
  secret ONLY when a new non-blank value is supplied (blank = leave unchanged); enabling requires all
  required fields present ("Cannot enable — missing required fields: <labels>"); upsert row.
- `clear_config(key)` — delete; nothing -> NotFound "No configuration to remove for 'key'".
- `test_config(key)` — deterministic validation only (required present + url-typed fields match
  `^(https?|ldaps?)://`); returns `{ok, message}` ("Configuration looks valid. Saved settings are complete
  and well-formed." on success). Not a live connection test.
- `configured_keys()` — keys with enabled=1 (drives catalog 'connected').
- `runtime_config(key)` — **server-internal only** accessor for live adapters such as LDAP. It requires an
  enabled config and every required key, then returns stored values including secrets. Never expose this
  return value from a router; public `get_config` remains secret-redacted.

### 22.4 `router.py` (prefix `/integrations`)
`ConfigPayload{values: dict[str,str] = {}, enabled: bool = False}`. Unknown connector (not in
CONNECTOR_ARCHETYPE nor NON_CONFIGURABLE) -> 404. Routes: `GET /catalog` (any signed-in);
`GET|PATCH|DELETE /{key}/config`, `POST /{key}/test` (all admin-only via `admin.integrations`); PATCH passes
`X-User-Id`/`X-User-Role` as the audit `updated_by`. Errors: NotFound->404, validation->400 `integration_invalid`.

---

## 23. L1 architecture baseline — `backend/l1arch/`

### 23.1 `models.py`
- `VisionUpdate{vision_statement (..4000), business_problem (..4000), target_users (..2000),
  vision_statement_details/business_problem_details/target_users_details (..20000) — rich markdown "more
  details" backing each summary field, strategic_theme (..200), status: draft|approved|baselined|archived|None}`.
- `OkrCreate{objective (1..400), key_result (..600), metric_name (..200), baseline_value/target_value/
  current_value (..100), owner (..160), status: on_track|at_risk|off_track|done = on_track,
  linked_element_id?}`; `OkrUpdate` all optional.
- `StakeholderCreate{name (1..160), resource_staff_id?, email (..200), department (..160), role (..160),
  stakeholder_type=internal, influence/interest=medium, raci=Informed, owns (..600), status=active}`;
  `StakeholderUpdate` all optional.
- `CapabilityCreate{name (1..200), description (..2000), parent_id?, cap_level: L1|L2|L3 = L1,
  business_owner/technology_owner (..160), criticality=medium, current_maturity=1 (1..5),
  target_maturity=3 (1..5), strategic_priority=medium, status=active, linked_element_id?}`; Update optional.
- `RiskCreate{title (1..300), category=delivery, risk_level=medium, owner (..160), mitigation (..2000),
  funding_source (..200), approved_budget/forecast_spend/actual_spend >= 0, status=proposed,
  target_date: date|None, linked_element_id?}`; Update optional.
- `ApprovalDecision{approve: bool, decided_by (..160), comment (..1000)}`;
  `CommentCreate{body (1..4000), author (..160), artifact_type="baseline" (..40), artifact_id?}`.

### 23.2 `store.py`
- `_require_l1` — must be an L1 element ("Architecture baselines attach only to L1 elements";
  `L1ArchValidationError`).
- Vision: singleton row per L1; `get_vision` returns defaults (all "" + status draft, updated_at None) when
  absent; `update_vision` merges exclude_unset non-None fields and upserts.
- Generic `_list` / `_delete` / `_update` helpers scope items to the project via the `l1_element_id IN
  (SELECT id FROM c4_elements WHERE project_id=?)` join.
- OKRs (order created_at), stakeholders (order name NOCASE; optional resource_staff_id validated to exist —
  "Resource 'X' was not found"), capabilities (order cap_level, name NOCASE; parent capability must belong to
  the same L1; "A capability cannot be its own parent"), risks (order created_at; target_date iso).
- **Approvals** — `APPROVAL_STAGES` (sequential): product "Product owner review", architecture
  "Architecture review", security "Security review", risk "Risk review", finance "Finance review", sponsor
  "Business sponsor approval". `submit_for_review` deletes + recreates all stages as pending.
  `decide_approval(stage, approve, decided_by, comment)` — unknown stage / not submitted -> validation errors
  ("Submit the baseline for review before recording approvals"); **every earlier stage must already be
  approved** ("'X' must be approved before 'Y'"); when ALL stages approved -> vision status set `baselined`;
  a rejection reverts a baselined vision to `draft`. `approval_state` -> `{submitted, stages (with label),
  approved_count, total, rejected, current_stage (first pending), complete}`.
- Comments: list (created_at DESC) / create (status open) / `resolve_comment(resolved=True|False)` toggles
  resolved/open / delete.
- `get_baseline(project_id, l1)` — one call: `{element, vision, okrs, stakeholders, capabilities, risks,
  approvals: approval_state, comments, readiness}` (readiness computed from this same baseline dict).

### 23.3 `service.py` — deterministic readiness + executive summary (no LLM)
`AREA_WEIGHTS = {vision_okrs: 15, stakeholders: 15, capability_map: 15, system_context: 20,
risk_funding: 15, traceability: 10, approval: 10}` (sum 100).

`readiness(project_id, l1, baseline=None)`:
- Context counts: `l2_children` (L2 elements with this parent), `relations` (touching the L1 or its
  children), `diagrams` (l1_diagrams rows).
- Derived: active stakeholders only; `measurable_okrs` (key_result AND target_value non-blank);
  `funded_risks` (funding_source non-blank or approved_budget > 0); `has_role(*keywords)` checks stakeholder
  role substrings.
- 15-item checklist: vision defined; >=1 objective; each objective measurable; primary stakeholders
  identified; business owner assigned (role contains business/sponsor); product owner (product); architecture
  owner (architect); security owner (security); capabilities mapped; system context diagram available
  (l2_children>=1 or diagrams>=1); internal/external systems identified (l2_children>=1); risks captured;
  funding source captured; approvals completed (vision status approved|baselined); L1 linked to >=1
  initiative/epic (l2_children>=1).
- Area scores (0..1): vision_okrs = 0.5*(vision statement present) + 0.5*min(measurable_okrs,1);
  stakeholders = 0.5*(any active) + 0.5*(any Accountable); capability_map = any; system_context =
  min(1, l2_children*0.5 + 0.5*(diagrams>0)); risk_funding = 0.5*(any risks) + 0.5*(any funded);
  traceability = l2_children >= 1; approval = vision approved|baselined.
- `score = round(sum(area * weight))`; labels: >=80 "Ready for L2 architecture review", >=50 "In progress —
  key gaps remain", else "Early draft — foundational artifacts missing".
- `recommendations` — fixed sentence per unfinished area, ordered by weight DESC (see `rec_for` in source).
- Returns `{score, status_label, complete, areas: [{area, weight, score(0-100)}], checklist: [{item, done}],
  gaps, recommendations}`.

`executive_summary(project_id, l1) -> {markdown, readiness_score}` — THE PowerPoint replacement; a single
Markdown doc with sections: `# <name> — L1 Architecture Baseline`, readiness blockquote, `## Vision`
(+business problem/target users bold lines), `## Objectives & Key Results` (md table Objective/Key result/
Metric/Target/Current/Owner/Status), `## Business Capability Map` (mermaid `flowchart TD` root -> capability
nodes, parented via capability parent_id else root; node ids = alnum name[:14]+index), `## Stakeholders &
RACI` (active only), `## Portfolio Risk & Funding` (+ totals line "**Total approved:** X · **Actual:** Y"),
`## Readiness Breakdown` (Area/Weight/Score). Empty sections render italic "_No … yet._" placeholders.
Route returns `{markdown, readiness_score}` — **readiness_score is an int, so the route must be typed
`dict[str, Any]`, not `dict[str, str]`** (a `dict[str,str]` annotation triggers ResponseValidationError).

`traceability(project_id, l1)` — links from OKRs/capabilities/risks (`linked_element_id`) to C4 elements:
`{links: [{artifact_type, artifact_id, artifact_name, linked_element_id, linked_element_name, linked_level,
orphaned}], linked_count, total}`.

`impact_analysis(project_id, l1)` — deterministic consistency findings, severity-sorted (high/medium/low):
orphaned traceability links (high); inactive-but-Accountable stakeholders (high, "reassign accountability");
owner-less capabilities (medium); risks past target_date and not completed (medium); off-track OKRs (medium);
open comments on a baselined vision (low, "consider re-review"). Returns `{findings, high, clean}`.

### 23.4 `exports.py`
Reuses `planning.exports` helpers (`_blocks, _diagram_bytes, _filename, _plain, MarkdownBlock`).
- `executive_markdown` -> (utf-8 bytes of the summary markdown, `<slug>.md`).
- `executive_docx` — Aptos 10.5pt, colored title (heading level-1 blocks skipped as duplicate title),
  bullets/numbers/quotes, mermaid blocks replaced by the client-rendered PNG (6.2" wide) when supplied.
- `executive_pptx` — 13.333x7.5; title slide subtitle "L1 Architecture Baseline · Executive summary";
  H1/H2 flush section slides (16pt paragraphs); mermaid -> picture slide (layout 5, 10.9" wide); code blocks skipped.

### 23.5 `router.py` (prefix `/projects/{project_id}/l1/{l1_element_id}/arch`)
Errors: NotFound->404; L1ArchValidationError->400 `l1arch_validation`.
- `GET ""` (get_baseline), `GET /readiness`, `GET /traceability`, `GET /impact`.
- Comments: `GET|POST /comments`, `PATCH /comments/{id}?resolved=true|false`, `DELETE /comments/{id}`.
- `POST /import/jira` — `JiraImportRequest{instance, project_code (1..50), target="capabilities"|"okrs",
  max_issues=50 (1..200)}`; unknown instance -> 400 `jira_not_configured` ("Jira instance 'X' is not
  configured. Set JIRA_INSTANCES and JIRA_<NAME>_* in backend/.env."); maps issues to OkrCreate(objective=
  title[:400]) or CapabilityCreate(name=title[:200], description=user_story[:1000]); returns
  `{created, target, source: "instance/code"}`.
- `GET /executive-summary` -> `{markdown, readiness_score}` (typed `dict[str, Any]`).
- `POST /executive-summary/export/{md|docx|pptx}` — `{diagram_images: [dataURL]}`; bad fmt -> 400
  `bad_format` "Use md, docx or pptx."; returns attachment with the matching media type.
- Approvals: `POST /approvals/submit` (returns `{stages, **approval_state}`), `POST /approvals/{stage}`
  (ApprovalDecision).
- `PATCH /vision`; CRUD: `POST /okrs`, `PATCH|DELETE /okrs/{id}`; same for `/stakeholders`, `/capabilities`,
  `/risks`.

---

## 24. L2 container architecture — `backend/l2arch/`

### 24.1 `models.py`
`L2Update{summary (..4000), container_diagram (..20000), status: draft|reviewed|approved|baselined|archived|None}`;
`ContainerCreate/Update`, `ApiCreate/Update`, `NfrCreate/Update`, `IntegrationCreate/Update` — field sets
mirror the DB columns and CHECK enums exactly (see section 6 schema; lengths: container responsibilities
..2000, owns_data ..600; api endpoint ..400, version ..40; nfr scenario ..600-ish per source; integration
data_exchanged/security_method free text).

### 24.2 `store.py`
- `_require_l2` — "Container architecture attaches only to L2 elements" (`L2ArchValidationError`).
- `l2_arch` singleton row: `get_l2` (defaults summary/diagram "", raci {}, status draft when absent; raci JSON
  hydrated), `update_l2` upsert (merge exclude_unset non-None; note: the upsert SQL persists summary/
  diagram/status — raci is handled only by `set_raci`).
- Generic `_list/_delete/_update/_create` helpers (project-scoped via join, like l1arch); column lists per
  table: containers `[name, capability, responsibilities, owns_data, owner_team, security_classification,
  nfr_criticality, status]` (ordered name NOCASE); apis `[name, provider, consumer, endpoint, api_type,
  data_classification, authentication, version, owner, status]` (name NOCASE); nfrs `[name, category,
  scenario, metric, baseline, target, owner, risk_level, status]` (created_at); integrations `[name,
  source_system, target_system, integration_type, data_exchanged, security_method, status]` (created_at).
- **RACI**: `RACI_ARTIFACTS = (container_diagram, service_boundaries, api_contracts, data_contracts,
  deployment_topology, nfrs, integration_plan, security_review)`; `RACI_ROLES = (product_owner,
  solution_architect, engineering_lead, security_architect, data_owner, sre, risk_owner)`.
  `set_raci(artifact, role, value)` — value must be R|A|C|I|"" (empty clears the cell); stored as JSON map
  `{"artifact:role": "R"}` read-modify-written; ensures the arch row exists first.
- **Approvals**: `APPROVAL_STAGES` = engineering "Engineering review", security "Security review", nfr
  "NFR review", data "Data ownership review", architecture "Architecture approval", sponsor "Sponsor
  sign-off". Same sequential mechanics as l1arch; all approved -> `l2_arch.status='baselined'`; a rejection
  on a baselined L2 -> status `reviewed`. `approval_state` same shape.
- `get_workspace(project_id, l2)` — `{element, parent ({id,name,level} or None), arch, containers, apis,
  nfrs, integrations, approvals, raci_artifacts, raci_roles, readiness}`.

### 24.3 `service.py`
`AREA_WEIGHTS = {l1_alignment: 10, container_diagram: 15, service_boundaries: 15, api_contracts: 15,
deployment_topology: 10, nfr_coverage: 15, security_review: 10, people_raci: 5, approval: 5}`.

`readiness` area scores: l1_alignment = 1.0 if parent else 0.5; container_diagram = diagram text present or
>=1 container; service_boundaries = fraction of containers with responsibilities AND owner_team;
api_contracts = any APIs; deployment_topology = any integrations; nfr_coverage = any NFRs; security_review =
0.5*(any security-category NFR) + 0.5*(sensitive-classified container OR security NFR); people_raci =
fraction of containers with owner_team; approval = status approved|baselined. Score = round(Σ min(1,area)*w).
11-item checklist + per-area recommendations (see source strings). Labels: >=80 "Ready for L3 component
design" / >=50 "In progress — key gaps remain" / else "Early draft — foundational artifacts missing".

`engineering_summary -> {markdown, readiness_score}` — sections: title `# <name> — L2 Container
Architecture`, readiness quote, "**Linked L1:** …", summary text, `## Container Diagram` (stored diagram or
auto `flowchart LR` root->containers fallback), `## Containers & Service Boundaries`, `## API & Data
Contracts`, `## Non-Functional Requirements`, `## Integration Plan` (md tables), `## Traceability` (mermaid),
`## Readiness Breakdown`.

`traceability(project_id, l2)` — `{l1, l2: {id,name}, l3_children: [{id,name}], l3_count, mermaid}`; mermaid
`flowchart LR` L1->L2->each L3 (or a `none["L3: none yet"]` node).

### 24.4 `imports.py` — offline OpenAPI/Kubernetes parsers
- `ImportError_(ValueError)` (router -> 400). `_load` — JSON first, else `yaml.safe_load` (missing PyYAML ->
  "YAML parsing is unavailable; paste JSON instead."); `_load_all` — JSON single doc else
  `yaml.safe_load_all` (multi-doc manifests).
- `parse_openapi(content)` — requires a dict with `paths` ("Not a recognisable OpenAPI document (no
  'paths')."); one API record per path×method (get/post/put/patch/delete): name `"METHOD /path"[:200]`,
  provider = info.title, endpoint = path[:400], api_type REST, data_classification internal, authentication
  from the first securityScheme (`oauth2->OAuth2, openidconnect->OIDC, apikey->API key, http->HTTP auth`) when
  the op (or spec) declares security, version = info.version, status active. No ops -> "No API operations
  found in the OpenAPI document."
- `parse_kubernetes(content)` — kinds Deployment/StatefulSet/DaemonSet/Service/CronJob/Job, deduped by
  metadata.name; capability from label `app.kubernetes.io/part-of` or `app`; responsibilities "Imported from
  Kubernetes <kind>. Namespace: <ns>."; owner_team from `team`/`owner` labels; classification internal,
  criticality medium, status active. None found -> "No Deployments, StatefulSets or Services found in the manifest."
- `run_import(project_id, l2, kind, content)` — kind `openapi` -> create_api each (-> `{kind, created_apis}`);
  `kubernetes` -> create_container each (-> `{kind, created_containers}`); else error.

### 24.5 `router.py` (prefix `/projects/{project_id}/l2/{l2_element_id}/arch`)
Bodies: `ApprovalDecision{approve, decided_by (..160), comment (..1000)}`; `RaciCell{artifact, role, value=""}`;
`ImportRequest{kind: ^(openapi|kubernetes)$, content (1..200000)}`.
Routes: `GET ""` (workspace), `GET /readiness`, `GET /engineering-summary`, `PATCH ""` (L2Update),
`GET /traceability`, `PATCH /raci`, `POST /approvals/submit`, `POST /approvals/{stage}`, `POST /import`,
and CRUD `POST /containers` + `PATCH|DELETE /containers/{id}`, same for `/apis`, `/nfrs`, `/integrations`.
Errors: NotFound->404; L2ArchValidationError|ImportError_ -> 400 `l2arch_validation`.

---

## 25. L3 component architecture — `backend/l3arch/` (full parity with l2arch, one level down)

- `models.py`: `L3Update{summary (..4000), component_diagram (..20000), status draft|reviewed|approved|
  baselined|archived|None}`; `ComponentCreate/Update`, `InterfaceCreate/Update`, `DependencyCreate/Update`,
  `ConcernCreate/Update` mirroring the DB enums (component_type controller|service|repository|gateway|model|
  client|config|ui|other; interface direction provided|consumed, type REST|GraphQL|gRPC|Event|Function|
  Message; dependency type internal|container|external|library; concern category logging|caching|validation|
  security|error_handling|config|observability|resilience).
- `store.py`: `_require_l3` ("Component design attaches only to L3 elements", `L3ArchValidationError`);
  `l3_arch` singleton (summary/component_diagram/raci/status) with the same get/update-upsert pattern;
  CRUD for components (name NOCASE), interfaces (name NOCASE), dependencies (created_at), concerns
  (created_at); **RACI**: `RACI_ARTIFACTS = (component_diagram, component_breakdown, interfaces,
  dependencies, design_concerns, security, testing, documentation)`, `RACI_ROLES = (product_owner, tech_lead,
  engineer, security_engineer, qa, sre)`, same `set_raci` mechanics; **approvals**: stages design "Design
  review", interfaces "Interface & contract review", security "Security review", testing "Test strategy
  review", architecture "Architecture approval", tech_lead "Tech-lead sign-off" — sequential, all approved ->
  `l3_arch.status='baselined'`, rejection of baselined -> `reviewed`; `get_workspace` -> `{element, parent,
  arch, components, interfaces, dependencies, concerns, approvals, raci_artifacts, raci_roles, readiness}`.
- `service.py`: `AREA_WEIGHTS = {l2_alignment: 10, component_diagram: 15, component_breakdown: 15,
  interfaces: 15, dependencies: 10, design_concerns: 15, security_review: 10, people_raci: 5, approval: 5}`.
  Areas: l2_alignment parent?1:0.5; component_diagram = diagram or >=1 component; component_breakdown =
  fraction with responsibilities; interfaces/dependencies/design_concerns = any; security_review =
  0.5*(security concern) + 0.5*(any interface with authentication); people_raci = fraction of components with
  owner; approval as usual. Checklist (10 items) + recommendations per source. Labels: >=80 "Ready for L4
  implementation" / >=50 / else as before. `engineering_summary` (title "— L3 Component Architecture",
  sections Component Diagram (fallback `flowchart TB` root->components with `<br/>(<type>)` labels),
  Components & Responsibilities, Interfaces & Contracts, Dependencies, Cross-Cutting Design Concerns,
  Traceability, Readiness Breakdown). `traceability` — L2 -> L3 -> L4 children (`{l2, l3, l4_children,
  l4_count, mermaid}`).
- `router.py` (prefix `/projects/{project_id}/l3/{l3_element_id}/arch`): `GET ""`, `GET /readiness`,
  `GET /engineering-summary`, `PATCH ""`, `GET /traceability`, `PATCH /raci`, `POST /approvals/submit`,
  `POST /approvals/{stage}`, CRUD `/components`, `/interfaces`, `/dependencies`, `/concerns`. Errors ->
  404 / 400 `l3arch_validation`. (No import endpoint.)

---

## 26. L4 implementation detail — `backend/l4arch/` (lean: NO approvals, NO RACI)

- `models.py`: `UnitType = class|interface|function|module|config|migration|test`; `TestType = unit|
  integration|e2e|contract|manual`; `ChecklistCategory = code|tests|docs|security|review|deploy`.
  `L4Update{summary (..4000), code_diagram (..20000), status: draft|reviewed|approved|done|archived|None}`;
  `CodeUnitCreate{name (1..200), unit_type=class, responsibility (..1000), tech (..200), path (..400),
  complexity=medium, status: todo|in_progress|done = todo}` (+Update); `TestCaseCreate{name, test_type=unit,
  scenario (..1000), expected (..1000), status: planned|passing|failing = planned}` (+Update) — **both
  TestCase models set `__test__ = False`** so pytest doesn't collect them; `ChecklistCreate{item (1..400),
  category=code, done=False}` (+Update).
- `store.py`: `_require_l4` ("Implementation detail attaches only to L4 elements", `L4ArchValidationError`);
  `l4_arch` singleton get/update-upsert (summary/code_diagram/status); CRUD for code units, test cases,
  checklist items (the `done` INTEGER is hydrated to bool on read); `get_workspace` -> `{element, parent,
  arch, code_units, test_cases, checklist, readiness}`.
- `service.py`: `AREA_WEIGHTS = {l3_alignment: 15, code_units: 25, test_coverage: 25, dod_checklist: 25,
  diagram: 10}`. Areas: l3_alignment parent?1:0.5; code_units = fraction with responsibility; test_coverage =
  any test cases; dod_checklist = done fraction; diagram = code_diagram present (no fallback credit).
  7-item checklist; labels: >=80 "Ready to implement" / >=50 "In progress — details being filled in" / else
  "Early draft — implementation not yet specified". `implementation_summary` — title "— L4 Implementation
  Detail"; `## Implementation Diagram` (stored, else auto `classDiagram` from code units with `<<unit_type>>`
  stereotype + sanitized responsibility method line); `## Code Units`, `## Test Cases` tables;
  `## Definition of Done` rendered as `- [x] **category** — item` task lines; `## Traceability` (upward
  L2 -> L3 -> L4 chain mermaid); `## Readiness Breakdown`. `traceability` -> `{l2, l3, l4, mermaid}`.
- `router.py` (prefix `/projects/{project_id}/l4/{l4_element_id}/arch`): `GET ""`, `GET /readiness`,
  `GET /implementation-summary`, `PATCH ""`, `GET /traceability`, CRUD `POST /code-units` +
  `PATCH|DELETE /code-units/{id}`, `/test-cases`, `/checklist`. Errors -> 404 / 400 `l4arch_validation`.

---

## 27. Frontend — `frontend/` (React 19 + Vite, `@karya/web`)

### 27.1 Tooling
- `package.json` deps: `@xyflow/react ^12`, `lucide-react 0.511`, `mermaid ^11.16`, `react/react-dom 19.1.0`,
  `react-markdown ^10`, `remark-gfm ^4`; dev: vite 6, vitest 3, @vitejs/plugin-react, jsdom,
  @testing-library/react + jest-dom. Scripts: dev/build/preview/test (`vitest run`)/test:watch.
- `vite.config.js`: root = frontend dir, react plugin, `build.outDir: '../dist'` (emptyOutDir), server port
  5173, vitest `environment: jsdom`, setupFiles `./src/test-setup.js` (imports `@testing-library/jest-dom/vitest`).
- `index.html`: `<div id="root">`, loads `/src/main.jsx`, title "Karya".
- `main.jsx`: StrictMode > ToastProvider > AuthProvider > App; imports styles.css, md3.css, ux.css.
- CSS: `md3.css` (Material 3 workspace shell: m3-* classes, top bar, rail, cards, chips, dialogs, canvas,
  tree, chatdock, wf-wizard, login, proj-* home, admin-*), `styles.css` (older estimation components:
  input-card, pipeline-card, result-card, tables), `ux.css` (shared UX polish: res-pill, l1-*, level-nav,
  ask-ai, ai-decompose, dockable panel, toast-stack). Tests colocate as `*.test.jsx`.

### 27.2 API client — `src/api/client.js`
- `API_BASE = window.karya?.apiBaseUrl || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'`
  (trailing slash stripped) — the Electron preload injects `window.karya`.
- Auth: reads localStorage key `karya.auth.user`; sends `X-User-Id` (staff_id) and `X-User-Role` headers on
  every request (`withAuth`).
- `jsonRequest` — fetch + JSON, on !ok throws `Error(detail.message)` with `.payload` from
  `body.error || body.detail || body`.
- `downloadRequest` — returns `{blob, filename}` (filename parsed from Content-Disposition, fallback
  "requirements-export").
- `consumeSSE(path, payload, onEvent, signal)` — POST with Accept text/event-stream; reads the body stream,
  splits on blank lines, parses `event:`/`data:` lines, calls `onEvent(event, JSON.parse(data))`.
- `api` object — one wrapper per backend endpoint (names mirror the route list in sections 9–26:
  config/health/jiraInstances/jiraIssues/parseUpload/estimate/estimateBatch/estimateUpload/writePoints/
  templateUrl; project + c4 + rollup + estimateElement; the full l1 plan/diagram/requirements set incl.
  generateDiagram/assistDiagram/assistProjectDiagram + exportRequirement; resources staff/lookups/
  custom-fields plus Excel template/import and LDAP/Active Directory import; access users, page registry,
  effective-user access and per-user page overrides; reporting; agentic AI (reportingNarrative,
  aiStaffing/applyStaffing, aiDecompose/
  applyDecompose, aiScaffold/applyScaffold, aiL1Baseline/applyL1Baseline, aiL2/3/4Baseline + applies,
  aiOrchestrate, aiSummarize); l1 arch CRUD + approvals + exportL1Summary + traceability/impact/comments +
  importJiraToL1; full l2/l3/l4 arch CRUD + raci + approvals + imports; workflowGuide; chat + chatStream +
  chatApply + conversations + attachments upload; integrationCatalog + per-connector config/test/clear).

### 27.3 Auth — `src/auth/`
- `permissions.js` — `ROLE_LABELS` + `ROLE_CAPS` **identical to the backend map** (section 10.1),
  `CAPABILITY_PAGE`, and `can(role, capability, pagePermissions)`. An explicit page override wins over the
  role default; administrator remains an unconditional allow safeguard.
- `AuthContext.jsx` — localStorage-persisted `{staff_id, name, role, staff_code, page_permissions}` under
  `karya.auth.user`; provides `{user, role, signIn, signOut, can, refreshAccess}`. For directory identities,
  sign-in and window-focus call `GET /access/me` so role/page changes take effect without a new browser
  session. `useAuth()` throws outside the provider.

### 27.4 App shell — `src/App.jsx`
State-based router (no router lib): `route.name ∈ home | wizard | project | quick | admin`. Renders `Login`
when signed out. On identity change, always resets to home (avoids showing a prior session's admin page).
Loads `/config` + `/health` after sign-in; top bar shows the LLM chip ("provider · model" or "LLM not
configured") and per-Jira-instance ok/bad chips + a user menu (avatar initials, sign-out). Top-level entries
are gated individually by `page.platforms`, `page.workspace`, `page.ask_ai`, and `page.guide`; Admin appears
when at least one Admin subsection capability is effective. **Ask AI** opens `AskAiDialog` →
`/ai/orchestrate`; `resolveAiDestination`
maps the action to a workspace tab / admin / needs-open-project toast; mapping in `askAiRouting.js`:
generate_l1_baseline→planning, auto_staffing→planning, decompose_story→canvas, scaffold_c4→canvas,
review_readiness→rollup, reporting_narrative→admin. The Guide link is cache-busted as
`/help/guide.html?v=20260722`. Configuration
errors from `/health` render as an error banner. `workspaceTab` token forwards Ask-AI tab requests into the
open ProjectWorkspace.

### 27.5 Screens — `src/screens/`
- **Login.jsx** — fetches `/access/login-users`; searchable identity list (name/staff code); picking one
  calls `signIn`; when the directory is EMPTY offers "Continue as Administrator" (`{staff_id: null,
  role: 'admin'}` — the header-role bootstrap admin). Footer: "Local demo sign-in — no password required."
- **ProjectsHome.jsx** — hero + card grid of projects (deterministic avatar color from name hash over 8 M3
  tonal pairs; leads avatars; "Stories estimated x/y · %" progress bar from story_count/estimated_count;
  repo/jira chips; delete button with confirm), an add-card + FAB (both gated by `platform.create`), empty
  state, retry banner.
- **NewProjectWizard.jsx** — 4-step stepper (Basics: name/description/LeadsEditor/sensitivity select
  standard|restricted; Code repo: existing|new mode + url + local path; Jira: instance from config + key;
  Seed C4: blank | scan local repo (needs path) | import Jira (needs link)). Finish: createProject → optional
  addRepo/addJiraLink → optional importRepoScan(apply:true) or importJira; `onDone(projectId, notice)`.
- **ProjectWorkspace.jsx** — hosts a left `DockablePanel` nav rail with TABS: canvas / planning ("L1 plan") /
  l2arch / l3arch / l4arch (all three lazy-loaded) / rollup / quick / overview; header **Workflow guide**
  button opens `WorkflowWizard`. Maintains per-level target ids (planningL1Id, l2Target, l3Target, l4Target)
  and `openElement(element)` which deep-links any element to its level tab. `graphVersion` counter bumps on
  chat-apply so graph-holding tabs refetch. Mounts `ChatDock` with `screenContext = {tab, tab_label, level
  (planning→L1 … l4arch→L4), element_id}`. The `Overview` tab: project summary card, LeadsEditor save,
  "Seed / grow the C4 model" (repo scan with local path + Jira import — both create *proposed* elements),
  add repo link, add Jira link forms.
- **WorkflowWizard.jsx** — modal stepper over `GET /workflow`: overall % bar + stage + "Next best step" CTA;
  steps = 4 levels + Estimation; each step shows status pill (not_started/in_progress/ready), stats (counts,
  ready x/y, avg readiness % / estimation totals), a readiness bar, and the recommended actions — clicking
  one calls `onNavigate(tab)` and closes.
- **QuickEstimate.jsx** — the original single-story flow: `SourceSwitcher` (manual | jira | upload);
  manual → `StoryForm` (title, user story, dynamic AC list, technical breakdown) → `api.estimate` SSE;
  jira → `JiraBrowser` (instance/project/status/sprint fetch, checkbox select, "Estimate selected") →
  `estimateBatch`; upload → `ExcelUpload` (drag-drop + template download) then `ColumnMapper` (5 target
  fields with suggested mapping, mapped-column preview, row selection max 100) → `estimateUpload`.
  Right pane `PipelineView` (live steps); `BatchTable` lists batch results (click → `ResultCard`);
  `ResultCard` shows the single result; Jira write-back button per row when `jira_write_enabled` (confirm
  dialog → `writePoints` with confirm:true).
- **AdminConsole.jsx** — capability-filtered sections: Access management (`admin.access`), **Page
  permissions** (`admin.access`), Reporting (`admin.reporting`), Resources (`admin.resources`), and
  Integrations (`admin.integrations`). It selects the first section the current identity may access.
- **admin/AccessManagement.jsx** — user table (search by name/code), role `<select>` per row + enabled
  toggle via `PATCH /access/users/{id}`; guards demoting/disabling the LAST enabled admin client-side.
- **admin/PagePermissions.jsx** — searchable person × page matrix over the server page registry. Each cell
  selects Role default / Allow / Deny and persists only an override; role-default effective state is shown
  in the control. Administrator cells are fixed allowed. Clicking a person opens a complete profile dialog
  assembled from the directory, lookups, custom fields, manager/direct reports, application access, and the
  effective permission source for every page.
- **admin/Reporting.jsx** — stat cards + breakdown bars from `/reporting/overview` (portfolio, resources,
  per-platform table) + an **AI summary** button calling `/reporting/narrative` and rendering
  headline/summary/highlights/risks/recommendations.
- **admin/Integrations.jsx** — catalog groups from `/integrations/catalog` with status chips
  (Connected / In-app adapter / Available) and per-tool **Configure/Manage** dialog (renders the connector's
  field schema; secret fields masked with "saved" hint from `secrets_set`, blank keeps existing; enable
  toggle; Validate → `/test`; Disconnect → DELETE config); plus the "AI command router" box →
  `/ai/orchestrate`.
- **ResourceDirectory.jsx** — staff table with filters (status/sub-status/type/tech-unit/rank/hr-role +
  search), add/edit staff dialog (fixed columns + reporting manager select + custom-field inputs rendered by
  type), delete; **"Lists & fields" dialog** managing the three lookup tables and custom-field definitions
  (text/number/date/select/boolean, required, options). The import actions download an Excel template,
  upload `.xlsx`/`.xls`/`.csv` files for preview + confirmed bulk upsert, or open the directory dialog for a
  single/bulk LDAP or Active Directory pull (base/filter/limit/update-existing controls and result summary).

### 27.6 C4 canvas — `src/c4/`
- **C4Canvas.jsx** — React Flow canvas of the CURRENT drill level (breadcrumb "System landscape ▸ …";
  double-click drills into non-L4 nodes). Custom `c4` node: level chip, points badge, name, tech, child
  count. Node positions persist via `PATCH element {pos_x,pos_y}` on drag stop; connecting two nodes prompts
  for a label and creates a relation; clicking an edge confirms deletion; async relations animate, `data`
  relations are dashed. Toolbar: **AI scaffold** (landscape only — description → `/c4/ai/scaffold` →
  preview of elements/relations → apply as proposed), "Add <kind> (Lx)" (next level for the drill context),
  refresh. Right `DockablePanel` hosts `InspectorPanel`; estimation opens `EstimateDialog`; per-element
  results cached in a `Map` ref so "View reasoning" reopens without re-running.
- **InspectorPanel.jsx** — selection details: level/artifact chip, name, delete (confirm, cascades),
  proposed banner with **Accept** (status→active), story-points summary block for L3/L4 (Estimate /
  Re-estimate / View reasoning), non-estimable note otherwise; **L1 nodes** get an operating-plan summary
  card (squads/people, monthly run-rate, approved budget via Intl currency of the plan's currency_code,
  diagram count, work/at-risk/FTE line) with "More details" → the L1 plan tab; key-value list (tech,
  code_path, status, artifacts with points + jira key); description editor (Save); actions: Tag bug,
  Link Jira (prompt for key), Create in Jira (only when write enabled; confirm), **AI: suggest stories**
  (non-L4; `/ai/decompose` → checkbox review → apply as proposed children).
- **EstimateDialog.jsx** — modal; auto-starts when no cached result; streams `estimateElement` (`node`
  events → `PipelineView` steps; `result` → `ResultCard` + cache callback; `error` banner); refinement input
  + "Refine" reruns with the same session; Escape/scrim closes and aborts; hidden-tasks notice ("added under
  this element as proposed L4 tasks"). StrictMode-safe auto-start guard.
- **RollupDashboard.jsx** — totals stat row (rolled-up points, estimated, pending, spikes, splits pending);
  collapsible tree (level chip, clickable name → `onNavigate(element)` deep-link, points column, coverage
  "x/y stories" or Jira key, flag chips spike/split-pending/proposed); **Estimate all pending (n)** loop —
  sequentially runs `estimateElement` for every non-proposed unestimated L3 with progress chip + Stop.

### 27.7 Planning workspaces — `src/planning/`
- **L1Planning.jsx** — L1 initiative picker (from the graph) + collapsible header (metrics chips) +
  section tabs: `baseline` (default → L1Architecture), `requirements` (RequirementsPlanning), `teams`
  (TeamPlanning), `work` (WorkCostPlanning), `architecture` (ArchitecturePlanning diagrams). Currency select
  (USD/EUR/GBP/INR/AUD/CAD/JPY/SGD) → `PATCH plan`. `LevelBreadcrumb` navigation. Lazy-loads the heavy sections.
- **L1Architecture.jsx** — the L1 baseline tab set: Vision & OKRs / Stakeholders & RACI / Capabilities /
  Risk & Funding / Governance / Discussion / Executive summary. Readiness gauge + checklist from the
  baseline payload; generic field-schema-driven add/edit `PlanningDialog`s per artifact (schemas mirror the
  backend models; `type:'element'` renders a C4-element dropdown for traceability links); vision editor with
  "more details" markdown editors + `AiAssist` summarize buttons (fields vision/problem/users); **AI generate
  baseline** (brief → `aiL1Baseline` → section-checkbox review → `applyL1Baseline`); Governance tab =
  impact-analysis findings + submit-for-review + sequential approval chain (approve/reject with comment);
  Discussion tab = comments post/resolve/delete; Executive summary tab renders the markdown via
  `MarkdownViewer` (live Mermaid) with **Download md/docx/pptx** (renders mermaid to PNGs via
  `renderMermaidImages` and POSTs them so Word/PPTX embed diagrams). `FlowForward` bridges vision→epics.
- **TeamPlanning.jsx** — tribes/squads hierarchy or grid view; unit add/edit dialog (type, name, parent
  tribe, mission, directory-backed lead, capacity FTE, target velocity). The lead selector lists active
  resources and, for `admin.resources`, offers **Add new lead…**: create the missing staff record inline,
  de-duplicate by name, refresh the shared resource data, and select the new person. Member dialog links to
  active directory staff via select — or free-text name, role, skills, location, allocation %, monthly cost;
  computed unit
  run-rates; **AI staffing** (`aiStaffing` → proposal list with reasons, checkbox select → `applyStaffing`,
  reports partial errors).
- **WorkCostPlanning.jsx** — work-item table + timeline bars (min/max date span), add/edit dialog (title,
  description, squad select, linked element select (L2–L4 descendants of the L1), start/end dates, status,
  allocation %, budget/actual cost); cost metrics from the plan payload.
- **ArchitecturePlanning.jsx** — the L1 diagram library: list + inline editor (title/type/source) with
  `MermaidView` preview, create-from-template (`diagramCatalog`), **Generate with AI** (prompt+type →
  `generateDiagram`), **Open studio** (DiagramStudio), download SVG, delete.
- **DiagramStudio.jsx** — full-screen visual mermaid editor for FLOWCHARTS: React Flow canvas bridged
  bidirectionally to mermaid text via `mermaidModel.js` (`parseFlowchart` / `modelToMermaid`; non-flowchart
  types fall back to text-only editing with preview); node palette (30+ v11 shapes in `NODE_SHAPES` with
  open/close bracket pairs or `@{ shape: … }` syntax), edge types (arrow/open/dotted/thick), direction,
  subgraph groups; per-node metadata inspector (explanation, custom properties, links, documents — stored in
  the diagram's `metadata` JSON keyed by node id, plus node positions); AI assist chat (`assistDiagram` /
  `assistProjectDiagram` with history) that returns full updated diagrams; save via `onSave(source, metadata)`.
- **diagramCatalog.js** — grouped catalog of the 24 diagram types (Workspace views / Systems and delivery /
  Data & domain / Planning & tracking / Analysis charts …), each `{id, label, title, template}` with rich
  mermaid starter templates; `DEFAULT_DIAGRAM_TYPE='architecture'`, `getDiagramType`, `diagramTypeLabel`.
- **mermaidModel.js** — the flowchart text↔model bridge: model `{direction, nodes:[{id,label,shape}],
  edges:[{id,source,target,type,label}], groups:[{id,title,members}], supported}`; `NODE_SHAPES` (28 shapes
  with mermaid v11 shape names + aliases), `EDGE_TYPES` (arrow `-->`, open `---`, dotted `-.->`, thick
  `==>`), `DIRECTIONS` (LR/TB/RL/BT); `parseFlowchart(source)` (regex-based, tolerant; marks unsupported
  diagrams), `modelToMermaid(model, metadata)`, `nextNodeId`.
- **RequirementsPlanning.jsx** — versioned L1 requirement documents: document list (status chips, open
  comments), `MarkdownEditor` (toolbar: bold/italic/strike/code/heading/lists/task list/quote/table/link/
  image/mermaid-block insert (`MERMAID_BLOCK_TEMPLATE`), edit/split/preview modes with live mermaid preview,
  DiagramStudio hook for editing embedded mermaid blocks), save with `expected_version` (409 conflict
  surfaced), review actions submit/approve/revoke, threaded comments (approve/resolve/reopen), version
  history viewer, audit trail, export docx/pptx with rendered diagram PNGs, a `STARTER` markdown template,
  `FlowForward` (requirements → proposed L2 epics).
- **L2Architecture.jsx / L3Architecture.jsx / L4Architecture.jsx** — the per-level workspaces (nav-rail
  tabs). Common shape: element picker (L2/L3/L4 elements of the project) + `LevelBreadcrumb`; readiness
  gauge + checklist + gaps/recommendations; tab sets:
  - L2: Container diagram (split `MermaidWorkbench` editor+preview + "Open studio"), Containers & boundaries,
    APIs & Data, NFRs, Integration plan, RACI (grid of `<select>` cells over RACI_ARTIFACTS×RACI_ROLES with
    the label maps), Governance (submit + sequential approvals), Traceability (mermaid), Engineering summary
    (MarkdownViewer). Header **Import** dialog (OpenAPI → APIs, Kubernetes manifest → containers). "AI
    generate L2" (brief → draft → section review → apply).
  - L3: Component diagram, Components, Interfaces & contracts, Dependencies, Design concerns, RACI,
    Governance, Traceability, Component summary; "AI generate L3"; `FlowForward` story→tasks.
  - L4: Implementation diagram, Code units, Test cases, Definition of Done (toggleable checklist),
    Traceability, Implementation summary; "AI generate L4"; **Dev handoff** button — `devHandoff.js
    buildDevHandoff(workspace)` renders a self-contained Markdown brief (story context, implementation
    summary, code units with meta, test cases given/expect, DoD checkboxes, design diagram, working
    agreement with suggested branch `feat/<slug>`) for pasting into a coding agent; `handoffFilename`.
  All artifact tables use field-schema-driven `PlanningDialog` add/edit forms mirroring the backend models.
- **PlanningDialog.jsx** — shared modal (scrim, header+close, body, actions footer, `wide` variant).

### 27.8 Shared components — `src/components/`
- **PipelineView** — the 9 node labels in order: score_parameters "Score parameters", identify_drivers
  "Identify drivers", compare_to_anchors "Compare anchors", derive_points "Derive points",
  spike_split_branch "Spike / split check", write_plain_language_reasoning "Write plain-language why",
  detect_hidden_tasks "Find hidden work", assess_risks "Assess risks", recommend_split "Recommend split" —
  rendered with done/current/pending icons, aria-live.
- **ResultCard** — refuses to render without `plain_language_why`+`tldr` ("An estimate was withheld because
  its required explanation is missing."); SPLIT/SPIKE banner; big points headline on the Fibonacci scale
  [1,2,3,5,8,13]; TL;DR + why; collapsible details: Scorecard (12-parameter table with Low/Medium/High
  pills), Drivers, Anchor comparison (+anchor_titles chips), Effort (`EffortBar` optimistic/likely/
  pessimistic person-days + react/spring/existing_code notes), Hidden tasks, Risks & assumptions, Split
  recommendation (proposed stories); Download JSON + Markdown export; optional Jira write button.
- **BatchTable** — batch results table (key/title/points/spike/split, row click selects), **StatusBadge**,
  **ErrorCard** (shows `error.payload` details when present), **SourceSwitcher** (manual/jira/upload
  segmented control), **StoryForm/JiraBrowser/ExcelUpload/ColumnMapper** (described under QuickEstimate),
  **LeadsEditor** (name+role row list add/remove).
- **ChatDock** — floating Assistant (FAB → panel; window modes float/docked/max persisted in localStorage
  `karya.chatdock.mode`). Mode chips Auto/Chat/Code/Research/Image/Document (persisted `karya.chat.mode`)
  set the backend `mode`. Sends via `chatStream` SSE showing live **agent activity** (Planner/Retrieval/
  Tools branch chips + Judge verdict from the concurrent graph), falls back to plain `POST /chat` if the
  stream fails. Replies render as GFM markdown; structured `DataView` for list (clickable element rows →
  `onOpenElement`), per-element readiness/status rows and level-overview chips. Descriptions are drawn from
  deterministic application data after name resolution, including scoped L2/L3/L4 architecture details;
  **proposed mutations** render an
  Apply/Dismiss card (Apply hidden without `platform.edit`; apply → `chatApply` → toast + `onChanged`
  refresh + "Open <name>" deep-link); "Agent evidence" collapsible (retrieval summary, tool calls, judge
  reason). Conversation history sidebar (list/new/open/delete via the conversations API; first user message
  titles the chat), attachment upload (10 max, chips with remove), Web Speech API mic input + optional
  spoken replies (SpeechSynthesis), suggestion chips on first open.
- **MarkdownEditor.jsx** — `MarkdownEditor` (toolbar + edit/split/preview modes, textarea with selection
  helpers, mermaid fence support), `MarkdownViewer` (ReactMarkdown + remark-gfm where ```mermaid blocks
  render via `MermaidView`), `renderMermaidImages(markdown)` — renders every mermaid block to PNG data URLs
  (via mermaid → SVG → canvas) for the export endpoints, `MERMAID_BLOCK_TEMPLATE`.
- **MermaidView.jsx** — shared debounced mermaid preview (150ms) with fit-to-container SVG, maximize portal
  popup with zoom/pan, onError + onSvg callbacks. **mermaidRuntime.js** — singleton
  `mermaid.initialize({startOnLoad:false, securityLevel:'strict', theme:'base', themeVariables: {M3 palette,
  Roboto}})` + `renderMermaid(source, id)`.
- **MermaidWorkbench.jsx** — reusable split editor (Edit/Split/Preview modes, type select over the catalog,
  AI generate prompt dialog via `assistProjectDiagram`, copy/download SVG, save button, "Open studio" hook).
- **AiAssist.jsx** — small "AI summarize → field" button; `getSource()` → `/ai/summarize` → `onResult`.
- **FlowForward.jsx** — "flow forward" bridge: `/ai/decompose` with caller context as guidance → review
  dialog (all preselected) → apply as proposed children one level down.
- **LevelBreadcrumb.jsx** — ancestor trail (L1 › L2 › …) + child drill chips; navigates via `onNavigate(element)`.
- **DockablePanel.jsx** — collapsible/resizable sidebar wrapper; persists `{width, collapsed}` per id in
  localStorage; drag gutter on the inner edge.
- **Toast.jsx** — `ToastProvider` + `useToast()` (`success/error/info`), auto-dismiss 3.5s (errors 6s),
  accepts Error objects (uses `.message`).
- **askAiRouting.js** — pure action→destination map (tested), see 27.4.
- **devHandoff.js** — pure Markdown builder (see L4 above).

Frontend tests (vitest + Testing Library, jsdom): `InspectorPanel.test.jsx`, `RollupDashboard.test.jsx`,
`AiAssist.test.jsx`, `AskAiDialog.test.jsx`, `ChatDock.test.jsx`, `DockablePanel.test.jsx`,
`FlowForward.test.jsx`, `LevelBreadcrumb.test.jsx`, `MermaidWorkbench.test.jsx`, `ResultCard.test.jsx`,
`askAiRouting.test.js`, `ProjectsHome.test.jsx`, `DiagramStudio.test.jsx`, `L2Architecture.test.jsx`,
`RequirementsPlanning.test.jsx`, `TeamPlanning.test.jsx`, `PagePermissions.test.jsx`,
`ResourceDirectory.test.jsx`, `permissions.test.js`, `devHandoff.test.js`, `mermaidModel.test.js`.

---

## 28. Desktop app — `desktop/` (Electron + PyInstaller)

- **`electron/main.cjs`** — Electron main process. Startup: single-instance lock; `startBackend()` then
  `createMainWindow()`; errors → dialog + quit.
  - `KARYA_EXTERNAL_API_URL` env short-circuits backend launch.
  - `chooseBackendPort()` — prefer `KARYA_API_PORT` or **8765**; if something already answers `/health`
    there, REUSE it (dev backend + desktop coexist); else use it if free; else a random free port.
  - `backendCommand()` — packaged: walk `process.resourcesPath/backend` for `karya-api(.exe)`;
    unpackaged: `<python> -m desktop.backend_launcher` from the repo root (python found from $PYTHON,
    venv/.venv, `python`/`python3`).
  - `desktopBackendEnv(port)` — sets PYTHONUNBUFFERED, KARYA_API_HOST=127.0.0.1, KARYA_API_PORT,
    `KARYA_DB=<userData>/data/karya.db`, `KARYA_ENV_FILE=<userData>/backend.env` (created on first run from
    the packaged `backend.env.example`, dev template, or an inline mock-mode fallback), KARYA_DESKTOP=true,
    and CORS_ORIGINS merged with `null` + the localhost dev origins (Electron `file://` renderers send
    Origin "null").
  - Spawns the backend (stdio inherit in dev; piped to `<userData>/backend.log` when packaged); races
    `waitForBackend` (poll `/health` every 350ms, 45s timeout) against early process exit; an unexpected
    later exit shows an error box.
  - Window: 1440×940 (min 1100×760), `backgroundColor #f8fafd`, contextIsolation on, nodeIntegration off,
    preload `preload.cjs`, **`additionalArguments: ['--karya-api-base=<url>']`** — the UI never bakes in the
    API URL. Loads `ELECTRON_DEV_SERVER_URL` when set (dev; `KARYA_OPEN_DEVTOOLS=true` opens devtools) else
    `dist/index.html`. `window.open` → external browser. `stopBackend` on quit (Windows: `taskkill /T /F`).
- **`electron/preload.cjs`** — exposes `window.karya = {apiBaseUrl (from the --karya-api-base argv, default
  http://localhost:8000), mode: 'electron', platform}` via contextBridge.
- **`backend_launcher.py`** — `uvicorn.run("backend.api.main:app", host=KARYA_API_HOST or 127.0.0.1,
  port=KARYA_API_PORT or 8765, log_level=KARYA_LOG_LEVEL or info, reload=False)`.
- **`backend.env.example`** — safe offline defaults (mock provider), commented local-LLM + Jira examples,
  CORS including `null`. Copied to the user's app-data on first desktop launch.
- **`pyinstaller/karya-api.spec`** — Analysis of `desktop/backend_launcher.py`; hiddenimports =
  `collect_submodules("backend")` (minus tests) + langchain_anthropic/google_genai/groq/mistralai/openai,
  langgraph, langgraph.checkpoint.sqlite, docx, pptx, and `ldap3`; `KARYA_BUNDLE_LOCAL_LLM=1` additionally bundles
  transformers/accelerate/safetensors/torch + sentencepiece/tiktoken(+tiktoken_ext.openai_public). onefile
  EXE `karya-api`, console=True. **A new LLM provider or optional dep must be added to hiddenimports** or
  it's missing at runtime.
- **`desktop/package.json`** (`@karya/desktop`) — scripts: `dev` (concurrently: vite dev + wait-on 5173 +
  `ELECTRON_DEV_SERVER_URL=http://127.0.0.1:5173 electron electron/main.cjs`), `backend:bundle`
  (build-backend-bundle.mjs), `icon` (generate-desktop-icon.mjs, uses sharp on `assets/icon.svg`),
  `prepare-app` (icon + web build + backend bundle), `build[:win|:mac]` / `pack` → electron-builder (config
  lives in ROOT package.json `build`: appId com.karya.app, productName Karya, output `release/`, files
  dist/** + desktop/electron/**, extraResources backend-dist→backend + backend.env.example; win nsis+portable,
  mac dmg+zip). devDeps: electron ^43, electron-builder ^26, concurrently, cross-env, wait-on, sharp.
- **`scripts/build-backend-bundle.mjs`** — finds a python that can `import PyInstaller` (else prints install
  instructions), cleans `desktop/backend-dist` + `backend-build`, runs PyInstaller with the spec, outputs
  `desktop/backend-dist/karya-api(.exe)`.

---

## 29. Root scripts & seeds — `scripts/`

- **run-python.mjs** — resolves Python from `$PYTHON`, `.venv`, `venv`, `py -3.11` (win), `python3`/`python`
  (validating each with `--version`), then spawns it with the requested args from the repo root; exits with
  the child's status. All root `api:*` npm scripts go through it.
- **run-monorepo.ps1** — PowerShell task wrapper: `dev|web|api|desktop-dev|test|build|seed-demo|seed-banking`
  → the matching npm script, exiting on failure.
- **seed_demo.py** — creates "Payments platform (demo)" project + repo link + a small C4 model (L1 system,
  L2 payments-web/payment-service/ledger-db with positions, L3 components, relations, one pre-set artifact)
  directly through the stores. Safe to re-run (new project each time).
- **seed_banking.py** — richer multi-level retail-banking sample; descriptions written as estimation
  evidence so every L3 is immediately estimable; includes relations, cross-cutting tags, artifacts.
- **seed_resources.py** — idempotently seeds the **Northstar Digital** sample organization: 47 people
  (45 active, 2 inactive), an executive-to-team reporting hierarchy across eight tech units, realistic HR
  roles/ranks/locations/skills, application roles, and selected page-permission examples. Stable employee
  numbers plus `sample_seed=northstar_sample_organization_v1` identify owned rows; re-runs update only those
  records and their reporting lines, never user-created people matched merely by name. It also creates the
  required lookups/custom fields when absent. Run with `npm run api:seed:resources`.
- **setup_local_llm.py** — one-time local-model prep: requires `LLM_PROVIDER=local`; downloads/validates the
  configured HF model + tokenizer into the cache; `--verify-load` additionally loads weights onto the device
  as a RAM/VRAM test. (`scripts/testlocalpathllm.py` is a manual localpath smoke script.)
- **generate-desktop-icon.mjs** — renders `desktop/assets/icon.svg` to the png/ico/icns set via sharp.

---

## 30. Backend tests — `backend/tests/` (pytest + pytest-asyncio)

- `pytest.ini`: `asyncio_default_fixture_loop_scope = function`.
- `conftest.py` — autouse fixture resetting the process-wide checkpointer (`set_checkpointer(None)`) and
  clearing the cached estimation graph after EVERY test: TestClient tests install the durable
  AsyncSqliteSaver process-wide, which otherwise leaks into later direct-graph tests
  ("threads can only be started once").
- Tests run against `LLM_PROVIDER=mock` and a temp `KARYA_DB`; FastAPI `TestClient` for API tests with
  `X-User-Role: admin` style headers for RBAC. Suite (25 files): test_access (roles, page registry,
  effective overrides and safeguards), test_ai (agentic proposals +
  applies), test_c4_store (level rules, artifacts, rollup), test_chat (interpreter routing, dispatch,
  proposals/apply, attachments, conversations — largest file), test_deep_flow / test_deep_invariants /
  test_deep_rbac_abac (end-to-end + invariant + security sweeps), test_diagram_ai, test_graph_routing
  (escalation branch), test_ingest, test_integrations (catalog/status/config secrets), test_l1_planning
  (plan invariants + metrics incl. `test_full_operating_plan_and_cost_metrics`), test_l1arch (readiness,
  approvals, exec summary incl. `test_executive_summary_endpoint_returns_200` and
  `test_jira_import_requires_configured_instance`), test_l2arch / test_l3arch / test_l4arch, test_local_llm
  (message normalization, load states, GGUF rejection), test_mapping (Jira ADF/AC mapping), test_mock_llm
  (determinism), test_rbac (route policy), test_resources, test_structured_output (`_parse_structured_result`
  quirks + `_schema_contract` and provider error wrapping), test_support_all, test_workflow. Resource tests
  cover Excel preview/commit, LDAP mapping/import boundaries, directory invariants and custom fields.

---

## 31. Cross-cutting invariants & regeneration checklist

Non-negotiable behaviors to preserve when regenerating:

1. **Provider boundary** — provider/model strings appear ONLY in `backend/llm/factory.py` (and env files).
   Adding a provider = editing the factory (+ PyInstaller hiddenimports for desktop).
2. **Point-with-explanation invariant** — the SSE `result` event is atomic and the server raises if
   `plain_language_why` or `tldr` is missing; the frontend `ResultCard` also refuses to render without them.
3. **Deterministic aggregations** — roll-ups, plan metrics, reporting, readiness scores, workflow guide,
   executive summaries are pure computations; the LLM never produces numbers that persist.
4. **Proposal-first AI** — every agentic service returns a draft; separate `/apply` endpoints persist after
   user review; scaffold/decompose/import outputs land as `status='proposed'` and are excluded from roll-ups.
5. **RBAC + page-override parity** — `backend/auth/permissions.py` and
   `frontend/src/auth/permissions.js` must stay identical. For page capabilities an explicit per-user
   Allow/Deny overrides the role default in both UI and API; administrators are always allowed to prevent
   lockout. `route_policy` is the backend enforcement map; ABAC restricted-project checking runs after it.
6. **C4 level rule** — a parent is exactly one level up, enforced in the store AND re-checked on chat apply
   (`_resolve_parent`).
7. **Jira write-back triple gate** — env flag + request confirm + UI confirmation.
8. **Config errors never crash startup** — they land in `app.state.configuration_errors`; `/health` reports;
   LLM-dependent routes 503.
9. **Secrets are write-only** in integration configs (`secrets_set` only on read; blank = keep).
   Directory imports obtain enabled connector credentials through server-only `runtime_config`; secrets
   never cross the API response boundary.
10. **Session/thread continuity** — estimation session_id == LangGraph thread_id; refinement reuses the
    stored artifact session id.
11. **Mock-mode completeness** — `LLM_PROVIDER=mock` must exercise every LLM-touching feature offline with
    deterministic outputs (title-hash points; label-parsing agentic builders). The prompt section labels
    (RESOURCE POOL, L1 INITIATIVE:, DIAGRAM TYPE:, USER MESSAGE:, `- L2 · name (status)` listings, …) are
    load-bearing contracts between agents.py/diagram_ai.py and llm/mock.py.
12. **Desktop URL injection** — the web bundle must read `window.karya.apiBaseUrl` before VITE_API_BASE_URL.
13. **Deterministic chat reads** — recognized list/status/readiness/description questions must resolve names
    against the graph, then use application stores/readiness services for facts. The LLM only interprets
    intent. `ChatCommand.status` normalizes provider booleans to strings so Groq/local/localpath/mock/hosted
    output quirks do not fail Pydantic validation.
14. **Resource write path** — manual entry, inline lead creation, Excel/CSV import and LDAP/AD import all
    persist through `backend.resources.store`; lookup, manager, custom-field and staff-code invariants remain
    centralized there.
15. **Idempotent sample organization** — the resource seed owns rows only through stable employee numbers
    plus its `sample_seed` marker; it must never rewrite unrelated user-created directory records.
16. Keep `AGENTS.md` in sync with `CLAUDE.md` when editing architecture notes.

### Suggested regeneration order
1. Scaffold repo + root/front/desktop package.json, requirements, env examples, pytest.ini.
2. `backend/storage/db.py` (schema) → `config.py` → `models.py` → `anchors.py`.
3. `llm/` (factory, mock, local) → `graph/` (state, nodes, checkpoint, build).
4. `api/streaming.py` + `api/main.py` skeleton → `auth/` → `access/` → `projects/` → `c4/` (+scan).
5. `ingest/`, `jira/`, `planning/` (+requirements/diagram_ai/exports), `resources/`, `reporting/`.
6. `l1arch/` → `l2arch/` (+imports) → `l3arch/` → `l4arch/` → `workflow/`.
7. `ai/` (schemas, masking, nl, agents, router) → `chat/` (store, service, graph, router) → `integrations/`.
8. Frontend: client.js + auth + shell → QuickEstimate components → C4 canvas → planning workspaces →
   admin screens → ChatDock + shared components.
9. Desktop shell + PyInstaller + scripts + seeds.
10. Tests last, validating every invariant above; run `npm run test:all` with `LLM_PROVIDER=mock`.
