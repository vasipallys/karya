import { Boxes, Code2, Compass, DownloadCloud, FolderGit2, Landmark, LayoutDashboard, Network, Puzzle, ScanSearch, Sigma, UsersRound, Zap } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import ChatDock from '../components/ChatDock'
import DockablePanel from '../components/DockablePanel'
import LeadsEditor from '../components/LeadsEditor'
import C4Canvas from '../c4/C4Canvas'
import RollupDashboard from '../c4/RollupDashboard'
import L1Planning from '../planning/L1Planning'
import QuickEstimate from './QuickEstimate'
import WorkflowWizard from './WorkflowWizard'

const L2Architecture = lazy(() => import('../planning/L2Architecture'))
const L3Architecture = lazy(() => import('../planning/L3Architecture'))
const L4Architecture = lazy(() => import('../planning/L4Architecture'))

const TABS = [
  { id: 'canvas', label: 'C4 canvas', icon: Network },
  { id: 'planning', label: 'L1 plan', icon: Landmark },
  { id: 'l2arch', label: 'L2 arch', icon: Boxes },
  { id: 'l3arch', label: 'L3 arch', icon: Puzzle },
  { id: 'l4arch', label: 'L4 detail', icon: Code2 },
  { id: 'rollup', label: 'Roll-up', icon: Sigma },
  { id: 'quick', label: 'Quick', icon: Zap },
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
]

