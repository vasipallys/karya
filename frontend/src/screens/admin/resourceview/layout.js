// Pure, deterministic layout helpers for the resource-view charts.
// No React, no DOM — just geometry, so they can be unit tested in isolation.

const TAU = Math.PI * 2
const START = -Math.PI / 2 // 12 o'clock

const weightOf = (node) => Math.max(1, node.weight || 1)

/**
 * Walk a reporting forest and assign every node an angular slice sized by its
 * subtree headcount. Depth 1 = the roots (depth 0 / centre is reserved for a
 * label). Returns a flat list of { node, depth, a0, a1, mid } plus maxDepth.
 * Shared by the sunburst (annular sectors) and the network (polar node-link).
 */
export function assignAngles(roots) {
  const arcs = []
  let maxDepth = 1
  const total = roots.reduce((sum, r) => sum + weightOf(r), 0) || 1

  const walk = (node, depth, a0, span) => {
    const a1 = a0 + span
    if (depth > maxDepth) maxDepth = depth
    arcs.push({ node, depth, a0, a1, mid: (a0 + a1) / 2 })
    const kids = node.children || []
    const kidWeight = kids.reduce((sum, k) => sum + weightOf(k), 0) || 1
    let cursor = a0
    for (const kid of kids) {
      const kidSpan = span * (weightOf(kid) / kidWeight)
      walk(kid, depth + 1, cursor, kidSpan)
      cursor += kidSpan
    }
  }

  let cursor = START
  for (const root of roots) {
    const span = TAU * (weightOf(root) / total)
    walk(root, 1, cursor, span)
    cursor += span
  }
  return { arcs, maxDepth }
}

/** SVG path for an annular sector (a sunburst wedge). */
export function arcPath(cx, cy, rInner, rOuter, a0, a1) {
  const point = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)]
  const large = a1 - a0 > Math.PI ? 1 : 0
  const [x0, y0] = point(rOuter, a0)
  const [x1, y1] = point(rOuter, a1)
  const [x2, y2] = point(rInner, a1)
  const [x3, y3] = point(rInner, a0)
  if (rInner <= 0.01) {
    return `M${cx},${cy} L${x0},${y0} A${rOuter},${rOuter} 0 ${large} 1 ${x1},${y1} Z`
  }
  return (
    `M${x0},${y0} A${rOuter},${rOuter} 0 ${large} 1 ${x1},${y1} ` +
    `L${x2},${y2} A${rInner},${rInner} 0 ${large} 0 ${x3},${y3} Z`
  )
}

export const polar = (cx, cy, r, angle) => [cx + r * Math.cos(angle), cy + r * Math.sin(angle)]

/**
 * Placement for a label sitting on a radius. Text on the left half of the circle
 * is rotated a further 180deg so it never reads upside down; `flip` tells the
 * caller to swap the text anchor to match.
 */
export function radialLabel(cx, cy, radius, angle) {
  const [x, y] = polar(cx, cy, radius, angle)
  const degrees = (((angle * 180) / Math.PI) % 360 + 360) % 360
  const flip = degrees > 90 && degrees < 270
  return { x, y, rotate: flip ? degrees + 180 : degrees, flip }
}

/** Clip a label to an approximate character budget, keeping it readable. */
export function truncate(text, maxChars) {
  const value = String(text || '')
  if (maxChars < 2) return ''
  return value.length <= maxChars ? value : `${value.slice(0, Math.max(1, maxChars - 1))}…`
}

/** A person's short label: first name plus last initial, e.g. "Daniel B." */
export function shortName(name) {
  const parts = String(name || '').trim().split(/\s+/)
  if (parts.length < 2) return parts[0] || ''
  return `${parts[0]} ${parts[parts.length - 1][0]}.`
}

/** Depth-first flatten of the forest into { node, depth } rows (export + search). */
export function treeRows(roots) {
  const rows = []
  const walk = (node, depth) => {
    rows.push({ node, depth })
    for (const kid of node.children || []) walk(kid, depth + 1)
  }
  roots.forEach((root) => walk(root, 0))
  return rows
}

// --------------------------------------------------------------------------- //
// Squarified treemap (Bruls, Huizing & van Wijk). Lays a node's children into
// its rectangle keeping cells close to square, then recurses for the hierarchy.
// --------------------------------------------------------------------------- //

