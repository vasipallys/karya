import { Download, Search } from 'lucide-react'
import { useState } from 'react'

export default function JiraBrowser({ instances, issues, onFetch, onEstimate, loading }) {
  const [instance, setInstance] = useState('')
  const [project, setProject] = useState('')
  const [status, setStatus] = useState('')
  const [sprint, setSprint] = useState('')
  const [selected, setSelected] = useState(new Set())
  const activeInstance = instance || instances[0]?.name || ''
  const toggle = (index) => setSelected((current) => {
    const next = new Set(current)
    next.has(index) ? next.delete(index) : next.add(index)
    return next
  })
  const selectedStories = issues.filter((_, index) => selected.has(index))
  return (
    <section className="input-card">
      <div className="section-heading"><div><span className="eyebrow">Connected work</span><h2>Browse a Jira project</h2></div></div>
      <div className="form-grid jira-controls">
        <label>Instance<select value={activeInstance} onChange={(event) => setInstance(event.target.value)}>{instances.map((item) => <option key={item.name} value={item.name}>{item.name} ({item.auth_type})</option>)}</select></label>
        <label>Project code<input value={project} onChange={(event) => setProject(event.target.value.toUpperCase())} placeholder="PAY" /></label>
        <label>Status <span className="optional">Optional</span><input value={status} onChange={(event) => setStatus(event.target.value)} placeholder="Ready for refinement" /></label>
        <label>Sprint <span className="optional">Optional</span><input value={sprint} onChange={(event) => setSprint(event.target.value)} placeholder="Sprint 24" /></label>
      </div>
      <button className="button secondary" disabled={!activeInstance || !project || loading} onClick={() => onFetch(activeInstance, project, { status, sprint })}><Search size={17} /> Fetch issues</button>
      {issues.length > 0 && <>
        <div className="table-wrap"><table className="select-table"><thead><tr><th><span className="sr-only">Select</span></th><th>Key</th><th>Summary</th><th>Status</th><th>Existing</th></tr></thead>
          <tbody>{issues.map((issue, index) => <tr key={issue.key || index}><td><input type="checkbox" aria-label={`Select ${issue.title}`} checked={selected.has(index)} onChange={() => toggle(index)} /></td><td className="mono">{issue.key}</td><td>{issue.title}</td><td>{issue.status || 'Unknown'}</td><td>{issue.existing_points ?? '—'}</td></tr>)}</tbody></table></div>
        <button className="button primary" disabled={!selected.size || loading} onClick={() => onEstimate(selectedStories)}><Download size={17} /> Estimate selected ({selected.size})</button>
      </>}
    </section>
  )
}
