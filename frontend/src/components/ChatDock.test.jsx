import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { ToastProvider } from '../ui/Toast'
import ChatDock from './ChatDock'

vi.mock('../api/client', () => ({
  api: { chat: vi.fn(), chatStream: vi.fn(), chatApply: vi.fn() },
}))

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ can: () => true }),
}))

// Deterministic SpeechRecognition stub for the voice tests.
class FakeRecognition {
  static instances = []
  constructor() { FakeRecognition.instances.push(this); this.started = false }
  start() { this.started = true }
  stop() { this.onend?.() }
}

const RESULT = {
  reply: 'You have 2 element(s) at L2.',
  action: 'list',
  data: { items: [] },
  mutation: null,
  evidence: {
    retrieval: { summary: '1 L1 · 2 L2' },
    tools: [{ tool: 'rollup', summary: '0/2 stories estimated · 0 points' }],
    verdict: { sufficient: true, reason: 'planner intent resolved and deterministic evidence collected' },
  },
}

const streamScript = (events) => (id, message, history, onEvent) => {
  events.forEach(([event, data]) => onEvent(event, data))
  return Promise.resolve()
}

const fullStream = streamScript([
  ['branch', { branch: 'retrieval', facts: { summary: '1 L1 · 2 L2' } }],
  ['branch', { branch: 'tools', tool_runs: { summary: '2 tool result(s)' } }],
  ['branch', { branch: 'planner', plan: { action: 'list' } }],
  ['judge', { sufficient: true, reason: 'planner intent resolved and deterministic evidence collected' }],
  ['result', RESULT],
])

const renderDock = (props = {}) => render(
  <ToastProvider>
    <ChatDock projectId="p1" onChanged={vi.fn()} {...props} />
  </ToastProvider>,
)

const openDock = () => fireEvent.click(screen.getByRole('button', { name: 'Open assistant' }))
const type = (text) => {
  fireEvent.change(screen.getByPlaceholderText('Ask or instruct…'), { target: { value: text } })
  fireEvent.keyDown(screen.getByPlaceholderText('Ask or instruct…'), { key: 'Enter' })
}

