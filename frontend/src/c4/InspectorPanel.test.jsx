import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '../api/client'
import InspectorPanel from './InspectorPanel'

vi.mock('../api/client', () => ({
  api: {
    l1Plan: vi.fn(),
    updateElement: vi.fn(),
    createArtifact: vi.fn(),
  },
}))

afterEach(() => cleanup())

test('shows the L1 plan summary and opens its workspace on demand', async () => {
  api.l1Plan.mockResolvedValue({
    settings: { currency_code: 'USD' },
    metrics: {
      squads: 2,
      people: 9,
      monthly_run_rate: 72000,
      planned_cost: 240000,
      at_risk_work: 1,
      allocated_fte: 8.5,
    },
    work_items: [{ id: 'work-1' }, { id: 'work-2' }],
    diagrams: [{ id: 'diagram-1' }],
  })
  const onOpenWorkspace = vi.fn()
  const element = { id: 'l1-1', level: 'L1', name: 'Digital servicing', description: 'Transform servicing', status: 'active', artifacts: [] }

  render(<InspectorPanel
    projectId="project-1"
    element={element}
    config={{ jira_write_enabled: false }}
    onOpenWorkspace={onOpenWorkspace}
    onChanged={vi.fn()}
    onDeleted={vi.fn()} />)

  const summary = screen.getByRole('region', { name: 'L1 operating plan summary' })
  await waitFor(() => expect(summary).toHaveTextContent('2 squads · 9 people'))
  expect(summary).toHaveTextContent('2 work packages · 1 at risk · 8.5 allocated FTE')
  expect(summary).toHaveTextContent('1 technical views')
  fireEvent.click(screen.getByRole('button', { name: 'Open L1 plan' }))
  expect(onOpenWorkspace).toHaveBeenCalledWith(element)
})

test.each([
  ['L2', 'L2 architecture'],
  ['L3', 'L3 architecture'],
  ['L4', 'L4 details'],
])('links a selected %s element to its owning workspace', (level, workspaceName) => {
  const onOpenWorkspace = vi.fn()
  const element = { id: `${level.toLowerCase()}-1`, level, name: `${level} element`, description: '', status: 'active', artifacts: [] }

  render(<InspectorPanel
    projectId="project-1"
    element={element}
    config={{ jira_write_enabled: false }}
    onOpenWorkspace={onOpenWorkspace}
    onChanged={vi.fn()}
    onDeleted={vi.fn()} />)

  expect(screen.getByRole('region', { name: `${workspaceName} link` })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open workspace' }))
  expect(onOpenWorkspace).toHaveBeenCalledWith(element)
})
