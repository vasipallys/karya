import { CheckCircle2, CheckSquare, Circle, Code2, FileText, FlaskConical, GitBranch, ListChecks, Network, Pencil, PencilRuler, Plus, Sparkles, Square, Trash2 } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { MarkdownViewer } from '../components/MarkdownEditor'
import MermaidView from '../components/MermaidView'
import { useToast } from '../ui/Toast'
import PlanningDialog from './PlanningDialog'

const DiagramStudio = lazy(() => import('./DiagramStudio'))

const TABS = [
  { id: 'overview', label: 'Implementation diagram', icon: Network },
  { id: 'code_units', label: 'Code units', icon: Code2 },
  { id: 'test_cases', label: 'Test cases', icon: FlaskConical },
  { id: 'checklist', label: 'Definition of Done', icon: ListChecks },
  { id: 'traceability', label: 'Traceability', icon: GitBranch },
  { id: 'summary', label: 'Implementation summary', icon: FileText },
]

const SELECT = (options) => ({ type: 'select', options })
const FIELDS = {
  code_unit: [
    { key: 'name', label: 'Code unit' },
    { key: 'unit_type', label: 'Type', ...SELECT(['class', 'interface', 'function', 'module', 'config', 'migration', 'test']) },
    { key: 'responsibility', label: 'Responsibility', type: 'textarea' },
    { key: 'tech', label: 'Tech / language' },
    { key: 'path', label: 'Code path' },
    { key: 'complexity', label: 'Complexity', ...SELECT(['high', 'medium', 'low']) },
    { key: 'status', label: 'Status', ...SELECT(['todo', 'in_progress', 'done']) },
  ],
  test_case: [
    { key: 'name', label: 'Test case' },
    { key: 'test_type', label: 'Type', ...SELECT(['unit', 'integration', 'e2e', 'contract', 'manual']) },
    { key: 'scenario', label: 'Scenario (given/when)', type: 'textarea' },
    { key: 'expected', label: 'Expected (then)', type: 'textarea' },
    { key: 'status', label: 'Status', ...SELECT(['planned', 'passing', 'failing']) },
  ],
  checklist: [
    { key: 'item', label: 'Item' },
    { key: 'category', label: 'Category', ...SELECT(['code', 'tests', 'docs', 'security', 'review', 'deploy']) },
  ],
}
const DEFAULTS = {
  code_unit: { name: '', unit_type: 'class', responsibility: '', tech: '', path: '', complexity: 'medium', status: 'todo' },
  test_case: { name: '', test_type: 'unit', scenario: '', expected: '', status: 'planned' },
  checklist: { item: '', category: 'code', done: false },
}
const API = {
  code_unit: { create: 'createL4CodeUnit', update: 'updateL4CodeUnit', del: 'deleteL4CodeUnit', nameKey: 'name' },
  test_case: { create: 'createL4TestCase', update: 'updateL4TestCase', del: 'deleteL4TestCase', nameKey: 'name' },
  checklist: { create: 'createL4Checklist', update: 'updateL4Checklist', del: 'deleteL4Checklist', nameKey: 'item' },
}
const PILL = (v) => `res-pill ${['high', 'failing', 'todo'].includes(v) ? 'sub-partiallyallocated' : ['low', 'passing', 'done'].includes(v) ? 'ok' : ''}`

