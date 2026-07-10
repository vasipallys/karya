import { Boxes, CheckCircle2, Circle, FileText, Gavel, GitBranch, Grid3x3, Layers, Network, Pencil, PencilRuler, Plug, Puzzle, ShieldAlert, Sparkles, ThumbsDown, ThumbsUp, Trash2, X } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { MarkdownViewer } from '../components/MarkdownEditor'
import MermaidView from '../components/MermaidView'
import { useToast } from '../ui/Toast'
import PlanningDialog from './PlanningDialog'

const DiagramStudio = lazy(() => import('./DiagramStudio'))

const TABS = [
  { id: 'overview', label: 'Component diagram', icon: Network },
  { id: 'components', label: 'Components', icon: Puzzle },
  { id: 'interfaces', label: 'Interfaces & contracts', icon: Plug },
  { id: 'dependencies', label: 'Dependencies', icon: Layers },
  { id: 'concerns', label: 'Design concerns', icon: ShieldAlert },
  { id: 'raci', label: 'RACI', icon: Grid3x3 },
  { id: 'governance', label: 'Governance', icon: Gavel },
  { id: 'traceability', label: 'Traceability', icon: GitBranch },
  { id: 'summary', label: 'Component summary', icon: FileText },
]
const RACI_LABELS = {
  component_diagram: 'Component Diagram', component_breakdown: 'Component Breakdown', interfaces: 'Interfaces',
  dependencies: 'Dependencies', design_concerns: 'Design Concerns', security: 'Security', testing: 'Testing',
  documentation: 'Documentation',
}
const ROLE_LABELS = {
  product_owner: 'Product Owner', tech_lead: 'Tech Lead', engineer: 'Engineer',
  security_engineer: 'Security Eng', qa: 'QA', sre: 'SRE',
}
const RACI_VALUES = ['', 'R', 'A', 'C', 'I']

const SELECT = (options) => ({ type: 'select', options })
const FIELDS = {
  component: [
    { key: 'name', label: 'Component' },
    { key: 'component_type', label: 'Type', ...SELECT(['controller', 'service', 'repository', 'gateway', 'model', 'client', 'config', 'ui', 'other']) },
    { key: 'responsibilities', label: 'Responsibilities', type: 'textarea' },
    { key: 'tech', label: 'Tech / framework' },
    { key: 'pattern', label: 'Design pattern' },
    { key: 'owner', label: 'Owner' },
    { key: 'status', label: 'Status', ...SELECT(['active', 'planned', 'retired']) },
  ],
  interface: [
    { key: 'name', label: 'Interface' },
    { key: 'direction', label: 'Direction', ...SELECT(['provided', 'consumed']) },
    { key: 'interface_type', label: 'Type', ...SELECT(['REST', 'GraphQL', 'gRPC', 'Event', 'Function', 'Message']) },
    { key: 'contract', label: 'Contract / signature', type: 'textarea' },
    { key: 'counterpart', label: 'Counterpart (consumer/provider)' },
    { key: 'authentication', label: 'Authentication' },
    { key: 'status', label: 'Status', ...SELECT(['proposed', 'active', 'deprecated']) },
  ],
  dependency: [
    { key: 'name', label: 'Dependency' },
    { key: 'dependency_type', label: 'Type', ...SELECT(['internal', 'container', 'external', 'library']) },
    { key: 'target', label: 'Target' },
    { key: 'reason', label: 'Reason', type: 'textarea' },
    { key: 'criticality', label: 'Criticality', ...SELECT(['high', 'medium', 'low']) },
    { key: 'status', label: 'Status', ...SELECT(['active', 'planned', 'retired']) },
  ],
  concern: [
    { key: 'name', label: 'Concern' },
    { key: 'category', label: 'Category', ...SELECT(['logging', 'caching', 'validation', 'security', 'error_handling', 'config', 'observability', 'resilience']) },
    { key: 'approach', label: 'Approach', type: 'textarea' },
    { key: 'owner', label: 'Owner' },
    { key: 'status', label: 'Status', ...SELECT(['planned', 'implemented', 'gap']) },
  ],
}
const DEFAULTS = {
  component: { name: '', component_type: 'service', responsibilities: '', tech: '', pattern: '', owner: '', status: 'active' },
  interface: { name: '', direction: 'provided', interface_type: 'REST', contract: '', counterpart: '', authentication: '', status: 'proposed' },
  dependency: { name: '', dependency_type: 'internal', target: '', reason: '', criticality: 'medium', status: 'active' },
  concern: { name: '', category: 'security', approach: '', owner: '', status: 'planned' },
}
const API = {
  component: { create: 'createL3Component', update: 'updateL3Component', del: 'deleteL3Component' },
  interface: { create: 'createL3Interface', update: 'updateL3Interface', del: 'deleteL3Interface' },
  dependency: { create: 'createL3Dependency', update: 'updateL3Dependency', del: 'deleteL3Dependency' },
  concern: { create: 'createL3Concern', update: 'updateL3Concern', del: 'deleteL3Concern' },
}
const PILL = (v) => `res-pill ${['high', 'gap', 'restricted'].includes(v) ? 'sub-partiallyallocated' : ['low', 'implemented', 'active', 'provided'].includes(v) ? 'ok' : ''}`

