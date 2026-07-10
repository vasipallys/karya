import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api/client'
import RequirementsPlanning from './RequirementsPlanning'

vi.mock('../api/client', () => ({
  api: {
    listRequirements: vi.fn(),
    createRequirement: vi.fn(),
    getRequirement: vi.fn(),
    getRequirementVersion: vi.fn(),
    updateRequirement: vi.fn(),
    addRequirementComment: vi.fn(),
    actOnRequirementComment: vi.fn(),
    reviewRequirement: vi.fn(),
    exportRequirement: vi.fn(),
  },
}))

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({ svg: '<svg viewBox="0 0 100 80"></svg>', bindFunctions: vi.fn() }),
  },
}))

vi.mock('./DiagramStudio', () => ({
  default: ({ diagram, onSave }) => (
    <div role="dialog" aria-label="Diagram studio">
      <span>{diagram.mermaid_source}</span>
      <button type="button" onClick={() => onSave({ ...diagram, mermaid_source: 'flowchart LR\n  A --> C' })}>Apply studio changes</button>
    </div>
  ),
}))

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.listRequirements.mockResolvedValue([])
})

afterEach(() => cleanup())

test('creates a separate Markdown requirement document with an audit actor', async () => {
  api.createRequirement.mockResolvedValue({ id: 'req-1' })
  render(<RequirementsPlanning projectId="project-1" l1Id="l1-1" setError={vi.fn()} />)

  expect(await screen.findByText('Turn the initiative into reviewable requirements')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Create requirements' }))
  fireEvent.change(screen.getByLabelText('Document title'), { target: { value: 'Customer onboarding' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create document' }))

  await waitFor(() => expect(api.createRequirement).toHaveBeenCalledWith(
    'project-1',
    'l1-1',
    expect.objectContaining({
      title: 'Customer onboarding',
      actor: 'Plan contributor',
      content: expect.stringContaining('```mermaid'),
    }),
  ))
})

test('markdown toolbar wraps the selection and keeps it selected', async () => {
  const summary = { id: 'req-1', title: 'Payments requirements', version: 1, status: 'draft', open_comments: 0 }
  api.listRequirements.mockResolvedValue([summary])
  api.getRequirement.mockResolvedValue({
    ...summary,
    project_id: 'project-1',
    content: 'Authorize a payment.',
    updated_at: '2026-07-06T08:00:00Z',
    comments: [],
    versions: [],
    audit: [],
  })

  const { container } = render(<RequirementsPlanning projectId="project-1" l1Id="l1-1" setError={vi.fn()} />)

  const textarea = await waitFor(() => {
    const el = container.querySelector('.md-source-pane textarea')
    if (!el) throw new Error('editor not ready')
    return el
  })
  textarea.focus()
  textarea.setSelectionRange(0, 'Authorize'.length)
  fireEvent.click(screen.getByRole('button', { name: 'Bold' }))

  expect(textarea.value).toContain('**Authorize**')
  expect(textarea.value.slice(textarea.selectionStart, textarea.selectionEnd)).toBe('Authorize')
})

test('opens an embedded Mermaid block in Diagram Studio and writes it back to Markdown', async () => {
  const summary = { id: 'req-1', title: 'Payments requirements', version: 1, status: 'draft', open_comments: 0 }
  api.listRequirements.mockResolvedValue([summary])
  api.getRequirement.mockResolvedValue({
    ...summary,
    project_id: 'project-1',
    content: '# Flow\n\n```mermaid\nflowchart LR\n  A --> B\n```\n',
    updated_at: '2026-07-06T08:00:00Z',
    comments: [],
    versions: [],
    audit: [],
  })
  api.updateRequirement.mockResolvedValue({
    ...summary,
    project_id: 'project-1',
    content: '# Flow\n\n```mermaid\nflowchart LR\n  A --> C\n```\n',
    updated_at: '2026-07-06T08:05:00Z',
    comments: [],
    versions: [],
    audit: [],
  })

  render(<RequirementsPlanning projectId="project-1" l1Id="l1-1" setError={vi.fn()} />)

  fireEvent.click(await screen.findByRole('button', { name: 'Edit in Diagram Studio' }))
  expect(screen.getByRole('dialog', { name: 'Diagram studio' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Apply studio changes' }))
  fireEvent.click(screen.getByRole('button', { name: /Save version/ }))

  await waitFor(() => expect(api.updateRequirement).toHaveBeenCalledWith(
    'project-1',
    'req-1',
    expect.objectContaining({
      content: expect.stringContaining('A --> C'),
    }),
  ))
})

test('shows review state, comments, and audit-preserved versions', async () => {
  const summary = {
    id: 'req-1',
    title: 'Payments requirements',
    version: 2,
    status: 'in_review',
    open_comments: 1,
  }
  api.listRequirements.mockResolvedValue([summary])
  api.getRequirement.mockResolvedValue({
    ...summary,
    project_id: 'project-1',
    content: '# Scope\n\nAuthorize a payment.',
    updated_at: '2026-07-06T08:00:00Z',
    comments: [{
      id: 'comment-1',
      author: 'Reviewer',
      body: 'Add the recovery path.',
      status: 'open',
      document_version: 2,
      created_at: '2026-07-06T08:10:00Z',
      acted_by: null,
      acted_at: null,
    }],
    versions: [{ id: 'version-2', version: 2, title: 'Payments requirements', changed_by: 'Owner', change_summary: 'Added scope' }],
    audit: [{ id: 'audit-1', event_type: 'document_updated', actor: 'Owner', document_version: 2, created_at: '2026-07-06T08:00:00Z', detail: {} }],
  })

  render(<RequirementsPlanning projectId="project-1" l1Id="l1-1" setError={vi.fn()} />)

  expect(await screen.findByText('Add the recovery path.')).toBeInTheDocument()
  expect(screen.getByText('in review')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Approve document/ })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Audit' }))
  expect(screen.getByRole('button', { name: /v2 Added scope Owner/ })).toBeInTheDocument()
  expect(screen.getByText('document updated')).toBeInTheDocument()
})
