"""SQLite persistence for projects, C4 models, and artifact links.

Standard-library sqlite3 keeps the storage layer dependency-free. Connections
are short-lived (one per operation) with WAL enabled, which is safe under the
app's low write concurrency.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_DIAGRAM_TYPES = (
    "architecture",
    "infrastructure",
    "architecture_beta",
    "block",
    "kanban",
    "packet",
    "sequence",
    "class",
    "state",
    "er",
    "requirement",
    "c4",
    "gantt",
    "journey",
    "timeline",
    "mindmap",
    "quadrant",
    "gitgraph",
    "pie",
    "xychart",
    "sankey",
    "radar",
    "treemap",
    "venn",
)
_DIAGRAM_TYPE_CHECK = ", ".join(f"'{diagram_type}'" for diagram_type in _DIAGRAM_TYPES)

_SCHEMA = f"""
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
  pos_x REAL,
  pos_y REAL,
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
  diagram_type TEXT NOT NULL CHECK (diagram_type IN ({_DIAGRAM_TYPE_CHECK})),
  title TEXT NOT NULL,
  mermaid_source TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{{}}',
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
  detail_json TEXT NOT NULL DEFAULT '{{}}',
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
  custom_values TEXT NOT NULL DEFAULT '{{}}',
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
CREATE INDEX IF NOT EXISTS idx_resource_staff_manager ON resource_staff(reporting_manager_id);
CREATE INDEX IF NOT EXISTS idx_resource_lookups_category ON resource_lookups(category);
CREATE INDEX IF NOT EXISTS idx_elements_project ON c4_elements(project_id);
CREATE INDEX IF NOT EXISTS idx_elements_parent ON c4_elements(parent_id);
CREATE INDEX IF NOT EXISTS idx_relations_project ON c4_relations(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_element ON artifact_links(element_id);
CREATE INDEX IF NOT EXISTS idx_l1_units_element ON l1_agile_units(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_members_unit ON l1_team_members(unit_id);
CREATE INDEX IF NOT EXISTS idx_l1_work_element ON l1_work_items(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_diagrams_element ON l1_diagrams(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_requirements_element ON l1_requirement_documents(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_requirement_versions_doc ON l1_requirement_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_l1_requirement_comments_doc ON l1_requirement_comments(document_id);
CREATE INDEX IF NOT EXISTS idx_l1_requirement_audit_doc ON l1_requirement_audit(document_id);
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
  decided_by TEXT,
  decided_at TEXT,
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
CREATE INDEX IF NOT EXISTS idx_l1_comments_element ON l1_comments(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_approvals_element ON l1_approvals(l1_element_id);
CREATE TABLE IF NOT EXISTS l2_arch (
  l2_element_id TEXT PRIMARY KEY REFERENCES c4_elements(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  summary TEXT NOT NULL DEFAULT '',
  container_diagram TEXT NOT NULL DEFAULT '',
  raci TEXT NOT NULL DEFAULT '{{}}',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','baselined','archived')),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l2_approvals (
  id TEXT PRIMARY KEY,
  l2_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  stage TEXT NOT NULL CHECK (stage IN ('engineering','security','nfr','data','architecture','sponsor')),
  ordinal INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_by TEXT,
  decided_at TEXT,
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (l2_element_id, stage)
);
CREATE INDEX IF NOT EXISTS idx_l2_approvals_element ON l2_approvals(l2_element_id);
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
CREATE INDEX IF NOT EXISTS idx_l2_containers_element ON l2_containers(l2_element_id);
CREATE INDEX IF NOT EXISTS idx_l2_apis_element ON l2_apis(l2_element_id);
CREATE INDEX IF NOT EXISTS idx_l2_nfrs_element ON l2_nfrs(l2_element_id);
CREATE INDEX IF NOT EXISTS idx_l2_integrations_element ON l2_integrations(l2_element_id);
CREATE TABLE IF NOT EXISTS l3_arch (
  l3_element_id TEXT PRIMARY KEY REFERENCES c4_elements(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  summary TEXT NOT NULL DEFAULT '',
  component_diagram TEXT NOT NULL DEFAULT '',
  raci TEXT NOT NULL DEFAULT '{{}}',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','approved','baselined','archived')),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS l3_approvals (
  id TEXT PRIMARY KEY,
  l3_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
  stage TEXT NOT NULL CHECK (stage IN ('design','interfaces','security','testing','architecture','tech_lead')),
  ordinal INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_by TEXT,
  decided_at TEXT,
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (l3_element_id, stage)
);
CREATE INDEX IF NOT EXISTS idx_l3_approvals_element ON l3_approvals(l3_element_id);
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
CREATE INDEX IF NOT EXISTS idx_l3_components_element ON l3_components(l3_element_id);
CREATE INDEX IF NOT EXISTS idx_l3_interfaces_element ON l3_interfaces(l3_element_id);
CREATE INDEX IF NOT EXISTS idx_l3_dependencies_element ON l3_dependencies(l3_element_id);
CREATE INDEX IF NOT EXISTS idx_l3_concerns_element ON l3_concerns(l3_element_id);
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
CREATE INDEX IF NOT EXISTS idx_l4_code_units_element ON l4_code_units(l4_element_id);
CREATE INDEX IF NOT EXISTS idx_l4_test_cases_element ON l4_test_cases(l4_element_id);
CREATE INDEX IF NOT EXISTS idx_l4_checklist_element ON l4_checklist(l4_element_id);
CREATE TABLE IF NOT EXISTS integration_configs (
  connector_key TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 0,
  settings TEXT NOT NULL DEFAULT '{{}}',
  updated_at TEXT,
  updated_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_l1_okrs_element ON l1_okrs(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_stakeholders_element ON l1_stakeholders(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_capabilities_element ON l1_capabilities(l1_element_id);
CREATE INDEX IF NOT EXISTS idx_l1_risks_element ON l1_risks(l1_element_id);
"""

_initialized: set[str] = set()


def db_path() -> Path:
    configured = os.getenv("STORYPOINTER_DB")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "storypointer.db"


def checkpoint_path() -> Path:
    return db_path().with_name("checkpoints.db")


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    """Add missing columns to an existing table (lightweight forward migration)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _ensure_l1_diagram_type_check(conn: sqlite3.Connection) -> None:
    """Rebuild old l1_diagrams tables whose CHECK only allowed two diagram types."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'l1_diagrams'"
    ).fetchone()
    sql = row[0] if row else ""
    if not sql or all(f"'{diagram_type}'" in sql for diagram_type in _DIAGRAM_TYPES):
        return

    conn.execute("DROP INDEX IF EXISTS idx_l1_diagrams_element")
    conn.execute("ALTER TABLE l1_diagrams RENAME TO l1_diagrams_old")
    conn.execute(
        f"""CREATE TABLE l1_diagrams (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          l1_element_id TEXT NOT NULL REFERENCES c4_elements(id) ON DELETE CASCADE,
          diagram_type TEXT NOT NULL CHECK (diagram_type IN ({_DIAGRAM_TYPE_CHECK})),
          title TEXT NOT NULL,
          mermaid_source TEXT NOT NULL,
          metadata TEXT NOT NULL DEFAULT '{{}}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """INSERT INTO l1_diagrams
           (id, project_id, l1_element_id, diagram_type, title, mermaid_source, metadata, created_at, updated_at)
           SELECT id, project_id, l1_element_id, diagram_type, title, mermaid_source, metadata, created_at, updated_at
           FROM l1_diagrams_old"""
    )
    conn.execute("DROP TABLE l1_diagrams_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_l1_diagrams_element ON l1_diagrams(l1_element_id)")


_DEFAULT_RESOURCE_LOOKUPS = {
    "tech_unit": [("PLATFORM", "Platform"), ("DATA", "Data & Analytics"), ("MOBILE", "Mobile"), ("CLOUD", "Cloud & Infra")],
    "rank": [("A1", "Analyst"), ("SA", "Senior Analyst"), ("C", "Consultant"), ("SC", "Senior Consultant"), ("M", "Manager")],
    "hr_role": [("ENG", "Engineer"), ("QA", "QA Engineer"), ("BA", "Business Analyst"), ("PM", "Project Manager"), ("ARCH", "Architect")],
}


def _seed_resource_lookups(conn: sqlite3.Connection) -> None:
    """Populate the reference tables once so the staff form has defaults to pick from."""
    if conn.execute("SELECT 1 FROM resource_lookups LIMIT 1").fetchone():
        return
    for category, entries in _DEFAULT_RESOURCE_LOOKUPS.items():
        for code, label in entries:
            conn.execute(
                "INSERT INTO resource_lookups (id, category, code, label) VALUES (?, ?, ?, ?)",
                (uuid.uuid4().hex, category, code, label),
            )


def init_db(path: Path | None = None) -> None:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        _ensure_columns(conn, "l1_diagrams", {"metadata": "TEXT NOT NULL DEFAULT '{}'"})
        _ensure_l1_diagram_type_check(conn)
        _ensure_columns(conn, "projects", {"leads": "TEXT NOT NULL DEFAULT '[]'", "sensitivity": "TEXT NOT NULL DEFAULT 'standard'"})
        _ensure_columns(conn, "l1_team_members", {"resource_staff_id": "TEXT REFERENCES resource_staff(id) ON DELETE SET NULL"})
        for table in ("l1_okrs", "l1_capabilities", "l1_risks"):
            _ensure_columns(conn, table, {"linked_element_id": "TEXT REFERENCES c4_elements(id) ON DELETE SET NULL"})
        _ensure_columns(conn, "l1_vision", {
            "vision_statement_details": "TEXT NOT NULL DEFAULT ''",
            "business_problem_details": "TEXT NOT NULL DEFAULT ''",
            "target_users_details": "TEXT NOT NULL DEFAULT ''",
        })
        _ensure_columns(conn, "l2_arch", {"raci": "TEXT NOT NULL DEFAULT '{}'"})
        _seed_resource_lookups(conn)
    _initialized.add(str(target))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    target = db_path()
    if str(target) not in _initialized:
        init_db(target)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def new_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
