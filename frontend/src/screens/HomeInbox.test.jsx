import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import HomeInbox from './HomeInbox'

vi.mock('../api/client', () => ({ api: { homeInbox: vi.fn() } }))

let mockUser = { staff_id: 'u1', name: 'Evan Dev', role: 'contributor' }
let mockCan = () => true
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: mockUser, can: (cap) => mockCan(cap) }) }))

const dashboard = {
  scope: 'personal',
  user: { staff_id: 'u1', name: 'Evan Dev', role: 'contributor', rank: 'Engineer', tech_unit: 'Platform' },
  summary: {
    tasks_open: 2, tasks_total: 3, at_risk: 1, overdue: 1, actions: 3,
    squads: 1, tribes: 1, projects: 1, stories: 2, points: 10, allocation: 80, reports: 0, bench_reports: 0,
  },
  tasks: [
    { id: 't1', title: 'Build refund', status: 'at_risk', squad_name: 'Refund Squad', project_id: 'p1', project_name: 'Payments', points: 5, due_in_days: 40, overdue: false },
    { id: 't2', title: 'Payout API', status: 'in_progress', squad_name: 'Refund Squad', project_id: 'p1', l1_id: 'l1-pay', project_name: 'Payments', points: 3, due_in_days: -3, overdue: true },
  ],
  actions: [
    { id: 'a1', type: 'at_risk_work', severity: 'high', title: 'Build refund', detail: 'At-risk work in Refund Squad', project_id: 'p1', project_name: 'Payments', category: 'work' },
    { id: 'a2', type: 'okr_off_track', severity: 'high', title: 'Cut latency', detail: 'OKR off track · you are the owner', project_id: 'p1', l1_id: 'l1-pay', project_name: 'Payments', category: 'okr' },
    { id: 'a3', type: 'open_comment', severity: 'low', title: 'Confirm rollback', detail: 'Open review comment · Payments', project_id: 'p1', project_name: 'Payments', category: 'comment' },
  ],
}

