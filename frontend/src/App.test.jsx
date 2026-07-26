import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./api/client', () => ({
  api: {
    config: vi.fn(() => Promise.resolve({ llm: { provider: 'mock', model: 'mock' } })),
    health: vi.fn(() => Promise.resolve({ jira: {}, llm: { errors: [] } })),
  },
}))

vi.mock('./auth/AuthContext', () => ({
  useAuth: () => ({
    user: { staff_id: null, name: 'Administrator', role: 'admin' },
    can: () => true,
    signOut: vi.fn(),
  }),
}))

vi.mock('./ui/Toast', () => ({
  useToast: () => ({ info: vi.fn(), error: vi.fn(), success: vi.fn() }),
}))

vi.mock('./screens/ProjectsHome', () => ({
  default: ({ onNavigate }) => (
    <div>
      <h1>Platforms home</h1>
      <button onClick={() => onNavigate({ kind: 'inbox', view: 'actions' })}>Open actions</button>
      <button onClick={() => onNavigate({ kind: 'admin', section: 'resources' })}>Open resources</button>
      <button onClick={() => onNavigate({ kind: 'admin', section: 'reporting', tab: 'resources' })}>Open reporting</button>
      <button onClick={() => onNavigate({ kind: 'project', id: 'p1', tab: 'planning' })}>Open project work</button>
    </div>
  ),
}))

vi.mock('./screens/HomeInbox', () => ({
  default: ({ view, onBack }) => (
    <div>
      <h1>Focused {view}</h1>
      <button onClick={onBack}>Back to Platforms</button>
    </div>
  ),
}))

vi.mock('./screens/AdminConsole', () => ({
  default: ({ initialSection, initialTab }) => <h1>Admin section: {initialSection} / {initialTab || 'default'}</h1>,
}))
vi.mock('./screens/Login', () => ({ default: () => null }))
vi.mock('./screens/NewProjectWizard', () => ({ default: () => null }))
vi.mock('./screens/ProjectWorkspace', () => ({
  default: ({ projectId, requestedTab }) => <h1>Project {projectId} / {requestedTab?.id || 'default'}</h1>,
}))
vi.mock('./screens/QuickEstimate', () => ({ default: () => null }))
vi.mock('./components/AskAiDialog', () => ({ default: () => null }))

describe('App home deep links', () => {
  afterEach(() => cleanup())

  it('opens the focused actions route and returns to Platforms', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open actions' }))
    expect(screen.getByRole('heading', { name: 'Focused actions' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Back to Platforms' }))
    expect(screen.getByRole('heading', { name: 'Platforms home' })).toBeInTheDocument()
  })

  it('passes resource deep links through to the requested Admin section', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open resources' }))
    expect(screen.getByRole('heading', { name: 'Admin section: resources / default' })).toBeInTheDocument()
  })

  it('preserves reporting sub-tabs and project workspace tabs', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open reporting' }))
    expect(screen.getByRole('heading', { name: 'Admin section: reporting / resources' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Platforms' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open project work' }))
    expect(screen.getByRole('heading', { name: 'Project p1 / planning' })).toBeInTheDocument()
  })
})
