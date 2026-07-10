import { ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { ROLE_LABELS } from '../../auth/permissions'
import { useToast } from '../../ui/Toast'

const ROLE_ORDER = ['admin', 'manager', 'contributor', 'viewer']

function initials(name) {
  return (name || '?').trim().split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'
}

export default function AccessManagement() {
  const { user } = useAuth()
  const toast = useToast()
  const [users, setUsers] = useState(null)
  const [roles, setRoles] = useState(ROLE_ORDER)
  const [query, setQuery] = useState('')

  const load = () => api.accessUsers().then(setUsers).catch((err) => toast.error(err))
  useEffect(() => { load(); api.roles().then(setRoles).catch(() => {}) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    const clean = query.trim().toLowerCase()
    return (users || []).filter((u) => !clean || u.staff_name.toLowerCase().includes(clean) || (u.staff_code || '').toLowerCase().includes(clean))
  }, [users, query])

  const adminCount = (users || []).filter((u) => u.role === 'admin' && u.enabled).length

  const changeRole = async (row, role) => {
    if (row.role === 'admin' && role !== 'admin' && adminCount <= 1) {
      toast.error('At least one enabled administrator is required.')
      return
    }
    try { await api.setAccess(row.id, { role }); toast.success(`${row.staff_name} is now ${ROLE_LABELS[role]}`); await load() } catch (err) { toast.error(err) }
  }

  const toggleEnabled = async (row) => {
    if (row.enabled && row.role === 'admin' && adminCount <= 1) {
      toast.error('Cannot disable the last administrator.')
      return
    }
    try { await api.setAccess(row.id, { enabled: !row.enabled }); toast.success(`${row.staff_name} ${row.enabled ? 'disabled' : 'enabled'}`); await load() } catch (err) { toast.error(err) }
  }

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div><h2>Access management</h2><p>Assign application roles to people in the resource directory. Roles gate what each person can see and do.</p></div>
        <span className="m3-chip"><ShieldCheck size={14} /> {adminCount} admin{adminCount !== 1 ? 's' : ''}</span>
      </div>

      <div className="res-filters"><input placeholder="Search name or code…" value={query} onChange={(event) => setQuery(event.target.value)} /></div>

      <div className="res-table-wrap"><table className="res-table">
        <thead><tr><th>Person</th><th>Code</th><th>Directory role</th><th>App role</th><th>Access</th></tr></thead>
        <tbody>
          {filtered.map((row) => (
            <tr key={row.id}>
              <td><span className="access-person"><span className="login-avatar sm">{initials(row.staff_name)}</span><strong>{row.staff_name}{row.id === user?.staff_id ? ' (you)' : ''}</strong></span></td>
              <td className="res-mono">{row.staff_code}</td>
              <td>{row.hr_role || '—'}</td>
              <td>
                <select className={`role-select role-${row.role}`} value={row.role} onChange={(event) => changeRole(row, event.target.value)}>
                  {roles.map((role) => <option key={role} value={role}>{ROLE_LABELS[role] || role}</option>)}
                </select>
              </td>
              <td>
                <button className={`access-toggle ${row.enabled ? 'on' : 'off'}`} onClick={() => toggleEnabled(row)} role="switch" aria-checked={row.enabled}>
                  <span className="access-knob" />{row.enabled ? 'Enabled' : 'Disabled'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {users !== null && filtered.length === 0 && <div className="login-empty">No people match.</div>}
    </section>
  )
}