describe('ChatDock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    FakeRecognition.instances = []
    window.SpeechRecognition = FakeRecognition
    api.chatStream.mockImplementation(fullStream)
  })
  afterEach(() => { cleanup(); delete window.SpeechRecognition })

  it('streams the concurrent agent and renders the final reply with evidence', async () => {
    renderDock()
    openDock()
    type('list L2 containers')

    await waitFor(() => expect(screen.getByText('You have 2 element(s) at L2.')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Agent evidence'))
    expect(screen.getByText(/1 L1 · 2 L2/)).toBeInTheDocument()
    expect(screen.getByText(/0\/2 stories estimated/)).toBeInTheDocument()
    expect(screen.getByText(/planner intent resolved/)).toBeInTheDocument()
  })

  it('sends the conversation history with each message', async () => {
    renderDock()
    openDock()
    type('create an L2 container')
    await waitFor(() => expect(api.chatStream).toHaveBeenCalledTimes(1))
    type('payments')
    await waitFor(() => expect(api.chatStream).toHaveBeenCalledTimes(2))

    const [, , history] = api.chatStream.mock.calls[1]
    expect(history.some((turn) => turn.role === 'user' && turn.text === 'create an L2 container')).toBe(true)
    expect(history.every((turn) => typeof turn.role === 'string' && typeof turn.text === 'string')).toBe(true)
  })

  it('falls back to the plain endpoint when streaming is unavailable', async () => {
    api.chatStream.mockRejectedValue(new Error('stream down'))
    api.chat.mockResolvedValue({ reply: 'fallback reply', action: 'help' })
    renderDock()
    openDock()
    type('hello')

    await waitFor(() => expect(screen.getByText('fallback reply')).toBeInTheDocument())
    expect(api.chat).toHaveBeenCalledWith('p1', 'hello', expect.any(Array), null, [], 'auto', null)
  })

  it('dictates a voice request straight into the chat', async () => {
    renderDock()
    openDock()

    fireEvent.click(screen.getByRole('button', { name: 'Speak your request' }))
    const rec = FakeRecognition.instances[0]
    expect(rec.started).toBe(true)

    rec.onresult({ results: [[{ transcript: 'create a payments container' }]] })
    await waitFor(() => expect(api.chatStream).toHaveBeenCalledWith(
      'p1', 'create a payments container', expect.any(Array), expect.any(Function), undefined, null, [], 'auto', null,
    ))
  })

  it('deep-links listed elements to their workspaces', async () => {
    api.chatStream.mockImplementation(streamScript([
      ['result', { reply: 'You have 1 element(s) at L2.', action: 'list', data: { items: [{ id: 'e1', level: 'L2', name: 'client-service', status: 'active' }] }, mutation: null }],
    ]))
    const onOpenElement = vi.fn()
    renderDock({ onOpenElement })
    openDock()
    type('list L2 containers')

    const link = await screen.findByRole('button', { name: 'client-service' })
    fireEvent.click(link)
    expect(onOpenElement).toHaveBeenCalledWith(expect.objectContaining({ id: 'e1', level: 'L2' }))
  })

  it('renders item-by-item readiness for a level status question', async () => {
    api.chatStream.mockImplementation(streamScript([
      ['result', {
        reply: 'L1 readiness by item averages 21%.', action: 'readiness', mutation: null,
        data: { level: 'L1', items: [
          { id: 'l1a', level: 'L1', name: 'Smart Banking', status: 'active', score: 15, status_label: 'Getting started' },
          { id: 'l1b', level: 'L1', name: 'Core CRM', status: 'active', score: 27, status_label: 'In progress' },
        ] },
      }],
    ]))
    const onOpenElement = vi.fn()
    renderDock({ onOpenElement })
    openDock()
    type('what is status of each L1 item')

    const coreCrm = await screen.findByRole('button', { name: 'Core CRM' })
    expect(screen.getByText(/15%.*Getting started/)).toBeInTheDocument()
    expect(screen.getByText(/27%.*In progress/)).toBeInTheDocument()
    fireEvent.click(coreCrm)
    expect(onOpenElement).toHaveBeenCalledWith(expect.objectContaining({ id: 'l1b', score: 27 }))
  })

  it('renders a grounded element description with a workspace link', async () => {
    api.chatStream.mockImplementation(streamScript([
      ['result', {
        reply: '**client-service** is an **L2 container** under **Smart Banking**.\n\nManages client profiles.',
        action: 'describe', mutation: null,
        data: {
          element: { id: 'l2-client', level: 'L2', name: 'client-service', status: 'active' },
          readiness: { score: 35, status_label: 'In progress' },
        },
      }],
    ]))
    const onOpenElement = vi.fn()
    renderDock({ onOpenElement })
    openDock()
    type('what is L2 client-service about')

    await screen.findByText(/Manages client profiles/)
    expect(screen.getByText(/35% ready/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /open workspace/i }))
    expect(onOpenElement).toHaveBeenCalledWith(expect.objectContaining({ id: 'l2-client', level: 'L2' }))
  })

  it('supports docked and maximized window modes', () => {
    renderDock()
    openDock()
    const dock = screen.getByRole('dialog', { name: 'Assistant' })
    expect(dock.className).toContain('mode-float')

    fireEvent.click(screen.getByRole('button', { name: 'Dock assistant to the side' }))
    expect(dock.className).toContain('mode-docked')

    fireEvent.click(screen.getByRole('button', { name: 'Maximize assistant' }))
    expect(dock.className).toContain('mode-max')

    fireEvent.click(screen.getByRole('button', { name: 'Restore assistant size' }))
    expect(dock.className).toContain('mode-float')
  })

  it('hides the mic when speech recognition is unsupported', () => {
    delete window.SpeechRecognition
    renderDock()
    openDock()

    expect(screen.queryByRole('button', { name: 'Speak your request' })).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText('Ask or instruct…')).toBeInTheDocument()
  })

  it('sends an explicit mode instead of relying on keyword detection', async () => {
    renderDock()
    openDock()
    fireEvent.click(screen.getByRole('button', { name: 'Code' }))
    fireEvent.change(screen.getByPlaceholderText('Describe code to write or review…'), { target: { value: 'make a hook' } })
    fireEvent.keyDown(screen.getByPlaceholderText('Describe code to write or review…'), { key: 'Enter' })

    await waitFor(() => expect(api.chatStream).toHaveBeenCalledWith(
      'p1', 'make a hook', expect.any(Array), expect.any(Function), undefined, null, [], 'code', null,
    ))
  })

  it('forwards the current screen context so bare reads act on the open screen', async () => {
    const screenContext = { tab: 'l2arch', tab_label: 'L2 arch', level: 'L2', element_id: 'e9' }
    renderDock({ screenContext })
    openDock()
    type('how ready is it?')

    await waitFor(() => expect(api.chatStream).toHaveBeenCalledWith(
      'p1', 'how ready is it?', expect.any(Array), expect.any(Function), undefined, null, [], 'auto', screenContext,
    ))
  })
})
