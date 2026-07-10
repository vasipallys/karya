// Bidirectional bridge between Mermaid flowchart text and an editable graph model.
//
// The model is the contract shared by the text editor, the visual (React Flow)
// editor, and the properties inspector:
//   { direction, nodes: [{id,label,shape}], edges: [{id,source,target,type,label}],
//     groups: [{id,title,members:[nodeId]}], supported }
//
// Only flowcharts round-trip through the visual editor. Other diagram types
// (sequence, class, …) parse as `supported: false` so callers can fall back to
// text-only editing without destroying the source.

export const NODE_SHAPES = [
  { id: 'rect', label: 'Process', open: '[', close: ']', mermaidShape: 'rect', aliases: ['rectangle', 'process', 'proc'] },
  { id: 'round', label: 'Event', open: '(', close: ')', mermaidShape: 'rounded', aliases: ['event', 'rounded'] },
  { id: 'stadium', label: 'Terminal', open: '([', close: '])', mermaidShape: 'stadium', aliases: ['pill', 'terminal'] },
  { id: 'subroutine', label: 'Subprocess', open: '[[', close: ']]', mermaidShape: 'fr-rect', aliases: ['framed-rectangle', 'subproc', 'subprocess'] },
  { id: 'cylinder', label: 'Database', open: '[(', close: ')]', mermaidShape: 'cyl', aliases: ['database', 'db'] },
  { id: 'circle', label: 'Start', open: '((', close: '))', mermaidShape: 'circle', aliases: ['circ'] },
  { id: 'diamond', label: 'Decision', open: '{', close: '}', mermaidShape: 'diam', aliases: ['decision', 'question'] },
  { id: 'hexagon', label: 'Prepare', open: '{{', close: '}}', mermaidShape: 'hex', aliases: ['prepare'] },
  { id: 'parallelogram', label: 'Input / output', open: '[/', close: '/]', mermaidShape: 'lean-r', aliases: ['in-out', 'lean-right'] },
  { id: 'doc', label: 'Document', mermaidShape: 'doc', aliases: ['document'] },
  { id: 'docs', label: 'Documents', mermaidShape: 'docs', aliases: ['documents', 'stacked-document', 'st-doc'] },
  { id: 'cloud', label: 'Cloud', mermaidShape: 'cloud', aliases: ['cloud'] },
  { id: 'card', label: 'Card', mermaidShape: 'notch-rect', aliases: ['card', 'notched-rectangle'] },
  { id: 'datastore', label: 'Data store', mermaidShape: 'datastore', aliases: ['data-store'] },
  { id: 'display', label: 'Display', mermaidShape: 'curv-trap', aliases: ['display', 'curved-trapezoid'] },
  { id: 'manual-input', label: 'Manual input', mermaidShape: 'sl-rect', aliases: ['manual-input', 'sloped-rectangle'] },
  { id: 'manual', label: 'Manual operation', mermaidShape: 'trap-t', aliases: ['manual', 'trapezoid-top', 'inv-trapezoid'] },
  { id: 'priority', label: 'Priority action', mermaidShape: 'trap-b', aliases: ['priority', 'trapezoid', 'trapezoid-bottom'] },
  { id: 'delay', label: 'Delay', mermaidShape: 'delay', aliases: ['half-rounded-rectangle'] },
  { id: 'fork', label: 'Fork / join', mermaidShape: 'fork', aliases: ['join'] },
  { id: 'junction', label: 'Junction', mermaidShape: 'f-circ', aliases: ['filled-circle'] },
  { id: 'bolt', label: 'Communication link', mermaidShape: 'bolt', aliases: ['com-link', 'lightning-bolt'] },
  { id: 'hourglass', label: 'Collate', mermaidShape: 'hourglass', aliases: ['collate'] },
  { id: 'triangle', label: 'Extract', mermaidShape: 'tri', aliases: ['extract'] },
  { id: 'lined-cylinder', label: 'Disk storage', mermaidShape: 'lin-cyl', aliases: ['disk', 'lined-cylinder'] },
  { id: 'horizontal-cylinder', label: 'Direct storage', mermaidShape: 'h-cyl', aliases: ['das', 'horizontal-cylinder'] },
  { id: 'window-pane', label: 'Internal storage', mermaidShape: 'win-pane', aliases: ['internal-storage', 'window-pane'] },
  { id: 'text', label: 'Text block', mermaidShape: 'text', aliases: ['text'] },
]

export const EDGE_TYPES = [
  { id: 'arrow', label: 'Arrow', plain: '-->', mid: (t) => `-- ${t} -->` },
  { id: 'open', label: 'Line', plain: '---', mid: (t) => `-- ${t} ---` },
  { id: 'dotted', label: 'Dotted', plain: '-.->', mid: (t) => `-. ${t} .->` },
  { id: 'thick', label: 'Thick', plain: '==>', mid: (t) => `== ${t} ==>` },
]

export const DIRECTIONS = [
  { id: 'LR', label: 'Left → Right' },
  { id: 'TB', label: 'Top → Bottom' },
  { id: 'RL', label: 'Right → Left' },
  { id: 'BT', label: 'Bottom → Top' },
]

