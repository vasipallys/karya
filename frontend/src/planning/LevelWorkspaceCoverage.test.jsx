import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { ToastProvider } from '../ui/Toast'
import L3Architecture from './L3Architecture'
import L4Architecture from './L4Architecture'

vi.mock('../api/client', () => ({
  api: {
    c4Graph: vi.fn(),
    l3Workspace: vi.fn(),
    l4Workspace: vi.fn(),
  },
}))
vi.mock('../components/AiAssist', () => ({ default: () => null }))
vi.mock('../components/FlowForward', () => ({ default: () => null }))
vi.mock('../components/MermaidWorkbench', () => ({ default: () => null }))
vi.mock('../components/MermaidView', () => ({ default: () => <div data-testid="mermaid-view" /> }))

const readiness = { score: 0, status_label: 'Early draft', checklist: [], gaps: [], recommendations: [], areas: [] }

const renderWithToast = (node) => render(<ToastProvider>{node}</ToastProvider>)

describe('level workspace coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.c4Graph.mockResolvedValue({
      elements: [
        { id: 'l2-1', name: 'Payments', level: 'L2', parent_id: null },
        { id: 'l3-1', name: 'Checkout', level: 'L3', parent_id: 'l2-1' },
        { id: 'l4-1', name: 'Create payment', level: 'L4', parent_id: 'l3-1' },
      ],
    })
    api.l3Workspace.mockResolvedValue({
      element: { id: 'l3-1', name: 'Checkout' },
      parent: { id: 'l2-1', name: 'Payments' },
      arch: { summary: '', component_diagram: '', status: 'draft', raci: {} },
      components: [], interfaces: [], dependencies: [], concerns: [], behavior_views: [],
      approvals: { submitted: false, stages: [], approved_count: 0, total: 6, complete: false },
      raci_roles: [], raci_artifacts: [], readiness,
      level_definition: { level: 'L3', focus: 'Behavior', artifact: 'Feature / Story', outcomes: ['user journeys', 'sequence flows', 'BPMN', 'ERD', 'test scenarios'] },
    })
    api.l4Workspace.mockResolvedValue({
      element: { id: 'l4-1', name: 'Create payment' },
      parent: { id: 'l3-1', name: 'Checkout' },
      arch: { summary: '', code_diagram: '', status: 'draft' },
      code_units: [], test_cases: [], checklist: [], delivery_assets: [], readiness,
      level_definition: { level: 'L4', focus: 'Change', artifact: 'Task / Sub-task / PR', outcomes: ['code', 'tests', 'CI', 'reviews', 'IaC', 'release package'] },
    })
  })

  afterEach(() => cleanup())

  it('offers first-class L3 behavioral artifacts', async () => {
    renderWithToast(<L3Architecture projectId="p1" />)

    fireEvent.click(await screen.findByRole('button', { name: /Behavior models/ }))
    expect(screen.getByText('User Journeys, Sequence Flows, BPMN, ERD & Test Scenarios')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByRole('dialog', { name: 'Add behavior view' })).toBeInTheDocument()
    expect(screen.getByText('Mermaid source (optional for test scenarios)')).toBeInTheDocument()
  })

  it('offers first-class L4 delivery and release evidence', async () => {
    renderWithToast(<L4Architecture projectId="p1" />)

    fireEvent.click(await screen.findByRole('button', { name: /Delivery assets/ }))
    expect(screen.getByText('CI, Code Review, Infrastructure as Code & Release Package')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByRole('dialog', { name: 'Add delivery asset' })).toBeInTheDocument()
    expect(screen.getByText('Repository / pipeline / package URL')).toBeInTheDocument()
  })
})
