import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { ToastProvider } from '../ui/Toast'
import AiAssist from './AiAssist'

vi.mock('../api/client', () => ({
  api: { aiSummarize: vi.fn() },
}))

const renderAssist = (props = {}) => render(
  <ToastProvider>
    <AiAssist getSource={() => 'the details'} onResult={vi.fn()} {...props} />
  </ToastProvider>,
)

describe('AiAssist', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => cleanup())

  it('summarizes the source with the requested style and hands the result back', async () => {
    api.aiSummarize.mockResolvedValue({ summary: 'A crisp vision.' })
    const onResult = vi.fn()
    renderAssist({ field: 'vision', onResult })

    fireEvent.click(screen.getByRole('button', { name: /AI summarize/ }))

    await waitFor(() => expect(onResult).toHaveBeenCalledWith('A crisp vision.'))
    expect(api.aiSummarize).toHaveBeenCalledWith('the details', 'vision')
    expect(screen.getByText('Summary generated — review and save')).toBeInTheDocument()
  })

  it('guards an empty source with an info toast and no API call', () => {
    renderAssist({ getSource: () => '   ' })

    fireEvent.click(screen.getByRole('button', { name: /AI summarize/ }))

    expect(api.aiSummarize).not.toHaveBeenCalled()
    expect(screen.getByText('Add some details first, then summarize.')).toBeInTheDocument()
  })

  it('shows the busy label and disables itself while the request is in flight', async () => {
    let resolve
    api.aiSummarize.mockReturnValue(new Promise((r) => { resolve = r }))
    renderAssist({ busyLabel: 'Drafting…' })

    fireEvent.click(screen.getByRole('button', { name: /AI summarize/ }))

    const busyButton = await screen.findByRole('button', { name: /Drafting…/ })
    expect(busyButton).toBeDisabled()

    resolve({ summary: 'done' })
    await waitFor(() => expect(screen.getByRole('button', { name: /AI summarize/ })).toBeEnabled())
  })

  it('surfaces errors as a toast and does not call onResult', async () => {
    api.aiSummarize.mockRejectedValue(new Error('LLM offline'))
    const onResult = vi.fn()
    renderAssist({ onResult })

    fireEvent.click(screen.getByRole('button', { name: /AI summarize/ }))

    await waitFor(() => expect(screen.getByText('LLM offline')).toBeInTheDocument())
    expect(onResult).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /AI summarize/ })).toBeEnabled()
  })
})
