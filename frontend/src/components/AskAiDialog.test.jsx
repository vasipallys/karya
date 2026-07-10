import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { ToastProvider } from '../ui/Toast'
import AskAiDialog from './AskAiDialog'

vi.mock('../api/client', () => ({
  api: { aiOrchestrate: vi.fn() },
}))

const renderDialog = (props = {}) => render(
  <ToastProvider>
    <AskAiDialog onClose={vi.fn()} onNavigate={vi.fn()} {...props} />
  </ToastProvider>,
)

const type = (text) => fireEvent.change(screen.getByPlaceholderText(/break the checkout epic/), { target: { value: text } })

describe('AskAiDialog', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => cleanup())

  it('keeps Ask disabled until a request is typed', () => {
    renderDialog()
    const ask = screen.getByRole('button', { name: /Ask$/ })
    expect(ask).toBeDisabled()
    type('split the epic')
    expect(ask).toBeEnabled()
  })

  it('routes the request and offers to take the user to the workspace', async () => {
    api.aiOrchestrate.mockResolvedValue({ action: 'decompose_story', rationale: 'The story is large', suggested_prompt: 'Split checkout into stories' })
    const onNavigate = vi.fn()
    const onClose = vi.fn()
    renderDialog({ onNavigate, onClose })

    type('split the epic')
    fireEvent.click(screen.getByRole('button', { name: /Ask$/ }))

    await waitFor(() => expect(screen.getByText(/The story is large/)).toBeInTheDocument())
    expect(api.aiOrchestrate).toHaveBeenCalledWith('split the epic')
    expect(screen.getByText('Decompose a story')).toBeInTheDocument()
    expect(screen.getByText('Split checkout into stories')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Take me there/ }))
    expect(onNavigate).toHaveBeenCalledWith('decompose_story')
    expect(onClose).toHaveBeenCalled()
  })

  it('shows a hint instead of navigation when no action matches', async () => {
    api.aiOrchestrate.mockResolvedValue({ action: 'none', rationale: 'Unclear request', suggested_prompt: '' })
    renderDialog()

    type('do something vague')
    fireEvent.click(screen.getByRole('button', { name: /Ask$/ }))

    await waitFor(() => expect(screen.getByText(/Unclear request/)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Take me there/ })).not.toBeInTheDocument()
    expect(screen.getByText(/No specific workspace action/)).toBeInTheDocument()
  })

  it('keeps the dialog open and toasts on error', async () => {
    api.aiOrchestrate.mockRejectedValue(new Error('LLM offline'))
    renderDialog()

    type('split the epic')
    fireEvent.click(screen.getByRole('button', { name: /Ask$/ }))

    await waitFor(() => expect(screen.getByText('LLM offline')).toBeInTheDocument())
    expect(screen.getByRole('dialog', { name: 'Ask AI' })).toBeInTheDocument()
  })
})
