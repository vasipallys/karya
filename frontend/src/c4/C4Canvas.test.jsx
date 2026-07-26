import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import C4Canvas from './C4Canvas'

vi.mock('../api/client', () => ({
  api: { c4Graph: vi.fn(), aiScaffold: vi.fn(), applyScaffold: vi.fn() },
}))

vi.mock('@xyflow/react', () => ({
  applyNodeChanges: (_changes, nodes) => nodes,
  Background: () => null,
  Controls: () => null,
  Handle: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  Position: { Left: 'left', Right: 'right' },
  ReactFlow: ({ nodes, children }) => <div data-testid="react-flow">
    {nodes.map((node) => <span key={node.id}>{node.data.element.name}</span>)}
    {children}
  </div>,
}))

vi.mock('./InspectorPanel', () => ({ default: ({ element }) => <div>Inspector: {element?.name || 'none'}</div> }))
vi.mock('./EstimateDialog', () => ({ default: () => null }))

describe('C4Canvas navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.aiScaffold.mockReset()
    api.c4Graph.mockResolvedValue({
      elements: [
        { id: 'l1-1', parent_id: null, level: 'L1', name: 'Smart Banking', status: 'active', artifacts: [] },
      ],
      relations: [],
    })
  })

  afterEach(() => cleanup())

  it('keeps the root nodes visible when System landscape is clicked at the root', async () => {
    render(<C4Canvas projectId="project-1" config={{}} />)

    expect(await screen.findByText('Smart Banking')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'System landscape' }))

    expect(screen.getByText('Smart Banking')).toBeInTheDocument()
  })

  it('restores the full drill path and selection for a requested nested element', async () => {
    api.c4Graph.mockResolvedValue({
      elements: [
        { id: 'l1-1', parent_id: null, level: 'L1', name: 'Banking', status: 'active', artifacts: [] },
        { id: 'l2-1', parent_id: 'l1-1', level: 'L2', name: 'Payments', status: 'active', artifacts: [] },
        { id: 'l3-1', parent_id: 'l2-1', level: 'L3', name: 'Payment orchestration', status: 'active', artifacts: [] },
      ],
      relations: [],
    })

    render(<C4Canvas projectId="project-1" config={{}} requestedElement={{ id: 'l3-1' }} />)

    expect(await screen.findByText('Inspector: Payment orchestration')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('react-flow')).toHaveTextContent('Payment orchestration'))
    expect(screen.getByText('Payments')).toHaveClass('current')
    expect(screen.getByRole('button', { name: 'Banking' })).toBeInTheDocument()
  })

  it('shows scaffold generation failures inside the open dialog', async () => {
    api.aiScaffold.mockRejectedValue(new Error('The configured LLM request failed.'))
    render(<C4Canvas projectId="project-1" config={{}} />)

    fireEvent.click(await screen.findByRole('button', { name: 'AI scaffold' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Describe the system' }), {
      target: { value: 'A corporate banking platform' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The configured LLM request failed.')
    expect(screen.getByRole('dialog', { name: 'AI scaffold' })).toBeInTheDocument()
  })
})
