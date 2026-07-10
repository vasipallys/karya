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
  manager: ['admin', 'admin.reporting', 'admin.resources', 'platform.create', 'platform.edit'],
  contributor: ['platform.create', 'platform.edit'],
  viewer: [],
}

export function can(role, capability) {
  const caps = ROLE_CAPS[role] || []
  return caps.includes('*') || caps.includes(capability)
}
