import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LevelBreadcrumb from './LevelBreadcrumb'

const elements = [
  { id: 'l1', name: 'Smart Banking', level: 'L1', parent_id: null },
  { id: 'l2', name: 'client-service', level: 'L2', parent_id: 'l1' },
  { id: 'l3', name: 'Client profile API', level: 'L3', parent_id: 'l2' },
  { id: 'l4a', name: 'ClientController', level: 'L4', parent_id: 'l3' },
  { id: 'l4b', name: 'Outbox publisher', level: 'L4', parent_id: 'l3' },
  { id: 'other-l2', name: 'messaging-service', level: 'L2', parent_id: 'l1' },
]

describe('LevelBreadcrumb', () => {
  afterEach(() => cleanup())

  it('renders the full ancestor trail and navigates up on click', () => {
    const onNavigate = vi.fn()
    render(<LevelBreadcrumb elements={elements} elementId="l3" onNavigate={onNavigate} />)

    expect(screen.getByRole('navigation', { name: 'Level navigation' })).toBeInTheDocument()
    // Ancestors are clickable, the current element is not.
    fireEvent.click(screen.getByRole('button', { name: /Smart Banking/ }))
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ id: 'l1', level: 'L1' }))
    fireEvent.click(screen.getByRole('button', { name: /client-service/ }))
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ id: 'l2', level: 'L2' }))
    expect(screen.queryByRole('button', { name: /Client profile API/ })).not.toBeInTheDocument()
    expect(screen.getByText('Client profile API')).toBeInTheDocument()
  })

  it('offers drill-down chips for children and navigates down on click', () => {
    const onNavigate = vi.fn()
    render(<LevelBreadcrumb elements={elements} elementId="l3" onNavigate={onNavigate} />)

    expect(screen.getByText('Drill down')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Outbox publisher/ }))
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ id: 'l4b', level: 'L4' }))
  })

  it('shows drill-down without ancestors at the top level', () => {
    render(<LevelBreadcrumb elements={elements} elementId="l1" onNavigate={vi.fn()} />)

    expect(screen.getByRole('button', { name: /client-service/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /messaging-service/ })).toBeInTheDocument()
    // L1 has no parents — only the current crumb plus children.
    expect(screen.getByText('Smart Banking')).toBeInTheDocument()
  })

  it('renders nothing for an unknown element or one with no relatives', () => {
    const { container } = render(<LevelBreadcrumb elements={elements} elementId="missing" onNavigate={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()

    const lonely = [{ id: 'solo', name: 'External CRM', level: 'L1', parent_id: null }]
    const { container: lonelyContainer } = render(<LevelBreadcrumb elements={lonely} elementId="solo" onNavigate={vi.fn()} />)
    expect(lonelyContainer).toBeEmptyDOMElement()
  })
})
