import {
  AlertTriangle, ArrowLeft, Boxes, CheckCircle2, ChevronRight, Clock, FolderKanban, Gauge, Inbox,
  ListChecks, MessageSquare, RefreshCw, ShieldAlert, Target, Users,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'

const firstName = (name) => String(name || '').trim().split(/\s+/)[0] || 'there'

function greeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

const STATUS_TONE = { at_risk: 'warn', in_progress: 'accent', planned: 'muted', done: 'ok' }
const STATUS_LABEL = { at_risk: 'At risk', in_progress: 'In progress', planned: 'Planned', done: 'Done' }

const ACTION_ICON = {
  work: ListChecks, okr: Target, risk: ShieldAlert, comment: MessageSquare, team: Users,
}

// Where a work item / action lands: work lives in a project's L1 plan, the
// bench pool lives in the Resources directory.
const taskTarget = (task) => (task.project_id ? { kind: 'project', id: task.project_id, tab: 'planning' } : null)
const actionTarget = (action) => {
  if (action.category === 'team') return { kind: 'admin', section: 'resources' }
  if (action.project_id) return { kind: 'project', id: action.project_id, tab: 'planning' }
  return null
}

function dueLabel(task) {
  if (task.status === 'done') return 'Completed'
  const days = task.due_in_days
  if (days === null || days === undefined) return 'No due date'
  if (days < 0) return `Overdue by ${Math.abs(days)}d`
  if (days === 0) return 'Due today'
  return `Due in ${days}d`
}

function Tile({ icon: Icon, label, value, tone, onClick, hint }) {
  const clickable = !!onClick
  const className = `home-tile${tone ? ` tone-${tone}` : ''}${clickable ? ' clickable' : ''}`
  const body = (
    <>
      <span className="home-tile-icon"><Icon size={16} /></span>
      <div><strong>{value}</strong><span>{label}</span></div>
      {clickable && <ChevronRight size={14} className="home-tile-arrow" />}
    </>
  )
  if (!clickable) return <div className={className}>{body}</div>
  return <button type="button" className={className} onClick={onClick} title={hint || `Go to ${label}`}>{body}</button>
}

function TaskRow({ task, go, canGo }) {
  const target = taskTarget(task)
  const clickable = canGo(target)
  const open = () => clickable && go(target)
  return (
    <li
      className={`home-item${clickable ? ' clickable' : ''}`}
      onClick={clickable ? open : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={clickable ? (e) => { if (e.key === 'Enter') open() } : undefined}
    >
      <div className="home-item-main">
        <div className="home-item-title">
          <span className="home-item-name">{task.title}</span>
          <span className={`home-chip tone-${STATUS_TONE[task.status] || 'muted'}`}>{STATUS_LABEL[task.status] || task.status}</span>
        </div>
        <div className="home-item-sub">
          <span><FolderKanban size={12} /> {task.project_name}</span>
          {task.squad_name && <span><Boxes size={12} /> {task.squad_name}</span>}
          {task.points != null && <span>{task.points} pts</span>}
        </div>
      </div>
      <div className="home-item-side">
        <span className={`home-due${task.overdue ? ' overdue' : task.status === 'done' ? ' done' : ''}`}>
          <Clock size={12} /> {dueLabel(task)}
        </span>
        {clickable && <ChevronRight size={15} className="home-item-arrow" />}
      </div>
    </li>
  )
}

function ActionRow({ action, go, canGo }) {
  const Icon = ACTION_ICON[action.category] || AlertTriangle
  const target = actionTarget(action)
  const clickable = canGo(target)
  const open = () => clickable && go(target)
  return (
    <li
      className={`home-item${clickable ? ' clickable' : ''}`}
      onClick={clickable ? open : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={clickable ? (e) => { if (e.key === 'Enter') open() } : undefined}
    >
      <span className={`home-sev sev-${action.severity}`} title={`${action.severity} priority`} />
      <span className="home-action-icon"><Icon size={15} /></span>
      <div className="home-item-main">
        <div className="home-item-title"><span className="home-item-name">{action.title}</span></div>
        <div className="home-item-sub">
          <span>{action.detail}</span>
          {action.project_name && <span><FolderKanban size={12} /> {action.project_name}</span>}
        </div>
      </div>
      {clickable && <ChevronRight size={15} className="home-item-arrow" />}
    </li>
  )
}

export default function HomeInbox({ onNavigate, view = 'overview', onBack }) {
  const { user, can } = useAuth()
  const identity = user ? `${user.staff_id || ''}:${user.role || ''}` : ''
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [collapsed, setCollapsed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  // Fetch for any signed-in identity — a directory person gets a personal
  // dashboard, the bootstrap admin gets the org-wide one (the backend decides
  // from the auth headers). Only the latest request may update state, so a
  // stale/unauthorised response from a previous identity can't clobber this one.
  useEffect(() => {
    if (!user) { setData({ user: null }); setError(null); return undefined }
    let live = true
    setError(null)
    setData(null)
    api.homeInbox()
      .then((res) => { if (live) { setData(res); setError(null) } })
      .catch((err) => { if (live) setError(err) })
    return () => { live = false }
  }, [identity, reloadKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => setReloadKey((key) => key + 1)

  // A deep-link target is reachable only if the caller has the capability for
  // its destination; otherwise the tile/item renders non-interactive.
  const canGo = (target) => {
    if (!target) return false
    if (target.kind === 'admin') {
      if (target.section === 'resources') return can('admin.resources')
      if (target.section === 'reporting') return can('admin.reporting')
      return false
    }
    if (target.kind === 'project') return can('page.workspace')
    return true // in-page targets (platforms grid)
  }
  const go = (target) => { if (canGo(target)) onNavigate?.(target) }

  // Nothing to personalise for the password-less bootstrap admin (no directory id).
  if (data && !data.user) return null
  if (error) {
    return (
      <div className="home-inbox home-inbox-error">
        <span>Your workspace inbox could not be loaded.</span>
        <button className="m3-btn text small" onClick={refresh}><RefreshCw size={13} /> Retry</button>
      </div>
    )
  }
  if (!data) {
    return <div className="home-inbox home-inbox-loading"><Inbox size={16} /> Loading your workspace…</div>
  }

  const { summary, tasks, actions } = data
  const isOrg = data.scope === 'organization'
  const isManager = summary.reports > 0

  const reportingTarget = { kind: 'admin', section: 'reporting', tab: 'resources' }
  const resourcesTarget = { kind: 'admin', section: 'resources' }
  const inboxTarget = (nextView) => ({ kind: 'inbox', view: nextView })
  const tileClick = (target) => (canGo(target) ? () => go(target) : undefined)

  const tiles = isOrg ? [
    { key: 'open', icon: Inbox, label: 'Open work', value: summary.tasks_open, tone: 'primary', onClick: () => go(inboxTarget('work')), hint: 'Open the work inbox' },
    { key: 'actions', icon: AlertTriangle, label: 'Actions pending', value: summary.actions, tone: summary.actions ? 'warn' : 'default', onClick: () => go(inboxTarget('actions')), hint: 'Open pending actions' },
    { key: 'atrisk', icon: AlertTriangle, label: 'At risk', value: summary.at_risk, tone: summary.at_risk ? 'warn' : 'default', onClick: () => go(inboxTarget('at_risk')), hint: 'Open at-risk work' },
    { key: 'overdue', icon: Clock, label: 'Overdue', value: summary.overdue, tone: summary.overdue ? 'warn' : 'default', onClick: () => go(inboxTarget('overdue')), hint: 'Open overdue work' },
    { key: 'platforms', icon: FolderKanban, label: 'Platforms', value: summary.projects, onClick: () => go({ kind: 'platforms' }), hint: 'See all platforms' },
    { key: 'squads', icon: Boxes, label: 'Squads', value: summary.squads, onClick: tileClick(reportingTarget), hint: 'Open reporting · resource view' },
    { key: 'resources', icon: Users, label: 'Resources', value: summary.resources, onClick: tileClick(resourcesTarget), hint: 'Open the resource directory' },
    { key: 'bench', icon: Users, label: 'On bench', value: summary.on_bench, tone: summary.on_bench ? 'warn' : 'default', onClick: tileClick(resourcesTarget), hint: 'Open the resource directory' },
  ] : [
    { key: 'open', icon: Inbox, label: 'Open tasks', value: summary.tasks_open, tone: 'primary', onClick: () => go(inboxTarget('work')), hint: 'Open your tasks' },
    { key: 'actions', icon: AlertTriangle, label: 'Actions pending', value: summary.actions, tone: summary.actions ? 'warn' : 'default', onClick: () => go(inboxTarget('actions')), hint: 'Open pending actions' },
    { key: 'atrisk', icon: AlertTriangle, label: 'At risk', value: summary.at_risk, tone: summary.at_risk ? 'warn' : 'default', onClick: () => go(inboxTarget('at_risk')), hint: 'Open at-risk work' },
    { key: 'overdue', icon: Clock, label: 'Overdue', value: summary.overdue, tone: summary.overdue ? 'warn' : 'default', onClick: () => go(inboxTarget('overdue')), hint: 'Open overdue work' },
    { key: 'allocation', icon: Gauge, label: 'Allocation', value: `${summary.allocation}%`, onClick: tileClick(reportingTarget), hint: 'Open reporting · resource view' },
    { key: 'squads', icon: Boxes, label: 'Squads', value: summary.squads, onClick: tileClick(reportingTarget), hint: 'Open reporting · resource view' },
    { key: 'projects', icon: FolderKanban, label: 'Projects', value: summary.projects, onClick: () => go({ kind: 'platforms' }), hint: 'See all platforms' },
    ...(isManager ? [{ key: 'reports', icon: Users, label: 'Reports', value: summary.reports, tone: summary.bench_reports ? 'warn' : 'default', onClick: tileClick(reportingTarget), hint: 'Open reporting · resource view' }] : []),
  ]

  if (view !== 'overview') {
    const definitions = {
      actions: {
        title: 'Actions pending',
        description: 'Items that need attention across delivery, objectives, risks, reviews, and staffing.',
        icon: AlertTriangle,
        items: actions,
        truncated: data.actions_truncated || 0,
      },
      work: {
        title: isOrg ? 'Open work' : 'Open tasks',
        description: isOrg ? 'Open delivery work across all platforms.' : 'Open delivery work assigned to your squads.',
        icon: ListChecks,
        items: tasks.filter((task) => task.status !== 'done'),
        truncated: data.tasks_truncated || 0,
      },
      tasks: {
        title: isOrg ? 'Work inbox' : 'Tasks inbox',
        description: isOrg ? 'Delivery work across all platforms.' : 'Delivery work assigned to your squads.',
        icon: ListChecks,
        items: tasks,
        truncated: data.tasks_truncated || 0,
      },
      at_risk: {
        title: 'At-risk work',
        description: 'Delivery work currently marked at risk.',
        icon: ShieldAlert,
        items: tasks.filter((task) => task.status === 'at_risk'),
        truncated: Math.max(0, summary.at_risk - tasks.filter((task) => task.status === 'at_risk').length),
      },
      overdue: {
        title: 'Overdue work',
        description: 'Open delivery work whose due date has passed.',
        icon: Clock,
        items: tasks.filter((task) => task.overdue),
        truncated: Math.max(0, summary.overdue - tasks.filter((task) => task.overdue).length),
      },
    }
    const detail = definitions[view] || definitions.actions
    const DetailIcon = detail.icon
    return (
      <section className="home-inbox home-inbox-detail" aria-label={detail.title}>
        <header className="home-detail-head">
          <button className="m3-btn text small" onClick={onBack}><ArrowLeft size={15} /> Back to Platforms</button>
          <div>
            <span className="home-detail-icon"><DetailIcon size={19} /></span>
            <div><h1>{detail.title}</h1><p>{detail.description}</p></div>
          </div>
        </header>
        <div className="home-panel home-detail-panel">
          <div className="home-panel-head">
            <h3><DetailIcon size={16} /> {detail.title}</h3>
            <span className="home-count">{detail.items.length + detail.truncated}</span>
          </div>
          {detail.items.length === 0 ? (
            <div className="home-empty"><CheckCircle2 size={22} /><p>Nothing to show here.</p></div>
          ) : (
            <ul className="home-list">
              {view === 'actions'
                ? detail.items.map((action) => <ActionRow key={action.id} action={action} go={go} canGo={canGo} />)
                : detail.items.map((task) => <TaskRow key={task.id} task={task} go={go} canGo={canGo} />)}
              {detail.truncated > 0 && <li className="home-more">+{detail.truncated} more</li>}
            </ul>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="home-inbox" aria-label="Your workspace">
      <header className="home-inbox-head">
        <div>
          {isOrg ? (
            <>
              <h2>Organization overview</h2>
              <p>Portfolio-wide tasks and actions across all platforms.</p>
            </>
          ) : (
            <>
              <h2>{greeting()}, {firstName(data.user.name)}</h2>
              <p>{data.user.rank} · {data.user.tech_unit} — here's what needs you today.</p>
            </>
          )}
        </div>
        <button className="home-collapse" onClick={() => setCollapsed((v) => !v)}>
          {collapsed ? 'Show' : 'Hide'} <ChevronRight size={14} className={collapsed ? '' : 'rot'} />
        </button>
      </header>

      {!collapsed && (
        <>
          <div className="home-tiles">
            {tiles.map(({ key, ...tile }) => <Tile key={key} {...tile} />)}
          </div>

          <div className="home-columns">
            <div className="home-panel">
              <div className="home-panel-head">
                <h3><ListChecks size={16} /> {isOrg ? 'Work inbox' : 'Tasks inbox'}</h3>
                <button className="home-panel-link" onClick={() => go(inboxTarget('tasks'))}>
                  <span className="home-count">{summary.tasks_total}</span> View all <ChevronRight size={13} />
                </button>
              </div>
              {tasks.length === 0 ? (
                <div className="home-empty"><CheckCircle2 size={20} /><p>{isOrg ? 'No open work items across platforms.' : 'No tasks assigned to your squads.'}</p></div>
              ) : (
                <ul className="home-list">
                  {tasks.map((task) => <TaskRow key={task.id} task={task} go={go} canGo={canGo} />)}
                  {data.tasks_truncated > 0 && <li className="home-more">+{data.tasks_truncated} more</li>}
                </ul>
              )}
            </div>

            <div className="home-panel">
              <div className="home-panel-head">
                <h3><AlertTriangle size={16} /> Actions pending</h3>
                <button className="home-panel-link" onClick={() => go(inboxTarget('actions'))}>
                  <span className="home-count">{summary.actions}</span> View all <ChevronRight size={13} />
                </button>
              </div>
              {actions.length === 0 ? (
                <div className="home-empty"><CheckCircle2 size={20} /><p>You're all caught up.</p></div>
              ) : (
                <ul className="home-list">
                  {actions.map((action) => <ActionRow key={action.id} action={action} go={go} canGo={canGo} />)}
                  {data.actions_truncated > 0 && <li className="home-more">+{data.actions_truncated} more</li>}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  )
}
