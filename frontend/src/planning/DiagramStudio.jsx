import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Blocks,
  FileCode2,
  Info,
  MessageSquare,
  MousePointerSquareDashed,
  Plus,
  Save,
  Send,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import mermaid from 'mermaid'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import MermaidView from '../components/MermaidView'
import { DIAGRAM_TYPE_GROUPS, DIAGRAM_TYPES, getDiagramType } from './diagramCatalog'
import { DIRECTIONS, EDGE_TYPES, modelToMermaid, NODE_SHAPES, nextNodeId, parseFlowchart } from './mermaidModel'

mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'base', themeVariables: { primaryColor: '#d3e3fd', primaryTextColor: '#1f1f1f', primaryBorderColor: '#0b57d0', lineColor: '#5f6368', secondaryColor: '#e6f4ea', tertiaryColor: '#fef7e0', fontFamily: 'Roboto, sans-serif' } })

const EDGE_STROKE = { arrow: '#5f6368', open: '#5f6368', dotted: '#5f6368', thick: '#0b57d0' }

function nodeHasMeta(meta) {
  if (!meta) return false
  return Boolean(
    (meta.explanation || '').trim() ||
    (meta.properties || []).length ||
    (meta.links || []).length ||
    (meta.documents || []).length,
  )
}

function normalizeMetadata(raw) {
  const source = raw && typeof raw === 'object' ? raw : {}
  return { nodes: source.nodes && typeof source.nodes === 'object' ? source.nodes : {}, positions: source.positions && typeof source.positions === 'object' ? source.positions : {} }
}

// Deterministic layered layout for nodes that have no persisted position yet.
function autoLayout(model) {
  const indegree = new Map(model.nodes.map((node) => [node.id, 0]))
  const adjacency = new Map(model.nodes.map((node) => [node.id, []]))
  for (const edge of model.edges) {
    if (indegree.has(edge.target)) indegree.set(edge.target, indegree.get(edge.target) + 1)
    if (adjacency.has(edge.source)) adjacency.get(edge.source).push(edge.target)
  }
  const depth = new Map()
  const queue = model.nodes.filter((node) => (indegree.get(node.id) || 0) === 0).map((node) => node.id)
  queue.forEach((id) => depth.set(id, 0))
  const seen = new Set(queue)
  for (let head = 0; head < queue.length; head += 1) {
    const id = queue[head]
    const here = depth.get(id) || 0
    for (const target of adjacency.get(id) || []) {
      if (!depth.has(target) || depth.get(target) < here + 1) depth.set(target, here + 1)
      if (!seen.has(target)) { seen.add(target); queue.push(target) }
    }
  }
  model.nodes.forEach((node) => { if (!depth.has(node.id)) depth.set(node.id, 0) })
  const columns = new Map()
  model.nodes.forEach((node) => {
    const level = depth.get(node.id)
    if (!columns.has(level)) columns.set(level, [])
    columns.get(level).push(node.id)
  })
  const horizontal = model.direction === 'LR' || model.direction === 'RL'
  const positions = {}
  columns.forEach((ids, level) => {
    ids.forEach((id, index) => {
      positions[id] = horizontal ? { x: level * 250, y: index * 130 } : { x: index * 220, y: level * 150 }
    })
  })
  return positions
}

