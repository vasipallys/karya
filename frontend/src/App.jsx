import { BookOpen, BrainCircuit, ChevronDown, LogOut, Server, ShieldCheck, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import { useAuth } from './auth/AuthContext'
import { ROLE_LABELS } from './auth/permissions'
import AskAiDialog from './components/AskAiDialog'
import { resolveAiDestination } from './components/askAiRouting'
import { useToast } from './ui/Toast'
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
  const toast = useToast()
  const [route, setRoute] = useState({ name: 'home' })
  const [config, setConfig] = useState(null)
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [askAi, setAskAi] = useState(false)
  const [workspaceTab, setWorkspaceTab] = useState(null)

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
  const showPlatforms = can('page.platforms')
  const showWorkspace = can('page.workspace')
  const showAskAi = can('page.ask_ai')
  const showGuide = can('page.guide')
  const showAdmin = ['admin.access', 'admin.reporting', 'admin.resources', 'admin.integrations']
    .some((capability) => can(capability))

  const go = (name) => setRoute({ name })

  // Deep links from the home dashboard into the right module.
  const handleHomeNavigate = (target) => {
    if (!target) return
    if (target.kind === 'project') {
      if (!showWorkspace) { toast.info('You do not have access to project workspaces.'); return }
      setWorkspaceTab(target.tab ? { id: target.tab } : null)
      setRoute({ name: 'project', id: target.id })
    } else if (target.kind === 'admin') {
      if (showAdmin) setRoute({ name: 'admin', section: target.section, sectionTab: target.tab })
      else toast.info('That area lives in Admin — ask an admin for access.')
    }
  }

  // Global "Ask AI": route the orchestrator's chosen action to its workspace.
  const handleAiNavigate = (action) => {
    const destination = resolveAiDestination(action, route.name === 'project')
    if (destination.kind === 'tab') setWorkspaceTab({ id: destination.tab })
    else if (destination.kind === 'admin') {
      if (showAdmin) go('admin')
      else toast.info('Reporting lives in the Admin area — ask an admin to run it.')
    } else if (destination.kind === 'need-project') {
      toast.info('Open a platform first, then ask again.')
      go('home')
    }
  }

  return <div className="m3 app-shell">
    <header className="m3-topbar">
      <button className="m3-brand" onClick={() => go(showPlatforms ? 'home' : showAdmin ? 'admin' : 'home')} aria-label="Karya home">
        <span className="m3-brand-mark"><BrainCircuit size={20} /></span>
        <span style={{ textAlign: 'left' }}><strong>Karya</strong><small>C4 workspace · evidence-led estimation</small></span>
      </button>
      <nav className="m3-topbar-nav">
        {showPlatforms && <button className={route.name === 'home' || route.name === 'project' || route.name === 'wizard' ? 'active' : ''} onClick={() => go('home')}>Platforms</button>}
        {showAdmin && <button className={route.name === 'admin' ? 'active' : ''} onClick={() => go('admin')}><ShieldCheck size={14} /> Admin</button>}
        {showAskAi && <button onClick={() => setAskAi(true)} title="Route a request to the right AI agent"><Sparkles size={14} /> Ask AI</button>}
        {showGuide && <a className="m3-topbar-link" href="/help/guide.html?v=20260722" target="_blank" rel="noreferrer" title="Open the interactive user guide in a new tab"><BookOpen size={14} /> Guide</a>}
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
        {showWorkspace
          ? <ProjectWorkspace key={route.id} projectId={route.id} config={config} notice={route.notice} requestedTab={workspaceTab} />
          : <div className="m3-content"><div className="m3-banner error">You don't have access to the project workspace.</div></div>}
      </>
      : <div className="m3-content" style={{ flex: 1 }}>
        {configurationError && <div className="m3-banner error">{configurationError}</div>}
        {route.name === 'home' && (showPlatforms ? <ProjectsHome
          canCreate={can('platform.create')}
          onOpen={(id) => { if (!showWorkspace) { toast.info('You do not have access to project workspaces.'); return }; setWorkspaceTab(null); setRoute({ name: 'project', id }) }}
          onNavigate={handleHomeNavigate}
          onNew={(seed = 'blank') => setRoute({ name: 'wizard', seed })} />
          : <div className="m3-banner error">You don't have access to the Platforms page.</div>)}
        {route.name === 'wizard' && showPlatforms && <NewProjectWizard config={config} initialSeed={route.seed}
          onDone={(id, notice) => { setWorkspaceTab(null); setRoute({ name: 'project', id, notice }) }}
          onCancel={() => setRoute({ name: 'home' })} />}
        {route.name === 'quick' && <>
          <div className="m3-page-title"><h1>Quick estimate</h1><p>One-off estimation without a platform — form, Jira browse, or spreadsheet.</p></div>
          <QuickEstimate config={config} />
        </>}
        {route.name === 'admin' && (showAdmin ? <AdminConsole initialSection={route.section} initialTab={route.sectionTab} /> : <div className="m3-banner error">You don't have access to the admin area.</div>)}
      </div>}
    {askAi && <AskAiDialog onClose={() => setAskAi(false)} onNavigate={handleAiNavigate} />}
  </div>
}
