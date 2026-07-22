import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import NewProjectWizard from './NewProjectWizard'

vi.mock('../api/client', () => ({
  api: {
    createProject: vi.fn(),
    aiScaffold: vi.fn(),
    applyScaffold: vi.fn(),
    listStaff: vi.fn(),
  },
}))

describe('NewProjectWizard AI scaffold', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listStaff.mockResolvedValue([])
    api.createProject.mockResolvedValue({ id: 'corporate-banking' })
    api.aiScaffold.mockResolvedValue({
      summary: 'Corporate banking C4 model',
      elements: [{ ref: 'system', level: 'L1', name: 'Corporate Banking', parent_ref: null }],
      relations: [],
    })
    api.applyScaffold.mockResolvedValue({ created_elements: 11, created_relations: 3 })
  })

  afterEach(() => cleanup())

  it('creates a platform and applies an AI scaffold from the prompt', async () => {
    const onDone = vi.fn()
    render(<NewProjectWizard config={{ jira_instances: [] }} initialSeed="ai" onDone={onDone} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Platform name' }), {
      target: { value: 'Corporate Banking' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))

    expect(screen.getByRole('radio', { name: /AI scaffold/ })).toBeChecked()
    fireEvent.change(screen.getByRole('textbox', { name: 'Describe the platform for AI' }), {
      target: { value: 'Corporate banking with lending, cash management, trade finance, and treasury.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create & scaffold platform' }))

    await waitFor(() => expect(api.aiScaffold).toHaveBeenCalledWith(
      'corporate-banking',
      'Corporate banking with lending, cash management, trade finance, and treasury.',
    ))
    expect(api.applyScaffold).toHaveBeenCalledWith('corporate-banking', expect.objectContaining({ summary: 'Corporate banking C4 model' }))
    expect(onDone).toHaveBeenCalledWith('corporate-banking', 'AI scaffold added 11 elements and 3 relations as proposed.')
  })
})
