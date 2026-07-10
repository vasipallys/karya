import { describe, expect, it } from 'vitest'
import { modelToMermaid, nextNodeId, parseFlowchart } from './mermaidModel'

const ARCHITECTURE = `flowchart LR
    Web["Web application"] --> API["Experience API"]
    API --> Domain["Domain services"]
    Domain --> Data[("Operational data")]
    Domain -. events .-> Bus{{"Event bus"}}
    Bus --> Analytics["Analytics platform"]`

const INFRASTRUCTURE = `flowchart TB
    User(("User")) --> Edge["CDN / WAF"]
    Edge --> LB["Load balancer"]
    subgraph cloud["Production cloud"]
      LB --> App1["App instance A"]
      LB --> App2["App instance B"]
      App1 --> DB[("Managed database")]
      App2 --> DB
    end`

describe('parseFlowchart', () => {
  it('extracts nodes, shapes, labels, edges and direction from the architecture template', () => {
    const model = parseFlowchart(ARCHITECTURE)
    expect(model.supported).toBe(true)
    expect(model.direction).toBe('LR')

    const ids = model.nodes.map((node) => node.id).sort()
    expect(ids).toEqual(['API', 'Analytics', 'Bus', 'Data', 'Domain', 'Web'])

    const byId = Object.fromEntries(model.nodes.map((node) => [node.id, node]))
    expect(byId.Web).toMatchObject({ label: 'Web application', shape: 'rect' })
    expect(byId.Data).toMatchObject({ label: 'Operational data', shape: 'cylinder' })
    expect(byId.Bus).toMatchObject({ label: 'Event bus', shape: 'hexagon' })

    expect(model.edges).toHaveLength(5)
    const labelled = model.edges.find((edge) => edge.label)
    expect(labelled).toMatchObject({ source: 'Domain', target: 'Bus', type: 'dotted', label: 'events' })
  })

  it('captures subgraph membership and circle/database shapes', () => {
    const model = parseFlowchart(INFRASTRUCTURE)
    expect(model.direction).toBe('TB')
    const user = model.nodes.find((node) => node.id === 'User')
    expect(user).toMatchObject({ label: 'User', shape: 'circle' })

    expect(model.groups).toHaveLength(1)
    expect(model.groups[0]).toMatchObject({ id: 'cloud', title: 'Production cloud' })
    expect(model.groups[0].members.sort()).toEqual(['App1', 'App2', 'DB', 'LB'])
  })

  it('marks non-flowchart diagrams as unsupported for visual editing', () => {
    const model = parseFlowchart('sequenceDiagram\n  A->>B: hi')
    expect(model.supported).toBe(false)
  })

  it('extracts expanded Mermaid v11 node shapes', () => {
    const model = parseFlowchart(`flowchart LR
      Contract@{ shape: doc, label: "API contract" } --> Link@{ shape: bolt, label: "Async channel" }
      Link --> Store@{ shape: lin-cyl, label: "Event store" }`)

    const byId = Object.fromEntries(model.nodes.map((node) => [node.id, node]))
    expect(byId.Contract).toMatchObject({ label: 'API contract', shape: 'doc' })
    expect(byId.Link).toMatchObject({ label: 'Async channel', shape: 'bolt' })
    expect(byId.Store).toMatchObject({ label: 'Event store', shape: 'lined-cylinder' })
    expect(model.edges).toHaveLength(2)
  })

  it('marks Mermaid 11 non-flowchart types as unsupported for visual editing', () => {
    expect(parseFlowchart('architecture-beta\n  service api(server)[API]').supported).toBe(false)
    expect(parseFlowchart('kanban\n  todo[Todo]').supported).toBe(false)
  })
})

describe('modelToMermaid round-trip', () => {
  it('regenerates a model that parses back to the same graph', () => {
    const first = parseFlowchart(ARCHITECTURE)
    const regenerated = modelToMermaid(first)
    const second = parseFlowchart(regenerated)

    expect(second.direction).toBe(first.direction)
    expect(second.nodes.map((n) => n.id).sort()).toEqual(first.nodes.map((n) => n.id).sort())
    expect(second.edges.map((e) => `${e.source}-${e.type}-${e.label}-${e.target}`).sort())
      .toEqual(first.edges.map((e) => `${e.source}-${e.type}-${e.label}-${e.target}`).sort())
  })

  it('preserves subgraph membership through a round-trip', () => {
    const first = parseFlowchart(INFRASTRUCTURE)
    const second = parseFlowchart(modelToMermaid(first))
    expect(second.groups[0].members.sort()).toEqual(first.groups[0].members.sort())
  })

  it('emits the middle-text form for labelled edges', () => {
    const text = modelToMermaid({
      direction: 'LR',
      nodes: [{ id: 'A', label: 'A', shape: 'rect' }, { id: 'B', label: 'B', shape: 'rect' }],
      edges: [{ id: 'e0', source: 'A', target: 'B', type: 'dotted', label: 'events' }],
      groups: [],
    })
    expect(text).toContain('A -. events .-> B')
  })

  it('emits object syntax for expanded flowchart shapes', () => {
    const text = modelToMermaid({
      direction: 'LR',
      nodes: [{ id: 'Doc', label: 'Source document', shape: 'doc' }],
      edges: [],
      groups: [],
    })
    expect(text).toContain('Doc@{ shape: doc, label: "Source document" }')
  })
})

describe('nextNodeId', () => {
  it('avoids collisions with existing ids', () => {
    const model = { nodes: [{ id: 'node1' }, { id: 'node2' }] }
    expect(nextNodeId(model)).toBe('node3')
  })
})
