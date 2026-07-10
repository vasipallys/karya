import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import ProjectsHome from './ProjectsHome'

vi.mock('../api/client', () => ({
  api: {
    deleteProject: vi.fn(),
    listProjects: vi.fn(),
  },
}))

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
})
