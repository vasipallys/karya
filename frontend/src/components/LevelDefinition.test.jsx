import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import LevelDefinition from './LevelDefinition'

test('renders the canonical level focus, agile artifact, and required outcomes', () => {
  render(<LevelDefinition definition={{
    level: 'L3',
    focus: 'Behavior',
    artifact: 'Feature / Story',
    outcomes: ['user journeys', 'components', 'sequence flows', 'BPMN', 'ERD', 'test scenarios'],
  }} />)

  const definition = screen.getByRole('region', { name: 'L3 Behavior definition' })
  expect(definition).toHaveTextContent('Feature / Story')
  expect(definition).toHaveTextContent('user journeys')
  expect(definition).toHaveTextContent('test scenarios')
})
