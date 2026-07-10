import { BarChart3, Plug, ShieldCheck, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import AccessManagement from './admin/AccessManagement'
import Integrations from './admin/Integrations'
import Reporting from './admin/Reporting'
import ResourceDirectory from './ResourceDirectory'

const SECTIONS = [
  { key: 'access', label: 'Access management', icon: ShieldCheck, cap: 'admin.access', Component: AccessManagement },
  { key: 'reporting', label: 'Reporting', icon: BarChart3, cap: 'admin.reporting', Component: Reporting },
  { key: 'resources', label: 'Resources', icon: Users, cap: 'admin.resources', Component: ResourceDirectory },
  { key: 'integrations', label: 'Integrations', icon: Plug, cap: 'admin.reporting', Component: Integrations },
]

export default function AdminConsole() {
  const { can } = useAuth()
  const available = useMemo(() => SECTIONS.filter((section) => can(section.cap)), [can])
  const [active, setActive] = useState(available[0]?.key || 'reporting')

  if (available.length === 0) {
    return <div className="admin-shell"><div className="login-empty"><ShieldCheck size={28} /><p>You don't have access to the admin area.</p></div></div>
  }

  const current = available.find((section) => section.key === active) || available[0]
  const Current = current.Component

  return (
    <div className="admin-shell">
      <div className="proj-hero admin-hero">
        <div className="proj-hero-text"><h1>Admin</h1><p>Access, reporting, and the shared resource directory in one place.</p></div>
      </div>
      <nav className="admin-subnav" aria-label="Admin sections">
        {available.map((section) => {
          const Icon = section.icon
          return (
            <button key={section.key} className={section.key === current.key ? 'active' : ''} onClick={() => setActive(section.key)}>
              <Icon size={16} /> {section.label}
            </button>
          )
        })}
      </nav>
      <Current />
    </div>
  )
}
