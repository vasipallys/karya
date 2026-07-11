import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { ToastProvider } from '../ui/Toast'
import FlowForward from './FlowForward'

vi.mock('../api/client', () => ({
  api: { aiDecompose: vi.fn(), applyDecompose: vi.fn() },
}))

const proposal = {
  summary: 'Two epics cover the journey',
  stories: [
    { name: 'Onboarding epic', description: 'Identity and KYC', rationale: 'From the vision' },
    { name: 'Payments epic', description: 'Initiation and screening', rationale: '' },
  ],
}

const renderBridge = (props = {}) => render(
  <ToastProvider>
    <FlowForward projectId="p1" elementId="l1-1" label="AI: draft epics from vision"
      childLabel="epics (L2)" guidance={() => 'the vision text'} {...props} />
  </ToastProvider>,
)

describe('FlowForward', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => cleanup())

  it('proposes children from upstream context and applies the selected subset', async () => {
    api.aiDecompose.mockResolvedValue(proposal)
    api.applyDecompose.mockResolvedValue({ created: 1 })
    const onApplied = vi.fn()
    renderBridge({ onApplied })

    fireEvent.click(screen.getByRole('button', { name: /draft epics from vision/ }))

    await waitFor(() => expect(screen.getByText('Onboarding epic')).toBeInTheDocument())
    expect(api.aiDecompose).toHaveBeenCalledWith('p1', 'l1-1', 'the vision text')

    // Deselect the second proposal, apply only the first.
    fireEvent.click(screen.getByText('Payments epic'))
    fireEvent.click(screen.getByRole('button', { name: /Create 1 proposed/ }))

    await waitFor(() => expect(api.applyDecompose).toHaveBeenCalledWith('p1', 'l1-1', [proposal.stories[0]]))
    expect(onApplied).toHaveBeenCalled()
    expect(screen.getByText(/Created 1 proposed epics \(L2\)/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('informs instead of opening an empty review when nothing is proposed', async () => {
    api.aiDecompose.mockResolvedValue({ summary: '', stories: [] })
    renderBridge()

    fireEvent.click(screen.getByRole('button', { name: /draft epics from vision/ }))

    await waitFor(() => expect(screen.getByText(/found nothing to propose/)).toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('surfaces proposal errors as a toast', async () => {
    api.aiDecompose.mockRejectedValue(new Error('LLM offline'))
    renderBridge()

    fireEvent.click(screen.getByRole('button', { name: /draft epics from vision/ }))

    await waitFor(() => expect(screen.getByText('LLM offline')).toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
