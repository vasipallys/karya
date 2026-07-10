import { Pencil, Plus, Settings2, Trash2, Users, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const STAFF_TYPES = ['Perm', 'Contract']
const STAFF_STATUSES = ['Active', 'Inactive']
const SUB_STATUSES = ['Allocated', 'UnAllocated', 'PartiallyAllocated']
const FIELD_TYPES = ['text', 'number', 'date', 'select', 'boolean']
const LOOKUP_META = [
  { category: 'tech_unit', label: 'Tech Units' },
  { category: 'rank', label: 'Ranks' },
  { category: 'hr_role', label: 'HR Roles' },
]

const emptyStaff = {
  staff_first_name: '', staff_last_name: '', staff_name: '', staff_type: 'Perm',
  staff_status: 'Active', sub_status: 'UnAllocated', tech_unit: '', citizenship: '',
  rank: '', hr_role: '', staff_start_date: '', staff_end_date: '', reporting_manager_id: '',
  custom_values: {},
}

function Dialog({ title, children, onClose, actions, wide = false }) {
  return <div className="m3-dialog-scrim" onMouseDown={onClose}>
    <section className={`m3-dialog${wide ? ' wide' : ''}`} onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
      <header className="l1-dialog-header"><h2>{title}</h2><button className="m3-icon-btn" onClick={onClose} aria-label="Close"><X size={19} /></button></header>
      <div>{children}</div>
      <footer className="m3-dialog-actions">{actions}</footer>
    </section>
  </div>
}

function CustomFieldInput({ field, value, onChange }) {
  const common = { value: value ?? '', onChange: (event) => onChange(event.target.value) }
  if (field.field_type === 'select') {
    return <label className="m3-field"><span>{field.label}{field.required ? ' *' : ''}</span>
      <select {...common}><option value="">—</option>{field.options.map((option) => <option key={option} value={option}>{option}</option>)}</select>
    </label>
  }
  if (field.field_type === 'boolean') {
    return <label className="m3-field"><span>{field.label}{field.required ? ' *' : ''}</span>
      <select value={value ? 'true' : 'false'} onChange={(event) => onChange(event.target.value === 'true')}><option value="false">No</option><option value="true">Yes</option></select>
    </label>
  }
  const type = field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'
  return <label className="m3-field"><span>{field.label}{field.required ? ' *' : ''}</span><input type={type} {...common} /></label>
}

export default function ResourceDirectory() {
  const [staff, setStaff] = useState(null)
  const [lookups, setLookups] = useState({ tech_unit: [], rank: [], hr_role: [] })
  const [customFields, setCustomFields] = useState([])
  const [filters, setFilters] = useState({ staff_status: '', sub_status: '', staff_type: '', search: '' })
  const [dialog, setDialog] = useState(null)      // { editing, draft }
  const [settings, setSettings] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const loadMeta = () => Promise.all([api.resourceLookups(), api.listCustomFields()])
    .then(([nextLookups, fields]) => { setLookups(nextLookups); setCustomFields(fields) })
    .catch(setError)

  const loadStaff = () => api.listStaff(filters).then(setStaff).catch(setError)

  useEffect(() => { loadMeta() }, [])
  useEffect(() => { loadStaff() }, [filters]) // eslint-disable-line react-hooks/exhaustive-deps

  const labelFor = (category, code) => lookups[category].find((row) => row.code === code)?.label || code || '—'
  const staffById = useMemo(() => Object.fromEntries((staff || []).map((row) => [row.id, row])), [staff])

  const openEditor = (record = null) => setDialog({
    editing: record,
    draft: record ? {
      ...emptyStaff, ...record,
      staff_start_date: record.staff_start_date || '', staff_end_date: record.staff_end_date || '',
      reporting_manager_id: record.reporting_manager_id || '', custom_values: { ...(record.custom_values || {}) },
    } : { ...emptyStaff, custom_values: {} },
  })

  const setDraft = (patch) => setDialog((current) => ({ ...current, draft: { ...current.draft, ...patch } }))

  const save = async () => {
    setBusy(true); setError(null)
    try {
      const draft = dialog.draft
      const payload = {
        ...draft,
        staff_start_date: draft.staff_start_date || null,
        staff_end_date: draft.staff_end_date || null,
        reporting_manager_id: draft.reporting_manager_id || null,
      }
      if (dialog.editing) await api.updateStaff(dialog.editing.id, payload)
      else await api.createStaff(payload)
      setDialog(null); await loadStaff()
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  const remove = async (record) => {
    if (!window.confirm(`Remove ${record.staff_name} (${record.staff_code}) from the resource directory?`)) return
    try { await api.deleteStaff(record.id); await loadStaff() } catch (err) { setError(err) }
  }

  const managerOptions = (staff || []).filter((row) => !dialog?.editing || row.id !== dialog.editing.id)

  return <div className="res-screen">
    <header className="proj-hero">
      <div className="proj-hero-text">
        <h1>Resources</h1>
        <p>A global directory of people that any module — squads, work items, reporting chains — can draw from. Add custom fields to capture whatever your teams track.</p>
      </div>
      <div className="l1-heading-actions">
        <button className="m3-btn outlined" onClick={() => setSettings(true)}><Settings2 size={16} /> Lists &amp; fields</button>
        <button className="m3-btn filled" onClick={() => openEditor()}><Plus size={16} /> Add resource</button>
      </div>
    </header>

    {error && <div className="m3-banner error">{String(error.message || error)}</div>}

    <div className="res-filters">
      <input placeholder="Search name or code…" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
      <select value={filters.staff_status} onChange={(event) => setFilters({ ...filters, staff_status: event.target.value })}><option value="">Any status</option>{STAFF_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}</select>
      <select value={filters.sub_status} onChange={(event) => setFilters({ ...filters, sub_status: event.target.value })}><option value="">Any allocation</option>{SUB_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}</select>
      <select value={filters.staff_type} onChange={(event) => setFilters({ ...filters, staff_type: event.target.value })}><option value="">Any type</option>{STAFF_TYPES.map((value) => <option key={value} value={value}>{value}</option>)}</select>
    </div>

    {staff && staff.length === 0
      ? <div className="l1-empty-panel"><Users size={32} /><h3>No resources yet</h3><p>Add your first person to build a directory the whole workspace can share.</p><button className="m3-btn filled" onClick={() => openEditor()}><Plus size={16} /> Add resource</button></div>
      : <div className="res-table-wrap"><table className="res-table">
        <thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Status</th><th>Allocation</th><th>Tech Unit</th><th>Rank</th><th>HR Role</th><th>Manager</th><th></th></tr></thead>
        <tbody>
          {(staff || []).map((row) => <tr key={row.id} onClick={() => openEditor(row)}>
            <td className="res-mono">{row.staff_code}</td>
            <td><strong>{row.staff_name}</strong></td>
            <td>{row.staff_type}</td>
            <td><span className={`res-pill ${row.staff_status === 'Active' ? 'ok' : 'muted'}`}>{row.staff_status}</span></td>
            <td><span className={`res-pill sub-${row.sub_status.toLowerCase()}`}>{row.sub_status}</span></td>
            <td>{labelFor('tech_unit', row.tech_unit)}</td>
            <td>{labelFor('rank', row.rank)}</td>
            <td>{labelFor('hr_role', row.hr_role)}</td>
            <td>{staffById[row.reporting_manager_id]?.staff_name || '—'}</td>
            <td className="res-row-actions" onClick={(event) => event.stopPropagation()}>
              <button className="m3-icon-btn" onClick={() => openEditor(row)} aria-label={`Edit ${row.staff_name}`}><Pencil size={15} /></button>
              <button className="m3-icon-btn danger-ink" onClick={() => remove(row)} aria-label={`Delete ${row.staff_name}`}><Trash2 size={15} /></button>
            </td>
          </tr>)}
        </tbody>
      </table></div>}

    {dialog && <Dialog wide title={dialog.editing ? `Edit ${dialog.editing.staff_name}` : 'Add resource'} onClose={() => setDialog(null)}
      actions={<><button className="m3-btn text" onClick={() => setDialog(null)}>Cancel</button><button className="m3-btn filled" disabled={busy || !dialog.draft.staff_first_name.trim() || !dialog.draft.staff_last_name.trim()} onClick={save}>Save</button></>}>
      <div className="l1-form-grid">
        <label className="m3-field"><span>First name *</span><input autoFocus value={dialog.draft.staff_first_name} onChange={(event) => setDraft({ staff_first_name: event.target.value })} /></label>
        <label className="m3-field"><span>Last name *</span><input value={dialog.draft.staff_last_name} onChange={(event) => setDraft({ staff_last_name: event.target.value })} /></label>
      </div>
      <label className="m3-field"><span>Display name</span><input value={dialog.draft.staff_name} onChange={(event) => setDraft({ staff_name: event.target.value })} placeholder="Auto-generated from first + last if blank" /></label>
      <div className="l1-form-grid">
        <label className="m3-field"><span>Type</span><select value={dialog.draft.staff_type} onChange={(event) => setDraft({ staff_type: event.target.value })}>{STAFF_TYPES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="m3-field"><span>Status</span><select value={dialog.draft.staff_status} onChange={(event) => setDraft({ staff_status: event.target.value })}>{STAFF_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="m3-field"><span>Allocation</span><select value={dialog.draft.sub_status} onChange={(event) => setDraft({ sub_status: event.target.value })}>{SUB_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      </div>
      <div className="l1-form-grid">
        <label className="m3-field"><span>Tech Unit</span><select value={dialog.draft.tech_unit} onChange={(event) => setDraft({ tech_unit: event.target.value })}><option value="">—</option>{lookups.tech_unit.map((row) => <option key={row.id} value={row.code}>{row.label}</option>)}</select></label>
        <label className="m3-field"><span>Rank</span><select value={dialog.draft.rank} onChange={(event) => setDraft({ rank: event.target.value })}><option value="">—</option>{lookups.rank.map((row) => <option key={row.id} value={row.code}>{row.label}</option>)}</select></label>
        <label className="m3-field"><span>HR Role</span><select value={dialog.draft.hr_role} onChange={(event) => setDraft({ hr_role: event.target.value })}><option value="">—</option>{lookups.hr_role.map((row) => <option key={row.id} value={row.code}>{row.label}</option>)}</select></label>
      </div>
      <div className="l1-form-grid">
        <label className="m3-field"><span>Citizenship (ISO)</span><input value={dialog.draft.citizenship} onChange={(event) => setDraft({ citizenship: event.target.value })} placeholder="GB, IN, US…" /></label>
        <label className="m3-field"><span>Reporting manager</span><select value={dialog.draft.reporting_manager_id} onChange={(event) => setDraft({ reporting_manager_id: event.target.value })}><option value="">—</option>{managerOptions.map((row) => <option key={row.id} value={row.id}>{row.staff_name}</option>)}</select></label>
      </div>
      <div className="l1-form-grid">
        <label className="m3-field"><span>Start date (joining)</span><input type="date" value={dialog.draft.staff_start_date} onChange={(event) => setDraft({ staff_start_date: event.target.value })} /></label>
        <label className="m3-field"><span>End date</span><input type="date" value={dialog.draft.staff_end_date} onChange={(event) => setDraft({ staff_end_date: event.target.value })} /></label>
      </div>
      {customFields.length > 0 && <>
        <div className="res-section-label">Custom fields</div>
        <div className="l1-form-grid">
          {customFields.map((field) => <CustomFieldInput key={field.id} field={field}
            value={dialog.draft.custom_values[field.key]}
            onChange={(value) => setDraft({ custom_values: { ...dialog.draft.custom_values, [field.key]: value } })} />)}
        </div>
      </>}
    </Dialog>}

    {settings && <SettingsDialog lookups={lookups} customFields={customFields} onClose={() => setSettings(false)}
      reload={loadMeta} setError={setError} />}
  </div>
}

function SettingsDialog({ lookups, customFields, onClose, reload, setError }) {
  const [lookupDraft, setLookupDraft] = useState({ tech_unit: { code: '', label: '' }, rank: { code: '', label: '' }, hr_role: { code: '', label: '' } })
  const [fieldDraft, setFieldDraft] = useState({ key: '', label: '', field_type: 'text', required: false, options: '' })

  const addLookup = async (category) => {
    const draft = lookupDraft[category]
    if (!draft.code.trim() || !draft.label.trim()) return
    try { await api.createLookup(category, draft); setLookupDraft({ ...lookupDraft, [category]: { code: '', label: '' } }); await reload() } catch (err) { setError(err) }
  }
  const removeLookup = async (row) => { try { await api.deleteLookup(row.id); await reload() } catch (err) { setError(err) } }

  const addField = async () => {
    if (!fieldDraft.key.trim() || !fieldDraft.label.trim()) return
    try {
      const options = fieldDraft.field_type === 'select' ? fieldDraft.options.split(',').map((value) => value.trim()).filter(Boolean) : []
      await api.createCustomField({ key: fieldDraft.key, label: fieldDraft.label, field_type: fieldDraft.field_type, required: fieldDraft.required, options })
      setFieldDraft({ key: '', label: '', field_type: 'text', required: false, options: '' }); await reload()
    } catch (err) { setError(err) }
  }
  const removeField = async (field) => { if (window.confirm(`Delete custom field "${field.label}"?`)) { try { await api.deleteCustomField(field.id); await reload() } catch (err) { setError(err) } } }

  return <Dialog wide title="Lists & custom fields" onClose={onClose} actions={<button className="m3-btn filled" onClick={onClose}>Done</button>}>
    <div className="res-settings-grid">
      {LOOKUP_META.map(({ category, label }) => <div key={category} className="res-lookup-block">
        <h3>{label}</h3>
        <ul className="res-lookup-list">
          {lookups[category].map((row) => <li key={row.id}><span className="res-mono">{row.code}</span><span>{row.label}</span><button className="m3-icon-btn danger-ink" onClick={() => removeLookup(row)} aria-label={`Delete ${row.label}`}><Trash2 size={14} /></button></li>)}
          {lookups[category].length === 0 && <li className="res-empty-row">Nothing defined yet.</li>}
        </ul>
        <div className="res-inline-add">
          <input placeholder="CODE" value={lookupDraft[category].code} onChange={(event) => setLookupDraft({ ...lookupDraft, [category]: { ...lookupDraft[category], code: event.target.value.toUpperCase() } })} />
          <input placeholder="Label" value={lookupDraft[category].label} onChange={(event) => setLookupDraft({ ...lookupDraft, [category]: { ...lookupDraft[category], label: event.target.value } })} />
          <button className="m3-btn tonal small" onClick={() => addLookup(category)}><Plus size={14} /></button>
        </div>
      </div>)}
    </div>

    <div className="res-section-label">Custom fields (apply to every resource)</div>
    <ul className="res-lookup-list">
      {customFields.map((field) => <li key={field.id}><span className="res-mono">{field.key}</span><span>{field.label} · {field.field_type}{field.required ? ' · required' : ''}{field.options?.length ? ` · [${field.options.join(', ')}]` : ''}</span><button className="m3-icon-btn danger-ink" onClick={() => removeField(field)} aria-label={`Delete ${field.label}`}><Trash2 size={14} /></button></li>)}
      {customFields.length === 0 && <li className="res-empty-row">No custom fields yet.</li>}
    </ul>
    <div className="res-field-add">
      <input placeholder="key (a-z_)" value={fieldDraft.key} onChange={(event) => setFieldDraft({ ...fieldDraft, key: event.target.value })} />
      <input placeholder="Label" value={fieldDraft.label} onChange={(event) => setFieldDraft({ ...fieldDraft, label: event.target.value })} />
      <select value={fieldDraft.field_type} onChange={(event) => setFieldDraft({ ...fieldDraft, field_type: event.target.value })}>{FIELD_TYPES.map((value) => <option key={value} value={value}>{value}</option>)}</select>
      {fieldDraft.field_type === 'select' && <input placeholder="Options (comma-separated)" value={fieldDraft.options} onChange={(event) => setFieldDraft({ ...fieldDraft, options: event.target.value })} />}
      <label className="res-required-toggle"><input type="checkbox" checked={fieldDraft.required} onChange={(event) => setFieldDraft({ ...fieldDraft, required: event.target.checked })} /> Required</label>
      <button className="m3-btn tonal small" onClick={addField}><Plus size={14} /> Add field</button>
    </div>
  </Dialog>
}
