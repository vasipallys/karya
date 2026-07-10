import { Activity, Boxes, FolderKanban, Layers, Sparkles, UserCheck, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { useToast } from '../../ui/Toast'

function StatCard({ icon: Icon, label, value, hint, tone = 'default' }) {
  return (
    <div className={`admin-stat tone-${tone}`}>
      <span className="admin-stat-icon"><Icon size={18} /></span>
      <div className="admin-stat-body">
        <strong>{value}</strong>
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </div>
    </div>
  )
}

function Breakdown({ title, rows }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  return (
    <div className="admin-breakdown">
      <h3>{title}</h3>
      {rows.length === 0 && <p className="admin-muted">No data yet.</p>}
      {rows.map((row) => (
        <div key={row.label} className="admin-bar-row">
          <span className="admin-bar-label">{row.label}</span>
          <span className="admin-bar-track"><span className="admin-bar-fill" style={{ width: `${(row.value / max) * 100}%` }} /></span>
          <span className="admin-bar-value">{row.value}</span>
        </div>
      ))}
    </div>
  )
}

export default function Reporting() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [narrative, setNarrative] = useState(null)
  const [generating, setGenerating] = useState(false)

  useEffect(() => { api.reportingOverview().then(setData).catch((err) => toast.error(err)) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const generate = async () => {
    setGenerating(true)
    try { setNarrative(await api.reportingNarrative()) } catch (err) { toast.error(err) } finally { setGenerating(false) }
  }

  if (!data) return <section className="admin-section"><div className="login-empty">Loading report…</div></section>

  const { portfolio, resources, access } = data
  const util = resources.avg_utilisation
  const platforms = portfolio.platforms || []

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div><h2>Reporting</h2><p>A live, deterministic snapshot across platforms, delivery, and the resource pool.</p></div>
        <button className="m3-btn tonal" onClick={generate} disabled={generating}><Sparkles size={16} /> {generating ? 'Generating…' : 'AI summary'}</button>
      </div>

      {narrative && (
        <div className="ai-narrative">
          <div className="ai-narrative-head"><Sparkles size={16} /><div><strong>{narrative.headline}</strong><span>AI-generated executive briefing</span></div></div>
          <p>{narrative.summary}</p>
          <div className="ai-narrative-cols">
            {narrative.highlights?.length > 0 && <div><h4>Highlights</h4><ul>{narrative.highlights.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
            {narrative.risks?.length > 0 && <div><h4>Risks</h4><ul>{narrative.risks.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
            {narrative.recommendations?.length > 0 && <div><h4>Recommendations</h4><ul>{narrative.recommendations.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
          </div>
        </div>
      )}

      <div className="admin-stat-grid">
        <StatCard icon={FolderKanban} label="Platforms" value={portfolio.projects} />
        <StatCard icon={Layers} label="Stories estimated" value={`${portfolio.estimated}/${portfolio.stories}`} hint={`${portfolio.estimated_pct}% complete`} tone="primary" />
        <StatCard icon={Boxes} label="Squads" value={portfolio.squads} hint={`${portfolio.members} people assigned`} />
        <StatCard icon={Activity} label="At-risk work items" value={portfolio.at_risk_work_items} tone={portfolio.at_risk_work_items ? 'warn' : 'default'} />
        <StatCard icon={Users} label="Active resources" value={`${resources.active}/${resources.total}`} hint={`${resources.on_bench} on bench`} />
        <StatCard icon={UserCheck} label="Avg. utilisation" value={`${util}%`} hint={`${resources.fully_allocated} fully allocated`} tone={util >= 85 ? 'warn' : 'primary'} />
      </div>

      <div className="admin-breakdown-grid">
        <Breakdown title="Resources by tech unit" rows={resources.by_tech_unit} />
        <Breakdown title="Allocation status" rows={resources.by_sub_status} />
        <Breakdown title="Employment type" rows={resources.by_type} />
        <Breakdown title="App roles" rows={['admin', 'manager', 'contributor', 'viewer'].map((role) => ({ label: role, value: access[role] || 0 }))} />
      </div>

      {platforms.length > 0 && (
        <div className="admin-breakdown">
          <h3>Estimation progress by platform</h3>
          <table className="res-table"><thead><tr><th>Platform</th><th>Stories</th><th>Estimated</th><th>Progress</th></tr></thead>
            <tbody>
              {platforms.map((p) => (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong></td>
                  <td>{p.stories}</td>
                  <td>{p.estimated}</td>
                  <td><div className="admin-inline-bar"><span style={{ width: `${p.estimated_pct}%` }} /></div> {p.estimated_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
