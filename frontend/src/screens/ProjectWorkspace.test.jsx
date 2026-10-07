import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProjectWorkspace from './ProjectWorkspace'

// a (L1) ─┬─ b (L2)
//         └─ c (L2) ── d (L3) ── e (L4)
const elements = [
  { id: 'a', level: 'L1', name: 'Bank', parent_id: null },
  { id: 'b', level: 'L2', name: 'Cards', parent_id: 'a' },
  { id: 'c', level: 'L2', name: 'Loans', parent_id: 'a' },
  { id: 'd', level: 'L3', name: 'Apply', parent_id: 'c' },
  { id: 'e', level: 'L4', name: 'Form', parent_id: 'd' },
]

vi.mock('../api/client', () => ({
  api: {
    getProject: vi.fn(() => Promise.resolve({ id: 'p1', name: 'Bank platform', repos: [], jira: [], leads: [] })),
    c4Graph: vi.fn(() => Promise.resolve({ elements, relations: [] })),
  },
}))

// Each level workspace mock reports its pick back, like the real ones do.
function levelMock(label, requestedKey, selectKey) {
  return function LevelMock(props) {
    const requested = props[requestedKey]
    const onSelect = props[selectKey]
    useEffect(() => { if (requested) onSelect?.(requested) }, [requested, onSelect])
    return <p>{label} on {requested || 'none'}</p>
  }
}

vi.mock('../planning/L1Planning', () => ({ default: levelMock('L1', 'requestedL1Id', 'onL1Change') }))
vi.mock('../planning/L2Architecture', () => ({ default: levelMock('L2', 'requestedId', 'onSelect') }))
vi.mock('../planning/L3Architecture', () => ({ default: levelMock('L3', 'requestedId', 'onSelect') }))
vi.mock('../planning/L4Architecture', () => ({ default: levelMock('L4', 'requestedId', 'onSelect') }))
vi.mock('../c4/C4Canvas', () => ({ default: ({ requestedElement }) => <p>Canvas on {requestedElement?.id || 'root'}</p> }))
vi.mock('../c4/RollupDashboard', () => ({ default: () => <p>Rollup</p> }))
vi.mock('../components/ChatDock', () => ({ default: () => null }))
vi.mock('./QuickEstimate', () => ({ default: () => null }))
vi.mock('./WorkflowWizard', () => ({ default: () => null }))

const rail = (name) => fireEvent.click(screen.getByRole('button', { name }))

describe('ProjectWorkspace cross-level navigation', () => {
  afterEach(() => cleanup())

  it('keeps every level tab on the focused branch', async () => {
    const onLocationChange = vi.fn()
    render(<ProjectWorkspace projectId="p1" requestedTab={{ id: 'l3arch', elementId: 'd' }} onLocationChange={onLocationChange} />)
    expect(await screen.findByText('L3 on d')).toBeInTheDocument()
    expect(onLocationChange).toHaveBeenLastCalledWith({ tab: 'l3arch', elementId: 'd' })

    rail('L2 arch')       // d's parent, not the L1's first L2 (b)
    expect(await screen.findByText('L2 on c')).toBeInTheDocument()

    rail('L4 detail')     // c's descendant task
    expect(await screen.findByText('L4 on e')).toBeInTheDocument()

    rail('L1 plan')
    expect(await screen.findByText('L1 on a')).toBeInTheDocument()

    rail('L2 arch')       // back down to the L2 we came from, not the first child
    expect(await screen.findByText('L2 on c')).toBeInTheDocument()

    rail('C4 canvas')     // canvas re-centres on what we were looking at
    expect(await screen.findByText('Canvas on c')).toBeInTheDocument()
    expect(onLocationChange).toHaveBeenLastCalledWith({ tab: 'canvas', elementId: 'c' })
  })
})
