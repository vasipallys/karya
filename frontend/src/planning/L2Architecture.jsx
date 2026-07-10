import { Boxes, CheckCircle2, Circle, DownloadCloud, FileText, Gavel, GitBranch, Grid3x3, Network, Pencil, PencilRuler, Plug, Plus, RefreshCw, ShieldAlert, Sparkles, ThumbsDown, ThumbsUp, Trash2, X } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { MarkdownViewer } from '../components/MarkdownEditor'
import MermaidView from '../components/MermaidView'
import { useToast } from '../ui/Toast'
import PlanningDialog from './PlanningDialog'

const DiagramStudio = lazy(() => import('./DiagramStudio'))

const TABS = [
  { id: 'overview', label: 'Container diagram', icon: Network },
  { id: 'containers', label: 'Containers & boundaries', icon: Boxes },
  { id: 'apis', label: 'APIs & Data', icon: Plug },
  { id: 'nfrs', label: 'NFRs', icon: ShieldAlert },
  { id: 'integrations', label: 'Integration plan', icon: Network },
  { id: 'raci', label: 'RACI', icon: Grid3x3 },
  { id: 'governance', label: 'Governance', icon: Gavel },
  { id: 'traceability', label: 'Traceability', icon: GitBranch },
  { id: 'summary', label: 'Engineering summary', icon: FileText },
]
const RACI_LABELS = {
  container_diagram: 'Container Diagram', service_boundaries: 'Service Boundaries', api_contracts: 'API Contracts',
  data_contracts: 'Data Contracts', deployment_topology: 'Deployment Topology', nfrs: 'NFRs',
  integration_plan: 'Integration Plan', security_review: 'Security Review',
}
const ROLE_LABELS = {
  product_owner: 'Product Owner', solution_architect: 'Solution Architect', engineering_lead: 'Engineering Lead',
  security_architect: 'Security Architect', data_owner: 'Data Owner', sre: 'SRE', risk_owner: 'Risk Owner',
}
const RACI_VALUES = ['', 'R', 'A', 'C', 'I']

const SELECT = (options) => ({ type: 'select', options })
const FIELDS = {
  container: [
    { key: 'name', label: 'Container / service' },
    { key: 'capability', label: 'Business capability' },
    { key: 'responsibilities', label: 'Responsibilities', type: 'textarea' },
    { key: 'owns_data', label: 'Owns data' },
    { key: 'owner_team', label: 'Owner team' },
    { key: 'security_classification', label: 'Security', ...SELECT(['public', 'internal', 'confidential', 'restricted']) },
    { key: 'nfr_criticality', label: 'NFR criticality', ...SELECT(['high', 'medium', 'low']) },
    { key: 'status', label: 'Status', ...SELECT(['active', 'planned', 'retired']) },
  ],
  api: [
    { key: 'name', label: 'API / topic' },
    { key: 'provider', label: 'Provider' },
    { key: 'consumer', label: 'Consumer' },
    { key: 'endpoint', label: 'Endpoint / topic' },
    { key: 'api_type', label: 'Type', ...SELECT(['REST', 'GraphQL', 'gRPC', 'Event', 'Batch', 'File']) },
    { key: 'data_classification', label: 'Data class', ...SELECT(['public', 'internal', 'confidential', 'restricted']) },
    { key: 'authentication', label: 'Authentication' },
    { key: 'version', label: 'Version' },
    { key: 'owner', label: 'Owner' },
    { key: 'status', label: 'Status', ...SELECT(['proposed', 'active', 'deprecated']) },
  ],
  nfr: [
    { key: 'name', label: 'NFR' },
    { key: 'category', label: 'Category', ...SELECT(['performance', 'security', 'availability', 'scalability', 'privacy', 'resilience']) },
    { key: 'scenario', label: 'Scenario', type: 'textarea' },
    { key: 'metric', label: 'Metric' },
    { key: 'baseline', label: 'Baseline' },
    { key: 'target', label: 'Target' },
    { key: 'owner', label: 'Owner' },
    { key: 'risk_level', label: 'Risk', ...SELECT(['high', 'medium', 'low']) },
    { key: 'status', label: 'Status', ...SELECT(['open', 'met', 'at_risk']) },
  ],
  integration: [
    { key: 'name', label: 'Integration' },
    { key: 'source_system', label: 'Source system' },
    { key: 'target_system', label: 'Target system' },
    { key: 'integration_type', label: 'Type', ...SELECT(['API', 'Event', 'Batch', 'File', 'UI', 'Manual']) },
    { key: 'data_exchanged', label: 'Data exchanged' },
    { key: 'security_method', label: 'Security method' },
    { key: 'status', label: 'Status', ...SELECT(['planned', 'active', 'blocked', 'done']) },
  ],
}
const DEFAULTS = {
  container: { name: '', capability: '', responsibilities: '', owns_data: '', owner_team: '', security_classification: 'internal', nfr_criticality: 'medium', status: 'active' },
  api: { name: '', provider: '', consumer: '', endpoint: '', api_type: 'REST', data_classification: 'internal', authentication: '', version: 'v1', owner: '', status: 'proposed' },
  nfr: { name: '', category: 'performance', scenario: '', metric: '', baseline: '', target: '', owner: '', risk_level: 'medium', status: 'open' },
  integration: { name: '', source_system: '', target_system: '', integration_type: 'API', data_exchanged: '', security_method: '', status: 'planned' },
}
const API = {
  container: { create: 'createL2Container', update: 'updateL2Container', del: 'deleteL2Container' },
  api: { create: 'createL2Api', update: 'updateL2Api', del: 'deleteL2Api' },
  nfr: { create: 'createL2Nfr', update: 'updateL2Nfr', del: 'deleteL2Nfr' },
  integration: { create: 'createL2Integration', update: 'updateL2Integration', del: 'deleteL2Integration' },
}
const PILL = (v) => `res-pill ${['high', 'at_risk', 'blocked', 'restricted'].includes(v) ? 'sub-partiallyallocated' : ['low', 'done', 'met', 'active', 'public'].includes(v) ? 'ok' : ''}`