describe('HomeInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUser = { staff_id: 'u1', name: 'Evan Dev', role: 'contributor' }
    mockCan = () => true
  })
  afterEach(() => cleanup())

  it('greets the user and renders tasks and actions', async () => {
    api.homeInbox.mockResolvedValue(dashboard)
    render(<HomeInbox onNavigate={vi.fn()} />)

    await waitFor(() => expect(screen.getByText(/Evan/)).toBeInTheDocument())
    expect(screen.getByText('Payout API')).toBeInTheDocument()
    expect(screen.getByText('Overdue by 3d')).toBeInTheDocument()
    expect(screen.getByText('Cut latency')).toBeInTheDocument()
    expect(screen.getByText(/you are the owner/)).toBeInTheDocument()
  })

  it('deep-links a task to its own L1 initiative plan', async () => {
    api.homeInbox.mockResolvedValue(dashboard)
    const onNavigate = vi.fn()
    render(<HomeInbox onNavigate={onNavigate} />)

    fireEvent.click(await screen.findByText('Payout API'))
    expect(onNavigate).toHaveBeenCalledWith({ kind: 'project', id: 'p1', tab: 'planning', elementId: 'l1-pay' })
  })

  it.each([
    ['Open tasks', 'work'],
    ['Actions pending', 'actions'],
    ['At risk', 'at_risk'],
    ['Overdue', 'overdue'],
  ])('opens a real focused page from the %s metric', async (label, view) => {
    api.homeInbox.mockResolvedValue(dashboard)
    const onNavigate = vi.fn()
    render(<HomeInbox onNavigate={onNavigate} />)

    const tile = await screen.findByTitle(
      label === 'Open tasks' ? 'Open your tasks'
        : label === 'Actions pending' ? 'Open pending actions'
          : label === 'At risk' ? 'Open at-risk work' : 'Open overdue work',
    )
    fireEvent.click(tile)
    expect(onNavigate).toHaveBeenCalledWith({ kind: 'inbox', view })
  })

  it('renders the focused pending-actions page and preserves row navigation', async () => {
    api.homeInbox.mockResolvedValue(dashboard)
    const onNavigate = vi.fn()
    const onBack = vi.fn()
    render(<HomeInbox view="actions" onNavigate={onNavigate} onBack={onBack} />)

    expect(await screen.findByRole('heading', { name: 'Actions pending', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Cut latency')).toBeInTheDocument()
    expect(screen.queryByText('Payout API')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Cut latency'))
    expect(onNavigate).toHaveBeenCalledWith({ kind: 'project', id: 'p1', tab: 'planning', elementId: 'l1-pay' })
    fireEvent.click(screen.getByRole('button', { name: /Back to Platforms/ }))
    expect(onBack).toHaveBeenCalled()
  })

  it('opens complete task and action views from the panel headers', async () => {
    api.homeInbox.mockResolvedValue(dashboard)
    const onNavigate = vi.fn()
    render(<HomeInbox onNavigate={onNavigate} />)

    const links = await screen.findAllByRole('button', { name: /View all/ })
    fireEvent.click(links[0])
    expect(onNavigate).toHaveBeenCalledWith({ kind: 'inbox', view: 'tasks' })
    fireEvent.click(links[1])
    expect(onNavigate).toHaveBeenCalledWith({ kind: 'inbox', view: 'actions' })
  })

  it('filters at-risk and overdue detail pages correctly', async () => {
    api.homeInbox.mockResolvedValue(dashboard)
    const { rerender } = render(<HomeInbox view="at_risk" onNavigate={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'At-risk work', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Build refund')).toBeInTheDocument()
    expect(screen.queryByText('Payout API')).not.toBeInTheDocument()

    rerender(<HomeInbox view="overdue" onNavigate={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'Overdue work', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Payout API')).toBeInTheDocument()
    expect(screen.queryByText('Build refund')).not.toBeInTheDocument()
  })

  it('deep-links the Squads tile to reporting when the user may see it', async () => {
    api.homeInbox.mockResolvedValue(dashboard)
    const onNavigate = vi.fn()
    render(<HomeInbox onNavigate={onNavigate} />)

    const squads = (await screen.findByText('Squads')).closest('button')
    expect(squads).not.toBeNull()
    fireEvent.click(squads)
    expect(onNavigate).toHaveBeenCalledWith({ kind: 'admin', section: 'reporting', tab: 'resources' })
  })

  it('does not make admin-targeted tiles clickable without the capability', async () => {
    mockCan = (cap) => cap === 'page.workspace' // no admin caps
    api.homeInbox.mockResolvedValue(dashboard)
    render(<HomeInbox onNavigate={vi.fn()} />)

    await screen.findByText(/Evan/)
    // Squads points at reporting; without admin.reporting it stays a plain tile.
    expect(screen.getByText('Squads').closest('button')).toBeNull()
    expect(screen.getByText('Allocation').closest('button')).toBeNull()
  })

  it('deep-links the org bench action to the resource directory', async () => {
    mockUser = { staff_id: null, name: 'Administrator', role: 'admin' }
    const onNavigate = vi.fn()
    api.homeInbox.mockResolvedValue({
      scope: 'organization',
      user: { staff_id: null, name: 'Administrator', role: 'admin', rank: 'Platform admin', tech_unit: 'All platforms' },
      summary: { tasks_open: 0, tasks_total: 0, at_risk: 0, overdue: 0, actions: 1, projects: 2, squads: 0, resources: 45, on_bench: 45 },
      tasks: [], tasks_truncated: 0,
      actions: [{ id: 'org-bench', type: 'bench_pool', severity: 'medium', title: '45 resources unallocated', detail: 'People with no team allocation', project_id: null, project_name: null, category: 'team' }],
      actions_truncated: 0,
    })
    render(<HomeInbox onNavigate={onNavigate} />)

    fireEvent.click(await screen.findByText('45 resources unallocated'))
    expect(onNavigate).toHaveBeenCalledWith({ kind: 'admin', section: 'resources' })
  })

  it('shows caught-up empty states when nothing is pending', async () => {
    api.homeInbox.mockResolvedValue({
      ...dashboard,
      summary: { ...dashboard.summary, tasks_open: 0, actions: 0 },
      tasks: [],
      actions: [],
    })
    render(<HomeInbox onNavigate={vi.fn()} />)

    expect(await screen.findByText('No tasks assigned to your squads.')).toBeInTheDocument()
    expect(screen.getByText("You're all caught up.")).toBeInTheDocument()
  })

  it('renders nothing and skips the API when signed out', async () => {
    mockUser = null
    const { container } = render(<HomeInbox onNavigate={vi.fn()} />)
    await waitFor(() => expect(container.querySelector('.home-inbox')).toBeNull())
    expect(api.homeInbox).not.toHaveBeenCalled()
  })

  it('renders an organization overview for the identity-less bootstrap admin', async () => {
    mockUser = { staff_id: null, name: 'Administrator', role: 'admin' }
    api.homeInbox.mockResolvedValue({
      scope: 'organization',
      user: { staff_id: null, name: 'Administrator', role: 'admin', rank: 'Platform admin', tech_unit: 'All platforms' },
      summary: { tasks_open: 0, tasks_total: 0, at_risk: 0, overdue: 0, actions: 1, projects: 2, squads: 0, resources: 45, on_bench: 45 },
      tasks: [], tasks_truncated: 0,
      actions: [{ id: 'org-bench', type: 'bench_pool', severity: 'medium', title: '45 resources unallocated', detail: 'People with no team allocation', project_id: null, project_name: null, category: 'team' }],
      actions_truncated: 0,
    })
    render(<HomeInbox onNavigate={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Organization overview')).toBeInTheDocument())
    expect(api.homeInbox).toHaveBeenCalled()
    expect(screen.getByText('45 resources unallocated')).toBeInTheDocument()
    expect(screen.getByText('No open work items across platforms.')).toBeInTheDocument()
  })

  it('recovers from a failed load via Retry', async () => {
    api.homeInbox.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(dashboard)
    render(<HomeInbox onNavigate={vi.fn()} />)

    await waitFor(() => expect(screen.getByText(/could not be loaded/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /Retry/ }))
    await waitFor(() => expect(screen.getByText('Payout API')).toBeInTheDocument())
  })
})
