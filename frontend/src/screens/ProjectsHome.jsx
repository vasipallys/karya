import { FolderGit2, Plus, Sparkles, Trash2, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

// Tonal container / accent pairs (Material 3 style) chosen deterministically per project.
const AVATAR_COLORS = [
  ['#e0e7ff', '#4f46e5'],
  ['#d1fae5', '#047857'],
  ['#ffe3d5', '#b0451f'],
  ['#fce7f3', '#be185d'],
  ['#e0f2fe', '#0369a1'],
  ['#fef3c7', '#b45309'],
  ['#ede9fe', '#6d28d9'],
  ['#ccfbf1', '#0f766e'],
]

function initials(name) {
  const clean = (name || '').trim()
  return clean.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join('').toUpperCase() || '?'
}

function avatarFor(name) {
  const clean = (name || '').trim()
  let hash = 0
  for (let index = 0; index < clean.length; index += 1) hash = (hash * 31 + clean.charCodeAt(index)) >>> 0
  const [bg, fg] = AVATAR_COLORS[hash % AVATAR_COLORS.length]
  return { initials: initials(name), bg, fg }
}

function leadSummary(leads) {
  if (!leads.length) return ''
  if (leads.length === 1) return leads[0].name
  return `${leads[0].name} +${leads.length - 1} more`
}

function ProjectCard({ project, onOpen, onDelete }) {
  const { initials: projectInitials, bg, fg } = avatarFor(project.name)
  const total = project.story_count || 0
  const percent = total ? Math.round((project.estimated_count / total) * 100) : 0
  const repoCount = project.repos.length
  const created = project.created_at
    ? new Date(project.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    : null

  const open = () => onOpen(project.id)
  return (
    <article
      className="proj-card"
      style={{ '--accent': fg, '--accent-bg': bg }}
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open() } }}
    >
      <button className="proj-card-delete" onClick={(event) => onDelete(event, project)} aria-label={`Delete ${project.name}`}>
        <Trash2 size={15} />
      </button>
      <div className="proj-card-head">
        <span className="proj-avatar" aria-hidden="true">{projectInitials}</span>
        <div className="proj-card-title">
          <h3>{project.name}</h3>
          {created && <span>Created {created}</span>}
        </div>
      </div>
      <p className="proj-card-desc">{project.description || 'No description yet.'}</p>
      {project.leads?.length > 0 && (
        <div className="proj-card-leads">
          <div className="proj-lead-avatars">
            {project.leads.slice(0, 4).map((lead, index) => (
              <span key={index} className="proj-lead-avatar" title={lead.role ? `${lead.name} · ${lead.role}` : lead.name}>{initials(lead.name)}</span>
            ))}
          </div>
          <span className="proj-lead-summary">{leadSummary(project.leads)}</span>
        </div>
      )}
      <div className="proj-progress" title={`${project.estimated_count} of ${total} stories estimated`}>
        <div className="proj-progress-head">
          <span>Stories estimated</span>
          <span>{project.estimated_count}/{total} · {percent}%</span>
        </div>
        <div className="proj-progress-track"><div className="proj-progress-fill" style={{ width: `${percent}%` }} /></div>
      </div>
      <div className="proj-card-tags">
        {repoCount > 0 && <span className="m3-chip"><FolderGit2 size={13} /> {repoCount} repo{repoCount !== 1 ? 's' : ''}</span>}
        {project.jira.map((link) => <span key={link.id} className="m3-chip filled">{link.instance_name} · {link.project_key}</span>)}
        {repoCount === 0 && project.jira.length === 0 && <span className="m3-chip">No sources linked</span>}
      </div>
    </article>
  )
}

export default function ProjectsHome({ onOpen, onNew, onQuick, canCreate = true }) {
  const [projects, setProjects] = useState(null)
  const [error, setError] = useState(null)

  const refresh = () => api.listProjects().then(setProjects).catch(setError)
  useEffect(() => { refresh() }, [])

  const remove = async (event, project) => {
    event.stopPropagation()
    if (!window.confirm(`Delete platform "${project.name}" and its whole C4 model? This cannot be undone.`)) return
    try { await api.deleteProject(project.id); refresh() } catch (err) { setError(err) }
  }

  const isEmpty = projects && projects.length === 0

  return (
    <div className="proj-home">
      <header className="proj-hero">
        <div className="proj-hero-text">
          <h1>Platforms</h1>
          <p>Each platform is led by one or more leads and modelled as an interactive C4 model you estimate straight from the architecture.</p>
        </div>
        <button className="m3-btn tonal" onClick={onQuick}><Zap size={16} /> Quick estimate</button>
      </header>

      {error && <div className="m3-banner error">{String(error.message || error)}</div>}

      {isEmpty && (
        <div className="proj-empty">
          <span className="proj-empty-icon"><Sparkles size={28} /></span>
          <h2>Start your first platform</h2>
          <p>Create a platform, name its leads, and model your system as C4 to estimate from the architecture — or run a one-off Quick estimate for a single story.</p>
          <div className="proj-empty-actions">
            {canCreate && <button className="m3-btn filled" onClick={onNew}><Plus size={16} /> New platform</button>}
            <button className="m3-btn text" onClick={onQuick}><Zap size={16} /> Quick estimate</button>
          </div>
        </div>
      )}

      {!isEmpty && (
        <div className="proj-grid">
          {(projects || []).map((project) => (
            <ProjectCard key={project.id} project={project} onOpen={onOpen} onDelete={remove} />
          ))}
          {projects && canCreate && (
            <button className="proj-add-card" onClick={onNew}>
              <span className="proj-add-icon"><Plus size={22} /></span>
              <strong>New platform</strong>
              <span>Name its leads &amp; link a repo to a fresh C4 model</span>
            </button>
          )}
        </div>
      )}

      {canCreate && <button className="m3-fab" onClick={onNew}><Plus size={20} /> New platform</button>}
    </div>
  )
}
