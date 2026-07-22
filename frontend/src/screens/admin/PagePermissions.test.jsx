import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api } from '../../api/client'
import { ToastProvider } from '../../ui/Toast'
import PagePermissions from './PagePermissions'

vi.mock('../../api/client', () => ({
  api: {
    accessUsers: vi.fn(),
    accessPages: vi.fn(),
    setPagePermissions: vi.fn(),
    getStaff: vi.fn(),
    listStaff: vi.fn(),
    resourceLookups: vi.fn(),
    listCustomFields: vi.fn(),
  },
}))

const pages = [
  { key: 'platforms', label: 'Platforms', description: 'View platforms' },
  { key: 'admin_reporting', label: 'Admin · Reporting', description: 'View reports' },
]
const users = [
  { id: 'admin-1', staff_name: 'Ada Admin', staff_code: 'STF-0001', role: 'admin', enabled: true, page_permissions: { platforms: true, admin_reporting: true }, page_permission_overrides: {} },
  { id: 'viewer-1', staff_name: 'Val Viewer', staff_code: 'STF-0002', role: 'viewer', enabled: true, page_permissions: { platforms: true, admin_reporting: false }, page_permission_overrides: {} },
]

beforeEach(() => {
  vi.clearAllMocks()
  api.accessUsers.mockResolvedValue(users)
  api.accessPages.mockResolvedValue(pages)
  api.getStaff.mockResolvedValue({
    id: 'viewer-1', staff_code: 'STF-0002', staff_name: 'Val Viewer',
    staff_first_name: 'Val', staff_last_name: 'Viewer', staff_type: 'Perm', staff_status: 'Active',
    sub_status: 'Allocated', tech_unit: 'PLATFORM', rank: 'SENIOR', hr_role: 'ENG',
    citizenship: 'CA', staff_start_date: '2022-01-10', staff_end_date: null,
    reporting_manager_id: 'admin-1',
    custom_values: { email: 'val@example.com', employee_number: 'EMP-2', skills: 'Testing' },
  })
  api.listStaff.mockResolvedValue([
    { id: 'admin-1', staff_name: 'Ada Admin', reporting_manager_id: null },
    { id: 'viewer-1', staff_name: 'Val Viewer', reporting_manager_id: 'admin-1' },
  ])
  api.resourceLookups.mockResolvedValue({
    tech_unit: [{ code: 'PLATFORM', label: 'Platform' }],
    rank: [{ code: 'SENIOR', label: 'Senior Professional' }],
    hr_role: [{ code: 'ENG', label: 'Engineer' }],
  })
  api.listCustomFields.mockResolvedValue([])
})

test('opens a complete user profile from the person column', async () => {
  render(<ToastProvider><PagePermissions /></ToastProvider>)

  fireEvent.click(await screen.findByRole('button', { name: 'View complete details for Val Viewer' }))

  const dialog = await screen.findByRole('dialog', { name: 'Val Viewer details' })
  expect(api.getStaff).toHaveBeenCalledWith('viewer-1')
  expect(within(dialog).getByText('val@example.com')).toBeInTheDocument()
  expect(within(dialog).getByText('Ada Admin')).toBeInTheDocument()
  expect(within(dialog).getByText('Testing')).toBeInTheDocument()
  expect(within(dialog).getByText('Platform')).toBeInTheDocument()
  expect(within(dialog).getAllByText('Role default').length).toBeGreaterThan(0)
})
afterEach(() => cleanup())

test('shows a per-user page matrix and saves an explicit grant', async () => {
  api.setPagePermissions.mockResolvedValue({
    ...users[1], page_permissions: { platforms: true, admin_reporting: true },
    page_permission_overrides: { admin_reporting: true },
  })
  render(<ToastProvider><PagePermissions /></ToastProvider>)

  const viewerReporting = await screen.findByLabelText('Val Viewer · Admin · Reporting')
  expect(viewerReporting).toHaveValue('inherit')
  expect(screen.getByLabelText('Ada Admin · Platforms')).toBeDisabled()

  fireEvent.change(viewerReporting, { target: { value: 'allow' } })
  await waitFor(() => expect(api.setPagePermissions).toHaveBeenCalledWith('viewer-1', { admin_reporting: true }))
  await waitFor(() => expect(screen.getByLabelText('Val Viewer · Admin · Reporting')).toHaveValue('allow'))
})
