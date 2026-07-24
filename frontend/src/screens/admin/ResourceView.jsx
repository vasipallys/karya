import {
  Boxes, ChevronDown, ChevronRight, Code2, Coins, Download, FileText, FolderKanban, GitBranch,
  Image as ImageIcon, Layers, LayoutGrid, Network, PieChart, Search, Tag, Users, UserCog, X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useToast } from '../../ui/Toast'
import { exportGif, exportPdf, exportPng } from './resourceview/export'
import {
  arcPath, assignAngles, colourFor, polar, radialLabel, shortName, treemap, treeRows, truncate,
} from './resourceview/layout'

const VIEWS = [
  { key: 'tree', label: 'Org hierarchy', icon: GitBranch },
  { key: 'sunburst', label: 'Sunburst', icon: PieChart },
  { key: 'treemap', label: 'Treemap', icon: LayoutGrid },
  { key: 'network', label: 'Network', icon: Network },
]

const EXPORTS = [
  { key: 'png', label: 'PNG', icon: ImageIcon },
  { key: 'gif', label: 'GIF', icon: ImageIcon },
  { key: 'pdf', label: 'PDF', icon: FileText },
]

function Chip({ children, tone }) {
  return <span className={`rv-chip${tone ? ` tone-${tone}` : ''}`}>{children}</span>
}

const subStatusTone = (s) => (s === 'Allocated' ? 'ok' : s === 'PartiallyAllocated' ? 'warn' : 'muted')

// --------------------------------------------------------------------------- //
// Org hierarchy (indented, collapsible tree)
// --------------------------------------------------------------------------- //
function TreeRow({ node, depth, expanded, toggle, onSelect, onHover, selectedId }) {
  const kids = node.children || []
  const isOpen = expanded.has(node.id)
  return (
    <div className="rv-tree-branch">
      <div
        className={`rv-tree-row${selectedId === node.id ? ' selected' : ''}`}
        style={{ paddingLeft: 8 + depth * 20 }}
        onClick={() => onSelect(node.id)}
        onMouseEnter={() => onHover(node)}
        onMouseLeave={() => onHover(null)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(node.id) } }}
      >
        <button
          className="rv-tree-toggle"
          onClick={(e) => { e.stopPropagation(); if (kids.length) toggle(node.id) }}
          aria-label={kids.length ? (isOpen ? 'Collapse' : 'Expand') : undefined}
        >
          {kids.length
            ? (isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />)
            : <span className="rv-dot" style={{ background: colourFor(node.tech_unit) }} />}
        </button>
        <span className="rv-tree-name">{node.name}</span>
        <span className="rv-tree-meta">
          <Chip>{node.rank}</Chip>
          <Chip tone={subStatusTone(node.sub_status)}>{node.sub_status}</Chip>
        </span>
        <span className="rv-tree-counts">
          {node.reports_count > 0 && <span title="Direct reports"><UserCog size={13} /> {node.reports_count}</span>}
          {node.squad_count > 0 && <span title="Squads"><Boxes size={13} /> {node.squad_count}</span>}
          {node.project_count > 0 && <span title="Projects"><FolderKanban size={13} /> {node.project_count}</span>}
          {node.story_count > 0 && <span title="Stories"><Layers size={13} /> {node.story_count}</span>}
        </span>
      </div>
      {isOpen && kids.map((kid) => (
        <TreeRow key={kid.id} node={kid} depth={depth + 1} expanded={expanded} toggle={toggle}
          onSelect={onSelect} onHover={onHover} selectedId={selectedId} />
      ))}
    </div>
  )
}

