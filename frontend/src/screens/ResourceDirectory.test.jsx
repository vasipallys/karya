import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api } from '../api/client'
import ResourceDirectory from './ResourceDirectory'

vi.mock('../api/client', () => ({
  api: {
    listStaff: vi.fn(() => Promise.resolve([])),
    resourceLookups: vi.fn(() => Promise.resolve({ tech_unit: [], rank: [], hr_role: [] })),
    listCustomFields: vi.fn(() => Promise.resolve([])),
    importResourcesExcel: vi.fn(),
    importResourcesLdap: vi.fn(),
    resourceImportTemplate: vi.fn(),
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  api.listStaff.mockResolvedValue([])
  api.resourceLookups.mockResolvedValue({ tech_unit: [], rank: [], hr_role: [] })
  api.listCustomFields.mockResolvedValue([])
})

afterEach(() => cleanup())

test('imports a single or bulk Excel resource file and shows counts', async () => {
  api.importResourcesExcel.mockResolvedValue({
    counts: { created: 2, updated: 0, skipped: 1, errors: 0 },
    errors: [],
  })
  render(<ResourceDirectory />)

  fireEvent.click(screen.getByRole('button', { name: /Import Excel/i }))
  const file = new File(['workbook'], 'resources.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  fireEvent.change(screen.getByLabelText('Resource file'), { target: { files: [file] } })
  fireEvent.click(screen.getByLabelText(/Update people/i))
  fireEvent.click(screen.getByRole('button', { name: 'Import resources' }))

  await waitFor(() => expect(api.importResourcesExcel).toHaveBeenCalledWith(file, true))
  expect(await screen.findByRole('status')).toHaveTextContent('2 created, 0 updated, 1 skipped, 0 failed')
})

test('imports LDAP resources with the selected connector and filter', async () => {
  api.importResourcesLdap.mockResolvedValue({
    counts: { created: 4, updated: 1, skipped: 0, errors: 0 },
    errors: [],
  })
  render(<ResourceDirectory />)

  fireEvent.click(screen.getByRole('button', { name: /Import directory/i }))
  fireEvent.change(screen.getByLabelText('Directory connector'), { target: { value: 'active_directory' } })
  fireEvent.change(screen.getByLabelText('Base LDAP search filter'), { target: { value: '(department=Platform)' } })
  fireEvent.change(screen.getByLabelText('Maximum results'), { target: { value: '250' } })
  fireEvent.click(screen.getByRole('button', { name: 'Import resources' }))

  await waitFor(() => expect(api.importResourcesLdap).toHaveBeenCalledWith({
    connector_key: 'active_directory',
    scope: 'bulk',
    identifier: '',
    search_filter: '(department=Platform)',
    max_results: 250,
    update_existing: false,
  }))
  expect(await screen.findByRole('status')).toHaveTextContent('4 created, 1 updated')
})

test('supports a single LDAP user lookup by username or email', async () => {
  api.importResourcesLdap.mockResolvedValue({
    counts: { created: 1, updated: 0, skipped: 0, errors: 0 }, errors: [],
  })
  render(<ResourceDirectory />)

  fireEvent.click(screen.getByRole('button', { name: /Import directory/i }))
  fireEvent.change(screen.getByLabelText('Import scope'), { target: { value: 'single' } })
  fireEvent.change(screen.getByLabelText('Username, email or employee number *'), { target: { value: 'ada@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Import resources' }))

  await waitFor(() => expect(api.importResourcesLdap).toHaveBeenCalledWith(expect.objectContaining({
    scope: 'single', identifier: 'ada@example.com',
  })))
  expect(await screen.findByRole('status')).toHaveTextContent('1 created')
})
