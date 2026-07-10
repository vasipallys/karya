import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import DiagramStudio from './DiagramStudio'

vi.mock('@xyflow/react', () => ({
  applyEdgeChanges: (_changes, edges) => edges,
  applyNodeChanges: (_changes, nodes) => nodes,
  Background: () => null,
  Controls: () => null,
  Handle: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  Position: { Left: 'left', Right: 'right' },
  ReactFlow: ({ nodes, edges, onEdgeClick, onNodeClick, children }) => (
    <div data-testid="react-flow">
      {nodes.map((node) => <button key={node.id} type="button" onClick={() => onNodeClick?.({}, node)} aria-label={`node-${node.id}`}>{node.data.label}</button>)}
      {edges.map((edge) => <button key={edge.id} type="button" onClick={() => onEdgeClick?.({}, edge)}>{edge.id}</button>)}
      {children}
    </div>
  ),
}))

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(),
  },
}))

const diagram = {
  id: 'diagram-1',
  title: 'Architecture',
  diagram_type: 'architecture',
  mermaid_source: `flowchart LR
  A["A"] --> B["B"]`,
  metadata: { nodes: {}, positions: { A: { x: 500, y: 500 }, B: { x: 800, y: 500 } } },
}

describe('DiagramStudio', () => {
  afterEach(() => cleanup())

  it('re-layouts the graph when direction changes and saves the new source', () => {
    const onSave = vi.fn()
    render(<DiagramStudio diagram={diagram} onClose={vi.fn()} onSave={onSave} />)

    fireEvent.change(screen.getByLabelText('Direction'), { target: { value: 'TB' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      mermaid_source: expect.stringContaining('flowchart TB'),
      metadata: expect.objectContaining({ positions: {} }),
    }))
  })

  it('uses the toolbar connector selector for a selected connector', () => {
    const onSave = vi.fn()
    render(<DiagramStudio diagram={diagram} onClose={vi.fn()} onSave={onSave} />)

    fireEvent.click(screen.getByRole('button', { name: 'e0' }))
    fireEvent.change(screen.getByLabelText('Selected connector'), { target: { value: 'dotted' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      mermaid_source: expect.stringContaining('A -.-> B'),
    }))
  })

  it('shows selected node shape controls in the toolbar and saves Mermaid v11 shape syntax', () => {
    const onSave = vi.fn()
    render(<DiagramStudio diagram={diagram} onClose={vi.fn()} onSave={onSave} />)

    fireEvent.click(screen.getByRole('button', { name: 'node-A' }))
    fireEvent.change(screen.getByLabelText('Selected node shape'), { target: { value: 'cloud' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      mermaid_source: expect.stringContaining('A@{ shape: cloud, label: "A" }'),
    }))
  })

  it('adds a labelled Mermaid node and links it from the selected node', () => {
    const onSave = vi.fn()
    render(<DiagramStudio diagram={diagram} onClose={vi.fn()} onSave={onSave} />)

    fireEvent.click(screen.getByRole('button', { name: 'node-A' }))
    fireEvent.change(screen.getByLabelText('New node label'), { target: { value: 'Worker service' } })
    fireEvent.change(screen.getByLabelText('New node shape'), { target: { value: 'doc' } })
    fireEvent.click(screen.getByRole('button', { name: /add linked node/i }))
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      mermaid_source: expect.stringContaining('node3@{ shape: doc, label: "Worker service" }'),
    }))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      mermaid_source: expect.stringContaining('A --> node3'),
    }))
  })

  it('opens non-flowchart diagrams in text mode and preserves their source on save', () => {
    const onSave = vi.fn()
    const kanban = {
      ...diagram,
      title: 'Delivery board',
      diagram_type: 'kanban',
      mermaid_source: 'kanban\n  todo[Todo]\n    task1[Clarify scope]',
    }
    render(<DiagramStudio diagram={kanban} onClose={vi.fn()} onSave={onSave} />)

    expect(screen.getByLabelText('Mermaid diagram source')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Diagram name'), { target: { value: 'Updated board' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Updated board',
      diagram_type: 'kanban',
      mermaid_source: kanban.mermaid_source,
    }))
  })
})
