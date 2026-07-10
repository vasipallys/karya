import { applyNodeChanges, Background, Controls, Handle, MarkerType, Position, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ChevronRight, Plus, RefreshCw, Sparkles, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import DockablePanel from '../components/DockablePanel'
import EstimateDialog from './EstimateDialog'
import InspectorPanel from './InspectorPanel'

const KIND_LABEL = { L1: 'system', L2: 'container', L3: 'component', L4: 'code' }
const NEXT_LEVEL = { root: 'L1', L1: 'L2', L2: 'L3', L3: 'L4' }

function C4Node({ data }) {
  const element = data.element
  return <div className={`c4-node level-${element.level} ${element.status === 'proposed' ? 'proposed' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <header>
      <span className="c4-level">{element.level} · {element.kind || KIND_LABEL[element.level]}</span>
      {data.points != null && <span className="c4-points">{data.points}</span>}
    </header>
    <strong>{element.name}</strong>
    {element.tech && <div className="c4-tech">{element.tech}</div>}
    {element.level === 'L1' && <div className="c4-tech">click for summary{data.childCount > 0 ? ' · double-click to open' : ''}</div>}
    {element.level !== 'L1' && data.childCount > 0 && <div className="c4-tech">{data.childCount} inside · double-click to open</div>}
    <Handle type="source" position={Position.Right} />
  </div>
}

const nodeTypes = { c4: C4Node }

export default function C4Canvas({ projectId, config, onOpenL1Plan }) {
  const [graph, setGraph] = useState({ elements: [], relations: [] })
  const [drill, setDrill] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState({ name: '', description: '', tech: '' })
  const [error, setError] = useState(null)
  const [nodes, setNodes] = useState([])
  const [estimating, setEstimating] = useState(null)
  const [scaffold, setScaffold] = useState(null) // { description, loading, result }
  const resultsCache = useRef(new Map())

  const refresh = useCallback(() => api.c4Graph(projectId).then(setGraph).catch(setError), [projectId])
  useEffect(() => { refresh() }, [refresh])

  const runScaffold = async () => {
    if (!scaffold.description.trim()) return
    setScaffold({ ...scaffold, loading: true })
    try {
      const result = await api.aiScaffold(projectId, scaffold.description)
      setScaffold((current) => ({ ...current, loading: false, result }))
    } catch (err) { setError(err); setScaffold((current) => ({ ...current, loading: false })) }
  }

  const applyScaffold = async () => {
    try {
      await api.applyScaffold(projectId, scaffold.result)
      setScaffold(null); await refresh()
    } catch (err) { setError(err) }
  }

  const parentId = drill.length ? drill[drill.length - 1].id : null
  const visible = useMemo(() => graph.elements.filter((element) => element.parent_id === parentId), [graph, parentId])
  const childCounts = useMemo(() => {
    const counts = {}
    for (const element of graph.elements) if (element.parent_id) counts[element.parent_id] = (counts[element.parent_id] || 0) + 1
    return counts
  }, [graph])

  useEffect(() => {
    setNodes((current) => visible.map((element, index) => {
      const artifact = (element.artifacts || []).find((item) => item.points != null)
      const existing = current.find((node) => node.id === element.id)
      return {
        id: element.id,
        type: 'c4',
        position: existing?.position || {
          x: element.pos_x ?? 40 + (index % 3) * 270,
          y: element.pos_y ?? 40 + Math.floor(index / 3) * 150,
        },
        measured: existing?.measured,
        data: { element, points: artifact?.points ?? null, childCount: childCounts[element.id] || 0 },
      }
    }))
  }, [visible, childCounts])

  const visibleIds = useMemo(() => new Set(visible.map((element) => element.id)), [visible])
  const edges = useMemo(() => graph.relations
    .filter((relation) => visibleIds.has(relation.source_id) && visibleIds.has(relation.target_id))
    .map((relation) => ({
      id: relation.id,
      source: relation.source_id,
      target: relation.target_id,
      label: relation.label || undefined,
      animated: relation.kind === 'async',
      style: { strokeDasharray: relation.kind === 'data' ? '5 4' : undefined },
      markerEnd: { type: MarkerType.ArrowClosed },
    })), [graph.relations, visibleIds])

  const onNodesChange = useCallback((changes) => {
    setNodes((current) => applyNodeChanges(changes, current))
  }, [])

  const onNodeDragStop = useCallback((_, node) => {
    api.updateElement(projectId, node.id, { pos_x: node.position.x, pos_y: node.position.y }).catch(setError)
  }, [projectId])

  const onConnect = useCallback((connection) => {
    const label = window.prompt('Relation label (for example "calls", "reads from")', '') ?? ''
    api.createRelation(projectId, { source_id: connection.source, target_id: connection.target, label })
      .then(refresh).catch(setError)
  }, [projectId, refresh])

  const onEdgeClick = useCallback((_, edge) => {
    if (window.confirm(`Delete the relation${edge.label ? ` "${edge.label}"` : ''}?`)) {
      api.deleteRelation(projectId, edge.id).then(refresh).catch(setError)
    }
  }, [projectId, refresh])

  const drillInto = (_, node) => {
    if (node.data.element.level !== 'L4') { setDrill([...drill, node.data.element]); setSelectedId(null); setNodes([]) }
  }

  const addLevel = NEXT_LEVEL[drill.length ? drill[drill.length - 1].level : 'root']
  const addElement = async () => {
    try {
      const created = await api.createElement(projectId, {
        level: addLevel, name: draft.name.trim(), description: draft.description.trim(),
        tech: draft.tech.trim(), parent_id: parentId,
      })
      setAdding(false); setDraft({ name: '', description: '', tech: '' })
      await refresh(); setSelectedId(created.id)
    } catch (err) { setError(err) }
  }

  const selected = graph.elements.find((element) => element.id === selectedId) || null

  return <div>
    {error && <div className="m3-banner error">{String(error.message || error)} <button className="m3-btn text small" onClick={() => setError(null)}>Dismiss</button></div>}
    <div className="m3-canvas-toolbar">
      <nav className="m3-breadcrumb" aria-label="C4 drill path">
        <button onClick={() => { setDrill([]); setSelectedId(null); setNodes([]) }}>System landscape</button>
        {drill.map((element, index) => <span key={element.id} style={{ display: 'inline-flex', alignItems: 'center' }}>
          <ChevronRight size={15} />
          {index === drill.length - 1
            ? <span className="current">{element.name}</span>
            : <button onClick={() => { setDrill(drill.slice(0, index + 1)); setSelectedId(null); setNodes([]) }}>{element.name}</button>}
        </span>)}
      </nav>
      <span style={{ flex: 1 }} />
      {drill.length === 0 && <button className="m3-btn text small" onClick={() => setScaffold({ description: '', loading: false, result: null })}><Sparkles size={15} /> AI scaffold</button>}
      {addLevel && <button className="m3-btn tonal small" onClick={() => setAdding(true)}><Plus size={15} /> Add {KIND_LABEL[addLevel]} ({addLevel})</button>}
      <button className="m3-btn text small" onClick={refresh} aria-label="Refresh"><RefreshCw size={15} /></button>
    </div>

    {scaffold && <div className="m3-dialog-scrim" onMouseDown={() => setScaffold(null)}>
      <section className="m3-dialog wide" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="AI scaffold">
        <header className="l1-dialog-header"><h2><Sparkles size={18} /> AI scaffold a C4 model</h2><button className="m3-icon-btn" onClick={() => setScaffold(null)} aria-label="Close"><X size={19} /></button></header>
        <div>
          {!scaffold.result && <>
            <label className="m3-field"><span>Describe the system</span>
              <textarea autoFocus rows={5} value={scaffold.description} placeholder="e.g. A retail banking platform with a customer web app, an accounts service, a payments service, and a ledger database…"
                onChange={(event) => setScaffold({ ...scaffold, description: event.target.value })} /></label>
            <p className="ai-hint">The agent proposes an L1 system with L2 containers, L3 components, and their relations. Nothing is created until you apply — everything lands as <strong>proposed</strong> so you can review it.</p>
          </>}
          {scaffold.result && <div className="ai-scaffold-preview">
            <div className="m3-banner info">{scaffold.result.summary}</div>
            <ul>{scaffold.result.elements.map((el) => <li key={el.ref}><span className={`res-pill`}>{el.level}</span> <strong>{el.name}</strong>{el.tech ? ` · ${el.tech}` : ''}</li>)}</ul>
            <p className="ai-hint">{scaffold.result.elements.length} elements · {scaffold.result.relations.length} relations will be added as proposed.</p>
          </div>}
        </div>
        <footer className="m3-dialog-actions">
          <button className="m3-btn text" onClick={() => setScaffold(null)}>Cancel</button>
          {!scaffold.result
            ? <button className="m3-btn filled" onClick={runScaffold} disabled={scaffold.loading || !scaffold.description.trim()}>{scaffold.loading ? 'Generating…' : 'Generate'}</button>
            : <button className="m3-btn filled" onClick={applyScaffold}>Add {scaffold.result.elements.length} elements</button>}
        </footer>
      </section>
    </div>}
    <div className="m3-workspace">
      <div className="m3-canvas-wrap">
        <ReactFlow
          nodes={nodes} edges={edges} nodeTypes={nodeTypes}
          onNodesChange={onNodesChange} onNodeDragStop={onNodeDragStop}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onNodeDoubleClick={drillInto}
          onConnect={onConnect} onEdgeClick={onEdgeClick}
          fitView proOptions={{ hideAttribution: true }}>
          <Background gap={18} />
          <Controls showInteractive={false} />
        </ReactFlow>
        {visible.length === 0 && <div className="m3-empty" style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
          <div><h2>{drill.length ? 'Nothing inside yet' : 'Empty landscape'}</h2>
            <p>Use “Add {KIND_LABEL[addLevel]}” to place the first {addLevel} element{drill.length === 0 ? ', or seed from a repo scan in Overview' : ''}.</p></div>
        </div>}
      </div>
      <DockablePanel id="c4-inspector" side="right" title="Inspector" defaultWidth={400} minWidth={300} maxWidth={640}>
        <InspectorPanel projectId={projectId} element={selected} config={config}
          hasCachedResult={selected ? resultsCache.current.has(selected.id) : false}
          onEstimate={(element, autoStart) => setEstimating({ element, autoStart })}
          onOpenL1Plan={onOpenL1Plan}
          onChanged={refresh} onDeleted={() => { setSelectedId(null); refresh() }} />
      </DockablePanel>
    </div>
    {estimating && <EstimateDialog projectId={projectId} element={estimating.element}
      autoStart={estimating.autoStart}
      cachedResult={estimating.autoStart ? null : resultsCache.current.get(estimating.element.id)}
      onResult={(result) => resultsCache.current.set(estimating.element.id, result)}
      onChanged={refresh} onClose={() => setEstimating(null)} />}
    {adding && <div className="m3-dialog-scrim" onClick={() => setAdding(false)}>
      <div className="m3-dialog" onClick={(event) => event.stopPropagation()} role="dialog" aria-label={`Add ${addLevel} element`}>
        <h2>Add {KIND_LABEL[addLevel]} ({addLevel})</h2>
        <label className="m3-field"><span>Name</span><input autoFocus value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label className="m3-field"><span>Description</span><textarea rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
        <label className="m3-field"><span>Tech (optional)</span><input value={draft.tech} onChange={(event) => setDraft({ ...draft, tech: event.target.value })} placeholder="React 19, Spring Boot 3, PostgreSQL…" /></label>
        <div className="m3-dialog-actions">
          <button className="m3-btn text" onClick={() => setAdding(false)}>Cancel</button>
          <button className="m3-btn filled" onClick={addElement} disabled={!draft.name.trim()}>Add</button>
        </div>
      </div>
    </div>}
  </div>
}
