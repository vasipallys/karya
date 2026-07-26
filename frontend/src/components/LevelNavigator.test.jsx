import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LevelNavigator, { relatedTarget } from './LevelNavigator'

const elements = [
  { id: 'l1-a', level: 'L1', name: 'Payments', parent_id: null },
  { id: 'l2-a', level: 'L2', name: 'Checkout', parent_id: 'l1-a' },
  { id: 'l3-a', level: 'L3', name: 'Authorize payment', parent_id: 'l2-a' },
  { id: 'l4-a', level: 'L4', name: 'Implement authorize', parent_id: 'l3-a' },
  { id: 'l1-b', level: 'L1', name: 'Lending', parent_id: null },
  { id: 'l2-b', level: 'L2', name: 'Origination', parent_id: 'l1-b' },
]

describe('LevelNavigator', () => {
  it('resolves ancestors and descendants from the current hierarchy', () => {
    expect(relatedTarget(elements, 'l3-a', 'L1')?.id).toBe('l1-a')
    expect(relatedTarget(elements, 'l1-a', 'L4')?.id).toBe('l4-a')
    expect(relatedTarget(elements, 'l2-b', 'L3')?.id).toBe('l3-a')
  })

  it('navigates to C4 and the related level while marking the current level', () => {
    const onNavigate = vi.fn()
    const onOpenCanvas = vi.fn()
    render(<LevelNavigator elements={elements} elementId="l3-a" activeLevel="L3"
      onNavigate={onNavigate} onOpenCanvas={onOpenCanvas} />)

    expect(screen.getByRole('button', { name: /Behavior.*Authorize payment/i })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Value.*Payments/i }))
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ id: 'l1-a' }))
    fireEvent.click(screen.getByRole('button', { name: /C4.*Canvas/i }))
    expect(onOpenCanvas).toHaveBeenCalledWith('l3-a')
  })

  it('disables levels that have not been created', () => {
    render(<LevelNavigator elements={elements.filter((element) => element.level !== 'L4')}
      elementId="l2-a" activeLevel="L2" />)
    expect(screen.getByRole('button', { name: /Change.*Not created/i })).toBeDisabled()
  })
})
