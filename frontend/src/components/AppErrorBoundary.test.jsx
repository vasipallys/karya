import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AppErrorBoundary from './AppErrorBoundary'

function Broken() {
  throw new Error('sensitive render detail')
}

afterEach(() => vi.restoreAllMocks())

it('contains render failures and offers a safe recovery action', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})

  render(<AppErrorBoundary><Broken /></AppErrorBoundary>)

  expect(screen.getByRole('alert')).toHaveTextContent('Karya couldn’t render this screen')
  expect(screen.queryByText('sensitive render detail')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reload application' })).toBeInTheDocument()
})
