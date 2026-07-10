# Story Pointer — User Guide

A step-by-step guide to using Story Pointer: modelling your system as a C4
architecture, estimating work with an evidence-led AI pipeline, planning
delivery, driving governance, and using the workflow guide and assistant to move
faster. For install/architecture details see the [README](../README.md); for the
internal design map see [CLAUDE.md](../CLAUDE.md).

---

## Contents

1. [Core concepts](#1-core-concepts)
2. [Install & run](#2-install--run)
3. [Signing in, roles & permissions](#3-signing-in-roles--permissions)
4. [The workspace at a glance](#4-the-workspace-at-a-glance)
5. [Create a platform (project)](#5-create-a-platform-project)
6. [Model the system on the C4 canvas](#6-model-the-system-on-the-c4-canvas)
7. [Estimate a story](#7-estimate-a-story)
8. [Quick estimate (form / Jira / Excel)](#8-quick-estimate-form--jira--excel)
9. [Roll-up dashboard](#9-roll-up-dashboard)
10. [L1 plan — operating plan](#10-l1-plan--operating-plan)
11. [L1 baseline — strategy, governance & exports](#11-l1-baseline--strategy-governance--exports)
12. [L2 / L3 / L4 architecture workspaces](#12-l2--l3--l4-architecture-workspaces)
13. [Workflow guide](#13-workflow-guide)
14. [The assistant (chat)](#14-the-assistant-chat)
15. [Admin console](#15-admin-console)
16. [Integrations & connectors](#16-integrations--connectors)
17. [Diagram studio & Mermaid](#17-diagram-studio--mermaid)
18. [Working offline (mock mode) & AI notes](#18-working-offline-mock-mode--ai-notes)
19. [Desktop app](#19-desktop-app)
20. [Troubleshooting & FAQ](#20-troubleshooting--faq)

---

## 1. Core concepts

**Story Pointer** turns your architecture into the source of truth for estimation
and planning. You model a system as an interactive **C4 model** and the tool
estimates the work, rolls the points up, and helps you plan and govern delivery.

**The four C4 levels** (each is a node on the canvas and has its own workspace):

| Level | C4 meaning | Agile artifact | What you do there |
|-------|------------|----------------|-------------------|
| **L1** | System context | Initiative / theme | Strategy, operating plan, governance |
| **L2** | Container | Epic | Container architecture (APIs, NFRs, integrations) |
| **L3** | Component | Story / feature | Component design **and** estimation |
| **L4** | Code | Task / sub-task | Implementation detail (code units, tests, DoD) |

A story's parent must be exactly one level up (L2 → L3 → L4). Points are
**estimated at L3** and **roll up deterministically** to L2 epics and L1
initiatives — roll-ups are always sums, never AI guesses.

**Key ideas**
- **Evidence-led estimation.** The estimator scores delivery factors, finds
  drivers, compares against six fixed calibration stories, and only then
  concludes a modified-Fibonacci point value (1/2/3/5/8/13) — always with a
  plain-language explanation. A point is never shown without its reasoning.
- **Markdown + Mermaid is the PowerPoint replacement.** Every summary
  (executive, engineering, component, implementation) is a living Markdown
  document with embedded Mermaid diagrams, rendered in-app and exportable.
- **AI proposes, you decide.** Every AI action returns a *draft/proposal* you
  review before anything is saved.
- **Readiness scores** (0–100%) tell you how complete each level is and what's
  missing, at L1, L2, L3 and L4.

---

## 2. Install & run

Prerequisites: **Python 3.11+** and **Node.js 20+**. From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item backend\.env.example backend\.env     # then fill in LLM_* keys (or use mock)
npm install
Copy-Item frontend\.env.example frontend\.env
```

Run the API (`:8000`) and the web app (`:5173`) together:

```powershell
npm run dev:all
```

Open **http://localhost:5173**.

> **Try it with no API key.** Set `LLM_PROVIDER=mock` in `backend/.env` to run the
> whole app offline with deterministic results — perfect for a first look, demos,
> and local UI work. See [§18](#18-working-offline-mock-mode--ai-notes).

Seed sample data (optional):

```powershell
npm run api:seed:demo       # small demo project + C4 model
npm run api:seed:banking    # richer multi-level banking sample
```

---

## 3. Signing in, roles & permissions

Story Pointer uses **local demo auth** — no passwords or tokens. Application
users *are* people in the **Resource directory**; each is assigned a role.

**First run:** the earliest-created person in the directory is automatically
promoted to **admin** so you're never locked out. Seed data creates users for
you; otherwise add staff in **Admin → Resources** (see [§15](#15-admin-console)).

**Signing in**
1. On the **Login** screen, pick your identity from the list of enabled, active
   people.
2. You're signed in; your name and role appear top-right. Sign-in is remembered
   in the browser.

**Roles** (most to least powerful): **admin › manager › contributor › viewer**.

| Capability | admin | manager | contributor | viewer |
|------------|:-----:|:-------:|:-----------:|:------:|
| See the app / read | ✓ | ✓ | ✓ | ✓ |
| Create & edit platforms (models, plans, estimate) | ✓ | ✓ | ✓ | — |
| Reporting dashboards | ✓ | ✓ | — | — |
| Manage the Resource directory | ✓ | ✓ | — | — |
| Manage users & roles (Access) | ✓ | — | — | — |
| Configure integration connectors | ✓ | — | — | — |

**Restricted platforms (ABAC).** A platform marked *restricted* (set at creation)
is visible only to **managers and admins** — viewers and contributors are blocked
from every part of that workspace.

---

## 4. The workspace at a glance

The top bar has **Platforms** (your projects) and **Admin** (if permitted), plus
your identity menu. Inside a platform, a left **nav rail** switches sections:

| Tab | What it's for |
|-----|---------------|
| **C4 canvas** | Model the system; create L1–L4 nodes; estimate |
| **L1 plan** | Operating plan + L1 strategy baseline & governance |
| **L2 arch** | Container architecture workspace |
| **L3 arch** | Component design workspace |
| **L4 detail** | Implementation-detail workspace |
| **Roll-up** | Deterministic points roll-up dashboard |
| **Quick** | One-off single-story estimate (form/Jira/Excel) |
| **Overview** | Platform settings, repo/Jira links, repo scan |

Two helpers are always available inside a platform:
- **Workflow guide** button (page header) — a guided tour of what to do next at
  every level ([§13](#13-workflow-guide)).
- **Assistant** dock (bottom-right) — ask questions or instruct changes in plain
  language ([§14](#14-the-assistant-chat)).

---

## 5. Create a platform (project)

1. On the home screen, click **New platform**.
2. Enter a **name** and (optionally) a description.
3. Add one or more **leads**.
4. Choose **sensitivity**:
   - **Standard** — visible to all signed-in users per their role.
   - **Restricted** — visible only to managers/admins (see ABAC above).
5. Optionally link a **code repository** and a **Jira project** now (you can also
   do this later in **Overview**).
6. Create it — you land on the **C4 canvas** for the new platform.

> **Bootstrap fast:** on the canvas you can use **AI scaffold** to turn a short
> description into a starter L1/L2/L3 model, or a **repo scan** (Overview) to
> propose elements from a linked codebase.

---

## 6. Model the system on the C4 canvas

The canvas (React Flow) is where you build the C4 model.

**Add elements**
1. Click **Add system (L1)** to create the top-level initiative.
2. Select a node and add children one level down (L1→L2→L3→L4). The tool enforces
   that a child is exactly one level below its parent.
3. Drag from a node's edge to another to create a **relation** (sync / async /
   data).

**Inspect & edit.** Click a node to open the **Inspector** panel — rename, set
description/tech/code path/status, tag cross-cutting artifacts (bug, tech-debt,
arch-flow), and jump to that element's architecture workspace ("More details").

**AI helpers on the canvas**
- **AI scaffold** — describe the system; get a proposed L1/L2/L3 model + relations
  (all `proposed` until you accept).
- **AI: suggest stories** (Inspector) — propose child stories one level down.

**Proposed vs active.** AI-suggested elements, split recommendations, and hidden
tasks arrive as **`proposed`** and stay **out of the roll-up** until you accept
them. This keeps estimates honest.

---

## 7. Estimate a story

Estimation happens at **L3** (a component/story). L4 tasks are seeded from
detected hidden tasks.

1. On the canvas, select an **L3** element and choose **Estimate** (opens the
   estimate modal).
2. The **pipeline streams live**: it scores parameters, identifies drivers,
   compares to calibration anchors, derives points, writes a plain-language
   rationale, detects hidden tasks, assesses risks, and recommends a split when a
   story is a 13 or highly uncertain.
3. The **Result card** shows the point value with a one-line summary (`tldr`) and
   a full plain-language explanation. A point value is never shown without its
   reasoning.
4. **Accept the outcomes** you want:
   - **Hidden tasks** can seed **L4** children.
   - A **split recommendation** (for 13-point stories) can seed sibling **L3**
     stories.
   Both arrive as `proposed`.
5. **Refine without losing history:** re-open and ask *"re-estimate assuming X"* —
   the pipeline is checkpointed per session, so refinements build on the prior
   run.

Results are cached per element — **View reasoning** re-opens the last result
without re-running.

---

## 8. Quick estimate (form / Jira / Excel)

Use the **Quick** tab (or the standalone Quick estimate screen) for one-off
estimates that don't need a full model.

- **Form** — type a title, user story, acceptance criteria and technical notes;
  estimate directly.
- **Jira** — browse a configured Jira project and pull an issue in to estimate
  (see [§16](#16-integrations--connectors) for configuring Jira). Write-back to
  Jira is triple-gated (env flag + request confirm + per-issue confirmation).
- **Excel upload** — upload a CSV/XLSX/XLS. The tool **suggests a column mapping**
  (title, user story, acceptance criteria, technical breakdown, existing points);
  confirm or adjust it, then batch-estimate. Download the starter template from
  the upload panel. Title is the only required column.

---

## 9. Roll-up dashboard

The **Roll-up** tab shows the deterministic points roll-up:

- Points summed from estimated **L3** stories up through **L2** epics to **L1**
  initiatives.
- **Estimated vs unestimated** story counts.
- Flagged **spikes** and **pending splits**.

`proposed` elements are excluded until accepted. These numbers are always sums —
never AI output.

---

## 10. L1 plan — operating plan

Open **L1 plan** and pick an L1 initiative. Beyond strategy, each L1 can carry an
**operating plan**:

1. **Teams** — model your org as **tribes → squads**, and add **team members**
   (optionally linked to people in the Resource directory). Each person's total
   allocation is capped at 100% across all squads.
2. **Work & cost** — add scheduled, costed work items; link each to an L2–L4
   descendant and to a squad. `end_date` must be on/after `start_date`.
3. **Metrics** — the plan shows deterministically computed metrics: head-count,
   allocated FTE, monthly run-rate, planned/actual cost + variance, and at-risk
   work. Money is presentation-only; the per-L1 currency just labels it.
4. **Diagrams** — attach architecture/infrastructure Mermaid diagrams via the
   [diagram studio](#17-diagram-studio--mermaid).

**AI staffing.** Click **AI staffing** to get proposed squad ↔ person assignments
that respect each person's remaining capacity; review and apply.

---

## 11. L1 baseline — strategy, governance & exports

The **L1 baseline** (default tab within L1 planning) is the strategy layer — the
PowerPoint replacement for an initiative.

**Capture the strategy**
1. **Vision** — vision statement, business problem, target users. Each field has
   a **"more details"** editor: write rich Markdown, then **AI-summarize** it back
   into the concise parent field.
2. **OKRs** — objectives + key results with metrics/targets/owners.
3. **Stakeholders** — a stakeholder map with influence/interest and a RACI value;
   add people manually or pick from the Resource directory.
4. **Capabilities** — a hierarchical business-capability map.
5. **Risks** — a portfolio risk & funding register.

OKRs, capabilities and risks can each **link to a C4 element** for traceability.

**Readiness & summary**
- A **readiness gauge + checklist** scores completeness across the requirement's
  areas and lists what's missing.
- The **executive summary** is a single Markdown document with an embedded live
  Mermaid capability map — the deliverable you share.

**AI generate baseline.** Provide a brief (or paste a strategy document via
**Integrations → Document import**) and the AI drafts vision/OKRs/stakeholders/
capabilities/risks; review and apply the sections you want.

**Governance, discussion & impact**
- **Governance** tab — a sequential sign-off chain
  (product → architecture → security → risk → finance → sponsor). Approvals must
  happen in order; completing them **baselines** the vision; a rejection reverts
  it to draft. The tab also shows a deterministic **change-impact analysis**
  (e.g. inactive-but-accountable stakeholders, owner-less capabilities, overdue
  risks, off-track OKRs).
- **Discussion** tab — post/resolve review comments.
- **Live Jira import** — pull a Jira project's issues in as capabilities or OKRs.

**Exports.** Export the executive summary to **Markdown, Word, or PowerPoint** —
the Mermaid diagrams are rendered to images and embedded. The Markdown+Mermaid
view remains the source of truth; exports are just renderings.

---

## 12. L2 / L3 / L4 architecture workspaces

The **L2 arch**, **L3 arch**, and **L4 detail** tabs are structured the same way
— pick an element of that level, then work through its artifacts. Each shows a
**readiness gauge + checklist** and produces a **Markdown + Mermaid summary**.

**Common layout**
- **Element picker** (top) — choose which L2/L3/L4 element you're working on.
- **Diagram tab** — a split **Mermaid editor + live preview**; **Open studio** for
  full editing; the preview **maximizes** to a zoom/pan popup.
- **Artifact tables** — add/edit/delete the level's building blocks (below).
- **AI generate** — draft the whole level from context + a brief; review & apply.
- **Summary tab** — the rendered Markdown+Mermaid engineering/component/
  implementation summary (copy the Markdown with one click).
- **Traceability tab** — a Mermaid graph of the level's place in the chain
  (L1→L2→L3, L2→L3→L4).

**What each level captures**

| Level | Artifacts | Governance | Extras |
|-------|-----------|:----------:|--------|
| **L2 container** | Containers & boundaries, API/data contracts, NFRs, integration plan | ✓ approvals + RACI | **Import**: OpenAPI → APIs, Kubernetes manifest → containers |
| **L3 component** | Components (controller/service/repository/gateway…), interfaces & contracts, dependencies, cross-cutting concerns | ✓ approvals + RACI | — |
| **L4 detail** | Code units (classes/functions/modules), test cases (given/when/then), Definition-of-Done checklist | lean — no approvals/RACI | Toggle DoD items done |

**Governance (L2/L3).** Submit for review, then approve stages **in order**;
completing them baselines the element. A rejection un-baselines it back to
*reviewed*. The **RACI** tab is a grid of *artifact × role* responsibility cells
(R/A/C/I).

**Live imports (L2).** Use the header **Import** dialog to paste an OpenAPI spec
(→ API contracts) or a Kubernetes manifest (→ containers), in JSON or YAML.

> **Tip:** the readiness label tells you when a level is "ready" for the next one
> down (e.g. an L2 at ≥80% is *Ready for L3 component design*). Use **AI generate**
> to bootstrap, then review and refine — don't accept blindly.

---

## 13. Workflow guide

Not sure what to do next? Click **Workflow guide** in the platform header.

1. A modal opens with your **overall progress %** and current **stage**, plus a
   prominent **"Next best step"**.
2. Step through **L1 → L2 → L3 → L4 → Estimation** (or jump via the stepper dots).
   Each stage shows element counts, average readiness, and status
   (not-started / in-progress / ready).
3. Each stage lists **recommended actions** — click one to **jump straight to the
   relevant tab** (the wizard closes and takes you there). Tips call out where to
   use *AI generate* to bootstrap.

A level "unlocks" once its parent exists, so an empty platform focuses you on L1
first. Everything here is deterministic (no AI) — it reflects your real data.

---

## 14. The assistant (chat)

The floating **Assistant** (bottom-right, inside a platform) lets you query,
report, and modify the model in plain language.

**Ask (executes immediately)**
- *"What's the project status?"* / *"What should I do next?"*
- *"List L2 containers"* · *"Readiness of onboarding-web"*
- *"Give me the roll-up"*

Answers come back with real numbers and structured data (element lists, readiness
chips, per-level progress).

**Instruct (proposed, then you Apply)**
- *"Create an L2 container called payments under Digital banking"*
- *"Rename pay-api to payments-api"* · *"Set onboarding-web status to reviewed"*
- *"Delete the L4 task X"*

Changes are **never applied silently** — the assistant shows a proposal card;
click **Apply** to confirm (or **Dismiss**). If an element name is ambiguous or
unknown, it asks you to clarify instead of guessing.

**Permissions.** Anyone signed in can query; **applying a change needs edit
rights** (contributor+). Restricted platforms follow the same ABAC rules.

---

## 15. Admin console

**Admin** (top bar; needs the `admin` capability to see it) hosts four sections:

**Access management** *(admin only)* — assign each directory person a role
(admin/manager/contributor/viewer) and enable/disable them. The earliest person
is auto-promoted to admin so the app is never locked out.

**Reporting** *(admin/manager)* — a deterministic cross-module overview:
portfolio progress, resource utilisation, allocation status, and app-role counts.
Click **AI summary** for an executive briefing generated from the metrics.

**Resources** *(admin/manager to edit; anyone can read)* — the app-global staff
pool that every module can reference:
1. Add **staff** (first/last name, type, status, dates, reporting manager). A
   `staff_code` (STF-0001…) is generated. A manager must exist and can't be
   yourself; deleting a manager nulls their reports' link.
2. The three lookup fields (**Tech Unit / Rank / HR Role**) are validated against
   editable lists.
3. Open **Lists & fields** to manage those lookups and to define **custom fields**
   (text/number/date/select/boolean) that appear on every staff row. A lookup
   value in use can't be deleted.

**Integrations** — see the next section.

---

## 16. Integrations & connectors

**Admin → Integrations** lists ~42 tools grouped by category (product & delivery,
documentation, architecture, people, engineering, risk & ops). Each card shows a
status:
- **In-app adapter** — works natively (document import, Mermaid, resource
  directory); no setup.
- **Connected** — a saved & enabled configuration (or Jira via environment
  config).
- **Available** — catalogued; configure it to activate.

**Configure a connector** *(admin only)*
1. Click **Configure** on a card. A dialog shows the fields that connector needs —
   e.g. Jira: Base URL + account email + API token; Slack: an incoming webhook
   URL; GitHub/GitLab: base URL + access token; LDAP/AD: server + bind DN +
   password + base DN.
2. Fill the URL/credentials and tick **Enabled**.
3. **Validate** checks that required fields are present and URLs are well-formed.
4. **Save** — the card flips to **Connected** and the button becomes **Manage**.

> **Secrets are write-only.** Saved credentials are stored server-side and **never
> sent back to the browser** — a secret field shows a "saved" placeholder; leave
> it blank to keep the existing value. **Disconnect** clears the configuration.
> Real live connectivity today is provided for Jira via environment config; the
> rest is a configuration framework ready to back real clients.

**AI command router.** Type a natural-language request (e.g. *"draft the vision
and OKRs"*) and it routes to the right AI capability. **Document import** pastes a
strategy/architecture document and extracts L1 artifacts from it.

---

## 17. Diagram studio & Mermaid

All diagrams are **Mermaid** (diagrams-as-code), used consistently across L1–L4,
the diagram studio, and Markdown summaries.

- **Live preview** sits beside every Mermaid editor and **auto-fits** the diagram.
- Click **maximize** on any preview to open a **zoom/pan popup** (mouse-wheel to
  zoom, drag to pan, fit-to-window).
- **Open studio** launches the full **Diagram Studio** for richer editing and
  auto-layout; saving writes the Mermaid back to the workspace.

Because diagrams are text, they're portable, diffable, and reviewable — and they
embed directly into the exportable summaries.

---

## 18. Working offline (mock mode) & AI notes

**Mock mode.** Set `LLM_PROVIDER=mock` in `backend/.env` to run the entire app
**offline with no API key**. Estimation points are a deterministic hash of the
story title, and every AI feature (baselines, staffing, decompose, scaffold,
summaries, the assistant) returns deterministic proposals. Ideal for demos,
local UI work, and tests.

**Where AI is used** (all gated on a configured LLM; 503 otherwise, and all
returning a *proposal* you review): estimation pipeline, L1–L4 "AI generate",
AI staffing, story decomposition, C4 scaffold, reporting narrative, field
summarize, the AI command router, and the assistant.

**Privacy.** Free-text you send to AI (briefs, decompose guidance, scaffold
descriptions, the orchestrator, the assistant) is **PII-masked** (emails, phones,
ids redacted) before it reaches the model.

**Switching providers** is a `backend/.env` change (`LLM_PROVIDER`, `LLM_MODEL`,
`LLM_API_KEY`, …) — see the README's *Provider switches*. No application code
changes.

---

## 19. Desktop app

The same web app + backend ship as a self-contained **desktop app** (Electron).

```powershell
npm run desktop:dev            # hot-reload dev shell (backend from source)
python -m pip install -r requirements-desktop.txt   # adds PyInstaller for bundling
npm run desktop:build:win      # NSIS installer + portable exe → release/
npm run desktop:build:mac      # dmg + zip (run on macOS)
```

The desktop app starts the backend, waits for health, then loads the UI. Data is
per-user (its own database and env file under the OS user-data directory).

---

## 20. Troubleshooting & FAQ

**I'm locked out / no admin.** The earliest-created person in the Resource
directory is auto-promoted to admin. Seed data (`npm run api:seed:demo`) creates
users; otherwise the first staff you add becomes admin.

**AI features return 503 / "configuration incomplete".** The configured LLM is
missing its key. Fix `backend/.env` (or use `LLM_PROVIDER=mock`) and restart the
API. **/health** reports configuration errors.

**A viewer/contributor can't open a platform.** It's probably **restricted**
(managers/admins only). Check the platform's sensitivity, or your role in
**Admin → Access**.

**The assistant won't apply my change.** Applying needs **edit rights**
(contributor+). Viewers can query but not modify.

**My points didn't roll up.** Roll-ups exclude **`proposed`** elements — accept
the proposed story/task first. Only **L3** stories are estimated directly.

**A connector still says "Available" after I configured it.** Make sure you ticked
**Enabled** and filled all required fields (Validate will tell you what's
missing).

**I can't estimate an L1/L2/L4 node.** Estimation runs on **L3** stories. L2/L1
points are roll-ups; L4 tasks are seeded from hidden tasks.

**Where are the deliverables?** Every level's **Summary** tab is the shareable
Markdown+Mermaid document; the L1 baseline additionally exports to Word/PowerPoint.

---

*For architecture internals and module boundaries, see [CLAUDE.md](../CLAUDE.md).
For provider/Jira/Excel configuration, see the [README](../README.md).*