export default function L3Architecture({ projectId, onOpenCanvas }) {
  const toast = useToast()
  const [elements, setElements] = useState([])
  const [l3Id, setL3Id] = useState('')
  const [ws, setWs] = useState(null)
  const [tab, setTab] = useState('overview')
  const [dialog, setDialog] = useState(null)
  const [ai, setAi] = useState(null)
  const [exec, setExec] = useState(null)
  const [diagram, setDiagram] = useState('')
  const [summary, setSummary] = useState('')
  const [studio, setStudio] = useState(false)
  const [trace, setTrace] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const fail = (err) => { setError(err); toast.error(err) }

  useEffect(() => {
    api.c4Graph(projectId).then((g) => {
      const l3s = g.elements.filter((e) => e.level === 'L3')
      setElements(l3s)
      setL3Id((cur) => cur && l3s.some((e) => e.id === cur) ? cur : (l3s[0]?.id || ''))
    }).catch(fail)
  }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    if (!l3Id) return
    api.l3Workspace(projectId, l3Id).then((data) => {
      setWs(data); setDiagram(data.arch.component_diagram || ''); setSummary(data.arch.summary || '')
    }).catch(fail)
  }, [projectId, l3Id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setWs(null); load() }, [load])

  const saveArch = async (patch) => {
    setBusy(true)
    try { await api.updateL3Arch(projectId, l3Id, patch); toast.success('Saved'); await load() }
    catch (err) { fail(err) } finally { setBusy(false) }
  }

  const openDialog = (entity, editing = null) => setDialog({ entity, editing, draft: editing ? { ...DEFAULTS[entity], ...editing } : { ...DEFAULTS[entity] } })
  const saveEntity = async () => {
    setBusy(true)
    const { entity, editing, draft } = dialog
    try {
      if (editing) await api[API[entity].update](projectId, l3Id, editing.id, draft)
      else await api[API[entity].create](projectId, l3Id, draft)
      setDialog(null); toast.success('Saved'); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }
  const removeEntity = async (entity, item) => {
    if (!window.confirm('Delete this item?')) return
    try { await api[API[entity].del](projectId, l3Id, item.id); await load() } catch (err) { fail(err) }
  }

  const runAi = async () => {
    setAi({ loading: true })
    try { setAi({ draft: await api.aiL3Baseline(projectId, l3Id, '') }) } catch (err) { fail(err); setAi(null) }
  }
  const applyAi = async () => {
    setBusy(true)
    try {
      const result = await api.applyL3Baseline(projectId, l3Id, ai.draft)
      setAi(null); toast.success(`Added ${Object.values(result).reduce((a, b) => a + b, 0)} items`); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  const openSummary = async () => {
    setTab('summary'); setExec({ loading: true })
    try { setExec({ markdown: (await api.l3EngineeringSummary(projectId, l3Id)).markdown }) } catch (err) { fail(err); setExec(null) }
  }
  const openTraceability = async () => {
    setTab('traceability'); setTrace({ loading: true })
    try { setTrace(await api.l3Traceability(projectId, l3Id)) } catch (err) { fail(err); setTrace(null) }
  }

  const submitForReview = async () => {
    try { await api.submitL3ForReview(projectId, l3Id); toast.success('Submitted for review'); await load() } catch (err) { fail(err) }
  }
  const decide = async (stage, approve) => {
    try { await api.decideL3Approval(projectId, l3Id, stage, { approve, decided_by: 'me' }); toast.success(approve ? 'Approved' : 'Rejected'); await load() } catch (err) { fail(err) }
  }
  const setRaci = async (artifact, role, value) => {
    try { await api.setL3Raci(projectId, l3Id, artifact, role, value); await load() } catch (err) { fail(err) }
  }

  if (elements.length === 0) {
    return <div className="l1-empty-panel prominent"><Puzzle size={38} /><h2>No L3 component yet</h2><p>Create an L3 component/story on the C4 canvas first (a child of an L2 container). It becomes the anchor for component architecture.</p><button className="m3-btn filled" onClick={onOpenCanvas}>Open C4 canvas</button></div>
  }

  return <div className="l1-planning">
    {error && <div className="m3-banner error"><span>{String(error.message || error)}</span><button className="m3-btn text small" onClick={() => setError(null)}>Dismiss</button></div>}
    <header className="l1-plan-hero">
      <div className="l1-plan-identity">
        <span className="l1-hero-icon"><Puzzle size={22} /></span>
        <div><span className="l1-eyebrow">L3 component architecture</span>
          <select value={l3Id} onChange={(e) => setL3Id(e.target.value)} aria-label="Select L3 element">{elements.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select>
          {ws?.parent && <p>Linked L2: {ws.parent.name}</p>}</div>
      </div>
      <div className="l1-plan-tools">
        <button className="m3-btn tonal small" onClick={runAi} disabled={ai?.loading}><Sparkles size={15} /> {ai?.loading ? 'Drafting…' : 'AI generate L3'}</button>
        <button className="m3-icon-btn" onClick={load} aria-label="Refresh"><Network size={17} /></button>
      </div>
    </header>

    {ws && <>
      <div className="l1arch-head"><ReadinessCard readiness={ws.readiness} /></div>
      <nav className="l1arch-tabs" aria-label="L3 sections">
        {TABS.map(({ id, label, icon: Icon }) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => (id === 'summary' ? openSummary() : id === 'traceability' ? openTraceability() : setTab(id))}><Icon size={15} /> {label}</button>)}
      </nav>

      {tab === 'overview' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Summary</h3></div>
        <textarea className="vision-field-summary" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One-paragraph L3 component summary" />
        <div className="l1arch-section-head"><h3>Component diagram <small>Mermaid — portable & reviewable</small></h3>
          <div className="l1arch-export-actions">
            <button className="m3-btn outlined small" onClick={() => setStudio(true)}><PencilRuler size={14} /> Open studio</button>
            <button className="m3-btn filled small" disabled={busy} onClick={() => saveArch({ summary, component_diagram: diagram })}>Save</button>
          </div>
        </div>
        <div className="l2-diagram-grid">
          <div className="l2-diagram-code"><header>Mermaid source</header>
            <textarea spellCheck="false" value={diagram} onChange={(e) => setDiagram(e.target.value)} placeholder={'flowchart TB\n  Controller --> Service\n  Service --> Repository'} /></div>
          <div className="l2-diagram-preview"><header>Live preview</header>
            {diagram.trim() ? <MermaidView source={diagram} /> : <p className="l1-node-empty">Write Mermaid or use “AI generate L3”.</p>}</div>
        </div>
        <div className="l1arch-section-head"><h3>Component status</h3></div>
        <div className="l1-form-grid">
          <label className="m3-field"><span>Lifecycle status</span>
            <select value={ws.arch.status} onChange={(e) => saveArch({ status: e.target.value })}>{['draft', 'reviewed', 'approved', 'baselined', 'archived'].map((s) => <option key={s}>{s}</option>)}</select></label>
        </div>
      </div>}

      {tab === 'components' && <ArtifactTab entity="component" title="Components & Responsibilities" columns={['name', 'component_type', 'tech', 'pattern', 'owner', 'status']} rows={ws.components} onAdd={() => openDialog('component')} onEdit={openDialog} onDelete={removeEntity} />}
      {tab === 'interfaces' && <ArtifactTab entity="interface" title="Interfaces & Contracts" columns={['name', 'direction', 'interface_type', 'counterpart', 'authentication', 'status']} rows={ws.interfaces} onAdd={() => openDialog('interface')} onEdit={openDialog} onDelete={removeEntity} />}
      {tab === 'dependencies' && <ArtifactTab entity="dependency" title="Dependencies" columns={['name', 'dependency_type', 'target', 'criticality', 'status']} rows={ws.dependencies} onAdd={() => openDialog('dependency')} onEdit={openDialog} onDelete={removeEntity} />}
      {tab === 'concerns' && <ArtifactTab entity="concern" title="Cross-Cutting Design Concerns" columns={['name', 'category', 'approach', 'status']} rows={ws.concerns} onAdd={() => openDialog('concern')} onEdit={openDialog} onDelete={removeEntity} />}

      {tab === 'raci' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>RACI matrix <small>Responsibility per L3 artifact × role</small></h3></div>
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
        <div className="l1arch-section-head"><h3>Traceability <small>L2 → L3 → L4</small></h3></div>
        {trace?.loading && <div className="l1-loading">Building trace…</div>}
        {trace?.mermaid && <>
          <div className="l1arch-diagram-box"><MermaidView source={trace.mermaid} /></div>
          <p className="admin-muted">{trace.l2 ? `L2 “${trace.l2.name}” → ` : ''}L3 “{trace.l3.name}” → {trace.l4_count} L4 task{trace.l4_count === 1 ? '' : 's'}{trace.l4_children.length ? `: ${trace.l4_children.map((c) => c.name).join(', ')}` : ''}.</p>
        </>}
      </div>}

      {tab === 'summary' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Component summary <small>Markdown + Mermaid — a living document</small></h3>
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

    {ai?.draft && <PlanningDialog wide title="AI L3 component draft" onClose={() => setAi(null)}
      actions={<><button className="m3-btn text" onClick={() => setAi(null)}>Cancel</button><button className="m3-btn filled" disabled={busy} onClick={applyAi}>Apply all</button></>}>
      <div className="m3-banner info">{ai.draft.summary}</div>
      <div className="ai-baseline-preview">
        <p><strong>{ai.draft.components.length}</strong> components · <strong>{ai.draft.interfaces.length}</strong> interfaces · <strong>{ai.draft.dependencies.length}</strong> deps · <strong>{ai.draft.concerns.length}</strong> concerns</p>
        {ai.draft.component_diagram && <MermaidView source={ai.draft.component_diagram} fit="width" />}
      </div>
    </PlanningDialog>}

    {studio && <Suspense fallback={null}><DiagramStudio
      diagram={{ title: `${ws?.element.name || 'L3'} component diagram`, diagram_type: 'architecture', mermaid_source: diagram || 'flowchart TB\n  Controller --> Service', metadata: {} }}
      onClose={() => setStudio(false)}
      onSave={async (payload) => { setDiagram(payload.mermaid_source); await saveArch({ component_diagram: payload.mermaid_source }); setStudio(false) }} /></Suspense>}
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
      <h3>Design approval workflow <small>Sequential sign-off — baselines the L3 when complete</small></h3>
      <button className="m3-btn tonal small" onClick={onSubmit}>{approvals.submitted ? 'Restart review' : 'Submit for review'}</button>
    </div>
    {!approvals.submitted && <p className="l1-node-empty">Not yet submitted. Submit to start the design → interfaces → security → testing → architecture → tech-lead sign-off chain.</p>}
    {approvals.submitted && <>
      <div className="l1arch-approval-progress"><span style={{ width: `${(approvals.approved_count / approvals.total) * 100}%` }} /></div>
      <p className="admin-muted">{approvals.approved_count}/{approvals.total} approved{approvals.complete ? ' · L3 baselined ✓' : approvals.current_stage ? ` · next: ${approvals.current_stage}` : ''}</p>
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
      <strong>L3 readiness</strong><p>{status_label}</p>
      <div className="l1arch-checklist">{checklist.map((c) => <span key={c.item} className={c.done ? 'done' : ''}>{c.done ? <CheckCircle2 size={13} /> : <Circle size={13} />} {c.item}</span>)}</div>
      <small>{done}/{checklist.length} complete</small>
    </div>
  </div>
}

function ArtifactTab({ entity, title, columns, rows, onAdd, onEdit, onDelete }) {
  return <div className="l1arch-panel">
    <div className="l1arch-section-head"><h3>{title}</h3><button className="m3-btn tonal small" onClick={onAdd}><Boxes size={14} /> Add</button></div>
    {rows.length === 0 ? <p className="l1-node-empty">Nothing captured yet.</p>
      : <div className="res-table-wrap"><table className="res-table">
        <thead><tr>{columns.map((c) => <th key={c}>{c.replace(/_/g, ' ')}</th>)}<th></th></tr></thead>
        <tbody>
          {rows.map((row) => <tr key={row.id} onClick={() => onEdit(entity, row)}>
            {columns.map((c) => <td key={c}>{['criticality', 'status', 'direction'].includes(c) ? <span className={PILL(row[c])}>{row[c]}</span> : String(row[c] ?? '—')}</td>)}
            <td className="res-row-actions" onClick={(e) => e.stopPropagation()}>
              <button className="m3-icon-btn" onClick={() => onEdit(entity, row)} aria-label="Edit"><Pencil size={15} /></button>
              <button className="m3-icon-btn danger-ink" onClick={() => onDelete(entity, row)} aria-label="Delete"><Trash2 size={15} /></button>
            </td>
          </tr>)}
        </tbody>
      </table></div>}
  </div>
}
