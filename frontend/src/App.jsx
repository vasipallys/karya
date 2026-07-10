import { BookOpen, BrainCircuit, ChevronDown, LogOut, Server, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import { useAuth } from './auth/AuthContext'
import { ROLE_LABELS } from './auth/permissions'
import AdminConsole from './screens/AdminConsole'
import Login from './screens/Login'
import NewProjectWizard from './screens/NewProjectWizard'
import ProjectsHome from './screens/ProjectsHome'
import ProjectWorkspace from './screens/ProjectWorkspace'
import QuickEstimate from './screens/QuickEstimate'

function initials(name) {
  return (name || '?').trim().split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'
}

function UserMenu() {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (event) => { if (ref.current && !ref.current.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  return (
    <div className="user-menu" ref={ref}>
      <button className="user-menu-trigger" onClick={() => setOpen((value) => !value)} aria-haspopup="menu" aria-expanded={open}>
        <span className="login-avatar sm">{initials(user.name)}</span>
        <span className="user-menu-id"><strong>{user.name}</strong><small>{ROLE_LABELS[user.role] || user.role}</small></span>
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="user-menu-pop" role="menu">
          <div className="user-menu-head"><span className="login-avatar">{initials(user.name)}</span><div><strong>{user.name}</strong><small>{user.staff_code ? `${user.staff_code} · ` : ''}{ROLE_LABELS[user.role] || user.role}</small></div></div>
          <button className="user-menu-item" role="menuitem" onClick={signOut}><LogOut size={15} /> Sign out</button>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const { user, can } = useAuth()
  const [route, setRoute] = useState({ name: 'home' })
  const [config, setConfig] = useState(null)
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  // Land every freshly signed-in identity on Home (avoids showing a prior
  // session's route, e.g. an admin page, to a user who can't access it).
  useEffect(() => { setRoute({ name: 'home' }) }, [user?.staff_id, user?.role])

  useEffect(() => {
    if (!user) return
    Promise.all([api.config(), api.health()])
      .then(([nextConfig, nextHealth]) => { setConfig(nextConfig); setHealth(nextHealth) })
      .catch(setError)
  }, [user])

  if (!user) return <Login />

  const jiraStatuses = health?.jira ? Object.entries(health.jira) : []
  const configurationError = health?.llm?.errors?.length
    ? `Backend configuration: ${health.llm.errors.join('; ')}`
    : error ? String(error.message || error) : null
  const showAdmin = can('admin')

  const go = (name) => setRoute({ name })

  return <div className="m3 app-shell">
    <header className="m3-topbar">
      <button className="m3-brand" onClick={() => go('home')} aria-label="Story Pointer home">
        <span className="m3-brand-mark"><BrainCircuit size={20} /></span>
        <span style={{ textAlign: 'left' }}><strong>Story Pointer</strong><small>C4 workspace · evidence-led estimation</small></span>
      </button>
      <nav className="m3-topbar-nav">
        <button className={route.name === 'home' || route.name === 'project' || route.name === 'wizard' ? 'active' : ''} onClick={() => go('home')}>Platforms</button>
        {showAdmin && <button className={route.name === 'admin' ? 'active' : ''} onClick={() => go('admin')}><ShieldCheck size={14} /> Admin</button>}
        <a className="m3-topbar-link" href="/help/guide.html" target="_blank" rel="noreferrer" title="Open the interactive user guide in a new tab"><BookOpen size={14} /> Guide</a>
      </nav>
      <div className="m3-topbar-status">
        <span className="m3-chip"><Server size={13} />{config ? (config.llm.provider ? `${config.llm.provider} · ${config.llm.model}` : 'LLM not configured') : 'Checking model…'}</span>
        {jiraStatuses.map(([name, value]) => <span key={name} className={`m3-chip ${value.status === 'ok' ? 'ok' : 'bad'}`}>{name}</span>)}
        <UserMenu />
      </div>
    </header>
    {route.name === 'project'
      ? <>
        {configurationError && <div className="m3-content" style={{ padding: '16px 28px 0' }}><div className="m3-banner error">{configurationError}</div></div>}
        <ProjectWorkspace key={route.id} projectId={route.id} config={config} notice={route.notice} />
      </>
      : <div className="m3-content" style={{ flex: 1 }}>
        {configurationError && <div className="m3-banner error">{configurationError}</div>}
        {route.name === 'home' && <ProjectsHome
          canCreate={can('platform.create')}
          onOpen={(id) => setRoute({ name: 'project', id })}
          onNew={() => setRoute({ name: 'wizard' })}
          onQuick={() => setRoute({ name: 'quick' })} />}
        {route.name === 'wizard' && <NewProjectWizard config={config}
          onDone={(id, notice) => setRoute({ name: 'project', id, notice })}
          onCancel={() => setRoute({ name: 'home' })} />}
        {route.name === 'quick' && <>
          <div className="m3-page-title"><h1>Quick estimate</h1><p>One-off estimation without a platform — form, Jira browse, or spreadsheet.</p></div>
          <QuickEstimate config={config} />
        </>}
        {route.name === 'admin' && (showAdmin ? <AdminConsole /> : <div className="m3-banner error">You don't have access to the admin area.</div>)}
      </div>}
  </div>
}
