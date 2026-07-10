import { Crown, Gauge, LayoutGrid, ListTree, Pencil, Plus, Sparkles, Trash2, UserPlus, UsersRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import PlanningDialog from './PlanningDialog'

const emptyUnit = { unit_type: 'squad', name: '', parent_unit_id: '', mission: '', lead_name: '', capacity_fte: 0, target_velocity: 0 }
const emptyMember = { name: '', resource_staff_id: '', role: '', skills: '', location: '', allocation_percent: 100, monthly_cost: 0 }

function number(value) {
  return Number(value || 0)
}

function clampPercent(value) {
  return Math.min(100, Math.max(0, number(value)))
}

function unitRunRate(unit) {
  return unit.members.reduce((total, member) => total + member.monthly_cost * member.allocation_percent / 100, 0)
}

export default function TeamPlanning({ projectId, l1Id, plan, refresh, setError, money }) {
  const [unitDialog, setUnitDialog] = useState(null)
  const [memberDialog, setMemberDialog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState('hierarchy')
  const [resources, setResources] = useState([])
  const [staffing, setStaffing] = useState(null) // { loading, proposal, selected:Set }

  // People come from the global resource directory; only active staff are assignable.
  useEffect(() => { api.listStaff({ staff_status: 'Active' }).then(setResources).catch(() => setResources([])) }, [])

  const runStaffing = async () => {
    setStaffing({ loading: true })
    try {
      const proposal = await api.aiStaffing(projectId, l1Id)
      setStaffing({ proposal, selected: new Set(proposal.assignments.map((_, index) => index)) })
    } catch (error) { setError(error); setStaffing(null) }
  }

  const applyStaffing = async () => {
    const chosen = staffing.proposal.assignments.filter((_, index) => staffing.selected.has(index))
    if (chosen.length === 0) { setStaffing(null); return }
    setBusy(true)
    try {
      const result = await api.applyStaffing(projectId, chosen)
      setStaffing(null)
      await refresh()
      if (result.errors?.length) setError(new Error(`Applied ${result.created}; skipped: ${result.errors.join('; ')}`))
    } catch (error) { setError(error) } finally { setBusy(false) }
  }

  const toggleAssignment = (index) => setStaffing((current) => {
    const selected = new Set(current.selected)
    selected.has(index) ? selected.delete(index) : selected.add(index)
    return { ...current, selected }
  })
  const tribes = plan.units.filter((unit) => unit.unit_type === 'tribe')
  const squads = plan.units.filter((unit) => unit.unit_type === 'squad')
  const independentSquads = squads.filter((squad) => !tribes.some((tribe) => tribe.id === squad.parent_unit_id))

  const saveUnit = async () => {
    setBusy(true)
    try {
      const draft = unitDialog.draft
      const payload = {
        ...draft,
        parent_unit_id: draft.unit_type === 'squad' ? draft.parent_unit_id || null : null,
        capacity_fte: number(draft.capacity_fte),
        target_velocity: number(draft.target_velocity),
      }
      if (unitDialog.editing) await api.updateAgileUnit(projectId, unitDialog.editing.id, payload)
      else await api.createAgileUnit(projectId, l1Id, payload)
      setUnitDialog(null); await refresh()
    } catch (error) { setError(error) } finally { setBusy(false) }
  }

  const saveMember = async () => {
    setBusy(true)
    try {
      const draft = memberDialog.draft
      const payload = {
        ...draft,
        resource_staff_id: draft.resource_staff_id || null,
        allocation_percent: clampPercent(draft.allocation_percent),
        monthly_cost: number(draft.monthly_cost),
      }
      if (memberDialog.editing) await api.updateTeamMember(projectId, memberDialog.editing.id, payload)
      else await api.createTeamMember(projectId, memberDialog.unit.id, payload)
      setMemberDialog(null); await refresh()
    } catch (error) { setError(error) } finally { setBusy(false) }
  }

  // Pick a directory person: copy their display name, and default the squad role from HR role if blank.
  const chooseResource = (staffId) => {
    const person = resources.find((row) => row.id === staffId)
    setMemberDialog((current) => ({
      ...current,
      draft: {
        ...current.draft,
        resource_staff_id: staffId,
        name: person ? person.staff_name : current.draft.name,
        role: current.draft.role || person?.hr_role || '',
      },
    }))
  }

  const removeUnit = async (unit) => {
    const warning = unit.unit_type === 'tribe'
      ? `Delete ${unit.name}? Its squads become independent and its members are removed.`
      : `Delete ${unit.name}? Team members will also be removed and assigned work will become unassigned.`
    if (!window.confirm(warning)) return
    try { await api.deleteAgileUnit(projectId, unit.id); await refresh() } catch (error) { setError(error) }
  }

  const removeMember = async (member) => {
    if (!window.confirm(`Remove ${member.name} from this operating plan?`)) return
    try { await api.deleteTeamMember(projectId, member.id); await refresh() } catch (error) { setError(error) }
  }

  const openUnit = (unit = null, type = 'squad', parentId = '') => setUnitDialog({
    editing: unit,
    draft: unit ? {
      unit_type: unit.unit_type, name: unit.name, parent_unit_id: unit.parent_unit_id || '', mission: unit.mission,
      lead_name: unit.lead_name, capacity_fte: unit.capacity_fte, target_velocity: unit.target_velocity,
    } : { ...emptyUnit, unit_type: type, parent_unit_id: type === 'squad' ? (parentId || (tribes.length === 1 ? tribes[0].id : '')) : '' },
  })

  const openMember = (unit, member = null) => setMemberDialog({
    unit,
    editing: member,
    draft: member ? {
      name: member.name, resource_staff_id: member.resource_staff_id || '', role: member.role, skills: member.skills, location: member.location,
      allocation_percent: member.allocation_percent, monthly_cost: member.monthly_cost,
    } : { ...emptyMember },
  })

  const unitActions = (unit) => <>
    <button className="m3-icon-btn" onClick={() => openUnit(unit)} aria-label={`Edit ${unit.name}`}><Pencil size={16} /></button>
    <button className="m3-icon-btn danger-ink" onClick={() => removeUnit(unit)} aria-label={`Delete ${unit.name}`}><Trash2 size={16} /></button>
  </>

  const memberList = (unit) => <div className="l1-member-list">
    {unit.members.map((member) => <button key={member.id} className="l1-member-row" onClick={() => openMember(unit, member)}>
      <span className="l1-avatar">{member.name.slice(0, 2).toUpperCase()}</span>
      <span><strong>{member.name}</strong><small>{member.role || 'Role not set'} · {member.allocation_percent}%</small></span>
      <span className="l1-member-cost">{money(member.monthly_cost * member.allocation_percent / 100)}</span>
      <span className="l1-row-delete" role="button" aria-label={`Remove ${member.name}`} onClick={(event) => { event.stopPropagation(); removeMember(member) }}><Trash2 size={14} /></span>
    </button>)}
    {unit.members.length === 0 && <p className="l1-node-empty">No people yet.</p>}
  </div>

  const sharedRoleAction = (tribe) => <button
    className="m3-btn text small l1-shared-role-action"
    onClick={() => openMember(tribe)}
    aria-label={`Add tribe-level shared role to ${tribe.name}`}>
    <UserPlus size={15} /> Add shared role
  </button>

  const squadCard = (squad, showParent) => {
    const parent = tribes.find((item) => item.id === squad.parent_unit_id)
    return <article key={squad.id} className="l1-team-card squad">
      <header>
        <span className="l1-unit-mark squad"><UsersRound size={18} /></span>
        <div className="l1-team-title"><span>squad{showParent && parent ? ` · ${parent.name}` : ''}</span><h3>{squad.name}</h3></div>
        {unitActions(squad)}
      </header>
      <p className="l1-team-mission">{squad.mission || 'No mission statement yet.'}</p>
      <div className="l1-team-facts">
        <span><Crown size={14} /> {squad.lead_name || 'Lead not assigned'}</span>
        <span><Gauge size={14} /> {squad.capacity_fte || 0} FTE · {squad.target_velocity || 0} pts/sprint</span>
      </div>
      <div className="l1-team-cost"><span>Allocated run-rate</span><strong>{money(unitRunRate(squad))}<small>/month</small></strong></div>
      {memberList(squad)}
      <button className="m3-btn text small l1-card-action" onClick={() => openMember(squad)}><UserPlus size={15} /> Add person</button>
    </article>
  }

  const heading = <div className="l1-section-heading">
    <div><h2>Tribes & squads</h2><p>Shape accountable teams around the initiative and make capacity, skills, and run-rate visible.</p></div>
    <div className="l1-heading-actions">
      <div className="l1-view-toggle" role="tablist" aria-label="Team view">
        <button role="tab" aria-selected={view === 'hierarchy'} className={view === 'hierarchy' ? 'active' : ''} onClick={() => setView('hierarchy')}><ListTree size={15} /> Hierarchy</button>
        <button role="tab" aria-selected={view === 'cards'} className={view === 'cards' ? 'active' : ''} onClick={() => setView('cards')}><LayoutGrid size={15} /> Cards</button>
      </div>
      <button className="m3-btn tonal small" onClick={runStaffing} disabled={staffing?.loading}><Sparkles size={15} /> {staffing?.loading ? 'Thinking…' : 'AI staffing'}</button>
      <button className="m3-btn outlined small" onClick={() => openUnit(null, 'tribe')}><Plus size={15} /> Tribe</button>
      <button className="m3-btn filled small" onClick={() => openUnit(null, 'squad')}><Plus size={15} /> Squad</button>
    </div>
  </div>

  const dialogs = <>
    {staffing?.proposal && <PlanningDialog wide title="AI staffing proposal" onClose={() => setStaffing(null)}
      actions={<><button className="m3-btn text" onClick={() => setStaffing(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || staffing.selected.size === 0} onClick={applyStaffing}>Assign {staffing.selected.size} {staffing.selected.size === 1 ? 'person' : 'people'}</button></>}>
      <div className="m3-banner info">{staffing.proposal.summary || 'Proposed assignments respecting each person’s remaining capacity.'}</div>
      {staffing.proposal.assignments.length === 0 && <p className="l1-node-empty">No assignments proposed — everyone may be fully allocated, or there are no squads yet.</p>}
      <div className="ai-staffing-list">
        {staffing.proposal.assignments.map((assignment, index) => (
          <label key={index} className={`ai-staffing-row ${staffing.selected.has(index) ? 'on' : ''}`}>
            <input type="checkbox" checked={staffing.selected.has(index)} onChange={() => toggleAssignment(index)} />
            <span className="ai-staffing-main"><strong>{assignment.staff_name}</strong> → {assignment.squad_name} <span className="ai-staffing-alloc">{Math.round(assignment.allocation_percent)}%</span></span>
            <span className="ai-staffing-reason">{assignment.reason}</span>
          </label>
        ))}
      </div>
    </PlanningDialog>}

    {unitDialog && <PlanningDialog title={`${unitDialog.editing ? 'Edit' : 'Add'} ${unitDialog.draft.unit_type}`} onClose={() => setUnitDialog(null)}
      actions={<><button className="m3-btn text" onClick={() => setUnitDialog(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !unitDialog.draft.name.trim()} onClick={saveUnit}>Save team</button></>}>
      {!unitDialog.editing && <div className="m3-radio-row">
        {['tribe', 'squad'].map((type) => <label key={type} className={unitDialog.draft.unit_type === type ? 'selected' : ''}><input type="radio" checked={unitDialog.draft.unit_type === type} onChange={() => setUnitDialog({ ...unitDialog, draft: { ...unitDialog.draft, unit_type: type, parent_unit_id: '' } })} />{type === 'tribe' ? 'Agile tribe' : 'Delivery squad'}</label>)}
      </div>}
      <label className="m3-field"><span>Name</span><input autoFocus value={unitDialog.draft.name} onChange={(event) => setUnitDialog({ ...unitDialog, draft: { ...unitDialog.draft, name: event.target.value } })} placeholder={unitDialog.draft.unit_type === 'tribe' ? 'Digital Commerce Tribe' : 'Checkout Squad'} /></label>
      {unitDialog.draft.unit_type === 'squad' && tribes.length > 0 && <label className="m3-field"><span>Parent tribe</span><select value={unitDialog.draft.parent_unit_id} onChange={(event) => setUnitDialog({ ...unitDialog, draft: { ...unitDialog.draft, parent_unit_id: event.target.value } })}><option value="">Independent squad</option>{tribes.map((tribe) => <option key={tribe.id} value={tribe.id}>{tribe.name}</option>)}</select></label>}
      <label className="m3-field"><span>Mission / work details</span><textarea rows={3} value={unitDialog.draft.mission} onChange={(event) => setUnitDialog({ ...unitDialog, draft: { ...unitDialog.draft, mission: event.target.value } })} placeholder="What outcome does this team own?" /></label>
      <label className="m3-field"><span>Lead</span><select value={unitDialog.draft.lead_name} onChange={(event) => setUnitDialog({ ...unitDialog, draft: { ...unitDialog.draft, lead_name: event.target.value } })}><option value="">— select from resource directory —</option>{unitDialog.draft.lead_name && !resources.some((row) => row.staff_name === unitDialog.draft.lead_name) && <option value={unitDialog.draft.lead_name}>{unitDialog.draft.lead_name} (not in directory)</option>}{resources.map((row) => <option key={row.id} value={row.staff_name}>{row.staff_name}</option>)}</select></label>
      <div className="l1-form-grid"><label className="m3-field"><span>Capacity (FTE)</span><input type="number" min="0" step="0.1" value={unitDialog.draft.capacity_fte} onChange={(event) => setUnitDialog({ ...unitDialog, draft: { ...unitDialog.draft, capacity_fte: event.target.value } })} /></label><label className="m3-field"><span>Target velocity / sprint</span><input type="number" min="0" step="1" value={unitDialog.draft.target_velocity} onChange={(event) => setUnitDialog({ ...unitDialog, draft: { ...unitDialog.draft, target_velocity: event.target.value } })} /></label></div>
    </PlanningDialog>}

    {memberDialog && <PlanningDialog title={`${memberDialog.editing ? 'Edit' : 'Add'} team member`} onClose={() => setMemberDialog(null)}
      actions={<><button className="m3-btn text" onClick={() => setMemberDialog(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !memberDialog.draft.resource_staff_id} onClick={saveMember}>Save person</button></>}>
      <div className="m3-banner info">
        {memberDialog.unit.unit_type === 'tribe'
          ? `Tribe shared role: ${memberDialog.unit.name}. Use this only for tribe-level leadership or shared roles; add delivery members inside squads.`
          : `Squad: ${memberDialog.unit.name}`}
      </div>
      <div className="l1-form-grid">
        <label className="m3-field"><span>Person (from resource directory)</span>
          <select autoFocus value={memberDialog.draft.resource_staff_id} onChange={(event) => chooseResource(event.target.value)}>
            <option value="">— select a resource —</option>
            {memberDialog.draft.resource_staff_id && !resources.some((row) => row.id === memberDialog.draft.resource_staff_id) && <option value={memberDialog.draft.resource_staff_id}>{memberDialog.draft.name || 'Current person'} (inactive/removed)</option>}
            {resources.map((row) => <option key={row.id} value={row.id}>{row.staff_name}{row.staff_code ? ` · ${row.staff_code}` : ''}</option>)}
          </select>
        </label>
        <label className="m3-field"><span>Role in this team</span><input value={memberDialog.draft.role} onChange={(event) => setMemberDialog({ ...memberDialog, draft: { ...memberDialog.draft, role: event.target.value } })} placeholder="Senior engineer" /></label>
      </div>
      {resources.length === 0 && <div className="m3-banner">No active resources found. Add people in the Resources directory first.</div>}
      <label className="m3-field"><span>Skills</span><input value={memberDialog.draft.skills} onChange={(event) => setMemberDialog({ ...memberDialog, draft: { ...memberDialog.draft, skills: event.target.value } })} placeholder="React, Java, AWS, payments" /></label>
      <div className="l1-form-grid"><label className="m3-field"><span>Location</span><input value={memberDialog.draft.location} onChange={(event) => setMemberDialog({ ...memberDialog, draft: { ...memberDialog.draft, location: event.target.value } })} /></label><label className="m3-field"><span>Allocation %</span><input type="number" min="0" max="100" value={memberDialog.draft.allocation_percent} onChange={(event) => setMemberDialog({ ...memberDialog, draft: { ...memberDialog.draft, allocation_percent: clampPercent(event.target.value) } })} /></label></div>
      <label className="m3-field"><span>Monthly loaded cost</span><input type="number" min="0" step="100" value={memberDialog.draft.monthly_cost} onChange={(event) => setMemberDialog({ ...memberDialog, draft: { ...memberDialog.draft, monthly_cost: event.target.value } })} /></label>
    </PlanningDialog>}
  </>

  if (plan.units.length === 0) {
    return <section>
      {heading}
      <div className="l1-empty-panel"><UsersRound size={32} /><h3>Start with the delivery shape</h3><p>Add a tribe for strategic ownership, then squads with people, skills, capacity, and monthly cost.</p><button className="m3-btn filled" onClick={() => openUnit(null, 'tribe')}><Plus size={16} /> Add first tribe</button></div>
      {dialogs}
    </section>
  }

  if (view === 'cards') {
    return <section>
      {heading}
      <div className="l1-team-grid">
        {[...tribes, ...squads].map((unit) => {
          const parent = tribes.find((item) => item.id === unit.parent_unit_id)
          return <article key={unit.id} className={`l1-team-card ${unit.unit_type}`}>
            <header>
              <span className={`l1-unit-mark ${unit.unit_type}`}><UsersRound size={18} /></span>
              <div className="l1-team-title"><span>{unit.unit_type}{parent ? ` · ${parent.name}` : ''}</span><h3>{unit.name}</h3></div>
              {unitActions(unit)}
            </header>
            <p className="l1-team-mission">{unit.mission || 'No mission statement yet.'}</p>
            <div className="l1-team-facts">
              <span><Crown size={14} /> {unit.lead_name || 'Lead not assigned'}</span>
              <span><Gauge size={14} /> {unit.capacity_fte || 0} FTE · {unit.target_velocity || 0} pts/sprint</span>
            </div>
            <div className="l1-team-cost"><span>Allocated run-rate</span><strong>{money(unitRunRate(unit))}<small>/month</small></strong></div>
            {memberList(unit)}
            <button className="m3-btn text small l1-card-action" onClick={() => openMember(unit)}><UserPlus size={15} /> Add person</button>
          </article>
        })}
      </div>
      {dialogs}
    </section>
  }

  return <section>
    {heading}
    <div className="l1-hierarchy">
      {tribes.map((tribe) => {
        const tribeSquads = squads.filter((squad) => squad.parent_unit_id === tribe.id)
        const units = [tribe, ...tribeSquads]
        const people = units.reduce((count, unit) => count + unit.members.length, 0)
        const runRate = units.reduce((sum, unit) => sum + unitRunRate(unit), 0)
        const capacity = units.reduce((sum, unit) => sum + number(unit.capacity_fte), 0)
        return <div key={tribe.id} className="l1-tribe-group">
          <header className="l1-tribe-head">
            <span className="l1-unit-mark tribe"><UsersRound size={18} /></span>
            <div className="l1-tribe-identity">
              <span>Tribe</span>
              <h3>{tribe.name}</h3>
              <p>{tribe.mission || 'No mission statement yet.'}</p>
            </div>
            <div className="l1-tribe-rollup">
              <span><strong>{tribeSquads.length}</strong> {tribeSquads.length === 1 ? 'squad' : 'squads'}</span>
              <span><strong>{people}</strong> {people === 1 ? 'person' : 'people'}</span>
              <span><strong>{capacity || 0}</strong> FTE</span>
              <span><strong>{money(runRate)}</strong>/mo</span>
            </div>
            <div className="l1-tribe-lead"><Crown size={14} /> {tribe.lead_name || 'Lead not assigned'}</div>
            {sharedRoleAction(tribe)}
            {unitActions(tribe)}
          </header>

          {tribe.members.length > 0 && <div className="l1-tribe-members">
            <span className="l1-node-label">Tribe leadership & shared roles</span>
            {memberList(tribe)}
            <button className="m3-btn text small" onClick={() => openMember(tribe)}><UserPlus size={15} /> Add shared role</button>
          </div>}

          <div className="l1-tribe-children">
            {tribeSquads.map((squad) => squadCard(squad, false))}
            <button className="l1-add-squad" onClick={() => openUnit(null, 'squad', tribe.id)}><Plus size={16} /> Add squad to {tribe.name}</button>
          </div>
        </div>
      })}

      {independentSquads.length > 0 && <div className="l1-tribe-group independent">
        <header className="l1-tribe-head">
          <span className="l1-unit-mark squad"><UsersRound size={18} /></span>
          <div className="l1-tribe-identity"><span>Unaligned</span><h3>Independent squads</h3><p>Squads not yet placed under a tribe.</p></div>
        </header>
        <div className="l1-tribe-children">
          {independentSquads.map((squad) => squadCard(squad, false))}
        </div>
      </div>}
    </div>
    {dialogs}
  </section>
}