export default function L2Architecture({ projectId, onOpenCanvas }) {
  const toast = useToast()
  const [elements, setElements] = useState([])
  const [l2Id, setL2Id] = useState('')
  const [ws, setWs] = useState(null)
  const [tab, setTab] = useState('overview')
  const [dialog, setDialog] = useState(null)
  const [ai, setAi] = useState(null)
  const [exec, setExec] = useState(null)
  const [diagram, setDiagram] = useState('')
  const [summary, setSummary] = useState('')
  const [studio, setStudio] = useState(false)
  const [trace, setTrace] = useState(null)
  const [importDlg, setImportDlg] = useState(null) // { kind, content }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const fail = (err) => { setError(err); toast.error(err) }

  useEffect(() => {
    api.c4Graph(projectId).then((g) => {
      const l2s = g.elements.filter((e) => e.level === 'L2')
      setElements(l2s)
      setL2Id((cur) => cur && l2s.some((e) => e.id === cur) ? cur : (l2s[0]?.id || ''))
    }).catch(fail)
  }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    if (!l2Id) return
    api.l2Workspace(projectId, l2Id).then((data) => {
      setWs(data); setDiagram(data.arch.container_diagram || ''); setSummary(data.arch.summary || '')
    }).catch(fail)
  }, [projectId, l2Id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setWs(null); load() }, [load])

  const saveArch = async (patch) => {
    setBusy(true)
    try { await api.updateL2Arch(projectId, l2Id, patch); toast.success('Saved'); await load() }
    catch (err) { fail(err) } finally { setBusy(false) }
  }

  const openDialog = (entity, editing = null) => setDialog({ entity, editing, draft: editing ? { ...DEFAULTS[entity], ...editing } : { ...DEFAULTS[entity] } })
  const saveEntity = async () => {
    setBusy(true)
    const { entity, editing, draft } = dialog
    try {
      if (editing) await api[API[entity].update](projectId, l2Id, editing.id, draft)
      else await api[API[entity].create](projectId, l2Id, draft)
      setDialog(null); toast.success('Saved'); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }
  const removeEntity = async (entity, item) => {
    if (!window.confirm('Delete this item?')) return
    try { await api[API[entity].del](projectId, l2Id, item.id); await load() } catch (err) { fail(err) }
  }

  const runAi = async () => {
    setAi({ loading: true })
    try { setAi({ draft: await api.aiL2Baseline(projectId, l2Id, '') }) } catch (err) { fail(err); setAi(null) }
  }
  const applyAi = async () => {
    setBusy(true)
    try {
      const result = await api.applyL2Baseline(projectId, l2Id, ai.draft)
      setAi(null); toast.success(`Added ${Object.values(result).reduce((a, b) => a + b, 0)} items`); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  const openSummary = async () => {
    setTab('summary'); setExec({ loading: true })
    try { setExec({ markdown: (await api.l2EngineeringSummary(projectId, l2Id)).markdown }) } catch (err) { fail(err); setExec(null) }
  }
  const openTraceability = async () => {
    setTab('traceability'); setTrace({ loading: true })
    try { setTrace(await api.l2Traceability(projectId, l2Id)) } catch (err) { fail(err); setTrace(null) }
  }

  const submitForReview = async () => {
    try { await api.submitL2ForReview(projectId, l2Id); toast.success('Submitted for review'); await load() } catch (err) { fail(err) }
  }
  const decide = async (stage, approve) => {
    try { await api.decideL2Approval(projectId, l2Id, stage, { approve, decided_by: 'me' }); toast.success(approve ? 'Approved' : 'Rejected'); await load() } catch (err) { fail(err) }
  }
  const setRaci = async (artifact, role, value) => {
    try { await api.setL2Raci(projectId, l2Id, artifact, role, value); await load() } catch (err) { fail(err) }
  }
  const runImport = async () => {
    if (!importDlg?.content.trim()) return
    setBusy(true)
    try {
      const result = await api.importL2Source(projectId, l2Id, importDlg.kind, importDlg.content)
      setImportDlg(null); toast.success(`Imported ${result.created_apis ?? result.created_containers} item(s)`); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  if (elements.length === 0) {
    return <div className="l1-empty-panel prominent"><Boxes size={38} /><h2>No L2 container yet</h2><p>Create an L2 container/epic on the C4 canvas first (a child of an L1 initiative). It becomes the anchor for container architecture.</p><button className="m3-btn filled" onClick={onOpenCanvas}>Open C4 canvas</button></div>
  }

  return <div className="l1-planning">
    {error && <div className="m3-banner error"><span>{String(error.message || error)}</span><button className="m3-btn text small" onClick={() => setError(null)}>Dismiss</button></div>}
    <header className="l1-plan-hero">
      <div className="l1-plan-identity">
        <span className="l1-hero-icon"><Network size={22} /></span>
        <div><span className="l1-eyebrow">L2 container architecture</span>
          <select value={l2Id} onChange={(e) => setL2Id(e.target.value)} aria-label="Select L2 element">{elements.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select>
          {ws?.parent && <p>Linked L1: {ws.parent.name}</p>}</div>
      </div>
      <div className="l1-plan-tools">
        <button className="m3-btn tonal small" onClick={runAi} disabled={ai?.loading}><Sparkles size={15} /> {ai?.loading ? 'Drafting…' : 'AI generate L2'}</button>
        <button className="m3-btn outlined small" onClick={() => setImportDlg({ kind: 'openapi', content: '' })}><DownloadCloud size={15} /> Import</button>
        <button className="m3-icon-btn" onClick={load} aria-label="Refresh"><RefreshCw size={17} /></button>
      </div>
    </header>

    {ws && <>
      <div className="l1arch-head"><ReadinessCard readiness={ws.readiness} /></div>
      <nav className="l1arch-tabs" aria-label="L2 sections">
        {TABS.map(({ id, label, icon: Icon }) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => (id === 'summary' ? openSummary() : id === 'traceability' ? openTraceability() : setTab(id))}><Icon size={15} /> {label}</button>)}
      </nav>

      {tab === 'overview' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Summary</h3></div>
        <textarea className="vision-field-summary" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One-paragraph L2 architecture summary" />
        <div className="l1arch-section-head"><h3>C4 container diagram <small>Mermaid — portable & reviewable</small></h3>
          <div className="l1arch-export-actions">
            <button className="m3-btn outlined small" onClick={() => setStudio(true)}><PencilRuler size={14} /> Open studio</button>
            <button className="m3-btn filled small" disabled={busy} onClick={() => saveArch({ summary, container_diagram: diagram })}>Save</button>
          </div>
        </div>
        <div className="l2-diagram-grid">
          <div className="l2-diagram-code"><header>Mermaid source</header>
            <textarea spellCheck="false" value={diagram} onChange={(e) => setDiagram(e.target.value)} placeholder={'flowchart LR\n  Web --> API\n  API --> DB[(Database)]'} /></div>
          <div className="l2-diagram-preview"><header>Live preview</header>
            {diagram.trim() ? <MermaidView source={diagram} /> : <p className="l1-node-empty">Write Mermaid or use “AI generate L2”.</p>}</div>
        </div>
        <div className="l1arch-section-head"><h3>Container status</h3></div>
        <div className="l1-form-grid">
          <label className="m3-field"><span>Lifecycle status</span>
            <select value={ws.arch.status} onChange={(e) => saveArch({ status: e.target.value })}>{['draft', 'reviewed', 'approved', 'baselined', 'archived'].map((s) => <option key={s}>{s}</option>)}</select></label>
        </div>
      </div>}

      {tab === 'containers' && <ArtifactTab entity="container" title="Containers & Service Boundaries" columns={['name', 'capability', 'owner_team', 'security_classification', 'nfr_criticality', 'status']} rows={ws.containers} onAdd={() => openDialog('container')} onEdit={openDialog} onDelete={removeEntity} />}
      {tab === 'apis' && <ArtifactTab entity="api" title="API & Data Contracts" columns={['name', 'provider', 'consumer', 'api_type', 'data_classification', 'authentication', 'version', 'status']} rows={ws.apis} onAdd={() => openDialog('api')} onEdit={openDialog} onDelete={removeEntity} />}
      {tab === 'nfrs' && <ArtifactTab entity="nfr" title="Non-Functional Requirements" columns={['name', 'category', 'metric', 'target', 'risk_level', 'status']} rows={ws.nfrs} onAdd={() => openDialog('nfr')} onEdit={openDialog} onDelete={removeEntity} />}
      {tab === 'integrations' && <ArtifactTab entity="integration" title="Integration Plan" columns={['name', 'source_system', 'target_system', 'integration_type', 'security_method', 'status']} rows={ws.integrations} onAdd={() => openDialog('integration')} onEdit={openDialog} onDelete={removeEntity} />}

      {tab === 'raci' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>RACI matrix <small>Responsibility per L2 artifact × role</small></h3></div>
        <div className="res-table-wrap"><table className="res-table raci-table">
          <thead><tr><th>Artifact</th>{ws.raci_roles.map((r) => <th key={r}>{ROLE_LABELS[r] || r}</th>)}</tr></thead>
          <tbody>
            {ws.raci_artifacts.map((artifact) => <tr key={artifact}>
              <td><strong>{RACI_LABELS[artifact] || artifact}</strong></td>
              {ws.raci_roles.map((role) => {
                const val = ws.arch.raci[`${artifact}:${role}`] || ''
                return <td key={role}><select className={`raci-cell raci-${val}`} value={val} onChange={(e) => setRaci(artifact, role, e.target.value)}>{RACI_VALUES.map((v) => <option key={v} value={v}>{v || '—'}</option>)}</select></td>
              })}
            </tr>)}
          </tbody>
        </table></div>
        <p className="ai-hint">R = Responsible · A = Accountable · C = Consulted · I = Informed</p>
      </div>}

      {tab === 'governance' && <GovernancePanel approvals={ws.approvals} readiness={ws.readiness} onSubmit={submitForReview} onDecide={decide} />}

      {tab === 'traceability' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Traceability <small>L1 → L2 → L3</small></h3></div>
        {trace?.loading && <div className="l1-loading">Building trace…</div>}
        {trace?.mermaid && <>
          <div className="l1arch-diagram-box"><MermaidView source={trace.mermaid} /></div>
          <p className="admin-muted">{trace.l1 ? `L1 “${trace.l1.name}” → ` : ''}L2 “{trace.l2.name}” → {trace.l3_count} L3 component{trace.l3_count === 1 ? '' : 's'}{trace.l3_children.length ? `: ${trace.l3_children.map((c) => c.name).join(', ')}` : ''}.</p>
        </>}
      </div>}

      {tab === 'summary' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Engineering summary <small>Markdown + Mermaid — a living document</small></h3>
          {exec?.markdown && <button className="m3-btn text small" onClick={() => { navigator.clipboard?.writeText(exec.markdown); toast.success('Markdown copied') }}>Copy MD</button>}</div>
        {exec?.loading && <div className="l1-loading">Composing summary…</div>}
        {exec?.markdown && <div className="l1arch-exec"><MarkdownViewer content={exec.markdown} /></div>}
      </div>}
    </>}

    {dialog && <PlanningDialog wide title={`${dialog.editing ? 'Edit' : 'Add'} ${dialog.entity}`} onClose={() => setDialog(null)}
      actions={<><button className="m3-btn text" onClick={() => setDialog(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !dialog.draft.name.trim()} onClick={saveEntity}>Save</button></>}>
      <div className="l1-form-grid">
        {FIELDS[dialog.entity].map((f) => <label key={f.key} className="m3-field"><span>{f.label}</span>
          {f.type === 'select'
            ? <select value={dialog.draft[f.key]} onChange={(e) => setDialog({ ...dialog, draft: { ...dialog.draft, [f.key]: e.target.value } })}>{f.options.map((o) => <option key={o} value={o}>{o}</option>)}</select>
            : f.type === 'textarea'
              ? <textarea rows={2} value={dialog.draft[f.key]} onChange={(e) => setDialog({ ...dialog, draft: { ...dialog.draft, [f.key]: e.target.value } })} />
              : <input value={dialog.draft[f.key]} onChange={(e) => setDialog({ ...dialog, draft: { ...dialog.draft, [f.key]: e.target.value } })} />}
        </label>)}
      </div>
    </PlanningDialog>}

    {ai?.draft && <PlanningDialog wide title="AI L2 architecture draft" onClose={() => setAi(null)}
      actions={<><button className="m3-btn text" onClick={() => setAi(null)}>Cancel</button><button className="m3-btn filled" disabled={busy} onClick={applyAi}>Apply all</button></>}>
      <div className="m3-banner info">{ai.draft.summary}</div>
      <div className="ai-baseline-preview">
        <p><strong>{ai.draft.containers.length}</strong> containers · <strong>{ai.draft.apis.length}</strong> APIs · <strong>{ai.draft.nfrs.length}</strong> NFRs · <strong>{ai.draft.integrations.length}</strong> integrations</p>
        {ai.draft.container_diagram && <MermaidView source={ai.draft.container_diagram} fit="width" />}
      </div>
    </PlanningDialog>}

    {importDlg && <PlanningDialog wide title="Import into L2" onClose={() => setImportDlg(null)}
      actions={<><button className="m3-btn text" onClick={() => setImportDlg(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !importDlg.content.trim()} onClick={runImport}>Import</button></>}>
      <div className="m3-banner info">Paste a spec — the parser extracts artifacts. OpenAPI → API contracts; Kubernetes manifest → containers. JSON or YAML.</div>
      <label className="m3-field"><span>Source</span>
        <select value={importDlg.kind} onChange={(e) => setImportDlg({ ...importDlg, kind: e.target.value })}>
          <option value="openapi">OpenAPI spec → APIs</option>
          <option value="kubernetes">Kubernetes manifest → Containers</option>
        </select></label>
      <label className="m3-field"><span>Content</span><textarea rows={10} spellCheck="false" value={importDlg.content} onChange={(e) => setImportDlg({ ...importDlg, content: e.target.value })} placeholder={importDlg.kind === 'openapi' ? '{ "info": {...}, "paths": { "/x": { "get": {} } } }' : 'kind: Deployment\\nmetadata:\\n  name: my-service'} /></label>
    </PlanningDialog>}

    {studio && <Suspense fallback={null}><DiagramStudio
      diagram={{ title: `${ws?.element.name || 'L2'} container diagram`, diagram_type: 'architecture', mermaid_source: diagram || 'flowchart LR\n  Web --> API', metadata: {} }}
      onClose={() => setStudio(false)}
      onSave={async (payload) => { setDiagram(payload.mermaid_source); await saveArch({ container_diagram: payload.mermaid_source }); setStudio(false) }} /></Suspense>}
  </div>
}

function GovernancePanel({ approvals, readiness, onSubmit, onDecide }) {
  return <div className="l1arch-panel">
    {readiness && (readiness.gaps?.length > 0 || readiness.recommendations?.length > 0) && (
      <div className="l1arch-review">
        <div className="l1arch-review-head"><Gavel size={15} /> Readiness review — {readiness.score}% · {readiness.status_label}</div>
        <div className="l1arch-review-cols">
          {readiness.gaps?.length > 0 && <div><h4>Open gaps ({readiness.gaps.length})</h4><ul>{readiness.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul></div>}
          {readiness.recommendations?.length > 0 && <div><h4>Recommendations</h4><ul>{readiness.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
        </div>
      </div>
    )}
    <div className="l1arch-section-head">
      <h3>Approval workflow <small>Sequential sign-off — baselines the L2 when complete</small></h3>
      <button className="m3-btn tonal small" onClick={onSubmit}>{approvals.submitted ? 'Restart review' : 'Submit for review'}</button>
    </div>
    {!approvals.submitted && <p className="l1-node-empty">Not yet submitted. Submit to start the engineering → security → NFR → data → architecture → sponsor sign-off chain.</p>}
    {approvals.submitted && <>
      <div className="l1arch-approval-progress"><span style={{ width: `${(approvals.approved_count / approvals.total) * 100}%` }} /></div>
      <p className="admin-muted">{approvals.approved_count}/{approvals.total} approved{approvals.complete ? ' · L2 baselined ✓' : approvals.current_stage ? ` · next: ${approvals.current_stage}` : ''}</p>
      <ol className="l1arch-approval-chain">
        {approvals.stages.map((s) => {
          const isCurrent = s.stage === approvals.current_stage
          return <li key={s.stage} className={`stage-${s.status}${isCurrent ? ' current' : ''}`}>
            <span className="l1arch-stage-mark">{s.status === 'approved' ? <CheckCircle2 size={16} /> : s.status === 'rejected' ? <X size={16} /> : <Circle size={16} />}</span>
            <span className="l1arch-stage-body"><strong>{s.label}</strong><small>{s.decided_by ? `${s.status} by ${s.decided_by}` : s.status}</small></span>
            {isCurrent && <span className="l1arch-stage-actions">
              <button className="m3-btn filled small" onClick={() => onDecide(s.stage, true)}><ThumbsUp size={13} /> Approve</button>
              <button className="m3-btn text small danger-ink" onClick={() => onDecide(s.stage, false)}><ThumbsDown size={13} /> Reject</button>
            </span>}
          </li>
        })}
      </ol>
    </>}
  </div>
}

function ReadinessCard({ readiness }) {
  const { score, status_label, checklist } = readiness
  const done = checklist.filter((c) => c.done).length
  return <div className="l1arch-readiness">
    <div className="l1arch-gauge" style={{ '--score': score }}><span>{score}%</span></div>
    <div className="l1arch-readiness-body">
      <strong>L2 readiness</strong><p>{status_label}</p>
      <div className="l1arch-checklist">{checklist.map((c) => <span key={c.item} className={c.done ? 'done' : ''}>{c.done ? <CheckCircle2 size={13} /> : <Circle size={13} />} {c.item}</span>)}</div>
      <small>{done}/{checklist.length} complete</small>
    </div>
  </div>
}

function ArtifactTab({ entity, title, columns, rows, onAdd, onEdit, onDelete }) {
  return <div className="l1arch-panel">
    <div className="l1arch-section-head"><h3>{title}</h3><button className="m3-btn tonal small" onClick={onAdd}><Plus size={14} /> Add</button></div>
    {rows.length === 0 ? <p className="l1-node-empty">Nothing captured yet.</p>
      : <div className="res-table-wrap"><table className="res-table">
        <thead><tr>{columns.map((c) => <th key={c}>{c.replace(/_/g, ' ')}</th>)}<th></th></tr></thead>
        <tbody>
          {rows.map((row) => <tr key={row.id} onClick={() => onEdit(entity, row)}>
            {columns.map((c) => <td key={c}>{['security_classification', 'nfr_criticality', 'risk_level', 'status', 'data_classification'].includes(c) ? <span className={PILL(row[c])}>{row[c]}</span> : String(row[c] ?? '—')}</td>)}
            <td className="res-row-actions" onClick={(e) => e.stopPropagation()}>
              <button className="m3-icon-btn" onClick={() => onEdit(entity, row)} aria-label="Edit"><Pencil size={15} /></button>
              <button className="m3-icon-btn danger-ink" onClick={() => onDelete(entity, row)} aria-label="Delete"><Trash2 size={15} /></button>
            </td>
          </tr>)}
        </tbody>
      </table></div>}
  </div>
}
