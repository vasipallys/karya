import { ArrowRight, Blocks, Bug, CalendarRange, ExternalLink, Eye, Save, Sparkles, Trash2, UsersRound, WalletCards } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

const ARTIFACT_LABEL = { initiative: 'Theme / initiative', epic: 'Epic', story: 'Story / feature', task: 'Task / sub-task', bug: 'Bug', tech_debt: 'Tech debt', arch_flow: 'Architecture flow' }
const LEVEL_ARTIFACT = { L1: 'initiative', L2: 'epic', L3: 'story', L4: 'task' }

export default function InspectorPanel({ projectId, element, config, hasCachedResult, onEstimate, onOpenL1Plan, onChanged, onDeleted }) {
  const [description, setDescription] = useState('')
  const [error, setError] = useState(null)
  const [l1Plan, setL1Plan] = useState(null)
  const [l1Loading, setL1Loading] = useState(false)
  const [decompose, setDecompose] = useState(null) // { loading, result, selected:Set }

  useEffect(() => {
    setDescription(element?.description || '')
    setError(null)
    setDecompose(null)
  }, [element?.id])

  const runDecompose = async () => {
    setDecompose({ loading: true })
    try {
      const result = await api.aiDecompose(projectId, element.id)
      setDecompose({ result, selected: new Set(result.stories.map((_, index) => index)) })
    } catch (nextError) { setError(nextError); setDecompose(null) }
  }

  const applyDecompose = async () => {
    const chosen = decompose.result.stories.filter((_, index) => decompose.selected.has(index))
    if (chosen.length === 0) { setDecompose(null); return }
    try { await api.applyDecompose(projectId, element.id, chosen); setDecompose(null); onChanged() }
    catch (nextError) { setError(nextError) }
  }

  const toggleStory = (index) => setDecompose((current) => {
    const selected = new Set(current.selected)
    selected.has(index) ? selected.delete(index) : selected.add(index)
    return { ...current, selected }
  })

  useEffect(() => {
    let active = true
    setL1Plan(null)
    if (element?.level !== 'L1') {
      setL1Loading(false)
      return () => { active = false }
    }
    setL1Loading(true)
    api.l1Plan(projectId, element.id)
      .then((plan) => { if (active) setL1Plan(plan) })
      .catch((nextError) => { if (active) setError(nextError) })
      .finally(() => { if (active) setL1Loading(false) })
    return () => { active = false }
  }, [projectId, element?.id, element?.level])

  if (!element) {
    return <aside className="m3-inspector"><div className="m3-empty" style={{ padding: '40px 10px' }}>
      <h2>Nothing selected</h2>
      <p>Click a node to inspect it, double-click to drill in,<br />drag from a node edge to another node to draw a relation.</p>
    </div></aside>
  }

  const estimable = element.level === 'L3' || element.level === 'L4'
  const artifacts = element.artifacts || []
  const estimated = artifacts.find((item) => item.points != null)
  const planCurrency = l1Plan?.settings?.currency_code || 'USD'
  const money = (value) => {
    try { return new Intl.NumberFormat(undefined, { style: 'currency', currency: planCurrency, maximumFractionDigits: 0 }).format(value || 0) }
    catch { return `${planCurrency} ${Math.round(value || 0).toLocaleString()}` }
  }

  const saveDescription = () => api.updateElement(projectId, element.id, { description }).then(onChanged).catch(setError)
  const acceptProposed = () => api.updateElement(projectId, element.id, { status: 'active' }).then(onChanged).catch(setError)
  const remove = () => {
    if (!window.confirm(`Delete "${element.name}" and everything nested under it?`)) return
    api.deleteElement(projectId, element.id).then(onDeleted).catch(setError)
  }
  const tagBug = () => api.tagElement(projectId, element.id, { artifact_type: 'bug' }).then(onChanged).catch(setError)
  const createJira = () => {
    if (!window.confirm(`Create a Jira issue for "${element.name}"? This writes to Jira.`)) return
    api.createArtifact(projectId, element.id, { confirm: true })
      .then((response) => { window.alert(`Created ${response.issue_key}`); onChanged() })
      .catch(setError)
  }
  const linkJira = () => {
    const key = window.prompt('Existing Jira issue key to link (for example PAY-42)')
    if (key) api.createArtifact(projectId, element.id, { link_existing_key: key.trim() }).then(onChanged).catch(setError)
  }

  return <aside className="m3-inspector">
    <div className="m3-inspector-header">
      <div>
        <span className={`m3-chip level-${element.level}`}>{element.level} · {ARTIFACT_LABEL[LEVEL_ARTIFACT[element.level]]}</span>
        <h2 style={{ marginTop: 8 }}>{element.name}</h2>
      </div>
      <button className="m3-icon-btn" onClick={remove} aria-label="Delete element"><Trash2 size={17} /></button>
    </div>
    {error && <div className="m3-banner error">{String(error.message || error)}</div>}
    {element.status === 'proposed' && <div className="m3-banner info">Proposed by a scan, import, or estimation — review and accept it.
      <button className="m3-btn tonal small" onClick={acceptProposed}>Accept</button></div>}

    {estimable && <div className="m3-estimate-summary">
      <div>
        <span className="m3-estimate-summary-label">Story points</span>
        <b>{estimated?.points ?? '—'}</b>
        {estimated?.estimated_at && <small>{new Date(estimated.estimated_at).toLocaleString()}</small>}
      </div>
      <div className="m3-estimate-summary-actions">
        {estimated && hasCachedResult && <button className="m3-btn tonal small" onClick={() => onEstimate(element, false)}>
          <Eye size={14} /> View reasoning</button>}
        <button className="m3-btn filled small" onClick={() => onEstimate(element, !estimated)}>
          <Sparkles size={14} /> {estimated ? 'Re-estimate' : 'Estimate'}</button>
      </div>
    </div>}
    {!estimable && <p style={{ color: 'var(--m3-on-surface-variant)', fontSize: 13 }}>
      {element.level} elements are not estimated directly — points roll up from the L3 stories inside (see the Roll-up tab).</p>}

    {element.level === 'L1' && <section className="l1-inspector-summary" aria-label="L1 operating plan summary">
      <header><div><span>Operating plan</span><strong>Delivery & investment</strong></div><span className="m3-chip">{planCurrency}</span></header>
      {l1Loading
        ? <div className="l1-inspector-loading">Loading plan summary…</div>
        : <><div className="l1-inspector-metrics">
          <div><UsersRound size={16} /><span><strong>{l1Plan?.metrics.squads || 0}</strong> squads · {l1Plan?.metrics.people || 0} people</span></div>
          <div><WalletCards size={16} /><span><strong>{money(l1Plan?.metrics.monthly_run_rate)}</strong> monthly run-rate</span></div>
          <div><CalendarRange size={16} /><span><strong>{money(l1Plan?.metrics.planned_cost)}</strong> approved budget</span></div>
          <div><Blocks size={16} /><span><strong>{l1Plan?.diagrams.length || 0}</strong> technical views</span></div>
        </div>
        <p>{l1Plan?.work_items.length || 0} work packages · {l1Plan?.metrics.at_risk_work || 0} at risk · {l1Plan?.metrics.allocated_fte || 0} allocated FTE</p></>}
      <button className="m3-btn filled l1-more-details" onClick={() => onOpenL1Plan?.(element.id)}>
        More details <ArrowRight size={16} />
      </button>
    </section>}

    <dl className="m3-kv">
      {element.tech && <><dt>Tech</dt><dd>{element.tech}</dd></>}
      {element.code_path && <><dt>Code path</dt><dd className="mono">{element.code_path}</dd></>}
      <dt>Status</dt><dd>{element.status}</dd>
      {artifacts.map((artifact) => <span key={artifact.id} style={{ display: 'contents' }}>
        <dt>{ARTIFACT_LABEL[artifact.artifact_type] || artifact.artifact_type}</dt>
        <dd>{artifact.points != null ? `${artifact.points} pts` : '—'}{artifact.jira_issue_key ? ` · ${artifact.jira_issue_key}` : ''}</dd>
      </span>)}
    </dl>
    <label className="m3-field"><span>Description (estimation evidence)</span>
      <textarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
    <div className="m3-inspector-actions">
      <button className="m3-btn text small" onClick={saveDescription} disabled={description === element.description}><Save size={14} /> Save</button>
      {estimable && <button className="m3-btn text small" onClick={tagBug}><Bug size={14} /> Tag bug</button>}
      <button className="m3-btn text small" onClick={linkJira}><ExternalLink size={14} /> Link Jira</button>
      {config?.jira_write_enabled && <button className="m3-btn text small" onClick={createJira}><ExternalLink size={14} /> Create in Jira</button>}
      {element.level !== 'L4' && <button className="m3-btn text small" onClick={runDecompose} disabled={decompose?.loading}>
        <Sparkles size={14} /> {decompose?.loading ? 'Thinking…' : 'AI: suggest stories'}</button>}
    </div>

    {decompose?.result && <div className="ai-decompose">
      <div className="ai-decompose-head"><Sparkles size={14} /> {decompose.result.summary || 'Proposed child stories'}</div>
      {decompose.result.stories.map((story, index) => (
        <label key={index} className={`ai-decompose-row ${decompose.selected.has(index) ? 'on' : ''}`}>
          <input type="checkbox" checked={decompose.selected.has(index)} onChange={() => toggleStory(index)} />
          <span><strong>{story.name}</strong>{story.rationale ? <small>{story.rationale}</small> : null}</span>
        </label>
      ))}
      <div className="ai-decompose-actions">
        <button className="m3-btn text small" onClick={() => setDecompose(null)}>Dismiss</button>
        <button className="m3-btn filled small" onClick={applyDecompose} disabled={decompose.selected.size === 0}>Add {decompose.selected.size} as proposed</button>
      </div>
    </div>}

    {error && <div className="m3-banner error" style={{ marginTop: 10 }}>{String(error.message || error)}</div>}
  </aside>
}
