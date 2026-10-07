import { Boxes, Code2, Compass, DownloadCloud, FolderGit2, Landmark, LayoutDashboard, Network, Puzzle, ScanSearch, Sigma, UsersRound, Zap } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import ChatDock from '../components/ChatDock'
import DockablePanel from '../components/DockablePanel'
import LeadsEditor from '../components/LeadsEditor'
import { lineageTarget } from '../components/LevelNavigator'
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

const LEVEL_TAB = { L1: 'planning', L2: 'l2arch', L3: 'l3arch', L4: 'l4arch' }
const TAB_LEVEL = { planning: 'L1', l2arch: 'L2', l3arch: 'L3', l4arch: 'L4' }
const TAB_IDS = new Set(TABS.map((item) => item.id))

export default function ProjectWorkspace({ projectId, config, notice, requestedTab, onLocationChange }) {
  const initialTab = TAB_IDS.has(requestedTab?.id) ? requestedTab.id : 'canvas'
  const initialElement = requestedTab?.elementId || null
  const [tab, setTab] = useState(initialTab)
  // The element selected in each level workspace, plus the one the user last
  // focused anywhere (canvas, any level tab). Switching tabs follows the focus
  // up/down its own branch so every layer stays on the same thread of work.
  const [targets, setTargets] = useState(() => (TAB_LEVEL[initialTab] && initialElement
    ? { [TAB_LEVEL[initialTab]]: initialElement } : {}))
  const [focusId, setFocusId] = useState(initialElement)
  const [canvasTarget, setCanvasTarget] = useState(() => (initialTab === 'canvas' && initialElement ? { id: initialElement } : null))
  const [project, setProject] = useState(null)
  const [error, setError] = useState(null)
  const [wizard, setWizard] = useState(false)
  // Bumped whenever something outside a tab (chat assistant apply) mutates the
  // C4 model, so graph-holding tabs refetch instead of showing stale data.
  const [graphVersion, setGraphVersion] = useState(0)
  const focusRef = useRef(focusId)
  focusRef.current = focusId
  const targetsRef = useRef(targets)
  targetsRef.current = targets

  const refresh = useCallback(() => api.getProject(projectId).then(setProject).catch(setError), [projectId])
  useEffect(() => { refresh() }, [refresh])

  const modelChanged = useCallback(() => { refresh(); setGraphVersion((version) => version + 1) }, [refresh])

  const selectAt = useCallback((level, id) => {
    if (!id) return
    setTargets((current) => (current[level] === id ? current : { ...current, [level]: id }))
    setFocusId(id)
  }, [])
  const selectL1 = useCallback((id) => selectAt('L1', id), [selectAt])
  const selectL2 = useCallback((id) => selectAt('L2', id), [selectAt])
  const selectL3 = useCallback((id) => selectAt('L3', id), [selectAt])
  const selectL4 = useCallback((id) => selectAt('L4', id), [selectAt])
  const canvasFocus = useCallback((element) => {
    if (LEVEL_TAB[element.level]) selectAt(element.level, element.id)
    else setFocusId(element.id)
  }, [selectAt])

  // Deep-link any element (roll-up row, breadcrumb, chat result...) to the
  // workspace that owns its level, preselected.
  const openElement = useCallback((element) => {
    const target = LEVEL_TAB[element?.level]
    if (!target) return
    selectAt(element.level, element.id)
    setTab(target)
  }, [selectAt])

  // A request object lets repeated returns to the same element restore the
  // canvas drill path and selection every time.
  const openCanvasElement = useCallback((elementId) => {
    setCanvasTarget({ id: elementId || null })
    if (elementId) setFocusId(elementId)
    setTab('canvas')
  }, [])

  // Open a tab, optionally on a specific element. Without one, a level tab
  // opens the element on the focused branch (L2 -> its L3 child, L4 -> its L3
  // parent...), and the canvas re-centres on the focused element.
  const navigate = useCallback(async (nextTab, elementId = null) => {
    if (!TAB_IDS.has(nextTab)) return
    const level = TAB_LEVEL[nextTab]
    if (nextTab === 'canvas') { openCanvasElement(elementId || focusRef.current); return }
    const anchor = elementId || focusRef.current
    if (level && anchor) {
      try {
        const { elements } = await api.c4Graph(projectId)
        const element = elements.find((item) => item.id === anchor)
        const previous = targetsRef.current[level]
        // Keep the tab's previous pick when it is still on the focused branch
        // (L2 X -> L1 -> L2 returns to X, not to the L1's first child).
        const keepPrevious = !elementId && previous && element
          && lineageTarget(elements, previous, element.level)?.id === element.id
        const target = keepPrevious ? { id: previous }
          : element?.level === level ? element : lineageTarget(elements, anchor, level)
        if (target) selectAt(level, target.id)
      } catch { /* keep the tab's own selection */ }
    }
    setTab(nextTab)
  }, [projectId, openCanvasElement, selectAt])

  // Shell-level tab requests (Ask AI, Home deep links, browser back/forward);
  // a token object so repeated identical requests still retrigger. The first
  // request is already applied by the initial state above.
  const firstRequest = useRef(requestedTab)
  useEffect(() => {
    if (!requestedTab?.id || requestedTab === firstRequest.current) return
    navigate(requestedTab.id, requestedTab.elementId || null)
  }, [requestedTab, navigate])

  // Report where we are so the app can keep the URL (refresh/back/share) in sync.
  const level = TAB_LEVEL[tab]
  const locationElement = level ? targets[level] || null : tab === 'canvas' ? focusId : null
  useEffect(() => { onLocationChange?.({ tab, elementId: locationElement }) }, [tab, locationElement, onLocationChange])

  if (error) return <div className="m3-content"><div className="m3-banner error">{String(error.message || error)}</div></div>
  if (!project) return <p className="m3-content">Loading platform…</p>

  return <div className="m3-body">
    <DockablePanel id="workspace-rail" side="left" title="Sections" defaultWidth={88} minWidth={76} maxWidth={140}>
      <nav className="m3-rail" aria-label="Platform sections">
        {TABS.map(({ id, label, icon: Icon }) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => navigate(id)}>
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
      {wizard && <WorkflowWizard projectId={projectId} onNavigate={navigate} onClose={() => setWizard(false)} />}
      {notice && tab === 'canvas' && <div className="m3-banner info">{notice}</div>}
      {tab === 'canvas' && <C4Canvas projectId={projectId} config={config} reloadToken={graphVersion}
        requestedElement={canvasTarget} onOpenWorkspace={openElement} onFocus={canvasFocus} />}
      {tab === 'planning' && <L1Planning projectId={projectId} requestedL1Id={targets.L1 || null} reloadToken={graphVersion}
        onL1Change={selectL1} onOpenCanvas={openCanvasElement} onOpenElement={openElement} />}
      {tab === 'l2arch' && <Suspense fallback={<p className="l1-loading">Loading L2 workspace…</p>}><L2Architecture projectId={projectId} requestedId={targets.L2 || null} onSelect={selectL2} reloadToken={graphVersion} onOpenCanvas={openCanvasElement} onOpenElement={openElement} /></Suspense>}
      {tab === 'l3arch' && <Suspense fallback={<p className="l1-loading">Loading L3 workspace…</p>}><L3Architecture projectId={projectId} requestedId={targets.L3 || null} onSelect={selectL3} reloadToken={graphVersion} onOpenCanvas={openCanvasElement} onOpenElement={openElement} /></Suspense>}
      {tab === 'l4arch' && <Suspense fallback={<p className="l1-loading">Loading L4 workspace…</p>}><L4Architecture projectId={projectId} requestedId={targets.L4 || null} onSelect={selectL4} reloadToken={graphVersion} onOpenCanvas={openCanvasElement} onOpenElement={openElement} /></Suspense>}
      {tab === 'rollup' && <RollupDashboard projectId={projectId} onNavigate={openElement} reloadToken={graphVersion} />}
      {tab === 'quick' && <QuickEstimate config={config} />}
      {tab === 'overview' && <Overview project={project} config={config} onChanged={refresh} />}
    </div>
    <ChatDock projectId={projectId} onChanged={modelChanged} onOpenElement={openElement}
      onNavigate={(result) => navigate(result.workspace, result.l1_id || result.element_id || null)}
      screenContext={{
        tab,
        tab_label: TABS.find((item) => item.id === tab)?.label || tab,
        level: level || '',
        element_id: locationElement,
      }} />
  </div>
}
