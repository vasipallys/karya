import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    aiL4Baseline: vi.fn(),
    applyL4Baseline: vi.fn(),
    l4ImplementationSummary: vi.fn(),
    l4Traceability: vi.fn(),
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

    fireEvent.click(await screen.findByRole('button', { name: /Deliverables/ }))
    expect(screen.getByText('Deliverables: CI, Code Review, Infrastructure as Code & Release Package')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByRole('dialog', { name: 'Add delivery asset' })).toBeInTheDocument()
    expect(screen.getByText('Repository / pipeline / package URL')).toBeInTheDocument()
  })

  it('generates the complete L4 plan from the implementation diagram and opens the final summary', async () => {
    const diagram = 'classDiagram\n  class PaymentController\n  class PaymentService\n  PaymentController --> PaymentService'
    api.l4Workspace.mockResolvedValue({
      element: { id: 'l4-1', name: 'Create payment' },
      parent: { id: 'l3-1', name: 'Checkout' },
      arch: { summary: '', code_diagram: diagram, status: 'draft' },
      code_units: [], test_cases: [], checklist: [], delivery_assets: [], readiness,
      level_definition: { level: 'L4', focus: 'Change', artifact: 'Task / Sub-task / PR', outcomes: ['code', 'tests', 'CI', 'reviews', 'IaC', 'release package'] },
    })
    api.aiL4Baseline.mockResolvedValue({
      summary: 'Diagram-derived plan',
      code_diagram: diagram,
      code_units: [{ name: 'PaymentController', unit_type: 'class', tech: 'Java', path: 'src/PaymentController.java' }],
      test_cases: [{ name: 'creates payment', test_type: 'integration', scenario: 'Valid request', expected: 'Payment created' }],
      delivery_assets: [{ name: 'CI pipeline', asset_type: 'ci_pipeline', location: '.github/workflows/ci.yml' }],
      checklist: [{ item: 'Tests pass', category: 'tests' }],
      traceability_mermaid: 'flowchart LR\n L2 --> L3\n L3 --> L4',
      implementation_summary: '# Proposed implementation\n\n## Proposed Code Units',
    })
    api.applyL4Baseline.mockResolvedValue({ summary: 1, code_units: 1, test_cases: 1, delivery_assets: 1, checklist: 1 })
    api.l4ImplementationSummary.mockResolvedValue({ markdown: '# Final implementation summary' })
    api.l4Traceability.mockResolvedValue({ mermaid: 'flowchart LR\n L2 --> L3 --> L4' })

    renderWithToast(<L4Architecture projectId="p1" />)

    const generateButton = await screen.findByRole('button', { name: 'AI generate from diagram' })
    await waitFor(() => expect(generateButton).toBeEnabled())
    fireEvent.click(generateButton)
    await waitFor(() => expect(api.aiL4Baseline).toHaveBeenCalledWith('p1', 'l4-1', '', diagram))
    expect(await screen.findByRole('dialog', { name: 'AI L4 context-grounded draft' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('PaymentController')).toBeInTheDocument()
    expect(screen.getByDisplayValue('creates payment')).toBeInTheDocument()
    expect(screen.getByDisplayValue('CI pipeline')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Tests pass')).toBeInTheDocument()
    expect(screen.getByText('Validated traceability')).toBeInTheDocument()
    expect(screen.getByText('Implementation summary preview')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save selected as draft' }))
    await waitFor(() => expect(api.applyL4Baseline).toHaveBeenCalledWith(
      'p1', 'l4-1', expect.any(Object), ['summary', 'code_units', 'test_cases', 'delivery_assets', 'checklist'], false,
    ))
    await waitFor(() => expect(api.l4ImplementationSummary).toHaveBeenCalledWith('p1', 'l4-1'))
    expect(await screen.findByText('Final implementation summary')).toBeInTheDocument()
  })
})