export default function L4Architecture({ projectId, onOpenCanvas }) {
  const toast = useToast()
  const [elements, setElements] = useState([])
  const [l4Id, setL4Id] = useState('')
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
      const l4s = g.elements.filter((e) => e.level === 'L4')
      setElements(l4s)
      setL4Id((cur) => cur && l4s.some((e) => e.id === cur) ? cur : (l4s[0]?.id || ''))
    }).catch(fail)
  }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(() => {
    if (!l4Id) return
    api.l4Workspace(projectId, l4Id).then((data) => {
      setWs(data); setDiagram(data.arch.code_diagram || ''); setSummary(data.arch.summary || '')
    }).catch(fail)
  }, [projectId, l4Id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setWs(null); load() }, [load])

  const saveArch = async (patch) => {
    setBusy(true)
    try { await api.updateL4Arch(projectId, l4Id, patch); toast.success('Saved'); await load() }
    catch (err) { fail(err) } finally { setBusy(false) }
  }

  const openDialog = (entity, editing = null) => setDialog({ entity, editing, draft: editing ? { ...DEFAULTS[entity], ...editing } : { ...DEFAULTS[entity] } })
  const saveEntity = async () => {
    setBusy(true)
    const { entity, editing, draft } = dialog
    try {
      if (editing) await api[API[entity].update](projectId, l4Id, editing.id, draft)
      else await api[API[entity].create](projectId, l4Id, draft)
      setDialog(null); toast.success('Saved'); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }
  const removeEntity = async (entity, item) => {
    if (!window.confirm('Delete this item?')) return
    try { await api[API[entity].del](projectId, l4Id, item.id); await load() } catch (err) { fail(err) }
  }
  const toggleChecklist = async (item) => {
    try { await api.updateL4Checklist(projectId, l4Id, item.id, { done: !item.done }); await load() } catch (err) { fail(err) }
  }

  const runAi = async () => {
    setAi({ loading: true })
    try { setAi({ draft: await api.aiL4Baseline(projectId, l4Id, '') }) } catch (err) { fail(err); setAi(null) }
  }
  const applyAi = async () => {
    setBusy(true)
    try {
      const result = await api.applyL4Baseline(projectId, l4Id, ai.draft)
      setAi(null); toast.success(`Added ${Object.values(result).reduce((a, b) => a + b, 0)} items`); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  const openSummary = async () => {
    setTab('summary'); setExec({ loading: true })
    try { setExec({ markdown: (await api.l4ImplementationSummary(projectId, l4Id)).markdown }) } catch (err) { fail(err); setExec(null) }
  }
  const openTraceability = async () => {
    setTab('traceability'); setTrace({ loading: true })
    try { setTrace(await api.l4Traceability(projectId, l4Id)) } catch (err) { fail(err); setTrace(null) }
  }

  if (elements.length === 0) {
    return <div className="l1-empty-panel prominent"><Code2 size={38} /><h2>No L4 task yet</h2><p>Create an L4 task on the C4 canvas first (a child of an L3 component). It becomes the anchor for implementation detail.</p><button className="m3-btn filled" onClick={onOpenCanvas}>Open C4 canvas</button></div>
  }

  return <div className="l1-planning">
    {error && <div className="m3-banner error"><span>{String(error.message || error)}</span><button className="m3-btn text small" onClick={() => setError(null)}>Dismiss</button></div>}
    <header className="l1-plan-hero">
      <div className="l1-plan-identity">
        <span className="l1-hero-icon"><Code2 size={22} /></span>
        <div><span className="l1-eyebrow">L4 implementation detail</span>
          <select value={l4Id} onChange={(e) => setL4Id(e.target.value)} aria-label="Select L4 element">{elements.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select>
          {ws?.parent && <p>Linked L3: {ws.parent.name}</p>}</div>
      </div>
      <div className="l1-plan-tools">
        <button className="m3-btn tonal small" onClick={runAi} disabled={ai?.loading}><Sparkles size={15} /> {ai?.loading ? 'Drafting…' : 'AI generate L4'}</button>
        <button className="m3-icon-btn" onClick={load} aria-label="Refresh"><Network size={17} /></button>
      </div>
    </header>

    {ws && <>
      <div className="l1arch-head"><ReadinessCard readiness={ws.readiness} /></div>
      <nav className="l1arch-tabs" aria-label="L4 sections">
        {TABS.map(({ id, label, icon: Icon }) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => (id === 'summary' ? openSummary() : id === 'traceability' ? openTraceability() : setTab(id))}><Icon size={15} /> {label}</button>)}
      </nav>

      {tab === 'overview' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Summary</h3></div>
        <textarea className="vision-field-summary" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One-paragraph implementation summary" />
        <div className="l1arch-section-head"><h3>Implementation diagram <small>Mermaid class / sequence diagram</small></h3>
          <div className="l1arch-export-actions">
            <button className="m3-btn outlined small" onClick={() => setStudio(true)}><PencilRuler size={14} /> Open studio</button>
            <button className="m3-btn filled small" disabled={busy} onClick={() => saveArch({ summary, code_diagram: diagram })}>Save</button>
          </div>
        </div>
        <div className="l2-diagram-grid">
          <div className="l2-diagram-code"><header>Mermaid source</header>
            <textarea spellCheck="false" value={diagram} onChange={(e) => setDiagram(e.target.value)} placeholder={'classDiagram\n  class Controller {\n    +create(req)\n  }'} /></div>
          <div className="l2-diagram-preview"><header>Live preview</header>
            {diagram.trim() ? <MermaidView source={diagram} /> : <p className="l1-node-empty">Write Mermaid or use “AI generate L4”.</p>}</div>
        </div>
        <div className="l1arch-section-head"><h3>Task status</h3></div>
        <div className="l1-form-grid">
          <label className="m3-field"><span>Lifecycle status</span>
            <select value={ws.arch.status} onChange={(e) => saveArch({ status: e.target.value })}>{['draft', 'reviewed', 'approved', 'done', 'archived'].map((s) => <option key={s}>{s}</option>)}</select></label>
        </div>
      </div>}

      {tab === 'code_units' && <ArtifactTab entity="code_unit" title="Code Units" columns={['name', 'unit_type', 'tech', 'path', 'complexity', 'status']} rows={ws.code_units} onAdd={() => openDialog('code_unit')} onEdit={openDialog} onDelete={removeEntity} />}
      {tab === 'test_cases' && <ArtifactTab entity="test_case" title="Test Cases" columns={['name', 'test_type', 'scenario', 'status']} rows={ws.test_cases} onAdd={() => openDialog('test_case')} onEdit={openDialog} onDelete={removeEntity} />}

      {tab === 'checklist' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Definition of Done <small>{ws.checklist.filter((c) => c.done).length}/{ws.checklist.length} done</small></h3>
          <button className="m3-btn tonal small" onClick={() => openDialog('checklist')}><Plus size={14} /> Add</button></div>
        {ws.checklist.length === 0 ? <p className="l1-node-empty">No Definition-of-Done items yet.</p>
          : <ul className="l4-dod-list">
            {ws.checklist.map((c) => <li key={c.id} className={c.done ? 'done' : ''}>
              <button className="l4-dod-toggle" onClick={() => toggleChecklist(c)} aria-label={c.done ? 'Mark not done' : 'Mark done'}>
                {c.done ? <CheckSquare size={18} /> : <Square size={18} />}</button>
              <span className={`res-pill ${c.done ? 'ok' : ''}`}>{c.category}</span>
              <span className="l4-dod-text">{c.item}</span>
              <button className="m3-icon-btn danger-ink" onClick={() => removeEntity('checklist', c)} aria-label="Delete"><Trash2 size={15} /></button>
            </li>)}
          </ul>}
      </div>}

      {tab === 'traceability' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Traceability <small>L2 → L3 → L4</small></h3></div>
        {trace?.loading && <div className="l1-loading">Building trace…</div>}
        {trace?.mermaid && <>
          <div className="l1arch-diagram-box"><MermaidView source={trace.mermaid} /></div>
          <p className="admin-muted">{trace.l2 ? `L2 “${trace.l2.name}” → ` : ''}{trace.l3 ? `L3 “${trace.l3.name}” → ` : ''}L4 “{trace.l4.name}”.</p>
        </>}
      </div>}

      {tab === 'summary' && <div className="l1arch-panel">
        <div className="l1arch-section-head"><h3>Implementation summary <small>Markdown + Mermaid — a living document</small></h3>
          {exec?.markdown && <button className="m3-btn text small" onClick={() => { navigator.clipboard?.writeText(exec.markdown); toast.success('Markdown copied') }}>Copy MD</button>}</div>
        {exec?.loading && <div className="l1-loading">Composing summary…</div>}
        {exec?.markdown && <div className="l1arch-exec"><MarkdownViewer content={exec.markdown} /></div>}
      </div>}
    </>}

    {dialog && <PlanningDialog wide title={`${dialog.editing ? 'Edit' : 'Add'} ${dialog.entity.replace('_', ' ')}`} onClose={() => setDialog(null)}
      actions={<><button className="m3-btn text" onClick={() => setDialog(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !String(dialog.draft[API[dialog.entity].nameKey] || '').trim()} onClick={saveEntity}>Save</button></>}>
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

    {ai?.draft && <PlanningDialog wide title="AI L4 implementation draft" onClose={() => setAi(null)}
      actions={<><button className="m3-btn text" onClick={() => setAi(null)}>Cancel</button><button className="m3-btn filled" disabled={busy} onClick={applyAi}>Apply all</button></>}>
      <div className="m3-banner info">{ai.draft.summary}</div>
      <div className="ai-baseline-preview">
        <p><strong>{ai.draft.code_units.length}</strong> code units · <strong>{ai.draft.test_cases.length}</strong> tests · <strong>{ai.draft.checklist.length}</strong> DoD items</p>
        {ai.draft.code_diagram && <MermaidView source={ai.draft.code_diagram} fit="width" />}
      </div>
    </PlanningDialog>}

    {studio && <Suspense fallback={null}><DiagramStudio
      diagram={{ title: `${ws?.element.name || 'L4'} implementation diagram`, diagram_type: 'class', mermaid_source: diagram || 'classDiagram\n  class Controller', metadata: {} }}
      onClose={() => setStudio(false)}
      onSave={async (payload) => { setDiagram(payload.mermaid_source); await saveArch({ code_diagram: payload.mermaid_source }); setStudio(false) }} /></Suspense>}
  </div>
}

function ReadinessCard({ readiness }) {
  const { score, status_label, checklist } = readiness
  const done = checklist.filter((c) => c.done).length
  return <div className="l1arch-readiness">
    <div className="l1arch-gauge" style={{ '--score': score }}><span>{score}%</span></div>
    <div className="l1arch-readiness-body">
      <strong>L4 readiness</strong><p>{status_label}</p>
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
            {columns.map((c) => <td key={c}>{['complexity', 'status'].includes(c) ? <span className={PILL(row[c])}>{row[c]}</span> : String(row[c] ?? '—')}</td>)}
            <td className="res-row-actions" onClick={(e) => e.stopPropagation()}>
              <button className="m3-icon-btn" onClick={() => onEdit(entity, row)} aria-label="Edit"><Pencil size={15} /></button>
              <button className="m3-icon-btn danger-ink" onClick={() => onDelete(entity, row)} aria-label="Delete"><Trash2 size={15} /></button>
            </td>
          </tr>)}
        </tbody>
      </table></div>}
  </div>
}
