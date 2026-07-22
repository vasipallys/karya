import { expect, test } from 'vitest'
import { can } from './permissions'

test('page permissions override role defaults without changing action capabilities', () => {
  expect(can('viewer', 'page.platforms')).toBe(true)
  expect(can('viewer', 'admin.reporting')).toBe(false)
  expect(can('viewer', 'admin.reporting', { admin_reporting: true })).toBe(true)
  expect(can('manager', 'admin.resources', { admin_resources: false })).toBe(false)
  expect(can('viewer', 'platform.edit', { workspace: true })).toBe(false)
  expect(can('admin', 'admin.access', { admin_access: false })).toBe(true)
})