function worstRatio(row, length, sum) {
  const max = Math.max(...row)
  const min = Math.min(...row)
  const s2 = sum * sum
  const l2 = length * length
  return Math.max((l2 * max) / s2, s2 / (l2 * min))
}

/** Place `items` ([{ node, area }]) inside rect; areas must sum to rect area. */
export function squarify(items, rect) {
  const placed = []
  let { x, y, w, h } = rect
  let remaining = items.slice()

  while (remaining.length) {
    const length = Math.min(w, h)
    if (length <= 0) break
    const row = []
    let rowSum = 0
    while (remaining.length) {
      const area = remaining[0].area
      const current = row.length ? worstRatio(row, length, rowSum) : Infinity
      const next = worstRatio([...row, area], length, rowSum + area)
      if (row.length === 0 || next <= current) {
        row.push(area)
        rowSum += area
        remaining.shift()
      } else break
    }
    const thickness = rowSum / length || 0
    const rowItems = items.slice(placed.length, placed.length + row.length)
    let offset = 0
    for (let i = 0; i < rowItems.length; i += 1) {
      const frac = row.length ? row[i] / rowSum : 0
      if (w >= h) {
        placed.push({ node: rowItems[i].node, x, y: y + offset, w: thickness, h: length * frac })
      } else {
        placed.push({ node: rowItems[i].node, x: x + offset, y, w: length * frac, h: thickness })
      }
      offset += length * frac
    }
    if (w >= h) { x += thickness; w -= thickness } else { y += thickness; h -= thickness }
  }
  return placed
}

const HEADER = 20
const PAD = 3
const MIN_CELL = 10

/**
 * Recursively lay out a reporting forest as a nested treemap. Each manager gets
 * a labelled group rectangle whose interior is split between a cell for
 * themselves (value 1) and their reports' subtrees (value = subtree headcount).
 * Returns a flat list of { node, x, y, w, h, depth, leaf, self } ordered so
 * groups render before the leaves drawn on top of them.
 */
export function treemap(roots, width, height) {
  const cells = []
  const virtual = { id: '__root__', children: roots }

  const layout = (node, rect, depth) => {
    const kids = node.children || []
    if (kids.length === 0 || rect.w < MIN_CELL || rect.h < MIN_CELL) {
      cells.push({ node, ...rect, depth, leaf: true })
      return
    }
    if (node.id !== '__root__') cells.push({ node, ...rect, depth, leaf: false })

    const inner = node.id === '__root__'
      ? { x: rect.x, y: rect.y, w: rect.w, h: rect.h }
      : { x: rect.x + PAD, y: rect.y + HEADER, w: rect.w - PAD * 2, h: rect.h - HEADER - PAD }
    if (inner.w < MIN_CELL || inner.h < MIN_CELL) return

    const items = []
    if (node.id !== '__root__') items.push({ node: { ...node, __self: true }, value: 1 })
    for (const kid of kids) items.push({ node: kid, value: weightOf(kid) })
    const totalValue = items.reduce((sum, it) => sum + it.value, 0) || 1
    const innerArea = inner.w * inner.h
    const scaled = items.map((it) => ({ node: it.node, area: (it.value / totalValue) * innerArea }))

    for (const p of squarify(scaled, inner)) {
      const childRect = { x: p.x, y: p.y, w: p.w, h: p.h }
      if (p.node.__self) {
        cells.push({ node, ...childRect, depth: depth + 1, leaf: true, self: true })
      } else {
        layout(p.node, childRect, depth + 1)
      }
    }
  }

  layout(virtual, { x: 0, y: 0, w: width, h: height }, 0)
  return cells
}

// A brand-neutral categorical palette; colourFor maps any string key to a
// stable colour so tech units / depths stay consistent across the charts.
export const PALETTE = [
  '#3b6fd4', '#2f9e78', '#c9761f', '#8a5cd1', '#c14b7a',
  '#4a9ec4', '#6f9e2f', '#b5872a', '#5566cf', '#c0574a',
]

export function colourFor(key) {
  const str = String(key || '')
  let hash = 0
  for (let i = 0; i < str.length; i += 1) hash = (hash * 31 + str.charCodeAt(i)) & 0xffffffff
  return PALETTE[Math.abs(hash) % PALETTE.length]
}
