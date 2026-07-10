import { ChevronDown, ChevronRight, Play, RefreshCw } from 'lucide-react'
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

function collectUnestimated(nodes, output = []) {
  for (const node of nodes) {
    if (node.element.level === 'L3' && node.element.status !== 'proposed' && node.artifact?.points == null) output.push(node.element)
    collectUnestimated(node.children, output)
  }
  return output
}

function Row({ node, depth, collapsed, toggle }) {
  const element = node.element
  const hasChildren = node.children.length > 0
  const isCollapsed = collapsed.has(element.id)
  const points = element.level === 'L3' || element.level === 'L4'
    ? node.artifact?.points
    : node.summary.rolled_up_points || null
  return <Fragment>
    <div className="m3-tree-row">
      <div className="m3-tree-name" style={{ paddingLeft: depth * 22 }}>
        {hasChildren
          ? <button className="m3-btn text small" style={{ padding: 0, height: 20, width: 20 }} onClick={() => toggle(element.id)} aria-label={isCollapsed ? 'Expand' : 'Collapse'}>
            {isCollapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} />}</button>
          : <span style={{ width: 20 }} />}
        <span className={`m3-chip level-${element.level}`}>{element.level}</span>
        <span className="label" style={element.status === 'proposed' ? { opacity: .6, fontStyle: 'italic' } : undefined}>{element.name}</span>
      </div>
      <span className="m3-tree-points">{points != null ? points : '—'}</span>
      <span className="m3-tree-extra" style={{ fontSize: 12, color: 'var(--m3-on-surface-variant)' }}>
        {element.level !== 'L3' && element.level !== 'L4' ? `${node.summary.estimated_stories}/${node.summary.estimated_stories + node.summary.unestimated_stories} stories` : node.artifact?.jira_issue_key || ''}
      </span>
      <span className="m3-tree-flags">
        {node.summary.spikes > 0 && <span className="m3-chip warn">spike</span>}
        {node.summary.pending_splits > 0 && <span className="m3-chip warn">split pending</span>}
        {element.status === 'proposed' && <span className="m3-chip">proposed</span>}
      </span>
    </div>
    {!isCollapsed && node.children.map((child) => <Row key={child.element.id} node={child} depth={depth + 1} collapsed={collapsed} toggle={toggle} />)}
  </Fragment>
}

export default function RollupDashboard({ projectId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [collapsed, setCollapsed] = useState(new Set())
  const [progress, setProgress] = useState(null)
  const stop = useRef(false)

  const refresh = useCallback(() => api.rollup(projectId).then(setData).catch(setError), [projectId])
  useEffect(() => { refresh(); return () => { stop.current = true } }, [refresh])

  const toggle = (id) => setCollapsed((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  const estimateAll = async () => {
    const pending = collectUnestimated(data.tree)
    stop.current = false
    for (let index = 0; index < pending.length; index += 1) {
      if (stop.current) break
      setProgress({ index: index + 1, total: pending.length, title: pending[index].name })
      try {
        await api.estimateElement(projectId, pending[index].id, {}, () => {})
      } catch (err) { setError(err); break }
      await refresh()
    }
    setProgress(null)
    refresh()
  }

  if (error) return <div className="m3-banner error">{String(error.message || error)}</div>
  if (!data) return <p>Loading roll-up…</p>
  const unestimated = collectUnestimated(data.tree).length

  return <div>
    <div className="m3-summary-row">
      <div className="m3-stat"><b>{data.totals.rolled_up_points}</b><span>rolled-up points</span></div>
      <div className="m3-stat"><b>{data.totals.estimated_stories}</b><span>stories estimated</span></div>
      <div className="m3-stat"><b>{data.totals.unestimated_stories}</b><span>stories pending</span></div>
      <div className="m3-stat"><b>{data.totals.spikes}</b><span>spikes recommended</span></div>
      <div className="m3-stat"><b>{data.totals.pending_splits}</b><span>splits pending</span></div>
      <span style={{ flex: 1 }} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {progress
          ? <><span className="m3-chip filled">Estimating {progress.index}/{progress.total}: {progress.title}</span>
            <button className="m3-btn outlined small" onClick={() => { stop.current = true }}>Stop</button></>
          : <button className="m3-btn filled" onClick={estimateAll} disabled={unestimated === 0}>
            <Play size={15} /> Estimate all pending ({unestimated})</button>}
        <button className="m3-btn text small" onClick={refresh} aria-label="Refresh"><RefreshCw size={15} /></button>
      </div>
    </div>
    <div className="m3-tree">
      <div className="m3-tree-row header"><span>Initiative → epic → story → task</span><span>Points</span><span>Coverage / Jira</span><span>Flags</span></div>
      {data.tree.length === 0 && <div className="m3-tree-row"><span style={{ color: 'var(--m3-on-surface-variant)' }}>The C4 model is empty — add elements in the canvas first.</span></div>}
      {data.tree.map((node) => <Row key={node.element.id} node={node} depth={0} collapsed={collapsed} toggle={toggle} />)}
    </div>
    <p style={{ color: 'var(--m3-on-surface-variant)', fontSize: 12, marginTop: 10 }}>
      Epic and initiative points are deterministic sums of the justified story estimates beneath them — proposed (unaccepted) stories are excluded.</p>
  </div>
}
