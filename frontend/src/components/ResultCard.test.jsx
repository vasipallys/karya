import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ResultCard from './ResultCard'

const complete = {
  points: 5,
  tldr: '5 - bounded cross-stack work using known patterns.',
  plain_language_why: 'This is a 5 because it changes the form and its existing service. It is similar to our preference anchor.',
  story: { title: 'Preference', source: 'manual' },
  scorecard: [], drivers: [], drivers_explanation: '', anchor_comparison: 'Similar to the preference anchor.',
  points_derivation: 'Bounded, known cross-stack work.', effort: null, hidden_tasks: [], risks: [], assumptions: [],
  split_recommendation: { split_recommended: false, rationale: 'Keep together.', proposed_stories: [] },
}

describe('ResultCard', () => {
  it('withholds a number when its explanation is absent', () => {
    render(<ResultCard result={{ ...complete, plain_language_why: '' }} />)
    expect(screen.queryByText('5')).not.toBeInTheDocument()
    expect(screen.getByText(/withheld/)).toBeInTheDocument()
  })

  it('renders points with the headline reason', () => {
    render(<ResultCard result={complete} />)
    expect(screen.getByText('5', { selector: '.points-block > strong' })).toBeInTheDocument()
    expect(screen.getByText(complete.tldr)).toBeInTheDocument()
  })
})