const SHAPE_BY_ID = Object.fromEntries(NODE_SHAPES.map((shape) => [shape.id, shape]))
const SHAPE_BY_ALIAS = new Map()
for (const shape of NODE_SHAPES) {
  SHAPE_BY_ALIAS.set(shape.id.toLowerCase(), shape)
  SHAPE_BY_ALIAS.set((shape.mermaidShape || shape.id).toLowerCase(), shape)
  for (const alias of shape.aliases || []) SHAPE_BY_ALIAS.set(alias.toLowerCase(), shape)
}
// Match most specific (two-char) wrappers before generic single-char ones.
const SHAPE_MATCH_ORDER = ['subroutine', 'cylinder', 'circle', 'parallelogram', 'stadium', 'hexagon', 'rect', 'round', 'diamond']

// Endpoint = id plus an optional shape wrapper. Non-greedy bodies stop at the
// first matching close so `Data[("x")]` and `Bus{{"y"}}` parse correctly.
const WRAPPER_SRC =
  '(\\[\\[[\\s\\S]*?\\]\\]|\\[\\([\\s\\S]*?\\)\\]|\\(\\([\\s\\S]*?\\)\\)|\\[\\/[\\s\\S]*?\\/\\]|' +
  '\\(\\[[\\s\\S]*?\\]\\)|\\{\\{[\\s\\S]*?\\}\\}|\\[[\\s\\S]*?\\]|\\([\\s\\S]*?\\)|\\{[\\s\\S]*?\\})'
const SHAPE_CONFIG_SRC = '@\\{[\\s\\S]*?\\}'
const ENDPOINT_SRC =
  '([A-Za-z0-9_]+)\\s*' +
  `(?:(${SHAPE_CONFIG_SRC})\\s*)?` +
  `(${WRAPPER_SRC})?`

const OP_BY_TOKEN = { '-->': 'arrow', '---': 'open', '-.->': 'dotted', '==>': 'thick' }

function stripQuotes(text) {
  const trimmed = text.trim()
  if (trimmed.length >= 2 && ((trimmed[0] === '"' && trimmed.at(-1) === '"') || (trimmed[0] === "'" && trimmed.at(-1) === "'"))) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"').replace(/\\'/g, "'").replace(/#quot;/g, '"')
  }
  return trimmed.replace(/#quot;/g, '"')
}

