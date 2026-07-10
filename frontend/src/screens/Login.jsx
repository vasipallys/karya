import { BrainCircuit, LogIn, Search, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { ROLE_LABELS } from '../auth/permissions'

function initials(name) {
  return (name || '?').trim().split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'
}

export default function Login() {
  const { signIn } = useAuth()
  const [users, setUsers] = useState(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    api.loginUsers().then(setUsers).catch((err) => { setError(err); setUsers([]) })
  }, [])

  const filtered = useMemo(() => {
    const clean = query.trim().toLowerCase()
    if (!clean) return users || []
    return (users || []).filter((u) => u.staff_name.toLowerCase().includes(clean) || (u.staff_code || '').toLowerCase().includes(clean))
  }, [users, query])

  const pick = (user) => signIn({
    staff_id: user.id, name: user.staff_name, role: user.role, staff_code: user.staff_code,
  })

  const bootstrap = () => signIn({ staff_id: null, name: 'Administrator', role: 'admin', staff_code: null })

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-brand">
          <span className="m3-brand-mark"><BrainCircuit size={24} /></span>
          <div><strong>Story Pointer</strong><span>C4 workspace · evidence-led estimation</span></div>
        </div>
        <h1 className="login-title">Sign in</h1>
        <p className="login-sub">Choose your identity from the resource directory to continue.</p>

        {error && <div className="m3-banner error">{String(error.message || error)}</div>}

        <div className="login-search">
          <Search size={16} />
          <input autoFocus placeholder="Search your name or staff code…" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>

        {users === null && <div className="login-empty">Loading directory…</div>}

        {users !== null && filtered.length === 0 && (
          <div className="login-empty">
            <ShieldCheck size={28} />
            <p>{users.length === 0 ? 'No users provisioned yet.' : 'No match for your search.'}</p>
            {users.length === 0 && (
              <button className="m3-btn filled" onClick={bootstrap}><LogIn size={16} /> Continue as Administrator</button>
            )}
          </div>
        )}

        <div className="login-users">
          {filtered.map((user) => (
            <button key={user.id} className="login-user" onClick={() => pick(user)}>
              <span className="login-avatar">{initials(user.staff_name)}</span>
              <span className="login-user-text">
                <strong>{user.staff_name}</strong>
                <small>{user.staff_code} · {ROLE_LABELS[user.role] || user.role}</small>
              </span>
              <span className={`res-pill role-${user.role}`}>{ROLE_LABELS[user.role] || user.role}</span>
            </button>
          ))}
        </div>

        <p className="login-foot">Local demo sign-in — no password required. Roles are managed in Admin → Access management.</p>
      </div>
    </div>
  )
}
