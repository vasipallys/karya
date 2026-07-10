import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import DockablePanel from './DockablePanel'

describe('DockablePanel', () => {
  beforeEach(() => window.localStorage.clear())
  afterEach(() => { cleanup(); window.localStorage.clear() })

  it('renders children at the default width', () => {
    render(<DockablePanel id="t1" title="Inspector" defaultWidth={400}><p>body</p></DockablePanel>)
    expect(screen.getByText('body')).toBeInTheDocument()
    const panel = document.querySelector('[data-dock="t1"]')
    expect(panel).toHaveStyle({ width: '400px' })
  })

  it('collapses to a reopen tab and restores', () => {
    render(<DockablePanel id="t2" title="Inspector"><p>body</p></DockablePanel>)
    fireEvent.click(screen.getByRole('button', { name: /collapse inspector/i }))
    expect(screen.queryByText('body')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /expand inspector/i }))
    expect(screen.getByText('body')).toBeInTheDocument()
  })

  it('persists collapsed state per id in localStorage', () => {
    const { unmount } = render(<DockablePanel id="t3" title="Panel"><p>body</p></DockablePanel>)
    fireEvent.click(screen.getByRole('button', { name: /collapse panel/i }))
    expect(JSON.parse(window.localStorage.getItem('sp.dock.t3')).collapsed).toBe(true)
    unmount()

    render(<DockablePanel id="t3" title="Panel"><p>body</p></DockablePanel>)
    expect(screen.queryByText('body')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /expand panel/i })).toBeInTheDocument()
  })

  it('clamps a stored width outside the allowed range', () => {
    window.localStorage.setItem('sp.dock.t4', JSON.stringify({ width: 9999, collapsed: false }))
    render(<DockablePanel id="t4" title="Panel" minWidth={200} maxWidth={500}><p>body</p></DockablePanel>)
    expect(document.querySelector('[data-dock="t4"]')).toHaveStyle({ width: '500px' })
  })
})
