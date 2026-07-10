import { Blocks, CalendarRange, CircleAlert, FileText, Landmark, PanelTopClose, PanelTopOpen, RefreshCw, ShieldCheck, UsersRound, WalletCards } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import TeamPlanning from './TeamPlanning'
import WorkCostPlanning from './WorkCostPlanning'

const ArchitecturePlanning = lazy(() => import('./ArchitecturePlanning'))
const RequirementsPlanning = lazy(() => import('./RequirementsPlanning'))
const L1Architecture = lazy(() => import('./L1Architecture'))

const SECTIONS = [
  { id: 'baseline', label: 'L1 baseline', icon: ShieldCheck },
  { id: 'requirements', label: 'Requirements', icon: FileText },
  { id: 'teams', label: 'Tribes & squads', icon: UsersRound },
  { id: 'work', label: 'Work & cost', icon: CalendarRange },
  { id: 'architecture', label: 'Architecture', icon: Blocks },
]
const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'AUD', 'CAD', 'JPY', 'SGD']

export default function L1Planning({ projectId, requestedL1Id, onL1Change, onOpenCanvas }) {
  const [graph, setGraph] = useState({ elements: [], relations: [] })
  const [l1Id, setL1Id] = useState(requestedL1Id || '')
  const [plan, setPlan] = useState(null)
  const [section, setSection] = useState('baseline')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [headerOpen, setHeaderOpen] = useState(() => {
    try { return window.localStorage.getItem('sp.dock.l1-header') !== 'collapsed' } catch { return true }
  })

  useEffect(() => {
    try { window.localStorage.setItem('sp.dock.l1-header', headerOpen ? 'open' : 'collapsed') } catch { /* ignore */ }
  }, [headerOpen])

  const initiatives = useMemo(() => graph.elements.filter((element) => element.level === 'L1'), [graph])
  const loadGraph = useCallback(async () => {
    const next = await api.c4Graph(projectId)
    setGraph(next)
    setL1Id((current) => {
      if (requestedL1Id && next.elements.some((item) => item.id === requestedL1Id && item.level === 'L1')) return requestedL1Id
      return current && next.elements.some((item) => item.id === current) ? current : (next.elements.find((item) => item.level === 'L1')?.id || '')
    })
  }, [projectId, requestedL1Id])
  const refresh = useCallback(async () => {
    if (!l1Id) return
    const next = await api.l1Plan(projectId, l1Id)
    setPlan(next)
  }, [projectId, l1Id])

  useEffect(() => { loadGraph().catch(setError).finally(() => setLoading(false)) }, [loadGraph])
  useEffect(() => { if (requestedL1Id) setL1Id(requestedL1Id) }, [requestedL1Id])
  useEffect(() => { if (l1Id) onL1Change?.(l1Id) }, [l1Id, onL1Change])
  useEffect(() => { setPlan(null); if (l1Id) refresh().catch(setError) }, [l1Id, refresh])

  const currency = plan?.settings?.currency_code || 'USD'
  const money = useCallback((value) => {
    try { return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value || 0) }
    catch { return `${currency} ${Math.round(value || 0).toLocaleString()}` }
  }, [currency])

  const changeCurrency = async (next) => {
    try { await api.updateL1Plan(projectId, l1Id, { currency_code: next }); await refresh() } catch (nextError) { setError(nextError) }
  }

  if (loading) return <div className="l1-loading">Loading operating plans…</div>
  if (initiatives.length === 0) return <div className="l1-empty-panel prominent"><Landmark size={38} /><h2>No L1 initiative yet</h2><p>Create an L1 system or initiative on the C4 canvas first. It becomes the anchor for teams, funding, work, and architecture.</p><button className="m3-btn filled" onClick={onOpenCanvas}>Open C4 canvas</button></div>

  return <div className="l1-planning">
    {error && <div className="m3-banner error"><CircleAlert size={18} /><span>{String(error.message || error)}</span><button className="m3-btn text small" onClick={() => setError(null)}>Dismiss</button></div>}
    <header className={`l1-plan-hero${headerOpen ? '' : ' collapsed'}`}>
      <div className="l1-plan-identity">
        <span className="l1-hero-icon"><Landmark size={22} /></span>
        <div><span className="l1-eyebrow">L1 operating plan</span><select value={l1Id} onChange={(event) => setL1Id(event.target.value)} aria-label="Select L1 initiative">{initiatives.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{headerOpen && <p>{plan?.element.description || 'Align organization, investment, delivery, and technology around this initiative.'}</p>}</div>
      </div>
      <div className="l1-plan-tools">
        <label><span>Reporting currency</span><select value={currency} onChange={(event) => changeCurrency(event.target.value)}>{CURRENCIES.map((item) => <option key={item}>{item}</option>)}</select></label>
        <button className="m3-icon-btn" onClick={() => refresh().catch(setError)} aria-label="Refresh plan"><RefreshCw size={17} /></button>
        <button className="m3-icon-btn" onClick={() => setHeaderOpen((open) => !open)} aria-label={headerOpen ? 'Collapse plan header' : 'Expand plan header'} title={headerOpen ? 'Collapse header' : 'Expand header'}>{headerOpen ? <PanelTopClose size={17} /> : <PanelTopOpen size={17} />}</button>
      </div>
    </header>

    {plan && <>
      {headerOpen && <div className="l1-metrics">
        <article><span className="l1-metric-icon teams"><UsersRound size={18} /></span><div><strong>{plan.metrics.squads}</strong><span>Squads · {plan.metrics.people} people</span></div></article>
        <article><span className="l1-metric-icon capacity"><Landmark size={18} /></span><div><strong>{plan.metrics.allocated_fte}</strong><span>Allocated FTE</span></div></article>
        <article><span className="l1-metric-icon runrate"><WalletCards size={18} /></span><div><strong>{money(plan.metrics.monthly_run_rate)}</strong><span>Monthly team run-rate</span></div></article>
        <article><span className="l1-metric-icon budget"><CalendarRange size={18} /></span><div><strong>{money(plan.metrics.planned_cost)}</strong><span>Approved work budget</span></div></article>
        <article className={plan.metrics.cost_variance < 0 ? 'negative' : ''}><span className="l1-metric-icon variance"><CircleAlert size={18} /></span><div><strong>{money(plan.metrics.cost_variance)}</strong><span>Budget remaining · {plan.metrics.at_risk_work} at risk</span></div></article>
      </div>}

      <nav className="l1-section-tabs" aria-label="L1 planning sections">
        {SECTIONS.map(({ id, label, icon: Icon }) => <button key={id} className={section === id ? 'active' : ''} onClick={() => setSection(id)}><Icon size={17} />{label}</button>)}
      </nav>
      <div className="l1-section-surface">
        {section === 'baseline' && <Suspense fallback={<div className="l1-loading">Loading L1 baseline…</div>}><L1Architecture projectId={projectId} l1Id={l1Id} setError={setError} /></Suspense>}
        {section === 'requirements' && <Suspense fallback={<div className="l1-loading">Loading requirements workspace…</div>}><RequirementsPlanning projectId={projectId} l1Id={l1Id} setError={setError} /></Suspense>}
        {section === 'teams' && <TeamPlanning projectId={projectId} l1Id={l1Id} plan={plan} refresh={refresh} setError={setError} money={money} />}
        {section === 'work' && <WorkCostPlanning projectId={projectId} l1Id={l1Id} plan={plan} graph={graph} refresh={refresh} setError={setError} money={money} />}
        {section === 'architecture' && <Suspense fallback={<div className="l1-loading">Loading diagram studio…</div>}><ArchitecturePlanning projectId={projectId} l1Id={l1Id} plan={plan} refresh={refresh} setError={setError} /></Suspense>}
      </div>
    </>}
  </div>
}