function StudioNode({ data }) {
  return (
    <div className={`ds-node shape-${data.shape}`} title={data.label}>
      <Handle type="target" position={Position.Left} />
      <span className="ds-node-label">{data.label}</span>
      {data.hasMeta && <span className="ds-node-badge" aria-label="Has details"><Info size={11} /></span>}
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { studio: StudioNode }

function DiagramTypeOptions() {
  return DIAGRAM_TYPE_GROUPS.map((group) => (
    <optgroup key={group.label} label={group.label}>
      {group.types.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
    </optgroup>
  ))
}

function MetaList({ title, addLabel, items, fields, onAdd, onChange, onRemove }) {
  return (
    <div className="ds-meta-list">
      <div className="ds-meta-list-head"><span>{title}</span><button type="button" className="m3-btn text small" onClick={onAdd}><Plus size={13} /> {addLabel}</button></div>
      {items.length === 0 && <p className="ds-meta-empty">None yet.</p>}
      {items.map((item, index) => (
        <div key={index} className="ds-meta-row">
          {fields.map((field) => (
            <input key={field.key} value={item[field.key] || ''} placeholder={field.placeholder}
              onChange={(event) => onChange(index, field.key, event.target.value)} />
          ))}
          <button type="button" className="m3-icon-btn small" onClick={() => onRemove(index)} aria-label={`Remove ${title}`}><Trash2 size={14} /></button>
        </div>
      ))}
    </div>
  )
}

export default function DiagramStudio({ diagram, onClose, onSave, onAssist, saving }) {
  const [draft, setDraft] = useState({ title: diagram.title, diagram_type: diagram.diagram_type, mermaid_source: diagram.mermaid_source })
  const [metadata, setMetadata] = useState(() => normalizeMetadata(diagram.metadata))
  const [initialModel] = useState(() => parseFlowchart(diagram.mermaid_source))
  const [model, setModel] = useState(initialModel)
  const [mode, setMode] = useState(initialModel.supported ? 'visual' : 'text')
  const [connector, setConnector] = useState('arrow')
  const [newNodeLabel, setNewNodeLabel] = useState('New node')
  const [newNodeShape, setNewNodeShape] = useState('rect')
  const [connectTargetId, setConnectTargetId] = useState('')
  const [selection, setSelection] = useState(() => (
    initialModel.supported && initialModel.nodes[0] ? { kind: 'node', id: initialModel.nodes[0].id } : null
  )) // { kind:'node'|'edge', id }
  const [rfNodes, setRfNodes] = useState([])
  const [rfEdges, setRfEdges] = useState([])
  const [previewError, setPreviewError] = useState(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [chatError, setChatError] = useState(null)
  const textDirty = useRef(false)
  const modelRef = useRef(model)
  useEffect(() => { modelRef.current = model }, [model])

  // Escape closes the assistant first, then the studio — a guaranteed way out
  // regardless of how the toolbar wraps at smaller widths.
  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== 'Escape') return
      if (chatOpen) setChatOpen(false)
      else onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [chatOpen, onClose])

  const dirty = draft.title !== diagram.title
    || draft.diagram_type !== diagram.diagram_type
    || draft.mermaid_source !== diagram.mermaid_source
    || JSON.stringify(normalizeMetadata(diagram.metadata)) !== JSON.stringify(metadata)

  // Visual edits are model-first: update the model and regenerate the text.
  const applyModel = useCallback((updater) => {
    const next = typeof updater === 'function' ? updater(modelRef.current) : updater
    modelRef.current = next
    setModel(next)
    setDraft((prevDraft) => ({ ...prevDraft, mermaid_source: modelToMermaid(next) }))
    textDirty.current = false
  }, [])

  // Text-first edits (AI assistant, imports): parse the source into the model.
  const applySource = useCallback((source) => {
    const parsed = parseFlowchart(source)
    modelRef.current = parsed
    setModel(parsed)
    setDraft((prevDraft) => ({ ...prevDraft, mermaid_source: source }))
    textDirty.current = false
  }, [])

  const sendChat = async () => {
    const prompt = chatInput.trim()
    if (!prompt || chatBusy || !onAssist) return
    const history = messages.slice(-8)
    setMessages((current) => [...current, { role: 'user', content: prompt }])
    setChatInput('')
    setChatBusy(true)
    setChatError(null)
    try {
      const source = textDirty.current || !modelRef.current.supported ? draft.mermaid_source : modelToMermaid(modelRef.current)
      const reply = await onAssist({ prompt, current_source: source, diagram_type: draft.diagram_type, history })
      if (reply?.mermaid) applySource(reply.mermaid)
      setMessages((current) => [...current, { role: 'assistant', content: reply?.message || 'Updated the diagram.' }])
    } catch (error) {
      setChatError(error)
      setMessages((current) => [...current, { role: 'assistant', content: `⚠️ ${String(error.message || error)}` }])
    } finally {
      setChatBusy(false)
    }
  }

  // Rebuild the React Flow graph whenever the model's structure (not positions) changes.
  const structureKey = useMemo(() => JSON.stringify({
    d: model.direction,
    n: model.nodes.map((node) => [node.id, node.label, node.shape]),
    e: model.edges.map((edge) => [edge.id, edge.source, edge.target, edge.type, edge.label]),
    m: Object.keys(metadata.nodes).filter((id) => nodeHasMeta(metadata.nodes[id])),
    s: selection ? `${selection.kind}:${selection.id}` : '',
  }), [model, metadata.nodes, selection])

  useEffect(() => {
    if (!model.supported) { setRfNodes([]); setRfEdges([]); return }
    const layout = autoLayout(model)
    setRfNodes(model.nodes.map((node) => ({
      id: node.id,
      type: 'studio',
      selected: selection?.kind === 'node' && selection.id === node.id,
      position: metadata.positions[node.id] || layout[node.id] || { x: 0, y: 0 },
      data: { label: node.label, shape: node.shape, hasMeta: nodeHasMeta(metadata.nodes[node.id]) },
    })))
    setRfEdges(model.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label || undefined,
      animated: edge.type === 'dotted',
      style: { stroke: EDGE_STROKE[edge.type] || '#5f6368', strokeWidth: edge.type === 'thick' ? 2.4 : 1.4, strokeDasharray: edge.type === 'dotted' ? '5 4' : undefined },
      markerEnd: edge.type === 'open' ? undefined : { type: MarkerType.ArrowClosed, color: EDGE_STROKE[edge.type] || '#5f6368' },
    })))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureKey])

  const onNodesChange = useCallback((changes) => setRfNodes((current) => applyNodeChanges(changes, current)), [])
  const onEdgesChange = useCallback((changes) => setRfEdges((current) => applyEdgeChanges(changes, current)), [])

  const persistPosition = useCallback((_, node) => {
    setMetadata((current) => ({ ...current, positions: { ...current.positions, [node.id]: { x: Math.round(node.position.x), y: Math.round(node.position.y) } } }))
  }, [])

  const onConnect = useCallback((connection) => {
    if (!connection.source || !connection.target) return
    applyModel((current) => {
      const id = `e${Date.now().toString(36)}`
      return { ...current, edges: [...current.edges, { id, source: connection.source, target: connection.target, type: connector, label: '' }] }
    })
  }, [applyModel, connector])

  const addNode = useCallback(() => {
    const id = nextNodeId(model)
    const sourceId = selection?.kind === 'node' ? selection.id : null
    const sourcePosition = sourceId ? rfNodes.find((node) => node.id === sourceId)?.position : null
    const position = sourcePosition ? { x: Math.round(sourcePosition.x + 250), y: Math.round(sourcePosition.y) } : { x: 60, y: 60 }
    const label = newNodeLabel.trim() || 'New node'
    const edgeId = `e${Date.now().toString(36)}`
    applyModel((current) => ({
      ...current,
      nodes: [...current.nodes, { id, label, shape: newNodeShape }],
      edges: sourceId ? [...current.edges, { id: edgeId, source: sourceId, target: id, type: connector, label: '' }] : current.edges,
    }))
    setMetadata((current) => ({ ...current, positions: { ...current.positions, [id]: position } }))
    setSelection({ kind: 'node', id })
  }, [applyModel, connector, model, newNodeLabel, newNodeShape, rfNodes, selection])

  const updateNode = useCallback((id, patch) => {
    applyModel((current) => ({ ...current, nodes: current.nodes.map((node) => (node.id === id ? { ...node, ...patch } : node)) }))
  }, [applyModel])
  const updateEdge = useCallback((id, patch) => {
    applyModel((current) => ({ ...current, edges: current.edges.map((edge) => (edge.id === id ? { ...edge, ...patch } : edge)) }))
  }, [applyModel])
  const removeSelected = useCallback(() => {
    if (!selection) return
    if (selection.kind === 'node') {
      applyModel((current) => ({
        ...current,
        nodes: current.nodes.filter((node) => node.id !== selection.id),
        edges: current.edges.filter((edge) => edge.source !== selection.id && edge.target !== selection.id),
        groups: (current.groups || []).map((group) => ({ ...group, members: group.members.filter((member) => member !== selection.id) })),
      }))
    } else {
      applyModel((current) => ({ ...current, edges: current.edges.filter((edge) => edge.id !== selection.id) }))
    }
    setSelection(null)
  }, [applyModel, selection])

  const setNodeMeta = useCallback((id, patch) => {
    setMetadata((current) => {
      const existing = current.nodes[id] || { explanation: '', properties: [], links: [], documents: [] }
      return { ...current, nodes: { ...current.nodes, [id]: { ...existing, ...patch } } }
    })
  }, [])

  const changeDirection = (direction) => {
    applyModel((current) => ({ ...current, direction }))
    setMetadata((current) => ({ ...current, positions: {} }))
  }
  // Switching type loads that type's starter template so the diagram actually
  // reflects the new type. Untouched diagrams (empty or an unedited template)
  // swap silently; edited ones ask before replacing the body.
  const changeDiagramType = (nextType) => {
    if (nextType === draft.diagram_type) return
    const meta = getDiagramType(nextType)
    const template = (meta?.template || '').trim()
    const currentSource = (draft.mermaid_source || '').trim()
    const untouched = !currentSource || DIAGRAM_TYPES.some((type) => (type.template || '').trim() === currentSource)
    let nextSource = draft.mermaid_source
    if (template && (untouched || window.confirm(`Load the ${meta.label} starter template? This replaces the current diagram body.`))) {
      nextSource = meta.template
    }
    const parsed = parseFlowchart(nextSource)
    modelRef.current = parsed
    setModel(parsed)
    if (nextSource !== draft.mermaid_source) setMetadata({ nodes: {}, positions: {} })
    setSelection(parsed.supported && parsed.nodes[0] ? { kind: 'node', id: parsed.nodes[0].id } : null)
    setDraft((current) => ({ ...current, diagram_type: nextType, mermaid_source: nextSource }))
    textDirty.current = false
    setMode(parsed.supported ? 'visual' : 'text')
  }
  const changeMode = (nextMode) => {
    if (nextMode === 'visual' && textDirty.current) {
      const parsed = parseFlowchart(draft.mermaid_source)
      modelRef.current = parsed
      setModel(parsed)
      textDirty.current = false
    }
    setMode(nextMode)
  }
  const onText = (value) => { setDraft((current) => ({ ...current, mermaid_source: value })); textDirty.current = true }

  const save = () => {
    const source = textDirty.current || !model.supported ? draft.mermaid_source : modelToMermaid(model)
    // Drop annotations/positions for nodes that no longer exist.
    const liveIds = new Set(parseFlowchart(source).nodes.map((node) => node.id))
    const prune = (record) => Object.fromEntries(Object.entries(record).filter(([id]) => liveIds.has(id)))
    const cleanMeta = { nodes: prune(metadata.nodes), positions: prune(metadata.positions) }
    setMetadata(cleanMeta)
    onSave({ title: draft.title.trim() || diagram.title, diagram_type: draft.diagram_type, mermaid_source: source || diagram.mermaid_source, metadata: cleanMeta })
  }

  const selectedNode = selection?.kind === 'node' ? model.nodes.find((node) => node.id === selection.id) : null
  const selectedEdge = selection?.kind === 'edge' ? model.edges.find((edge) => edge.id === selection.id) : null
  const activeConnector = selectedEdge?.type || connector
  const targetOptions = selectedNode ? model.nodes.filter((node) => node.id !== selectedNode.id) : []
  const activeTargetId = targetOptions.some((node) => node.id === connectTargetId) ? connectTargetId : targetOptions[0]?.id || ''
  const nodeMeta = selectedNode ? (metadata.nodes[selectedNode.id] || { explanation: '', properties: [], links: [], documents: [] }) : null
  const changeConnector = (type) => {
    setConnector(type)
    if (selection?.kind === 'edge') updateEdge(selection.id, { type })
  }
  const connectSelectedNode = () => {
    if (!selectedNode || !activeTargetId) return
    const id = `e${Date.now().toString(36)}`
    applyModel((current) => ({ ...current, edges: [...current.edges, { id, source: selectedNode.id, target: activeTargetId, type: connector, label: '' }] }))
    setSelection({ kind: 'edge', id })
  }

  return (
    <div className="ds-scrim" role="dialog" aria-modal="true" aria-label="Diagram studio" onMouseDown={onClose}>
      <div className="ds-modal" onMouseDown={(event) => event.stopPropagation()}>
        <header className="ds-topbar">
          <div className="ds-topbar-main">
            <span className="ds-brand"><Blocks size={18} /> Diagram studio</span>
            <input className="ds-title-input" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} aria-label="Diagram name" />
            <select value={draft.diagram_type} onChange={(event) => changeDiagramType(event.target.value)} aria-label="Diagram type">
              <DiagramTypeOptions />
            </select>
            <div className="ds-mode-toggle">
              <button className={mode === 'visual' ? 'active' : ''} onClick={() => changeMode('visual')}><MousePointerSquareDashed size={14} /> Visual</button>
              <button className={mode === 'text' ? 'active' : ''} onClick={() => changeMode('text')}><FileCode2 size={14} /> Text</button>
            </div>
            <span className="ds-dirty">{dirty ? 'Unsaved' : 'Saved'}</span>
          </div>
          <div className="ds-topbar-actions">
            {onAssist && <button className={`m3-btn small ${chatOpen ? 'filled' : 'tonal'}`} onClick={() => setChatOpen((open) => !open)}><MessageSquare size={14} /> Assistant</button>}
            <button className="m3-btn filled small" onClick={save} disabled={saving || !dirty}><Save size={14} /> Save</button>
            <button className="m3-icon-btn" onClick={onClose} aria-label="Close studio"><X size={18} /></button>
          </div>
        </header>

        {mode === 'visual' && (
          <div className="ds-visual">
            <div className="ds-toolbar">
              <label className="ds-inline-field ds-node-label-field"><span>New node</span>
                <input value={newNodeLabel} onChange={(event) => setNewNodeLabel(event.target.value)} aria-label="New node label" /></label>
              <label className="ds-inline-field"><span>New shape</span>
                <select value={newNodeShape} onChange={(event) => setNewNodeShape(event.target.value)} aria-label="New node shape">{NODE_SHAPES.map((shape) => <option key={shape.id} value={shape.id}>{shape.label}</option>)}</select></label>
              <button className="m3-btn tonal small" onClick={addNode}><Plus size={14} /> {selectedNode ? 'Add linked node' : 'Add node'}</button>
              <label className="ds-inline-field"><span>Direction</span>
                <select value={model.direction} onChange={(event) => changeDirection(event.target.value)}>{DIRECTIONS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
              {selectedNode && <label className="ds-inline-field ds-node-label-field"><span>Selected label</span>
                <input value={selectedNode.label} onChange={(event) => updateNode(selectedNode.id, { label: event.target.value })} aria-label="Selected node label" /></label>}
              {selectedNode && <label className="ds-inline-field"><span>Selected shape</span>
                <select value={selectedNode.shape} onChange={(event) => updateNode(selectedNode.id, { shape: event.target.value })} aria-label="Selected node shape">{NODE_SHAPES.map((shape) => <option key={shape.id} value={shape.id}>{shape.label}</option>)}</select></label>}
              <label className="ds-inline-field"><span>{selectedEdge ? 'Selected connector' : 'New connector'}</span>
                <select value={activeConnector} onChange={(event) => changeConnector(event.target.value)}>{EDGE_TYPES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
                <span className={`ds-connector-preview type-${activeConnector}`} aria-hidden="true" />
              </label>
              {selectedNode && targetOptions.length > 0 && <label className="ds-inline-field"><span>Connect to</span>
                <select value={activeTargetId} onChange={(event) => setConnectTargetId(event.target.value)} aria-label="Connector target">{targetOptions.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label>}
              {selectedNode && targetOptions.length > 0 && <button className="m3-btn outlined small" onClick={connectSelectedNode}>Connect</button>}
              <span className="ds-toolbar-hint">Drag between node edges to connect</span>
            </div>
            <div className="ds-canvas-row">
              <div className="ds-canvas">
                {model.supported ? (
                  <ReactFlow
                    nodes={rfNodes}
                    edges={rfEdges}
                    nodeTypes={nodeTypes}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onNodeDragStop={persistPosition}
                    onConnect={onConnect}
                    onNodeClick={(_, node) => setSelection({ kind: 'node', id: node.id })}
                    onEdgeClick={(_, edge) => setSelection({ kind: 'edge', id: edge.id })}
                    onPaneClick={() => setSelection(null)}
                    fitView
                    proOptions={{ hideAttribution: true }}
                  >
                    <Background gap={18} />
                    <Controls showInteractive={false} />
                  </ReactFlow>
                ) : (
                  <div className="ds-unsupported">
                    <Blocks size={30} />
                    <h3>Visual editing supports flowcharts</h3>
                    <p>This diagram uses a Mermaid type the visual editor cannot round-trip yet. Switch to <b>Text</b> to edit it safely.</p>
                    <button className="m3-btn tonal small" onClick={() => changeMode('text')}>Open text editor</button>
                  </div>
                )}
              </div>
              <aside className="ds-inspector">
                {selectedNode && (
                  <div className="ds-inspector-body">
                    <div className="ds-inspector-head"><span className="l1-eyebrow">Node</span><button className="m3-icon-btn small danger-ink" onClick={removeSelected} aria-label="Delete node"><Trash2 size={15} /></button></div>
                    <label className="m3-field"><span>Label</span><input value={selectedNode.label} onChange={(event) => updateNode(selectedNode.id, { label: event.target.value })} /></label>
                    <label className="m3-field"><span>Shape</span><select value={selectedNode.shape} onChange={(event) => updateNode(selectedNode.id, { shape: event.target.value })}>{NODE_SHAPES.map((shape) => <option key={shape.id} value={shape.id}>{shape.label}</option>)}</select></label>
                    <label className="m3-field"><span>Explanation</span><textarea rows={3} value={nodeMeta.explanation} onChange={(event) => setNodeMeta(selectedNode.id, { explanation: event.target.value })} placeholder="What is this component responsible for?" /></label>
                    <MetaList title="Custom properties" addLabel="Property" items={nodeMeta.properties} fields={[{ key: 'key', placeholder: 'Key' }, { key: 'value', placeholder: 'Value' }]}
                      onAdd={() => setNodeMeta(selectedNode.id, { properties: [...nodeMeta.properties, { key: '', value: '' }] })}
                      onChange={(index, field, value) => setNodeMeta(selectedNode.id, { properties: nodeMeta.properties.map((item, i) => (i === index ? { ...item, [field]: value } : item)) })}
                      onRemove={(index) => setNodeMeta(selectedNode.id, { properties: nodeMeta.properties.filter((_, i) => i !== index) })} />
                    <MetaList title="Hyperlinks" addLabel="Link" items={nodeMeta.links} fields={[{ key: 'label', placeholder: 'Label' }, { key: 'url', placeholder: 'https://' }]}
                      onAdd={() => setNodeMeta(selectedNode.id, { links: [...nodeMeta.links, { label: '', url: '' }] })}
                      onChange={(index, field, value) => setNodeMeta(selectedNode.id, { links: nodeMeta.links.map((item, i) => (i === index ? { ...item, [field]: value } : item)) })}
                      onRemove={(index) => setNodeMeta(selectedNode.id, { links: nodeMeta.links.filter((_, i) => i !== index) })} />
                    <MetaList title="Documents" addLabel="Document" items={nodeMeta.documents} fields={[{ key: 'name', placeholder: 'Name' }, { key: 'url', placeholder: 'https:// or path' }]}
                      onAdd={() => setNodeMeta(selectedNode.id, { documents: [...nodeMeta.documents, { name: '', url: '' }] })}
                      onChange={(index, field, value) => setNodeMeta(selectedNode.id, { documents: nodeMeta.documents.map((item, i) => (i === index ? { ...item, [field]: value } : item)) })}
                      onRemove={(index) => setNodeMeta(selectedNode.id, { documents: nodeMeta.documents.filter((_, i) => i !== index) })} />
                  </div>
                )}
                {selectedEdge && (
                  <div className="ds-inspector-body">
                    <div className="ds-inspector-head"><span className="l1-eyebrow">Connector</span><button className="m3-icon-btn small danger-ink" onClick={removeSelected} aria-label="Delete connector"><Trash2 size={15} /></button></div>
                    <label className="m3-field"><span>Label</span><input value={selectedEdge.label} onChange={(event) => updateEdge(selectedEdge.id, { label: event.target.value })} placeholder="e.g. reads from" /></label>
                    <label className="m3-field"><span>Type</span><select value={selectedEdge.type} onChange={(event) => updateEdge(selectedEdge.id, { type: event.target.value })}>{EDGE_TYPES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
                    <p className="ds-inspector-hint">{selectedEdge.source} → {selectedEdge.target}</p>
                  </div>
                )}
                {!selection && (
                  <div className="ds-inspector-empty">
                    <MousePointerSquareDashed size={26} />
                    <p>Select a node to edit its label, shape, explanation, properties, links, and documents — or a connector to change its type.</p>
                  </div>
                )}
              </aside>
            </div>
          </div>
        )}

        {mode === 'text' && (
          <div className="ds-text">
            <div className="ds-code-pane"><header><FileCode2 size={14} /> Mermaid source</header>
              <textarea spellCheck="false" value={draft.mermaid_source} onChange={(event) => onText(event.target.value)} aria-label="Mermaid diagram source" /></div>
            <div className="ds-preview-pane"><header><Blocks size={14} /> Live preview</header>
              {previewError && <div className="l1-diagram-error"><strong>Diagram needs attention</strong><span>{String(previewError.message || previewError).split('\n')[0]}</span></div>}
              <MermaidLive source={draft.mermaid_source} onError={setPreviewError} /></div>
          </div>
        )}

        {onAssist && chatOpen && (
          <ChatDrawer
            messages={messages}
            input={chatInput}
            busy={chatBusy}
            error={chatError}
            onInput={setChatInput}
            onSend={sendChat}
            onClose={() => setChatOpen(false)}
          />
        )}
      </div>
    </div>
  )
}

const CHAT_SUGGESTIONS = [
  'Add a Redis cache between the API and the database',
  'Group the services into a subgraph called "Backend"',
  'Add a message queue and a worker that consumes from it',
]

function ChatDrawer({ messages, input, busy, error, onInput, onSend, onClose }) {
  const scrollRef = useRef(null)
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [messages, busy])
  const submit = (event) => { event.preventDefault(); onSend() }

  return (
    <aside className="ds-chat" aria-label="Diagram assistant">
      <header className="ds-chat-head">
        <span><Sparkles size={15} /> Assistant</span>
        <button className="m3-icon-btn small" onClick={onClose} aria-label="Close assistant"><X size={15} /></button>
      </header>
      <div className="ds-chat-log" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="ds-chat-intro">
            <p>Describe the change you want and I’ll update the diagram. For example:</p>
            {CHAT_SUGGESTIONS.map((suggestion) => (
              <button key={suggestion} type="button" className="ds-chat-suggestion" onClick={() => onInput(suggestion)}>{suggestion}</button>
            ))}
          </div>
        )}
        {messages.map((message, index) => (
          <div key={index} className={`ds-chat-msg ${message.role}`}>{message.content}</div>
        ))}
        {busy && <div className="ds-chat-msg assistant busy">Thinking…</div>}
      </div>
      <form className="ds-chat-input" onSubmit={submit}>
        {error && <div className="ds-chat-error">{String(error.message || error)}</div>}
        <textarea
          rows={2}
          value={input}
          placeholder="Describe a change to the diagram…"
          onChange={(event) => onInput(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); onSend() } }}
        />
        <button type="submit" className="m3-btn filled small" disabled={busy || !input.trim()}><Send size={14} /> Send</button>
      </form>
    </aside>
  )
}

function MermaidLive({ source, onError }) {
  return <MermaidView source={source} onError={onError} className="ds-mermaid-live" />
}