function Overview({ project, config, onChanged }) {
  const [scanPath, setScanPath] = useState(project.repos.find((repo) => repo.local_path)?.local_path || '')
  const [jiraForm, setJiraForm] = useState({ instance_name: '', project_key: '' })
  const [repoForm, setRepoForm] = useState({ url: '', local_path: '' })
  const [leads, setLeads] = useState(project.leads || [])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)

  const act = async (action, message) => {
    setBusy(true); setError(null); setNotice(null)
    try { const outcome = await action(); setNotice(message(outcome)); onChanged() }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  const saveLeads = () => act(
    () => api.updateProject(project.id, { leads: leads.map((lead) => ({ name: (lead.name || '').trim(), role: (lead.role || '').trim() })).filter((lead) => lead.name) }),
    () => 'Leads updated.',
  )
  const leadsDirty = JSON.stringify(leads) !== JSON.stringify(project.leads || [])

  return <div style={{ maxWidth: 760 }}>
    {notice && <div className="m3-banner info">{notice}</div>}
    {error && <div className="m3-banner error">{String(error.message || error)}</div>}
    <div className="m3-card" style={{ marginBottom: 16 }}>
      <h3>{project.name}</h3>
      <div className="m3-meta">{project.description || 'No description'}</div>
      <div className="m3-card-chips">
        {(project.leads || []).map((lead, index) => <span key={index} className="m3-chip filled"><UsersRound size={13} /> {lead.name}{lead.role ? ` · ${lead.role}` : ''}</span>)}
        {project.repos.map((repo) => <span key={repo.id} className="m3-chip"><FolderGit2 size={13} /> {repo.url || repo.local_path}{repo.mode === 'new' ? ' (planned)' : ''}</span>)}
        {project.jira.map((link) => <span key={link.id} className="m3-chip filled">{link.instance_name} · {link.project_key}</span>)}
      </div>
    </div>

    <div className="m3-card" style={{ marginBottom: 16 }}>
      <h3>Platform leads</h3>
      <p className="m3-meta">The people accountable for this platform. Add one or more.</p>
      <LeadsEditor leads={leads} onChange={setLeads} />
      <div className="m3-inspector-actions">
        <button className="m3-btn filled small" disabled={busy || !leadsDirty} onClick={saveLeads}>Save leads</button>
      </div>
    </div>

    <div className="m3-card" style={{ marginBottom: 16 }}>
      <h3>Seed / grow the C4 model</h3>
      <p className="m3-meta">Both importers create elements with a “proposed” status so nothing enters the roll-up until you accept it.</p>
      <label className="m3-field"><span>Local repo path to scan</span>
        <input value={scanPath} onChange={(event) => setScanPath(event.target.value)} placeholder="D:\\work\\my-repo" /></label>
      <div className="m3-inspector-actions">
        <button className="m3-btn tonal" disabled={busy || !scanPath.trim()}
          onClick={() => act(() => api.importRepoScan(project.id, { local_path: scanPath.trim(), apply: true }),
            (outcome) => `Repo scan proposed ${outcome.created} new elements.`)}>
          <ScanSearch size={16} /> Scan repo into C4</button>
        <button className="m3-btn tonal" disabled={busy || project.jira.length === 0}
          onClick={() => act(() => api.importJira(project.id),
            (outcome) => `Imported ${outcome.created} Jira issues as proposed stories.`)}>
          <DownloadCloud size={16} /> Import Jira issues</button>
      </div>
    </div>

    <div className="m3-card" style={{ marginBottom: 16 }}>
      <h3>Add a repo link</h3>
      <label className="m3-field"><span>URL</span><input value={repoForm.url} onChange={(event) => setRepoForm({ ...repoForm, url: event.target.value })} /></label>
      <label className="m3-field"><span>Local path</span><input value={repoForm.local_path} onChange={(event) => setRepoForm({ ...repoForm, local_path: event.target.value })} /></label>
      <button className="m3-btn outlined small" disabled={busy || (!repoForm.url.trim() && !repoForm.local_path.trim())}
        onClick={() => act(() => api.addRepo(project.id, { ...repoForm, mode: 'existing' }), () => 'Repo linked.')}>Link repo</button>
    </div>

    <div className="m3-card">
      <h3>Add a Jira link</h3>
      <label className="m3-field"><span>Instance</span>
        <select value={jiraForm.instance_name} onChange={(event) => setJiraForm({ ...jiraForm, instance_name: event.target.value })}>
          <option value="">— choose —</option>
          {(config?.jira_instances || []).map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
        </select></label>
      <label className="m3-field"><span>Project key</span><input value={jiraForm.project_key} onChange={(event) => setJiraForm({ ...jiraForm, project_key: event.target.value })} /></label>
      <button className="m3-btn outlined small" disabled={busy || !jiraForm.instance_name || !jiraForm.project_key.trim()}
        onClick={() => act(() => api.addJiraLink(project.id, jiraForm), () => 'Jira linked.')}>Link Jira</button>
    </div>
  </div>
}

export default function ProjectWorkspace({ projectId, config, notice }) {
  const [tab, setTab] = useState('canvas')
  const [planningL1Id, setPlanningL1Id] = useState(null)
  const [project, setProject] = useState(null)
  const [error, setError] = useState(null)
  const [wizard, setWizard] = useState(false)

  const refresh = useCallback(() => api.getProject(projectId).then(setProject).catch(setError), [projectId])
  useEffect(() => { refresh() }, [refresh])

  if (error) return <div className="m3-content"><div className="m3-banner error">{String(error.message || error)}</div></div>
  if (!project) return <p className="m3-content">Loading platform…</p>

  return <div className="m3-body">
    <DockablePanel id="workspace-rail" side="left" title="Sections" defaultWidth={88} minWidth={76} maxWidth={140}>
      <nav className="m3-rail" aria-label="Platform sections">
        {TABS.map(({ id, label, icon: Icon }) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>
          <span className="m3-rail-icon"><Icon size={20} /></span>{label}</button>)}
      </nav>
    </DockablePanel>
    <div className="m3-content">
      <div className="m3-page-title">
        <div>
          <h1>{project.name}</h1>
          <p>{TABS.find((item) => item.id === tab)?.label}</p>
        </div>
        <button className="m3-btn tonal small wf-launch" onClick={() => setWizard(true)}><Compass size={15} /> Workflow guide</button>
      </div>
      {wizard && <WorkflowWizard projectId={projectId} onNavigate={setTab} onClose={() => setWizard(false)} />}
      {notice && tab === 'canvas' && <div className="m3-banner info">{notice}</div>}
      {tab === 'canvas' && <C4Canvas projectId={projectId} config={config}
        onOpenL1Plan={(elementId) => { setPlanningL1Id(elementId); setTab('planning') }} />}
      {tab === 'planning' && <L1Planning projectId={projectId} requestedL1Id={planningL1Id}
        onL1Change={setPlanningL1Id} onOpenCanvas={() => setTab('canvas')} />}
      {tab === 'l2arch' && <Suspense fallback={<p className="l1-loading">Loading L2 workspace…</p>}><L2Architecture projectId={projectId} onOpenCanvas={() => setTab('canvas')} /></Suspense>}
      {tab === 'l3arch' && <Suspense fallback={<p className="l1-loading">Loading L3 workspace…</p>}><L3Architecture projectId={projectId} onOpenCanvas={() => setTab('canvas')} /></Suspense>}
      {tab === 'l4arch' && <Suspense fallback={<p className="l1-loading">Loading L4 workspace…</p>}><L4Architecture projectId={projectId} onOpenCanvas={() => setTab('canvas')} /></Suspense>}
      {tab === 'rollup' && <RollupDashboard projectId={projectId} />}
      {tab === 'quick' && <QuickEstimate config={config} />}
      {tab === 'overview' && <Overview project={project} config={config} onChanged={refresh} />}
    </div>
    <ChatDock projectId={projectId} onChanged={refresh} />
  </div>
}