function parseShapeConfig(config) {
  if (!config) return null
  const shapeMatch = config.match(/\bshape\s*:\s*["']?([A-Za-z0-9_-]+)["']?/i)
  const labelMatch = config.match(/\blabel\s*:\s*("(\\"|[^"])*"|'(\\'|[^'])*'|[^,}]+)/i)
  const shape = SHAPE_BY_ALIAS.get((shapeMatch?.[1] || '').toLowerCase()) || SHAPE_BY_ID.rect
  return {
    shape: shape.id,
    label: labelMatch ? stripQuotes(labelMatch[1]) : null,
  }
}

function unwrapShape(config, wrapper) {
  const configured = parseShapeConfig(config)
  if (configured) return configured
  if (!wrapper) return { shape: 'rect', label: null }
  for (const id of SHAPE_MATCH_ORDER) {
    const { open, close } = SHAPE_BY_ID[id]
    if (wrapper.startsWith(open) && wrapper.endsWith(close) && wrapper.length >= open.length + close.length) {
      return { shape: id, label: stripQuotes(wrapper.slice(open.length, wrapper.length - close.length)) }
    }
  }
  return { shape: 'rect', label: null }
}

// Rewrite the three "middle text" edge forms into the uniform pipe form so the
// scanner only has to handle `OP` optionally followed by `|label|`.
function normalizeEdgeLabels(line) {
  return line
    .replace(/--\s+([^|>]+?)\s+-->/g, '-->|$1|')
    .replace(/-\.\s+([^|>]+?)\s+\.->/g, '-.->|$1|')
    .replace(/==\s+([^|>]+?)\s+==>/g, '==>|$1|')
    .replace(/--\s+([^|>]+?)\s+---/g, '---|$1|')
}

function looksLikeEdge(line) {
  return /-->|---|-\.->|==>|-\.\s|==\s|--\s/.test(line)
}

export function parseFlowchart(text) {
  const model = { direction: 'LR', nodes: [], edges: [], groups: [], supported: true }
  const source = String(text ?? '')
  const rawLines = source.split('\n')

  const nodeMap = new Map()
  const groupMap = new Map()
  const groupStack = []
  let edgeSeq = 0
  let sawHeader = false

  const registerNode = (id, config, wrapper) => {
    const { shape, label } = unwrapShape(config, wrapper)
    let node = nodeMap.get(id)
    if (!node) {
      node = { id, label: label ?? id, shape: shape || 'rect' }
      nodeMap.set(id, node)
    } else if (config || wrapper) {
      node.shape = shape || node.shape
      if (label != null) node.label = label
    }
    const group = groupStack.at(-1)
    if (group && !group.members.includes(id)) group.members.push(id)
    return id
  }

  for (const raw of rawLines) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('%%')) continue

    if (!sawHeader) {
      const header = line.match(/^(flowchart|graph)\s+(TB|TD|BT|RL|LR)\b/i)
      if (header) {
        const dir = header[2].toUpperCase()
        model.direction = dir === 'TD' ? 'TB' : dir
        sawHeader = true
        continue
      }
      // First meaningful line is not a flowchart header → unsupported for visual editing.
      if (/^(sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart|C4Context|requirementDiagram|architecture-beta|block-beta|packet|kanban|radar-beta|treemap-beta|venn-beta|xychart-beta|sankey-beta)/i.test(line)) {
        model.supported = false
        return model
      }
      if (/^(flowchart|graph)\b/i.test(line)) { sawHeader = true; continue }
    }

    // Styling / class directives are preserved by the text editor but ignored by the model.
    if (/^(classDef|class |style |linkStyle|click |direction )/i.test(line)) continue

    const subgraph = line.match(/^subgraph\s+(?:([A-Za-z0-9_]+)\s*)?(?:\[?"?([^"\]]*)"?\]?)?\s*$/i)
    if (line.toLowerCase().startsWith('subgraph')) {
      const id = subgraph?.[1] || `group${groupMap.size + 1}`
      const title = stripQuotes(subgraph?.[2] || '') || id
      const group = { id, title, members: [] }
      groupMap.set(id, group)
      groupStack.push(group)
      continue
    }
    if (line === 'end') { groupStack.pop(); continue }

    const normalized = normalizeEdgeLabels(line)
    if (looksLikeEdge(normalized)) {
      scanChain(normalized, registerNode, (source, target, type, label) => {
        model.edges.push({ id: `e${edgeSeq++}`, source, target, type, label: label ? label.trim() : '' })
      })
      continue
    }

    // Node-only declaration.
    const nodeOnly = normalized.match(new RegExp(`^${ENDPOINT_SRC}\\s*$`))
    if (nodeOnly) registerNode(nodeOnly[1], nodeOnly[2], nodeOnly[3])
  }

  model.nodes = [...nodeMap.values()]
  model.groups = [...groupMap.values()]
  return model
}

function scanChain(line, registerNode, addEdge) {
  const endpointRe = new RegExp(ENDPOINT_SRC, 'y')
  const opRe = /\s*(-->|-\.->|==>|---)\s*(?:\|([^|]*)\|)?\s*/y

  endpointRe.lastIndex = 0
  let match = endpointRe.exec(line)
  if (!match) return
  let prev = registerNode(match[1], match[2], match[3])
  let pos = endpointRe.lastIndex

  while (pos < line.length) {
    opRe.lastIndex = pos
    const op = opRe.exec(line)
    if (!op) break
    pos = opRe.lastIndex
    endpointRe.lastIndex = pos
    const next = endpointRe.exec(line)
    if (!next) break
    const current = registerNode(next[1], next[2], next[3])
    addEdge(prev, current, OP_BY_TOKEN[op[1]] || 'arrow', op[2] || '')
    prev = current
    pos = endpointRe.lastIndex
  }
}

function quoteLabel(label) {
  return String(label ?? '').replace(/"/g, '#quot;')
}

function quoteConfigValue(value) {
  return String(value ?? '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function declareNode(node) {
  const shape = SHAPE_BY_ID[node.shape] || SHAPE_BY_ID.rect
  if (shape.open && shape.close) return `${node.id}${shape.open}"${quoteLabel(node.label)}"${shape.close}`
  return `${node.id}@{ shape: ${shape.mermaidShape || shape.id}, label: "${quoteConfigValue(node.label)}" }`
}

function edgeSegment(edge) {
  const type = EDGE_TYPES.find((item) => item.id === edge.type) || EDGE_TYPES[0]
  const connector = edge.label ? type.mid(edge.label) : type.plain
  return `${edge.source} ${connector} ${edge.target}`
}

export function modelToMermaid(model) {
  const direction = DIRECTIONS.some((item) => item.id === model.direction) ? model.direction : 'LR'
  const lines = [`flowchart ${direction}`]
  const declared = new Set()
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]))

  for (const group of model.groups || []) {
    const title = group.title && group.title !== group.id ? `["${quoteLabel(group.title)}"]` : ''
    lines.push(`  subgraph ${group.id}${title}`)
    for (const memberId of group.members || []) {
      const node = nodeById.get(memberId)
      if (node && !declared.has(node.id)) { lines.push(`    ${declareNode(node)}`); declared.add(node.id) }
    }
    lines.push('  end')
  }

  for (const node of model.nodes) {
    if (!declared.has(node.id)) { lines.push(`  ${declareNode(node)}`); declared.add(node.id) }
  }
  for (const edge of model.edges) {
    lines.push(`  ${edgeSegment(edge)}`)
  }
  return lines.join('\n')
}

// Unique, mermaid-safe node id (letters/digits/underscore) for newly added nodes.
export function nextNodeId(model, base = 'node') {
  const taken = new Set(model.nodes.map((node) => node.id))
  let index = model.nodes.length + 1
  let candidate = `${base}${index}`
  while (taken.has(candidate)) { index += 1; candidate = `${base}${index}` }
  return candidate
}
