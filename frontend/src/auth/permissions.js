// Capability map for UI role-gating (local demo auth). Roles are ordered
// admin > manager > contributor > viewer. '*' means every capability.
//
// Capabilities used across the app:
//   admin              — see the Admin area at all
//   admin.access       — manage users & roles
//   admin.reporting    — view reporting dashboards
//   admin.resources    — manage the resource directory
//   admin.integrations — configure connector URLs/credentials (admin-only)
//   platform.create    — create a new platform
//   platform.edit      — edit C4 model, plans, estimate
export const ROLE_LABELS = {
  admin: 'Administrator',
  manager: 'Manager',
  contributor: 'Contributor',
  viewer: 'Viewer',
}

const ROLE_CAPS = {
  admin: ['*'],
  manager: ['admin', 'admin.reporting', 'admin.resources', 'page.platforms', 'page.workspace', 'page.ask_ai', 'page.guide', 'platform.create', 'platform.edit'],
  contributor: ['page.platforms', 'page.workspace', 'page.ask_ai', 'page.guide', 'platform.create', 'platform.edit'],
  viewer: ['page.platforms', 'page.workspace', 'page.ask_ai', 'page.guide'],
}

const CAPABILITY_PAGE = {
  'page.platforms': 'platforms',
  'page.workspace': 'workspace',
  'page.ask_ai': 'ask_ai',
  'page.guide': 'guide',
  'admin.access': 'admin_access',
  'admin.reporting': 'admin_reporting',
  'admin.resources': 'admin_resources',
  'admin.integrations': 'admin_integrations',
}

export function can(role, capability, pagePermissions = null) {
  if (role === 'admin') return true
  const pageKey = CAPABILITY_PAGE[capability]
  if (pageKey && pagePermissions && Object.hasOwn(pagePermissions, pageKey)) return Boolean(pagePermissions[pageKey])
  const caps = ROLE_CAPS[role] || []
  return caps.includes('*') || caps.includes(capability)
}
