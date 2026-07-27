import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import AiLevelDraftReview, { AI_DRAFT_SECTIONS } from './AiLevelDraftReview'

function Harness() {
  const [draft, setDraft] = useState({
    context: {
      target_level: 'L1', target_name: 'Banking', source_level: 'Project', source_name: 'Portfolio',
      inherited_items: ['Lead: Product Owner', 'L2: Existing channel'], assumptions: [],
    },
    vision_statement: 'Original vision', business_problem: 'Fragmented journeys', target_users: 'Customers',
    okrs: [], stakeholders: [],
    capabilities: [{ name: 'Payments', description: 'Move money', criticality: 'high' }],
    risks: [{ title: 'Delivery delay', category: 'delivery', risk_level: 'medium', mitigation: 'Sequence work' }],
  })
  const [selected, setSelected] = useState(AI_DRAFT_SECTIONS.L1.map((section) => section.key))
  return <>
    <AiLevelDraftReview level="L1" draft={draft} selected={selected}
      onDraftChange={setDraft} onSelectedChange={setSelected} />
    <output data-testid="selected">{selected.join(',')}</output>
  </>
}

describe('AiLevelDraftReview', () => {
  it('shows upstream evidence and supports editing, removing, and excluding draft sections', () => {
    render(<Harness />)

    expect(screen.getByText('Grounded in Project context')).toBeInTheDocument()
    expect(screen.getByText('L2: Existing channel')).toBeInTheDocument()

    fireEvent.change(screen.getByDisplayValue('Original vision'), { target: { value: 'Edited vision' } })
    expect(screen.getByDisplayValue('Edited vision')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Remove Payments' }))
    expect(screen.queryByDisplayValue('Payments')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Risks & funding' }))
    expect(screen.getByTestId('selected')).not.toHaveTextContent('risks')
  })
})
