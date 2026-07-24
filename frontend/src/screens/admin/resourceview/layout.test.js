import { describe, expect, it } from 'vitest'
import { assignAngles, colourFor, squarify, treemap } from './layout'

const forest = [
  {
    id: 'a', name: 'A', weight: 4,
    children: [
      { id: 'b', name: 'B', weight: 2, children: [{ id: 'd', name: 'D', weight: 1, children: [] }] },
      { id: 'c', name: 'C', weight: 1, children: [] },
    ],
  },
  { id: 'e', name: 'E', weight: 1, children: [] },
]

describe('assignAngles', () => {
  it('covers the full circle and nests children within parents', () => {
    const { arcs, maxDepth } = assignAngles(forest)
    expect(maxDepth).toBe(3)
    // Every node appears exactly once.
    expect(arcs.map((a) => a.node.id).sort()).toEqual(['a', 'b', 'c', 'd', 'e'])
    // Total angular span of the roots is a full turn.
    const roots = arcs.filter((a) => a.depth === 1)
    const span = roots.reduce((sum, a) => sum + (a.a1 - a.a0), 0)
    expect(span).toBeCloseTo(Math.PI * 2, 6)
    // A child stays inside its parent's wedge.
    const a = arcs.find((x) => x.node.id === 'a')
    const b = arcs.find((x) => x.node.id === 'b')
    expect(b.a0).toBeGreaterThanOrEqual(a.a0 - 1e-9)
    expect(b.a1).toBeLessThanOrEqual(a.a1 + 1e-9)
  })
})

describe('squarify', () => {
  it('places every item inside the rectangle', () => {
    const rect = { x: 0, y: 0, w: 100, h: 100 }
    const items = [
      { node: 1, area: 5000 }, { node: 2, area: 3000 }, { node: 3, area: 2000 },
    ]
    const placed = squarify(items, rect)
    expect(placed).toHaveLength(3)
    for (const cell of placed) {
      expect(cell.x).toBeGreaterThanOrEqual(-1e-6)
      expect(cell.y).toBeGreaterThanOrEqual(-1e-6)
      expect(cell.x + cell.w).toBeLessThanOrEqual(100 + 1e-6)
      expect(cell.y + cell.h).toBeLessThanOrEqual(100 + 1e-6)
    }
  })
})

describe('treemap', () => {
  it('emits a leaf cell for each person plus group cells for managers', () => {
    const cells = treemap(forest, 400, 400)
    const leaves = cells.filter((c) => c.leaf).map((c) => c.node.id).sort()
    // Every one of the five people gets a clickable leaf cell.
    expect(leaves).toEqual(['a', 'b', 'c', 'd', 'e'])
    // Managers (a, b) also produce a non-leaf group cell.
    const groups = cells.filter((c) => !c.leaf).map((c) => c.node.id).sort()
    expect(groups).toEqual(['a', 'b'])
  })
})

describe('colourFor', () => {
  it('is stable for a given key', () => {
    expect(colourFor('Platform')).toBe(colourFor('Platform'))
  })
})
