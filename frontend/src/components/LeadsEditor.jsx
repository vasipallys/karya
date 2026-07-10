import { Trash2, UserPlus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

/**
 * Add / remove / edit the people accountable for a platform.
 * `leads` is a list of { name, role }; `onChange` receives the next list.
 * Names are chosen from the global resource directory (active staff).
 */
export default function LeadsEditor({ leads, onChange }) {
  const [resources, setResources] = useState([])
  useEffect(() => { api.listStaff({ staff_status: 'Active' }).then(setResources).catch(() => setResources([])) }, [])

  const update = (index, key, value) => onChange(leads.map((lead, i) => (i === index ? { ...lead, [key]: value } : lead)))
  const add = () => onChange([...leads, { name: '', role: '' }])
  const remove = (index) => onChange(leads.filter((_, i) => i !== index))

  return (
    <div className="leads-editor">
      {leads.length === 0 && <p className="leads-empty">No leads yet — add the people accountable for this platform.</p>}
      {leads.map((lead, index) => (
        <div key={index} className="leads-row">
          <select value={lead.name} aria-label="Lead name" onChange={(event) => update(index, 'name', event.target.value)}>
            <option value="">— select from resource directory —</option>
            {lead.name && !resources.some((row) => row.staff_name === lead.name) && <option value={lead.name}>{lead.name} (not in directory)</option>}
            {resources.map((row) => <option key={row.id} value={row.staff_name}>{row.staff_name}</option>)}
          </select>
          <input value={lead.role || ''} placeholder="Role (optional)" aria-label="Lead role" onChange={(event) => update(index, 'role', event.target.value)} />
          <button type="button" className="m3-icon-btn small" onClick={() => remove(index)} aria-label="Remove lead"><Trash2 size={15} /></button>
        </div>
      ))}
      {resources.length === 0 && <p className="leads-empty">No active resources found. Add people in the Resources directory first.</p>}
      <button type="button" className="m3-btn text small" onClick={add}><UserPlus size={15} /> Add lead</button>
    </div>
  )
}
