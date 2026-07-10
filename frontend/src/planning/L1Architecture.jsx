import { AlertTriangle, CheckCircle2, Circle, Download, FileText, Gavel, Landmark, Link2, MessageSquare, Pencil, Plus, ShieldAlert, Sparkles, Target, ThumbsDown, ThumbsUp, Trash2, Users, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import MarkdownEditor, { MarkdownViewer, renderMermaidImages } from '../components/MarkdownEditor'
import { useToast } from '../ui/Toast'
import PlanningDialog from './PlanningDialog'

const TABS = [
  { id: 'vision', label: 'Vision & OKRs', icon: Target },
  { id: 'stakeholders', label: 'Stakeholders & RACI', icon: Users },
  { id: 'capabilities', label: 'Capabilities', icon: Landmark },
  { id: 'risks', label: 'Risk & Funding', icon: ShieldAlert },
  { id: 'governance', label: 'Governance', icon: Gavel },
  { id: 'discussion', label: 'Discussion', icon: MessageSquare },
  { id: 'summary', label: 'Executive summary', icon: FileText },
]

// Field schemas drive a generic add/edit dialog to keep this file lean.
const SELECT = (options) => ({ type: 'select', options })
const FIELDS = {
  okr: [
    { key: 'objective', label: 'Objective' },
    { key: 'key_result', label: 'Key result' },
    { key: 'metric_name', label: 'Metric' },
    { key: 'target_value', label: 'Target' },
    { key: 'current_value', label: 'Current' },
    { key: 'owner', label: 'Owner' },
    { key: 'status', label: 'Status', ...SELECT(['on_track', 'at_risk', 'off_track', 'done']) },
    { key: 'linked_element_id', label: 'Traceability link (initiative/epic)', type: 'element' },
  ],
  stakeholder: [
    { key: 'name', label: 'Name' },
    { key: 'role', label: 'Role' },
    { key: 'department', label: 'Department' },
    { key: 'stakeholder_type', label: 'Type', ...SELECT(['internal', 'external', 'vendor', 'regulator']) },
    { key: 'influence', label: 'Influence', ...SELECT(['high', 'medium', 'low']) },
    { key: 'interest', label: 'Interest', ...SELECT(['high', 'medium', 'low']) },
    { key: 'raci', label: 'RACI', ...SELECT(['Responsible', 'Accountable', 'Consulted', 'Informed']) },
    { key: 'owns', label: 'Owns (systems / capabilities)' },
    { key: 'status', label: 'Status', ...SELECT(['active', 'inactive', 'replaced']) },
  ],
  capability: [
    { key: 'name', label: 'Capability' },
    { key: 'description', label: 'Description', type: 'textarea' },
    { key: 'cap_level', label: 'Level', ...SELECT(['L1', 'L2', 'L3']) },
    { key: 'business_owner', label: 'Business owner' },
    { key: 'technology_owner', label: 'Technology owner' },
    { key: 'criticality', label: 'Criticality', ...SELECT(['high', 'medium', 'low']) },
    { key: 'current_maturity', label: 'Current maturity (1-5)', type: 'number' },
    { key: 'target_maturity', label: 'Target maturity (1-5)', type: 'number' },
    { key: 'strategic_priority', label: 'Priority', ...SELECT(['high', 'medium', 'low']) },
    { key: 'linked_element_id', label: 'Supporting system (C4 container)', type: 'element' },
  ],
  risk: [
    { key: 'title', label: 'Risk' },
    { key: 'category', label: 'Category', ...SELECT(['delivery', 'architecture', 'security', 'compliance', 'operational', 'financial']) },
    { key: 'risk_level', label: 'Level', ...SELECT(['high', 'medium', 'low']) },
    { key: 'owner', label: 'Owner' },
    { key: 'mitigation', label: 'Mitigation', type: 'textarea' },
    { key: 'funding_source', label: 'Funding source' },
    { key: 'approved_budget', label: 'Approved budget', type: 'number' },
    { key: 'actual_spend', label: 'Actual spend', type: 'number' },
    { key: 'status', label: 'Status', ...SELECT(['proposed', 'approved', 'active', 'blocked', 'completed']) },
    { key: 'linked_element_id', label: 'Affected element (C4)', type: 'element' },
  ],
}
const DEFAULTS = {
  okr: { objective: '', key_result: '', metric_name: '', target_value: '', current_value: '', owner: '', status: 'on_track', linked_element_id: '' },
  stakeholder: { name: '', resource_staff_id: '', role: '', department: '', stakeholder_type: 'internal', influence: 'medium', interest: 'medium', raci: 'Informed', owns: '', status: 'active' },
  capability: { name: '', description: '', cap_level: 'L1', business_owner: '', technology_owner: '', criticality: 'medium', current_maturity: 1, target_maturity: 3, strategic_priority: 'medium', linked_element_id: '' },
  risk: { title: '', category: 'delivery', risk_level: 'medium', owner: '', mitigation: '', funding_source: '', approved_budget: 0, actual_spend: 0, status: 'proposed', linked_element_id: '' },
}
const API = {
  okr: { create: 'createL1Okr', update: 'updateL1Okr', del: 'deleteL1Okr' },
  stakeholder: { create: 'createL1Stakeholder', update: 'updateL1Stakeholder', del: 'deleteL1Stakeholder' },
  capability: { create: 'createL1Capability', update: 'updateL1Capability', del: 'deleteL1Capability' },
  risk: { create: 'createL1Risk', update: 'updateL1Risk', del: 'deleteL1Risk' },
}
const LEVEL_PILL = (value) => `res-pill ${['high', 'off_track', 'blocked'].includes(value) ? 'sub-partiallyallocated' : ['low', 'done', 'active'].includes(value) ? 'ok' : ''}`

export default function L1Architecture({ projectId, l1Id, setError }) {
  const toast = useToast()
  const [baseline, setBaseline] = useState(null)
  const [tab, setTab] = useState('vision')
  const [dialog, setDialog] = useState(null)   // { entity, editing, draft }
  const [ai, setAi] = useState(null)           // { loading, draft }
  const [exec, setExec] = useState(null)       // { loading, markdown }
  const [vision, setVision] = useState(null)
  const [busy, setBusy] = useState(false)
  const [docImport, setDocImport] = useState(null) // { text }
  const [suggest, setSuggest] = useState(null)     // { staff, selected:Set }
  const [capView, setCapView] = useState('table')  // 'table' | 'heatmap'
  const [elements, setElements] = useState([])     // C4 elements for traceability links
  const [staffPool, setStaffPool] = useState([])   // active resource-directory staff
  const [impact, setImpact] = useState(null)
  const [commentBody, setCommentBody] = useState('')
  const [jira, setJira] = useState(null)           // { instance, project_code, target }

  const load = useCallback(() => api.l1Baseline(projectId, l1Id)
    .then((data) => { setBaseline(data); setVision(null) })
    .catch(setError), [projectId, l1Id, setError])
  useEffect(() => { load() }, [load])
  useEffect(() => { api.c4Graph(projectId).then((g) => setElements(g.elements.filter((e) => e.level !== 'L1'))).catch(() => setElements([])) }, [projectId])
  useEffect(() => { api.listStaff({ staff_status: 'Active' }).then(setStaffPool).catch(() => setStaffPool([])) }, [])
  useEffect(() => { api.l1Impact(projectId, l1Id).then(setImpact).catch(() => setImpact(null)) }, [projectId, l1Id, baseline])

  const addComment = async () => {
    if (!commentBody.trim()) return
    try { await api.createL1Comment(projectId, l1Id, { body: commentBody, author: 'me' }); setCommentBody(''); toast.success('Comment added'); await load() } catch (err) { fail(err) }
  }
  const resolveComment = async (c) => { try { await api.resolveL1Comment(projectId, l1Id, c.id, c.status !== 'resolved'); await load() } catch (err) { fail(err) } }
  const deleteComment = async (c) => { try { await api.deleteL1Comment(projectId, l1Id, c.id); await load() } catch (err) { fail(err) } }

  const runJiraImport = async () => {
    if (!jira?.instance.trim() || !jira?.project_code.trim()) return
    setBusy(true)
    try {
      const result = await api.importJiraToL1(projectId, l1Id, jira)
      setJira(null); toast.success(`Imported ${result.created} from Jira`); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  const fail = (err) => { (setError || toast.error)(err); toast.error(err) }

  const saveVision = async () => {
    setBusy(true)
    try { await api.updateL1Vision(projectId, l1Id, vision); toast.success('Vision saved'); await load() }
    catch (err) { fail(err) } finally { setBusy(false) }
  }

  // Generate a concise summary of a field's "more details" into the parent field.
  const summarizeField = async (fieldKey, detailKey, style, current) => {
    const details = (current[detailKey] || '').trim()
    if (!details) { toast.info('Add some details first, then summarize.'); return }
    try {
      const { summary } = await api.aiSummarize(details, style)
      setVision({ ...current, [fieldKey]: summary })
      toast.success('Summary generated — review and save')
    } catch (err) { fail(err) }
  }

  const openDialog = (entity, editing = null) => setDialog({
    entity, editing, draft: editing ? { ...DEFAULTS[entity], ...editing } : { ...DEFAULTS[entity] },
  })

  const saveEntity = async () => {
    setBusy(true)
    const { entity, editing, draft } = dialog
    const payload = { ...draft }
    for (const f of FIELDS[entity]) {
      if (f.type === 'number') payload[f.key] = Number(payload[f.key] || 0)
      if (f.type === 'element') payload[f.key] = payload[f.key] || null
    }
    if ('resource_staff_id' in payload && !payload.resource_staff_id) payload.resource_staff_id = null
    try {
      if (editing) await api[API[entity].update](projectId, l1Id, editing.id, payload)
      else await api[API[entity].create](projectId, l1Id, payload)
      setDialog(null); toast.success('Saved'); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  const removeEntity = async (entity, item) => {
    if (!window.confirm('Delete this item?')) return
    try { await api[API[entity].del](projectId, l1Id, item.id); await load() } catch (err) { fail(err) }
  }

  const runAi = async (brief = '') => {
    setAi({ loading: true })
    try { const draft = await api.aiL1Baseline(projectId, l1Id, brief); setAi({ draft }); setDocImport(null) }
    catch (err) { fail(err); setAi(null) }
  }

  // Document import (Confluence/SharePoint/Drive stand-in): paste a doc, AI extracts the baseline.
  const importDoc = async () => {
    if (!docImport?.text.trim()) return
    await runAi(docImport.text)
  }

  // Stakeholder suggestion from the global resource directory (section 8.3).
  const suggestStakeholders = async () => {
    try {
      const staff = await api.listStaff({ staff_status: 'Active' })
      if (staff.length === 0) { toast.info('No active resources in the directory yet.'); return }
      setSuggest({ staff, selected: new Set() })
    } catch (err) { fail(err) }
  }
  const applySuggested = async () => {
    const chosen = suggest.staff.filter((s) => suggest.selected.has(s.id))
    setBusy(true)
    try {
      for (const s of chosen) {
        await api.createL1Stakeholder(projectId, l1Id, {
          name: s.staff_name, resource_staff_id: s.id, role: s.hr_role || '', department: s.tech_unit || '',
          stakeholder_type: 'internal', raci: 'Consulted',
        })
      }
      setSuggest(null); toast.success(`Added ${chosen.length} stakeholder(s)`); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }
  const applyAi = async () => {
    setBusy(true)
    try {
      const result = await api.applyL1Baseline(projectId, l1Id, ai.draft)
      setAi(null); toast.success(`Added ${Object.values(result).reduce((a, b) => a + b, 0)} items`); await load()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  const openSummary = async () => {
    setTab('summary'); setExec({ loading: true })
    try { setExec({ markdown: (await api.l1ExecutiveSummary(projectId, l1Id)).markdown }) }
    catch (err) { fail(err); setExec(null) }
  }

  const submitForReview = async () => {
    try { await api.submitL1ForReview(projectId, l1Id); toast.success('Submitted for review'); await load() } catch (err) { fail(err) }
  }
  const decide = async (stage, approve) => {
    try { await api.decideL1Approval(projectId, l1Id, stage, { approve, decided_by: 'me' }); toast.success(approve ? 'Approved' : 'Rejected'); await load() } catch (err) { fail(err) }
  }

  const exportSummary = async (fmt) => {
    setBusy(true)
    try {
      // Render the exec-summary Mermaid blocks to images so Word/PPTX embed the diagram.
      const md = exec?.markdown || (await api.l1ExecutiveSummary(projectId, l1Id)).markdown
      const images = fmt === 'md' ? [] : await renderMermaidImages(md)
      const { blob, filename } = await api.exportL1Summary(projectId, l1Id, fmt, images)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
      toast.success(`Exported ${filename}`)
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  if (!baseline) return <div className="l1-loading">Loading L1 architecture baseline…</div>

  const { readiness, okrs, stakeholders, capabilities, risks } = baseline
  const v = vision || baseline.vision

  return <section className="l1arch">
    <div className="l1arch-head">
      <ReadinessCard readiness={readiness} />
      <div className="l1arch-head-actions">
        <button className="m3-btn tonal" onClick={() => runAi('')} disabled={ai?.loading}><Sparkles size={16} /> {ai?.loading ? 'Drafting…' : 'AI generate baseline'}</button>
        <button className="m3-btn outlined small" onClick={() => setDocImport({ text: '' })}><FileText size={15} /> Import from document</button>
      </div>
    </div>

    <nav className="l1arch-tabs" aria-label="L1 architecture sections">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button key={id} className={tab === id ? 'active' : ''} onClick={() => (id === 'summary' ? openSummary() : setTab(id))}><Icon size={15} /> {label}</button>
      ))}
    </nav>

    {tab === 'vision' && <div className="l1arch-panel">
      <div className="l1arch-section-head"><h3>Vision</h3>
        <button className="m3-btn filled small" onClick={saveVision} disabled={busy || !vision}>Save vision</button></div>
      <VisionField label="Vision statement" fieldKey="vision_statement" detailKey="vision_statement_details" style="vision" rows={3}
        value={v} onChange={setVision} onSummarize={summarizeField} />
      <VisionField label="Business problem" fieldKey="business_problem" detailKey="business_problem_details" style="problem" rows={2}
        value={v} onChange={setVision} onSummarize={summarizeField} />
      <VisionField label="Target users" fieldKey="target_users" detailKey="target_users_details" style="users" rows={2}
        value={v} onChange={setVision} onSummarize={summarizeField} />
      <label className="m3-field"><span>Status</span><select value={v.status} onChange={(e) => setVision({ ...v, status: e.target.value })}>{['draft', 'approved', 'baselined', 'archived'].map((s) => <option key={s}>{s}</option>)}</select></label>

      <div className="l1arch-section-head"><h3>Objectives & Key Results</h3><button className="m3-btn tonal small" onClick={() => openDialog('okr')}><Plus size={14} /> Add OKR</button></div>
      <EntityTable entity="okr" columns={['objective', 'key_result', 'metric_name', 'target_value', 'current_value', 'owner', 'status']} rows={okrs} onEdit={openDialog} onDelete={removeEntity} />
    </div>}

    {tab === 'stakeholders' && <div className="l1arch-panel">
      <div className="l1arch-section-head"><h3>Stakeholders & RACI</h3><div className="l1arch-export-actions">
        <button className="m3-btn outlined small" onClick={suggestStakeholders}><Users size={14} /> Suggest from directory</button>
        <button className="m3-btn tonal small" onClick={() => openDialog('stakeholder')}><Plus size={14} /> Add stakeholder</button>
      </div></div>
      <EntityTable entity="stakeholder" columns={['name', 'role', 'stakeholder_type', 'influence', 'interest', 'raci', 'status']} rows={stakeholders} onEdit={openDialog} onDelete={removeEntity} />
    </div>}

    {tab === 'capabilities' && <div className="l1arch-panel">
      <div className="l1arch-section-head"><h3>Business Capability Map</h3><div className="l1arch-export-actions">
        <div className="l1-view-toggle" role="tablist" aria-label="Capability view">
          <button role="tab" aria-selected={capView === 'table'} className={capView === 'table' ? 'active' : ''} onClick={() => setCapView('table')}>Table</button>
          <button role="tab" aria-selected={capView === 'heatmap'} className={capView === 'heatmap' ? 'active' : ''} onClick={() => setCapView('heatmap')}>Heatmap</button>
        </div>
        <button className="m3-btn outlined small" onClick={() => setJira({ instance: '', project_code: '', target: 'capabilities' })}><Link2 size={14} /> Import from Jira</button>
        <button className="m3-btn tonal small" onClick={() => openDialog('capability')}><Plus size={14} /> Add capability</button>
      </div></div>
      {capView === 'table'
        ? <EntityTable entity="capability" columns={['name', 'cap_level', 'criticality', 'current_maturity', 'target_maturity', 'strategic_priority']} rows={capabilities} onEdit={openDialog} onDelete={removeEntity} />
        : <CapabilityHeatmap capabilities={capabilities} onEdit={(c) => openDialog('capability', c)} />}
    </div>}

    {tab === 'risks' && <div className="l1arch-panel">
      <div className="l1arch-section-head"><h3>Portfolio Risk & Funding</h3><button className="m3-btn tonal small" onClick={() => openDialog('risk')}><Plus size={14} /> Add risk</button></div>
      <EntityTable entity="risk" columns={['title', 'category', 'risk_level', 'owner', 'funding_source', 'approved_budget', 'actual_spend', 'status']} rows={risks} onEdit={openDialog} onDelete={removeEntity} />
    </div>}

    {tab === 'governance' && <GovernancePanel approvals={baseline.approvals} readiness={readiness} impact={impact} onSubmit={submitForReview} onDecide={decide} />}

    {tab === 'discussion' && <div className="l1arch-panel">
      <div className="l1arch-section-head"><h3>Discussion &amp; review feedback</h3></div>
      <div className="l1arch-comment-add">
        <textarea rows={2} value={commentBody} placeholder="Leave review feedback…" onChange={(e) => setCommentBody(e.target.value)} />
        <button className="m3-btn filled small" disabled={!commentBody.trim()} onClick={addComment}>Post</button>
      </div>
      {(baseline.comments || []).length === 0 && <p className="l1-node-empty">No comments yet.</p>}
      <div className="l1arch-comment-list">
        {(baseline.comments || []).map((c) => <div key={c.id} className={`l1arch-comment ${c.status}`}>
          <div className="l1arch-comment-body"><strong>{c.author || 'Anon'}</strong> · <small>{new Date(c.created_at).toLocaleString()}</small><p>{c.body}</p></div>
          <div className="l1arch-comment-actions">
            <button className="m3-btn text small" onClick={() => resolveComment(c)}>{c.status === 'resolved' ? 'Reopen' : 'Resolve'}</button>
            <button className="m3-icon-btn danger-ink" onClick={() => deleteComment(c)} aria-label="Delete"><Trash2 size={14} /></button>
          </div>
        </div>)}
      </div>
    </div>}

    {tab === 'summary' && <div className="l1arch-panel">
      <div className="l1arch-section-head"><h3>Executive summary <small>Markdown + Mermaid — a living document</small></h3>
        <div className="l1arch-export-actions">
          {exec?.markdown && <button className="m3-btn text small" onClick={() => { navigator.clipboard?.writeText(exec.markdown); toast.success('Markdown copied') }}>Copy MD</button>}
          <button className="m3-btn text small" disabled={busy} onClick={() => exportSummary('md')}><Download size={14} /> Markdown</button>
          <button className="m3-btn text small" disabled={busy} onClick={() => exportSummary('docx')}><Download size={14} /> Word</button>
          <button className="m3-btn tonal small" disabled={busy} onClick={() => exportSummary('pptx')}><Download size={14} /> PowerPoint</button>
        </div>
      </div>
      {exec?.loading && <div className="l1-loading">Composing summary…</div>}
      {exec?.markdown && <div className="l1arch-exec"><MarkdownViewer content={exec.markdown} /></div>}
    </div>}

    {dialog && <PlanningDialog wide title={`${dialog.editing ? 'Edit' : 'Add'} ${dialog.entity}`} onClose={() => setDialog(null)}
      actions={<><button className="m3-btn text" onClick={() => setDialog(null)}>Cancel</button><button className="m3-btn filled" disabled={busy} onClick={saveEntity}>Save</button></>}>
      {dialog.entity === 'stakeholder' && <label className="m3-field"><span>From resource directory (or fill manually below)</span>
        <select value={dialog.draft.resource_staff_id || ''} onChange={(e) => {
          const person = staffPool.find((s) => s.id === e.target.value)
          setDialog({ ...dialog, draft: person
            ? { ...dialog.draft, resource_staff_id: person.id, name: person.staff_name, role: dialog.draft.role || person.hr_role || '', department: dialog.draft.department || person.tech_unit || '' }
            : { ...dialog.draft, resource_staff_id: '' } })
        }}>
          <option value="">— add manually —</option>
          {staffPool.map((s) => <option key={s.id} value={s.id}>{s.staff_name}{s.staff_code ? ` · ${s.staff_code}` : ''}</option>)}
        </select></label>}
      <div className="l1-form-grid">
        {FIELDS[dialog.entity].map((f) => <label key={f.key} className="m3-field"><span>{f.label}</span>
          {f.type === 'select'
            ? <select value={dialog.draft[f.key]} onChange={(e) => setDialog({ ...dialog, draft: { ...dialog.draft, [f.key]: e.target.value } })}>{f.options.map((o) => <option key={o} value={o}>{o}</option>)}</select>
            : f.type === 'element'
              ? <select value={dialog.draft[f.key] || ''} onChange={(e) => setDialog({ ...dialog, draft: { ...dialog.draft, [f.key]: e.target.value } })}><option value="">— not linked —</option>{elements.map((el) => <option key={el.id} value={el.id}>{el.level} · {el.name}</option>)}</select>
              : f.type === 'textarea'
                ? <textarea rows={2} value={dialog.draft[f.key]} onChange={(e) => setDialog({ ...dialog, draft: { ...dialog.draft, [f.key]: e.target.value } })} />
                : <input type={f.type === 'number' ? 'number' : 'text'} value={dialog.draft[f.key]} onChange={(e) => setDialog({ ...dialog, draft: { ...dialog.draft, [f.key]: e.target.value } })} />}
        </label>)}
      </div>
    </PlanningDialog>}

    {ai?.draft && <PlanningDialog wide title="AI L1 baseline draft" onClose={() => setAi(null)}
      actions={<><button className="m3-btn text" onClick={() => setAi(null)}>Cancel</button><button className="m3-btn filled" disabled={busy} onClick={applyAi}>Apply all</button></>}>
      <div className="m3-banner info">{ai.draft.summary}</div>
      <div className="ai-baseline-preview">
        <p><strong>Vision:</strong> {ai.draft.vision_statement}</p>
        <p><strong>{ai.draft.okrs.length}</strong> OKRs · <strong>{ai.draft.stakeholders.length}</strong> stakeholders · <strong>{ai.draft.capabilities.length}</strong> capabilities · <strong>{ai.draft.risks.length}</strong> risks</p>
        <ul>{ai.draft.capabilities.map((c, i) => <li key={i}>{c.name}</li>)}</ul>
      </div>
    </PlanningDialog>}

    {docImport && <PlanningDialog wide title="Import from document" onClose={() => setDocImport(null)}
      actions={<><button className="m3-btn text" onClick={() => setDocImport(null)}>Cancel</button><button className="m3-btn filled" disabled={ai?.loading || !docImport.text.trim()} onClick={importDoc}>{ai?.loading ? 'Extracting…' : 'Extract L1 baseline'}</button></>}>
      <div className="m3-banner info">Paste a strategy, architecture or product document. The AI extracts a draft vision, OKRs, stakeholders, capabilities and risks — PII is masked before it reaches the model. You review before anything is saved.</div>
      <label className="m3-field"><span>Document text</span><textarea rows={10} autoFocus value={docImport.text} onChange={(e) => setDocImport({ text: e.target.value })} placeholder="Paste from Confluence, SharePoint, Google Drive, Notion…" /></label>
    </PlanningDialog>}

    {suggest && <PlanningDialog wide title="Suggest stakeholders from the directory" onClose={() => setSuggest(null)}
      actions={<><button className="m3-btn text" onClick={() => setSuggest(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || suggest.selected.size === 0} onClick={applySuggested}>Add {suggest.selected.size} stakeholder(s)</button></>}>
      <div className="m3-banner info">Active people from the global resource directory. Pick who to add as stakeholders (RACI defaults to Consulted — refine after).</div>
      <div className="ai-staffing-list">
        {suggest.staff.map((s) => <label key={s.id} className={`ai-staffing-row ${suggest.selected.has(s.id) ? 'on' : ''}`}>
          <input type="checkbox" checked={suggest.selected.has(s.id)} onChange={() => setSuggest((cur) => { const sel = new Set(cur.selected); sel.has(s.id) ? sel.delete(s.id) : sel.add(s.id); return { ...cur, selected: sel } })} />
          <span className="ai-staffing-main"><strong>{s.staff_name}</strong> · {s.hr_role || 'role n/a'} <span className="ai-staffing-alloc">{s.tech_unit || '—'}</span></span>
        </label>)}
      </div>
    </PlanningDialog>}

    {jira && <PlanningDialog title="Import from Jira" onClose={() => setJira(null)}
      actions={<><button className="m3-btn text" onClick={() => setJira(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !jira.instance.trim() || !jira.project_code.trim()} onClick={runJiraImport}>Import</button></>}>
      <div className="m3-banner info">Pulls issues from a configured Jira instance and maps them into this L1. Requires <code>JIRA_INSTANCES</code> + <code>JIRA_&lt;NAME&gt;_*</code> in backend/.env; you'll get a clear message if none is configured.</div>
      <div className="l1-form-grid">
        <label className="m3-field"><span>Instance name</span><input value={jira.instance} onChange={(e) => setJira({ ...jira, instance: e.target.value })} placeholder="prod" /></label>
        <label className="m3-field"><span>Jira project key</span><input value={jira.project_code} onChange={(e) => setJira({ ...jira, project_code: e.target.value })} placeholder="PAY" /></label>
      </div>
      <label className="m3-field"><span>Import as</span><select value={jira.target} onChange={(e) => setJira({ ...jira, target: e.target.value })}><option value="capabilities">Capabilities</option><option value="okrs">Objectives (OKRs)</option></select></label>
    </PlanningDialog>}
  </section>
}

function ReadinessCard({ readiness }) {
  const { score, status_label, checklist } = readiness
  const done = checklist.filter((c) => c.done).length
  return <div className="l1arch-readiness">
    <div className="l1arch-gauge" style={{ '--score': score }}>
      <span>{score}%</span>
    </div>
    <div className="l1arch-readiness-body">
      <strong>L1 readiness</strong>
      <p>{status_label}</p>
      <div className="l1arch-checklist">
        {checklist.map((c) => <span key={c.item} className={c.done ? 'done' : ''}>{c.done ? <CheckCircle2 size={13} /> : <Circle size={13} />} {c.item}</span>)}
      </div>
      <small>{done}/{checklist.length} complete</small>
    </div>
  </div>
}

function GovernancePanel({ approvals, readiness, impact, onSubmit, onDecide }) {
  return <div className="l1arch-panel">
    {impact && (impact.findings?.length > 0
      ? <div className="l1arch-impact">
        <div className="l1arch-impact-head"><AlertTriangle size={15} /> Change-impact analysis — {impact.findings.length} finding(s){impact.high ? `, ${impact.high} high` : ''}</div>
        <ul>{impact.findings.map((f, i) => <li key={i} className={`sev-${f.severity}`}><span className="l1arch-sev">{f.severity}</span> {f.message}</li>)}</ul>
      </div>
      : <div className="l1arch-impact clean"><div className="l1arch-impact-head"><CheckCircle2 size={15} /> Change-impact analysis — no consistency issues detected</div></div>)}
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
      <h3>Approval workflow <small>Sequential sign-off — baselines the L1 when complete</small></h3>
      <button className="m3-btn tonal small" onClick={onSubmit}>{approvals.submitted ? 'Restart review' : 'Submit for review'}</button>
    </div>
    {!approvals.submitted && <p className="l1-node-empty">Not yet submitted. Submit the baseline to start the product → architecture → security → risk → finance → sponsor sign-off chain.</p>}
    {approvals.submitted && <>
      <div className="l1arch-approval-progress"><span style={{ width: `${(approvals.approved_count / approvals.total) * 100}%` }} /></div>
      <p className="admin-muted">{approvals.approved_count}/{approvals.total} approved{approvals.complete ? ' · L1 baselined ✓' : approvals.current_stage ? ` · next: ${approvals.current_stage}` : ''}</p>
      <ol className="l1arch-approval-chain">
        {approvals.stages.map((s) => {
          const isCurrent = s.stage === approvals.current_stage
          return <li key={s.stage} className={`stage-${s.status}${isCurrent ? ' current' : ''}`}>
            <span className="l1arch-stage-mark">{s.status === 'approved' ? <CheckCircle2 size={16} /> : s.status === 'rejected' ? <X size={16} /> : <Circle size={16} />}</span>
            <span className="l1arch-stage-body"><strong>{s.label}</strong>{s.decided_by ? <small>{s.status} by {s.decided_by}</small> : <small>{s.status}</small>}</span>
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

function VisionField({ label, fieldKey, detailKey, style, rows, value, onChange, onSummarize }) {
  const [open, setOpen] = useState(false)
  return <div className="vision-field">
    <div className="vision-field-head">
      <span>{label}</span>
      <div className="vision-field-actions">
        <button type="button" className="m3-btn text small" onClick={() => setOpen((o) => !o)}>{open ? 'Hide details' : 'More details'}</button>
        <button type="button" className="m3-btn tonal small" onClick={() => onSummarize(fieldKey, detailKey, style, value)}><Sparkles size={13} /> AI summarize → field</button>
      </div>
    </div>
    <textarea className="vision-field-summary" rows={rows} value={value[fieldKey] || ''} placeholder={`Concise ${label.toLowerCase()} (or generate from details)`} onChange={(e) => onChange({ ...value, [fieldKey]: e.target.value })} />
    {open && <div className="vision-field-details">
      <p className="ai-hint">Write rich detail here (formatting supported). Use <strong>AI summarize</strong> to distil it into the field above.</p>
      <MarkdownEditor value={value[detailKey] || ''} onChange={(md) => onChange({ ...value, [detailKey]: md })} defaultMode="split" toolbarLabel="Details" placeholder={`Detailed notes for ${label.toLowerCase()}…`} />
    </div>}
  </div>
}

function CapabilityHeatmap({ capabilities, onEdit }) {
  if (capabilities.length === 0) return <p className="l1-node-empty">No capabilities mapped yet.</p>
  // Colour by business criticality; the maturity gap (target − current) drives urgency.
  const critClass = { high: 'crit-high', medium: 'crit-medium', low: 'crit-low' }
  return <div className="l1arch-heatmap">
    {capabilities.map((c) => {
      const gap = Math.max(0, (c.target_maturity || 0) - (c.current_maturity || 0))
      return <button key={c.id} className={`l1arch-heat-cell ${critClass[c.criticality] || 'crit-medium'}`} onClick={() => onEdit(c)} title={`${c.criticality} criticality · maturity ${c.current_maturity}/${c.target_maturity}`}>
        <strong>{c.name}</strong>
        <span className="l1arch-heat-meta">{c.cap_level} · {c.criticality}</span>
        <span className="l1arch-heat-bar"><span style={{ width: `${(c.current_maturity / 5) * 100}%` }} /></span>
        <small>{c.current_maturity}→{c.target_maturity}{gap > 0 ? ` · gap ${gap}` : ' · on target'}</small>
      </button>
    })}
  </div>
}

function EntityTable({ entity, columns, rows, onEdit, onDelete }) {
  if (rows.length === 0) return <p className="l1-node-empty">Nothing captured yet.</p>
  return <div className="res-table-wrap"><table className="res-table">
    <thead><tr>{columns.map((c) => <th key={c}>{c.replace(/_/g, ' ')}</th>)}<th></th></tr></thead>
    <tbody>
      {rows.map((row) => <tr key={row.id} onClick={() => onEdit(entity, row)}>
        {columns.map((c) => <td key={c}>{['risk_level', 'criticality', 'status', 'influence'].includes(c)
          ? <span className={LEVEL_PILL(row[c])}>{row[c]}</span> : String(row[c] ?? '—')}</td>)}
        <td className="res-row-actions" onClick={(e) => e.stopPropagation()}>
          <button className="m3-icon-btn" onClick={() => onEdit(entity, row)} aria-label="Edit"><Pencil size={15} /></button>
          <button className="m3-icon-btn danger-ink" onClick={() => onDelete(entity, row)} aria-label="Delete"><Trash2 size={15} /></button>
        </td>
      </tr>)}
    </tbody>
  </table></div>
}
