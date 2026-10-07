// Hash routes keep the app's place across refresh, back/forward and shared
// links without a router library (and work under Electron's file:// too):
//   #/                       home
//   #/inbox/<view>           focused inbox
//   #/admin[/<section>[/<tab>]]
//   #/quick                  standalone quick estimate
//   #/p/<projectId>[/<tab>[/<elementId>]]
// The new-platform wizard is transient and never written to the URL.

const segments = (hash) => String(hash || '').replace(/^#\/?/, '').split('/').filter(Boolean).map((part) => {
  try { return decodeURIComponent(part) } catch { return part }
})

export function parseHash(hash) {
  const [head, a, b, c] = segments(hash)
  switch (head) {
    case 'p':
      if (!a) return { route: { name: 'home' }, tab: null }
      return { route: { name: 'project', id: a }, tab: b ? { id: b, elementId: c || null } : null }
    case 'inbox': return { route: { name: 'inbox', view: a || 'actions' }, tab: null }
    case 'admin': return { route: { name: 'admin', section: a, sectionTab: b }, tab: null }
    case 'quick': return { route: { name: 'quick' }, tab: null }
    default: return { route: { name: 'home' }, tab: null }
  }
}

export function routeToHash(route, location) {
  const join = (...parts) => `#/${parts.filter(Boolean).map(encodeURIComponent).join('/')}`
  switch (route?.name) {
    case 'project': return join('p', route.id, location?.tab, location?.tab && location?.elementId)
    case 'inbox': return join('inbox', route.view)
    case 'admin': return join('admin', route.section, route.section && route.sectionTab)
    case 'quick': return join('quick')
    case 'wizard': return null
    default: return '#/'
  }
}