function HierarchyView({ tree, onSelect, onHover, selectedId }) {
  const [expanded, setExpanded] = useState(() => new Set(tree.map((n) => n.id)))
  const toggle = (id) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  return (
    <div className="rv-tree">
      <div className="rv-tree-actions">
        <button className="rv-link-btn" onClick={() => setExpanded(new Set(treeRows(tree).map((r) => r.node.id)))}>Expand all</button>
        <button className="rv-link-btn" onClick={() => setExpanded(new Set())}>Collapse all</button>
      </div>
      {tree.map((node) => (
        <TreeRow key={node.id} node={node} depth={0} expanded={expanded} toggle={toggle}
          onSelect={onSelect} onHover={onHover} selectedId={selectedId} />
      ))}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Sunburst
// --------------------------------------------------------------------------- //
function SunburstView({ tree, onSelect, onHover, selectedId, showLabels }) {
  const { arcs, maxDepth } = useMemo(() => assignAngles(tree), [tree])
  const size = 660
  const cx = size / 2
  const cy = size / 2
  const radius = size / 2 - 10
  const ring = radius / (maxDepth + 1)

  return (
    <div className="rv-chart-wrap">
      <svg viewBox={`0 0 ${size} ${size}`} className="rv-svg" role="img" aria-label="Sunburst of the reporting hierarchy">
        <rect width={size} height={size} fill="var(--m3-surface)" />
        {arcs.map(({ node, depth, a0, a1 }) => {
          const inner = depth * ring
          const outer = (depth + 1) * ring
          const selected = selectedId === node.id
          return (
            <path
              key={node.id}
              d={arcPath(cx, cy, inner, outer, a0, a1)}
              fill={colourFor(node.tech_unit)}
              fillOpacity={selected ? 1 : 0.85}
              stroke={selected ? 'var(--m3-on-surface)' : '#ffffff'}
              strokeWidth={selected ? 2.2 : 0.8}
              className="rv-arc"
              onClick={() => onSelect(node.id)}
              onMouseEnter={() => onHover(node)}
              onMouseLeave={() => onHover(null)}
            >
              <title>{`${node.name} · ${node.rank} · ${node.tech_unit}`}</title>
            </path>
          )
        })}
        {/* Labels are a second pass so they always sit above every wedge. */}
        {showLabels && arcs.map(({ node, depth, a0, a1, mid }) => {
          const inner = depth * ring
          const outer = (depth + 1) * ring
          const mid_r = (inner + outer) / 2
          const arcLength = (a1 - a0) * mid_r
          if (arcLength < 30 || ring < 14) return null
          const { x, y, rotate } = radialLabel(cx, cy, mid_r, mid)
          const label = truncate(shortName(node.name), Math.floor(arcLength / 6))
          if (!label) return null
          return (
            <text key={`l-${node.id}`} className="rv-arc-label" textAnchor="middle"
              transform={`translate(${x.toFixed(2)},${y.toFixed(2)}) rotate(${rotate.toFixed(2)})`}>
              {label}
            </text>
          )
        })}
        <circle cx={cx} cy={cy} r={ring - 2} fill="var(--m3-surface)" />
        <text x={cx} y={cy - 3} textAnchor="middle" className="rv-center-num">{arcs.length}</text>
        <text x={cx} y={cy + 13} textAnchor="middle" className="rv-center-label">people</text>
      </svg>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Treemap
// --------------------------------------------------------------------------- //
function TreemapView({ tree, onSelect, onHover, selectedId, showLabels }) {
  const width = 940
  const height = 560
  const cells = useMemo(() => treemap(tree, width, height), [tree])
  return (
    <div className="rv-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="rv-svg rv-treemap" role="img" aria-label="Treemap of the reporting hierarchy">
        <rect width={width} height={height} fill="var(--m3-surface)" />
        {cells.map((cell, i) => {
          const { node, x, y, w, h, leaf, self } = cell
          if (leaf) {
            const selected = selectedId === node.id
            return (
              <g key={`${node.id}-${i}`} className="rv-tm-cell"
                onClick={() => onSelect(node.id)}
                onMouseEnter={() => onHover(node)} onMouseLeave={() => onHover(null)}>
                <rect
                  x={x + 1} y={y + 1} width={Math.max(0, w - 2)} height={Math.max(0, h - 2)} rx={3}
                  fill={colourFor(node.tech_unit)} fillOpacity={self ? 0.95 : 0.82}
                  stroke={selected ? 'var(--m3-on-surface)' : '#ffffff'} strokeWidth={selected ? 2.2 : 1}
                />
                {showLabels && w > 52 && h > 24 && (
                  <text x={x + 6} y={y + 16} className="rv-tm-label">
                    {truncate(shortName(node.name), Math.floor((w - 10) / 5.6))}
                  </text>
                )}
                <title>{`${node.name} · ${node.rank} · ${node.tech_unit}`}</title>
              </g>
            )
          }
          return (
            <g key={`g-${node.id}-${i}`} className="rv-tm-group">
              <rect x={x} y={y} width={Math.max(0, w)} height={Math.max(0, h)} rx={4}
                fill="none" stroke="var(--m3-outline-variant)" strokeWidth={1} />
              {showLabels && w > 70 && (
                <text x={x + 6} y={y + 14} className="rv-tm-group-label">
                  {truncate(node.name, Math.floor((w - 12) / 5.6))} · {node.weight}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Network (radial node-link)
// --------------------------------------------------------------------------- //
function NetworkView({ tree, edges, onSelect, onHover, selectedId, showLabels }) {
  const { arcs, maxDepth } = useMemo(() => assignAngles(tree), [tree])
  const size = 760
  const cx = size / 2
  const cy = size / 2
  // Leave a generous outer margin so radial labels are not clipped.
  const radius = size / 2 - (showLabels ? 96 : 26)
  const ringStep = radius / (maxDepth + 0.5)

  const positions = useMemo(() => {
    const map = {}
    for (const { node, depth, mid } of arcs) {
      map[node.id] = { point: polar(cx, cy, depth * ringStep, mid), depth, mid }
    }
    return map
  }, [arcs, ringStep])

  const nodeRadius = (node) => 5 + Math.min(11, Math.sqrt(node.weight || 1) * 2.4)

  return (
    <div className="rv-chart-wrap">
      <svg viewBox={`0 0 ${size} ${size}`} className="rv-svg" role="img" aria-label="Network graph of reporting relationships">
        <rect width={size} height={size} fill="var(--m3-surface)" />
        <g stroke="var(--m3-outline-variant)" strokeWidth={1.1}>
          {edges.map((edge, i) => {
            const a = positions[edge.source]
            const b = positions[edge.target]
            if (!a || !b) return null
            return <line key={i} x1={a.point[0]} y1={a.point[1]} x2={b.point[0]} y2={b.point[1]} />
          })}
        </g>
        {arcs.map(({ node }) => {
          const spot = positions[node.id]
          if (!spot) return null
          const [x, y] = spot.point
          const selected = selectedId === node.id
          return (
            <g key={node.id} className="rv-net-node"
              onClick={() => onSelect(node.id)}
              onMouseEnter={() => onHover(node)} onMouseLeave={() => onHover(null)}>
              <circle cx={x} cy={y} r={nodeRadius(node)}
                fill={colourFor(node.tech_unit)}
                stroke={selected ? 'var(--m3-on-surface)' : '#ffffff'} strokeWidth={selected ? 2.6 : 1.3} />
              <title>{`${node.name} · ${node.rank} · ${node.tech_unit}`}</title>
            </g>
          )
        })}
        {showLabels && arcs.map(({ node, depth, mid }) => {
          const spot = positions[node.id]
          if (!spot) return null
          const offset = depth * ringStep + nodeRadius(node) + 5
          const { x, y, rotate, flip } = radialLabel(cx, cy, offset, mid)
          return (
            <text key={`l-${node.id}`} className="rv-net-label"
              textAnchor={flip ? 'end' : 'start'}
              transform={`translate(${x.toFixed(2)},${y.toFixed(2)}) rotate(${rotate.toFixed(2)})`}>
              {truncate(shortName(node.name), 14)}
            </text>
          )
        })}
      </svg>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Org-hierarchy export: the HTML tree cannot be rasterised, so build an
// equivalent off-screen SVG (full hierarchy, regardless of what is collapsed).
// --------------------------------------------------------------------------- //
const SVG_NS = 'http://www.w3.org/2000/svg'

function buildTreeSvg(rows, heading) {
  const rowHeight = 22
  const indent = 18
  const padX = 18
  const top = 44
  const width = 940
  const height = top + rows.length * rowHeight + 18

  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('xmlns', SVG_NS)
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`)

  const el = (tag, attrs, text) => {
    const node = document.createElementNS(SVG_NS, tag)
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value))
    if (text !== undefined) node.textContent = text
    svg.appendChild(node)
    return node
  }

  el('rect', { x: 0, y: 0, width, height, fill: '#ffffff' })
  el('text', { x: padX, y: 26, 'font-family': 'Segoe UI, Roboto, sans-serif', 'font-size': 15, 'font-weight': 600, fill: '#1b1b1f' }, heading)

  rows.forEach(({ node, depth }, index) => {
    const y = top + index * rowHeight + 14
    const x = padX + depth * indent
    if (index % 2 === 1) {
      el('rect', { x: padX - 6, y: y - 13, width: width - (padX - 6) * 2, height: rowHeight - 2, fill: '#f5f5f8' })
    }
    el('circle', { cx: x + 4, cy: y - 4, r: 4, fill: colourFor(node.tech_unit) })
    el('text', {
      x: x + 15, y, 'font-family': 'Segoe UI, Roboto, sans-serif', 'font-size': 12, fill: '#1b1b1f',
    }, node.name)
    const meta = [
      node.rank,
      node.tech_unit,
      node.reports_count ? `${node.reports_count} reports` : null,
      node.squad_count ? `${node.squad_count} squads` : null,
      node.project_count ? `${node.project_count} projects` : null,
      node.story_count ? `${node.story_count} stories` : null,
    ].filter(Boolean).join('  ·  ')
    el('text', {
      x: width - padX, y, 'text-anchor': 'end',
      'font-family': 'Segoe UI, Roboto, sans-serif', 'font-size': 10.5, fill: '#5a5a66',
    }, meta)
  })
  return svg
}

// --------------------------------------------------------------------------- //
// Detail drawer
// --------------------------------------------------------------------------- //
function Stat({ icon: Icon, label, value }) {
  return (
    <div className="rv-stat">
      <span className="rv-stat-icon"><Icon size={15} /></span>
      <div><strong>{value}</strong><small>{label}</small></div>
    </div>
  )
}

function DetailDrawer({ staffId, onClose, onSelect }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    api.reportingResourceProfile(staffId)
      .then((res) => { if (live) setData(res) })
      .catch((err) => toast.error(err))
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [staffId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const p = data?.profile
  const s = data?.summary

  return (
    <div className="rv-drawer-scrim" onClick={onClose}>
      <aside className="rv-drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Resource details">
        <header className="rv-drawer-head">
          <div>
            <h3>{p?.name || 'Resource'}</h3>
            {p && <span className="rv-drawer-sub">{p.code} · {p.rank} · {p.tech_unit}</span>}
          </div>
          <button className="rv-icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>

        {loading && <div className="rv-drawer-body"><p className="admin-muted">Loading resource…</p></div>}

        {!loading && data && (
          <div className="rv-drawer-body">
            <div className="rv-chip-row">
              <Chip tone={p.status === 'Active' ? 'ok' : 'muted'}>{p.status}</Chip>
              <Chip tone={subStatusTone(p.sub_status)}>{p.sub_status}</Chip>
              <Chip>{p.type}</Chip>
              <Chip>{p.hr_role}</Chip>
            </div>

            <div className="rv-stat-grid">
              <Stat icon={UserCog} label="Reports" value={s.reports_count} />
              <Stat icon={Boxes} label="Squads" value={s.squad_count} />
              <Stat icon={GitBranch} label="Tribes" value={s.tribe_count} />
              <Stat icon={FolderKanban} label="Projects" value={s.project_count} />
              <Stat icon={Layers} label="Stories" value={s.story_count} />
              <Stat icon={PieChart} label="Points" value={s.points} />
              <Stat icon={Coins} label="Allocation" value={`${s.allocation}%`} />
            </div>

            {data.manager_chain.length > 0 && (
              <section className="rv-section">
                <h4>Reporting line</h4>
                <div className="rv-crumbs">
                  {[...data.manager_chain].reverse().map((m) => (
                    <button key={m.id} className="rv-crumb" onClick={() => onSelect(m.id)}>{m.name}</button>
                  ))}
                  <span className="rv-crumb current">{p.name}</span>
                </div>
              </section>
            )}

            {data.reports.length > 0 && (
              <section className="rv-section">
                <h4>Direct reports ({data.reports.length})</h4>
                <div className="rv-pill-row">
                  {data.reports.map((r) => (
                    <button key={r.id} className="rv-pill" onClick={() => onSelect(r.id)}>{r.name} <small>{r.rank}</small></button>
                  ))}
                </div>
              </section>
            )}

            <section className="rv-section">
              <h4>Teams, squads &amp; tribes ({data.teams.length})</h4>
              {data.teams.length === 0 && <p className="admin-muted">Not assigned to any squad or tribe yet.</p>}
              {data.teams.length > 0 && (
                <div className="rv-table-scroll">
                  <table className="res-table rv-table">
                    <thead><tr><th>Unit</th><th>Type</th><th>Tribe</th><th>Project</th><th>Initiative</th><th>Role</th><th>Alloc</th></tr></thead>
                    <tbody>
                      {data.teams.map((t) => (
                        <tr key={t.unit_id}>
                          <td><strong>{t.unit_name}</strong></td>
                          <td><Chip tone={t.unit_type === 'tribe' ? 'accent' : 'muted'}>{t.unit_type}</Chip></td>
                          <td>{t.tribe_name || '—'}</td>
                          <td>{t.project_name}</td>
                          <td>{t.initiative_name}</td>
                          <td>{t.role}</td>
                          <td>{t.allocation_percent}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="rv-section">
              <h4>Stories ({data.stories.length})</h4>
              {data.stories.length === 0 && <p className="admin-muted">No stories linked through this person's squads.</p>}
              {data.stories.length > 0 && (
                <div className="rv-table-scroll">
                  <table className="res-table rv-table">
                    <thead><tr><th>Story</th><th>Project</th><th>Points</th><th>Status</th></tr></thead>
                    <tbody>
                      {data.stories.map((story) => (
                        <tr key={story.id}>
                          <td><strong>{story.name}</strong>{story.code_path && <div className="rv-code"><Code2 size={12} /> {story.code_path}</div>}</td>
                          <td>{story.project_name}</td>
                          <td>{story.points ?? '—'}</td>
                          <td><Chip tone={story.work_status === 'at_risk' ? 'warn' : 'muted'}>{story.work_status}</Chip></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {data.code_paths.length > 0 && (
              <section className="rv-section">
                <h4>Code paths ({data.code_paths.length})</h4>
                <ul className="rv-code-list">
                  {data.code_paths.map((path) => <li key={path}><Code2 size={13} /> {path}</li>)}
                </ul>
              </section>
            )}
          </div>
        )}
      </aside>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Main
// --------------------------------------------------------------------------- //
export default function ResourceView() {
  const toast = useToast()
  const [graph, setGraph] = useState(null)
  const [failed, setFailed] = useState(false)
  const [view, setView] = useState('tree')
  const [selectedId, setSelectedId] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [showLabels, setShowLabels] = useState(true)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState('')
  const canvasRef = useRef(null)

  const load = () => {
    setFailed(false)
    api.reportingResourceGraph().then(setGraph).catch((err) => { setFailed(true); toast.error(err) })
  }
  useEffect(load, []) // eslint-disable-line react-hooks/exhaustive-deps

  const allRows = useMemo(() => (graph ? treeRows(graph.tree) : []), [graph])
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return allRows
      .filter(({ node }) => node.name.toLowerCase().includes(q) || (node.code || '').toLowerCase().includes(q))
      .slice(0, 8)
  }, [query, allRows])

  const legend = useMemo(() => {
    if (!graph) return []
    const counts = new Map()
    for (const node of graph.nodes) counts.set(node.tech_unit, (counts.get(node.tech_unit) || 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([label, count]) => ({ label, count }))
  }, [graph])

  const runExport = async (kind) => {
    if (busy) return
    setBusy(kind)
    let temporary = null
    try {
      let svg = canvasRef.current?.querySelector('svg')
      if (view === 'tree') {
        temporary = buildTreeSvg(allRows, 'Karya — Resource view · Org hierarchy')
        Object.assign(temporary.style, { position: 'fixed', left: '-10000px', top: '0' })
        document.body.appendChild(temporary)
        svg = temporary
      }
      if (!svg) throw new Error('There is no chart to export yet.')
      const label = VIEWS.find((v) => v.key === view)?.label || 'chart'
      const name = `karya-resource-${view}`
      const title = `Karya — Resource view · ${label}`
      const subtitle = `${graph.totals.resources} resources · ${graph.totals.managers} managers · exported ${new Date().toLocaleDateString()}`
      if (kind === 'png') await exportPng(svg, name)
      else if (kind === 'gif') await exportGif(svg, name)
      else await exportPdf(svg, name, title, subtitle)
      toast.success(`${label} exported as ${kind.toUpperCase()}`)
    } catch (err) {
      toast.error(err)
    } finally {
      if (temporary) temporary.remove()
      setBusy('')
    }
  }

  if (failed) {
    return (
      <section className="admin-section">
        <div className="login-empty">
          <Users size={26} />
          <p>The resource view could not be loaded.</p>
          <button className="m3-btn tonal" onClick={load}>Retry</button>
        </div>
      </section>
    )
  }
  if (!graph) return <section className="admin-section"><div className="login-empty">Loading resource view…</div></section>

  const empty = graph.tree.length === 0
  const totals = graph.totals
  const chartView = view !== 'tree'

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div>
          <h2>Resource view</h2>
          <p>Explore the org hierarchy as an interactive chart. Click any resource to see their teams, squads, tribes, projects, stories and code.</p>
        </div>
      </div>

      <div className="rv-summary">
        <Stat icon={Users} label="Resources" value={totals.resources} />
        <Stat icon={UserCog} label="Managers" value={totals.managers} />
        <Stat icon={GitBranch} label="Top of chain" value={totals.roots} />
        <Stat icon={Boxes} label="Squads" value={totals.squads} />
      </div>

      <div className="rv-toolbar">
        <div className="rv-view-switch">
          {VIEWS.map((v) => {
            const Icon = v.icon
            return (
              <button key={v.key} className={view === v.key ? 'active' : ''} onClick={() => setView(v.key)}>
                <Icon size={15} /> {v.label}
              </button>
            )
          })}
        </div>

        <div className="rv-toolbar-right">
          <div className="rv-search">
            <Search size={15} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Find a resource…"
              aria-label="Find a resource"
            />
            {matches.length > 0 && (
              <ul className="rv-search-results">
                {matches.map(({ node }) => (
                  <li key={node.id}>
                    <button onClick={() => { setSelectedId(node.id); setQuery('') }}>
                      <span className="rv-dot" style={{ background: colourFor(node.tech_unit) }} />
                      {node.name} <small>{node.code} · {node.rank}</small>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <label className="rv-switch" title="Show names on the chart">
            <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
            <Tag size={14} /> Names
          </label>

          <div className="rv-export" role="group" aria-label="Export chart">
            <span className="rv-export-label"><Download size={14} /> Export</span>
            {EXPORTS.map((item) => (
              <button key={item.key} onClick={() => runExport(item.key)} disabled={!!busy || empty}
                title={`Export the current view as ${item.label}`}>
                {busy === item.key ? '…' : item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {empty ? (
        <div className="login-empty"><Users size={26} /><p>No resources in the directory yet.</p></div>
      ) : (
        <>
          {chartView && (
            <div className="rv-caption" aria-live="polite">
              {hovered ? (
                <>
                  <span className="rv-dot" style={{ background: colourFor(hovered.tech_unit) }} />
                  <strong>{hovered.name}</strong>
                  <span>{hovered.rank} · {hovered.tech_unit}</span>
                  <span className="rv-caption-counts">
                    {hovered.reports_count} reports · {hovered.squad_count} squads · {hovered.project_count} projects · {hovered.story_count} stories
                  </span>
                </>
              ) : <span className="admin-muted">Hover a resource to see their name, or click to open the full report.</span>}
            </div>
          )}

          <div className="rv-canvas" ref={canvasRef}>
            {view === 'tree' && <HierarchyView tree={graph.tree} onSelect={setSelectedId} onHover={setHovered} selectedId={selectedId} />}
            {view === 'sunburst' && <SunburstView tree={graph.tree} onSelect={setSelectedId} onHover={setHovered} selectedId={selectedId} showLabels={showLabels} />}
            {view === 'treemap' && <TreemapView tree={graph.tree} onSelect={setSelectedId} onHover={setHovered} selectedId={selectedId} showLabels={showLabels} />}
            {view === 'network' && <NetworkView tree={graph.tree} edges={graph.edges} onSelect={setSelectedId} onHover={setHovered} selectedId={selectedId} showLabels={showLabels} />}
          </div>

          {legend.length > 1 && (
            <div className="rv-legend">
              {legend.map((entry) => (
                <span key={entry.label} className="rv-legend-item">
                  <span className="rv-dot" style={{ background: colourFor(entry.label) }} />
                  {entry.label} <small>{entry.count}</small>
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {selectedId && (
        <DetailDrawer staffId={selectedId} onClose={() => setSelectedId(null)} onSelect={setSelectedId} />
      )}
    </section>
  )
}
