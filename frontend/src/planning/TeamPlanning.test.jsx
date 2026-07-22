import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '../api/client'
import TeamPlanning from './TeamPlanning'

vi.mock('../api/client', () => ({
  api: {
    listStaff: vi.fn(() => Promise.resolve([])),
    createStaff: vi.fn(),
    createAgileUnit: vi.fn(),
    updateAgileUnit: vi.fn(),
    deleteAgileUnit: vi.fn(),
    createTeamMember: vi.fn(),
    updateTeamMember: vi.fn(),
    deleteTeamMember: vi.fn(),
  },
}))

const money = (value) => `$${Math.round(value || 0).toLocaleString()}`

afterEach(() => cleanup())

const basePlan = {
  units: [
    {
      id: 'tribe-1',
      unit_type: 'tribe',
      parent_unit_id: null,
      name: 'Digital Commerce',
      mission: 'Own checkout modernization',
      lead_name: 'Priya',
      capacity_fte: 1,
      target_velocity: 0,
      members: [],
    },
    {
      id: 'squad-1',
      unit_type: 'squad',
      parent_unit_id: 'tribe-1',
      name: 'Checkout Squad',
      mission: 'Improve checkout conversion',
      lead_name: 'Ari',
      capacity_fte: 6,
      target_velocity: 34,
      members: [],
    },
  ],
}

test('keeps tribe shared roles optional while allowing them to be added', () => {
  render(<TeamPlanning
    projectId="project-1"
    l1Id="l1-1"
    plan={basePlan}
    refresh={vi.fn()}
    setError={vi.fn()}
    money={money} />)

  expect(screen.queryByText('Tribe leadership & shared roles')).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Add tribe-level shared role to Digital Commerce' }))

  expect(screen.getByRole('dialog', { name: 'Add team member' })).toBeInTheDocument()
  expect(screen.getByText(/Tribe shared role: Digital Commerce/)).toBeInTheDocument()
  expect(screen.getByText(/add delivery members inside squads/i)).toBeInTheDocument()
})

test('shows tribe leadership section only when direct tribe members exist', () => {
  const plan = {
    ...basePlan,
    units: basePlan.units.map((unit) => unit.id === 'tribe-1'
      ? {
          ...unit,
          members: [{
            id: 'member-1',
            name: 'Samira',
            role: 'Tribe architect',
            skills: 'Architecture',
            location: 'Remote',
            allocation_percent: 50,
            monthly_cost: 20000,
          }],
        }
      : unit),
  }

  render(<TeamPlanning
    projectId="project-1"
    l1Id="l1-1"
    plan={plan}
    refresh={vi.fn()}
    setError={vi.fn()}
    money={money} />)

  expect(screen.getByText('Tribe leadership & shared roles')).toBeInTheDocument()
  expect(screen.getByText('Samira')).toBeInTheDocument()
  expect(screen.getByText('Tribe architect · 50%')).toBeInTheDocument()
})

test('creates a missing lead in the resource directory and selects it for the team', async () => {
  api.createStaff.mockResolvedValue({
    id: 'staff-9', staff_code: 'STF-0009', staff_name: 'Jaya Yu',
    staff_first_name: 'Jaya', staff_last_name: 'Yu', staff_type: 'Perm',
    staff_status: 'Active', sub_status: 'UnAllocated',
  })
  api.updateAgileUnit.mockResolvedValue({})
  const refresh = vi.fn(() => Promise.resolve())
  const setError = vi.fn()

  render(<TeamPlanning
    projectId="project-1"
    l1Id="l1-1"
    plan={basePlan}
    refresh={refresh}
    setError={setError}
    canCreateResource
    money={money} />)

  fireEvent.click(screen.getByRole('button', { name: 'Edit Digital Commerce' }))
  fireEvent.change(screen.getByLabelText('Lead'), { target: { value: '__new_lead__' } })
  fireEvent.change(screen.getByLabelText('First name'), { target: { value: 'Jaya' } })
  fireEvent.change(screen.getByLabelText('Last name'), { target: { value: 'Yu' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add & select lead' }))

  await waitFor(() => expect(api.createStaff).toHaveBeenCalledWith({
    staff_first_name: 'Jaya',
    staff_last_name: 'Yu',
    staff_name: 'Jaya Yu',
    staff_type: 'Perm',
    staff_status: 'Active',
    sub_status: 'UnAllocated',
  }))
  await waitFor(() => expect(screen.getByLabelText('Lead')).toHaveValue('Jaya Yu'))

  fireEvent.click(screen.getByRole('button', { name: 'Save team' }))
  await waitFor(() => expect(api.updateAgileUnit).toHaveBeenCalledWith(
    'project-1',
    'tribe-1',
    expect.objectContaining({ lead_name: 'Jaya Yu' }),
  ))
  expect(setError).not.toHaveBeenCalled()
})
