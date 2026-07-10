import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import RollupDashboard from './RollupDashboard'

vi.mock('../api/client', () => ({
  api: { rollup: vi.fn(), estimateElement: vi.fn() },
}))

const rollupData = {
  totals: { rolled_up_points: 5, estimated_stories: 1, unestimated_stories: 0, spikes: 0, pending_splits: 0 },
  tree: [{
    element: { id: 'e1', name: 'Payments', level: 'L2', status: 'active' },
    artifact: null,
    summary: { rolled_up_points: 5, estimated_stories: 1, unestimated_stories: 0, spikes: 0, pending_splits: 0 },
    children: [],
  }],
}

describe('RollupDashboard deep-linking', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.rollup.mockResolvedValue(rollupData)
  })
  afterEach(() => cleanup())

  it('navigates to the element workspace when a row name is clicked', async () => {
    const onNavigate = vi.fn()
    render(<RollupDashboard projectId="p1" onNavigate={onNavigate} />)

    const row = await screen.findByRole('button', { name: 'Payments' })
    fireEvent.click(row)

    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ id: 'e1', level: 'L2', name: 'Payments' }))
  })

  it('does not crash when no navigation handler is provided', async () => {
    render(<RollupDashboard projectId="p1" />)

    const row = await screen.findByRole('button', { name: 'Payments' })
    expect(() => fireEvent.click(row)).not.toThrow()
    await waitFor(() => expect(screen.getByText('Payments')).toBeInTheDocument())
  })
})
