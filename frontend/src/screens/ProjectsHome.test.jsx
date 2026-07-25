import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import ProjectsHome from './ProjectsHome'

vi.mock('../api/client', () => ({
  api: {
    deleteProject: vi.fn(),
    listProjects: vi.fn(),
  },
}))

// The personalised inbox has its own test; stub it here so these cases stay
// focused on the platform cards and don't need auth wiring.
vi.mock('./HomeInbox', () => ({ default: () => null }))

describe('ProjectsHome', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => cleanup())

  it('renders project leads without crashing the project card', async () => {
    api.listProjects.mockResolvedValue([
      {
        id: 'project-1',
        name: 'Payments Platform',
        description: 'Card payments and settlement.',
        created_at: '2026-01-01T00:00:00Z',
        estimated_count: 2,
        story_count: 4,
        repos: [],
        jira: [],
        leads: [
          { name: 'Siva Kumar', role: 'Engineering lead' },
          { name: 'Riya Shah', role: 'Product lead' },
        ],
      },
    ])

    render(<ProjectsHome onOpen={vi.fn()} onNew={vi.fn()} onQuick={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Payments Platform')).toBeInTheDocument())
    expect(screen.getByText('Siva Kumar +1 more')).toBeInTheDocument()
    expect(screen.getByText('SK')).toBeInTheDocument()
    expect(screen.getByText('RS')).toBeInTheDocument()
  })

  it('shows loading and lets the user retry a failed platform request', async () => {
    api.listProjects.mockRejectedValueOnce(new Error('Backend is starting'))
      .mockResolvedValueOnce([])
    render(<ProjectsHome onOpen={vi.fn()} onNew={vi.fn()} />)

    expect(screen.getByText('Loading platforms\u2026')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Backend is starting/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /Retry/ }))
    await waitFor(() => expect(screen.getByText('Start your first platform')).toBeInTheDocument())
    expect(api.listProjects).toHaveBeenCalledTimes(2)
  })

  it('offers AI scaffolding as a separate new-platform path', async () => {
    api.listProjects.mockResolvedValue([])
    const onNew = vi.fn()
    render(<ProjectsHome onOpen={vi.fn()} onNew={onNew} />)

    fireEvent.click(await screen.findByRole('button', { name: 'New platform with AI' }))

    expect(onNew).toHaveBeenCalledWith('ai')
  })
})
