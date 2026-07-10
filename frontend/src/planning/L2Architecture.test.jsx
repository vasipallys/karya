import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { ToastProvider } from '../ui/Toast'
import L2Architecture from './L2Architecture'

vi.mock('../api/client', () => ({
  api: {
    c4Graph: vi.fn(),
    l2Workspace: vi.fn(),
    aiSummarize: vi.fn(),
  },
}))

vi.mock('../components/MermaidView', () => ({
  default: () => <div data-testid="mermaid-stub" />,
}))

const workspace = (overrides = {}) => ({
  element: { id: 'l2-1', name: 'Checkout' },
  parent: { id: 'l1-1', name: 'Commerce' },
  arch: { container_diagram: '', summary: '', status: 'draft', raci: {} },
  containers: [{ id: 'c1', name: 'Cart API', capability: '', owner_team: '', security_classification: 'internal', nfr_criticality: 'medium', status: 'active' }],
  apis: [],
  nfrs: [],
  integrations: [],
  readiness: { score: 20, status_label: 'Early draft', checklist: [], gaps: [], recommendations: [] },
  approvals: { submitted: false, stages: [], total: 0, approved_count: 0, complete: false, current_stage: null },
  raci_roles: [],
  raci_artifacts: [],
  ...overrides,
})

const renderL2 = (props = {}) => render(
  <ToastProvider>
    <L2Architecture projectId="p1" onOpenCanvas={vi.fn()} {...props} />
  </ToastProvider>,
)

describe('L2Architecture AI draft summary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.c4Graph.mockResolvedValue({
      elements: [
        { id: 'l1-1', name: 'Commerce', level: 'L1', parent_id: null },
        { id: 'l2-1', name: 'Checkout', level: 'L2', parent_id: 'l1-1' },
        { id: 'l3-1', name: 'Payment intent API', level: 'L3', parent_id: 'l2-1' },
      ],
    })
  })
  afterEach(() => cleanup())

  it('drafts the summary from workspace context and fills the field for review', async () => {
    api.l2Workspace.mockResolvedValue(workspace())
    api.aiSummarize.mockResolvedValue({ summary: 'One paragraph.' })
    renderL2()

    const button = await screen.findByRole('button', { name: /AI draft summary/ })
    fireEvent.click(button)

    await waitFor(() => expect(api.aiSummarize).toHaveBeenCalledWith(expect.stringContaining('Cart API'), 'default'))
    expect(api.aiSummarize).toHaveBeenCalledWith(expect.stringContaining('L2 container: Checkout'), 'default')
    await waitFor(() => expect(screen.getByPlaceholderText('One-paragraph L2 architecture summary')).toHaveValue('One paragraph.'))
  })

  it('guards an empty workspace with an info toast and no API call', async () => {
    api.l2Workspace.mockResolvedValue(workspace({
      element: { id: 'l2-1', name: '' },
      containers: [],
    }))
    renderL2()

    fireEvent.click(await screen.findByRole('button', { name: /AI draft summary/ }))

    expect(api.aiSummarize).not.toHaveBeenCalled()
    expect(screen.getByText('Add containers, APIs, or a diagram first.')).toBeInTheDocument()
  })

  it('navigates up and down the hierarchy from the breadcrumb', async () => {
    api.l2Workspace.mockResolvedValue(workspace())
    const onOpenElement = vi.fn()
    renderL2({ onOpenElement })

    fireEvent.click(await screen.findByRole('button', { name: /Commerce/ }))
    expect(onOpenElement).toHaveBeenCalledWith(expect.objectContaining({ id: 'l1-1', level: 'L1' }))

    fireEvent.click(screen.getByRole('button', { name: /Payment intent API/ }))
    expect(onOpenElement).toHaveBeenCalledWith(expect.objectContaining({ id: 'l3-1', level: 'L3' }))
  })
})
