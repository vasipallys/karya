import { LockKeyhole, Search, UserRound, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import { ROLE_LABELS } from '../../auth/permissions'
import { useToast } from '../../ui/Toast'

function choiceFor(user, pageKey) {
  if (user.role === 'admin') return 'allow'
  if (!Object.hasOwn(user.page_permission_overrides || {}, pageKey)) return 'inherit'
  return user.page_permission_overrides[pageKey] ? 'allow' : 'deny'
}

function displayValue(value) {
  if (value === true) return 'Yes'
  if (value === false) return 'No'
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function formatDate(value) {
  if (!value) return '—'
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

function Detail({ label, value, wide = false }) {
  return <div className={`user-detail-item${wide ? ' wide' : ''}`}>
    <dt>{label}</dt><dd>{displayValue(value)}</dd>
  </div>
}

function UserDetailsDialog({ profile, pages, onClose }) {
  const { user, staff, directory = [], lookups = {}, customFields = [], loading, error } = profile
  const labelFor = (category, code) => (lookups[category] || []).find((item) => item.code === code)?.label || code
  const manager = directory.find((item) => item.id === staff?.reporting_manager_id)
  const reports = directory.filter((item) => item.reporting_manager_id === user.id)
  const custom = staff?.custom_values || {}
  const knownCustom = new Set(['email', 'username', 'employee_number', 'phone', 'location', 'cost_center', 'skills', 'work_arrangement', 'sample_seed'])
  const additionalFields = customFields.filter((field) => !knownCustom.has(field.key) && Object.hasOwn(custom, field.key))

  return <div className="m3-dialog-scrim" onMouseDown={onClose}>
    <section className="m3-dialog user-details-dialog" onMouseDown={(event) => event.stopPropagation()}
      role="dialog" aria-modal="true" aria-label={`${user.staff_name} details`}>
      <header className="user-details-header">
        <span className="user-details-avatar"><UserRound size={26} /></span>
        <div><h2>{user.staff_name}</h2><p>{user.staff_code} · {ROLE_LABELS[user.role] || user.role}</p></div>
        <button className="m3-icon-btn" onClick={onClose} aria-label="Close user details"><X size={19} /></button>
      </header>

      {loading && <div className="user-details-state">Loading complete directory profile…</div>}
      {error && <div className="m3-banner error">{String(error.message || error)}</div>}
      {!loading && staff && <div className="user-details-body">
        <section>
          <h3>Identity and contact</h3>
          <dl className="user-details-grid">
            <Detail label="First name" value={staff.staff_first_name} />
            <Detail label="Last name" value={staff.staff_last_name} />
            <Detail label="Employee number" value={custom.employee_number} />
            <Detail label="Directory username" value={custom.username} />
            <Detail label="Work email" value={custom.email} />
            <Detail label="Work phone" value={custom.phone} />
            <Detail label="Citizenship" value={staff.citizenship} />
            <Detail label="Location" value={custom.location} />
          </dl>
        </section>

        <section>
          <h3>Organization</h3>
          <dl className="user-details-grid">
            <Detail label="Technology unit" value={labelFor('tech_unit', staff.tech_unit)} />
            <Detail label="HR role" value={labelFor('hr_role', staff.hr_role)} />
            <Detail label="Rank" value={labelFor('rank', staff.rank)} />
            <Detail label="Cost center" value={custom.cost_center} />
            <Detail label="Reporting manager" value={manager?.staff_name} />
            <Detail label="Direct reports" value={reports.length ? reports.map((item) => item.staff_name).join(', ') : 'None'} wide />
          </dl>
        </section>

        <section>
          <h3>Employment</h3>
          <dl className="user-details-grid">
            <Detail label="Employment type" value={staff.staff_type} />
            <Detail label="Directory status" value={staff.staff_status} />
            <Detail label="Allocation" value={staff.sub_status} />
            <Detail label="Work arrangement" value={custom.work_arrangement} />
            <Detail label="Joining date" value={formatDate(staff.staff_start_date)} />
            <Detail label="End date" value={formatDate(staff.staff_end_date)} />
            <Detail label="Primary skills" value={custom.skills} wide />
          </dl>
        </section>

        {additionalFields.length > 0 && <section>
          <h3>Additional directory fields</h3>
          <dl className="user-details-grid">
            {additionalFields.map((field) => <Detail key={field.key} label={field.label} value={custom[field.key]} />)}
          </dl>
        </section>}

        <section>
          <h3>Application access</h3>
          <dl className="user-details-grid user-access-summary">
            <Detail label="Application role" value={ROLE_LABELS[user.role] || user.role} />
            <Detail label="Login status" value={user.enabled ? 'Enabled' : 'Disabled'} />
          </dl>
          <div className="user-permission-list">
            {pages.map((page) => {
              const explicit = Object.hasOwn(user.page_permission_overrides || {}, page.key)
              const allowed = user.page_permissions?.[page.key]
              return <div className="user-permission-row" key={page.key}>
                <span><strong>{page.label}</strong><small>{explicit ? 'Individual override' : 'Role default'}</small></span>
                <span className={`res-pill ${allowed ? 'ok' : 'denied'}`}>{allowed ? 'Allowed' : 'Denied'}</span>
              </div>
            })}
          </div>
        </section>
      </div>}
      <footer className="m3-dialog-actions"><button className="m3-btn filled" onClick={onClose}>Close</button></footer>
    </section>
  </div>
}

export default function PagePermissions() {
  const toast = useToast()
  const [users, setUsers] = useState(null)
  const [pages, setPages] = useState([])
  const [query, setQuery] = useState('')
  const [busyCell, setBusyCell] = useState('')
  const [profile, setProfile] = useState(null)

  const load = () => Promise.all([api.accessUsers(), api.accessPages()])
    .then(([nextUsers, nextPages]) => { setUsers(nextUsers); setPages(nextPages) })
    .catch((error) => toast.error(error))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    const clean = query.trim().toLowerCase()
    return (users || []).filter((user) => !clean || user.staff_name.toLowerCase().includes(clean)
      || (user.staff_code || '').toLowerCase().includes(clean))
  }, [users, query])

  const change = async (user, pageKey, choice) => {
    const cell = `${user.id}:${pageKey}`
    setBusyCell(cell)
    try {
      const value = choice === 'inherit' ? null : choice === 'allow'
      const updated = await api.setPagePermissions(user.id, { [pageKey]: value })
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item))
      toast.success(`${user.staff_name}'s page access was updated.`)
    } catch (error) { toast.error(error) } finally { setBusyCell('') }
  }

  const openProfile = async (user) => {
    setProfile({ user, loading: true, staff: null, directory: [], lookups: {}, customFields: [], error: null })
    try {
      const [staff, directory, lookups, customFields] = await Promise.all([
        api.getStaff(user.id), api.listStaff(), api.resourceLookups(), api.listCustomFields(),
      ])
      setProfile((current) => current?.user.id === user.id
        ? { user, staff, directory, lookups, customFields, loading: false, error: null }
        : current)
    } catch (error) {
      setProfile((current) => current?.user.id === user.id ? { ...current, loading: false, error } : current)
    }
  }

  return <section className="admin-section">
    <div className="admin-section-head">
      <div><h2>Page permissions</h2><p>Override role defaults for individual users. “Role default” follows the selected application role; explicit Allow or Deny wins immediately in both the UI and API.</p></div>
      <span className="m3-chip"><LockKeyhole size={14} /> Per-user access</span>
    </div>
    <div className="login-search permission-search"><Search size={16} /><input placeholder="Search name or code…" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
    <div className="res-table-wrap permission-matrix"><table className="res-table">
      <thead><tr><th className="permission-person-col">Person</th>{pages.map((page) => <th key={page.key} title={page.description}>{page.label}</th>)}</tr></thead>
      <tbody>{filtered.map((user) => <tr key={user.id}>
        <td className="permission-person-col"><button type="button" className="permission-person-button" onClick={() => openProfile(user)} aria-label={`View complete details for ${user.staff_name}`}>
          <strong>{user.staff_name}</strong><small>{user.staff_code} · {ROLE_LABELS[user.role] || user.role}</small>
        </button></td>
        {pages.map((page) => {
          const choice = choiceFor(user, page.key)
          const effective = user.page_permissions?.[page.key]
          return <td key={page.key}>
            <select aria-label={`${user.staff_name} · ${page.label}`} className={`permission-select ${effective ? 'allowed' : 'denied'}`}
              value={choice} disabled={user.role === 'admin' || busyCell === `${user.id}:${page.key}`}
              onChange={(event) => change(user, page.key, event.target.value)}>
              <option value="inherit">Role default ({effective ? 'Allowed' : 'Denied'})</option>
              <option value="allow">Allow</option>
              <option value="deny">Deny</option>
            </select>
          </td>
        })}
      </tr>)}</tbody>
    </table></div>
    {users !== null && filtered.length === 0 && <div className="login-empty">No people match.</div>}
    <p className="admin-muted">Administrator access is always allowed as a lockout safeguard. Allowing an Admin page also grants that page’s administrative actions; platform creation and editing still follow the user’s role.</p>
    {profile && <UserDetailsDialog profile={profile} pages={pages} onClose={() => setProfile(null)} />}
  </section>
}
