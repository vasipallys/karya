import { CalendarRange, CircleAlert, Pencil, Plus, Trash2, WalletCards } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import PlanningDialog from './PlanningDialog'

const iso = (date) => date.toISOString().slice(0, 10)
const initialWork = () => {
  const start = new Date()
  const end = new Date(); end.setDate(end.getDate() + 42)
  return { title: '', description: '', squad_id: '', linked_element_id: '', start_date: iso(start), end_date: iso(end), status: 'planned', allocation_percent: 100, budget_cost: 0, actual_cost: 0 }
}

const STATUS = { planned: 'Planned', in_progress: 'In progress', at_risk: 'At risk', done: 'Done' }

export default function WorkCostPlanning({ projectId, l1Id, plan, graph, refresh, setError, money }) {
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)
  const squads = plan.units.filter((unit) => unit.unit_type === 'squad')
  const descendants = graph.elements.filter((element) => element.level !== 'L1' && belongsTo(element, l1Id, graph.elements))
  const timeline = useMemo(() => {
    if (!plan.work_items.length) return null
    const starts = plan.work_items.map((item) => new Date(`${item.start_date}T00:00:00`).getTime())
    const ends = plan.work_items.map((item) => new Date(`${item.end_date}T00:00:00`).getTime())
    const min = Math.min(...starts); const max = Math.max(...ends); const span = Math.max(max - min, 86400000)
    return { min, max, span }
  }, [plan.work_items])

  const open = (item = null) => setDialog({
    editing: item,
    draft: item ? {
      title: item.title, description: item.description, squad_id: item.squad_id || '', linked_element_id: item.linked_element_id || '',
      start_date: item.start_date, end_date: item.end_date, status: item.status, allocation_percent: item.allocation_percent,
      budget_cost: item.budget_cost, actual_cost: item.actual_cost,
    } : initialWork(),
  })

  const save = async () => {
    setBusy(true)
    try {
      const draft = dialog.draft
      const payload = {
        ...draft, squad_id: draft.squad_id || null, linked_element_id: draft.linked_element_id || null,
        allocation_percent: Number(draft.allocation_percent || 0), budget_cost: Number(draft.budget_cost || 0), actual_cost: Number(draft.actual_cost || 0),
      }
      if (dialog.editing) await api.updateWorkItem(projectId, dialog.editing.id, payload)
      else await api.createWorkItem(projectId, l1Id, payload)
      setDialog(null); await refresh()
    } catch (error) { setError(error) } finally { setBusy(false) }
  }

  const remove = async (item) => {
    if (!window.confirm(`Delete work package "${item.title}"?`)) return
    try { await api.deleteWorkItem(projectId, item.id); await refresh() } catch (error) { setError(error) }
  }

  return <section>
    <div className="l1-section-heading">
      <div><h2>Work plan & cost</h2><p>Connect delivery packages to squads and the C4 backlog, then track budget against actual cost.</p></div>
      <button className="m3-btn filled small" onClick={() => open()}><Plus size={15} /> Work package</button>
    </div>

    {plan.work_items.length === 0
      ? <div className="l1-empty-panel"><CalendarRange size={32} /><h3>Turn the initiative into a funded plan</h3><p>Add work packages with squad ownership, dates, allocation, budget, and actual cost.</p><button className="m3-btn filled" onClick={() => open()}><Plus size={16} /> Add work package</button></div>
      : <div className="l1-work-layout">
        <div className="l1-timeline">
          <header><span>Delivery timeline</span><small>{new Date(timeline.min).toLocaleDateString()} — {new Date(timeline.max).toLocaleDateString()}</small></header>
          {plan.work_items.map((item) => {
            const start = new Date(`${item.start_date}T00:00:00`).getTime()
            const end = new Date(`${item.end_date}T00:00:00`).getTime()
            const left = (start - timeline.min) / timeline.span * 100
            const width = Math.max((end - start) / timeline.span * 100, 2)
            return <button key={item.id} className="l1-timeline-row" onClick={() => open(item)}>
              <span className="l1-timeline-label"><strong>{item.title}</strong><small>{item.squad_name || 'Unassigned'}</small></span>
              <span className="l1-timeline-track"><i className={`status-${item.status}`} style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }} /></span>
            </button>
          })}
        </div>

        <div className="l1-work-table-wrap">
          <table className="l1-work-table">
            <thead><tr><th>Work package</th><th>Owner</th><th>Status</th><th>Dates</th><th>Budget</th><th>Actual</th><th /></tr></thead>
            <tbody>{plan.work_items.map((item) => <tr key={item.id}>
              <td><strong>{item.title}</strong>{item.linked_element_name && <small>C4 · {item.linked_element_name}</small>}</td>
              <td>{item.squad_name || <span className="muted">Unassigned</span>}</td>
              <td><span className={`l1-status ${item.status}`}>{item.status === 'at_risk' && <CircleAlert size={13} />}{STATUS[item.status]}</span></td>
              <td>{new Date(`${item.start_date}T00:00:00`).toLocaleDateString()}<small>to {new Date(`${item.end_date}T00:00:00`).toLocaleDateString()}</small></td>
              <td>{money(item.budget_cost)}</td><td>{money(item.actual_cost)}</td>
              <td><div className="l1-table-actions"><button className="m3-icon-btn" onClick={() => open(item)} aria-label={`Edit ${item.title}`}><Pencil size={15} /></button><button className="m3-icon-btn danger-ink" onClick={() => remove(item)} aria-label={`Delete ${item.title}`}><Trash2 size={15} /></button></div></td>
            </tr>)}</tbody>
          </table>
        </div>
      </div>}

    {dialog && <PlanningDialog title={`${dialog.editing ? 'Edit' : 'Add'} work package`} wide onClose={() => setDialog(null)}
      actions={<><button className="m3-btn text" onClick={() => setDialog(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !dialog.draft.title.trim() || !dialog.draft.start_date || !dialog.draft.end_date} onClick={save}>Save work</button></>}>
      <label className="m3-field"><span>Work package</span><input autoFocus value={dialog.draft.title} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, title: event.target.value } })} placeholder="Customer onboarding release" /></label>
      <label className="m3-field"><span>Outcome / details</span><textarea rows={3} value={dialog.draft.description} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, description: event.target.value } })} /></label>
      <div className="l1-form-grid"><label className="m3-field"><span>Squad</span><select value={dialog.draft.squad_id} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, squad_id: event.target.value } })}><option value="">Unassigned</option>{squads.map((squad) => <option key={squad.id} value={squad.id}>{squad.name}</option>)}</select></label><label className="m3-field"><span>Linked C4 scope</span><select value={dialog.draft.linked_element_id} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, linked_element_id: event.target.value } })}><option value="">No C4 link</option>{descendants.map((element) => <option key={element.id} value={element.id}>{element.level} · {element.name}</option>)}</select></label></div>
      <div className="l1-form-grid"><label className="m3-field"><span>Start date</span><input type="date" value={dialog.draft.start_date} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, start_date: event.target.value } })} /></label><label className="m3-field"><span>End date</span><input type="date" value={dialog.draft.end_date} min={dialog.draft.start_date} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, end_date: event.target.value } })} /></label></div>
      <div className="l1-form-grid three"><label className="m3-field"><span>Status</span><select value={dialog.draft.status} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, status: event.target.value } })}>{Object.entries(STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="m3-field"><span>Allocation %</span><input type="number" min="0" max="100" value={dialog.draft.allocation_percent} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, allocation_percent: event.target.value } })} /></label><span /></div>
      <div className="l1-form-grid"><label className="m3-field"><span>Approved budget</span><input type="number" min="0" value={dialog.draft.budget_cost} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, budget_cost: event.target.value } })} /></label><label className="m3-field"><span>Actual cost to date</span><input type="number" min="0" value={dialog.draft.actual_cost} onChange={(event) => setDialog({ ...dialog, draft: { ...dialog.draft, actual_cost: event.target.value } })} /></label></div>
      {Number(dialog.draft.actual_cost) > Number(dialog.draft.budget_cost) && <div className="m3-banner error"><WalletCards size={18} /> Actual cost is above the approved budget.</div>}
    </PlanningDialog>}
  </section>
}

function belongsTo(element, l1Id, elements) {
  let current = element
  const byId = new Map(elements.map((item) => [item.id, item]))
  while (current?.parent_id) {
    if (current.parent_id === l1Id) return true
    current = byId.get(current.parent_id)
  }
  return false
}
