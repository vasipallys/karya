import { ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { Fragment, useState } from 'react'
import { api } from '../api/client'
import LeadsEditor from '../components/LeadsEditor'

const STEPS = ['Basics', 'Code repo', 'Jira', 'Seed C4']

export default function NewProjectWizard({ config, onDone, onCancel }) {
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    name: '', description: '', leads: [], sensitivity: 'standard',
    repoMode: 'existing', repoUrl: '', repoPath: '',
    jiraInstance: '', jiraKey: '',
    seed: 'blank',
  })
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const pick = (key, value) => () => setForm({ ...form, [key]: value })
  const instances = config?.jira_instances || []

  const finish = async () => {
    setBusy(true); setError(null)
    try {
      const leads = form.leads
        .map((lead) => ({ name: (lead.name || '').trim(), role: (lead.role || '').trim() }))
        .filter((lead) => lead.name)
      const project = await api.createProject({ name: form.name.trim(), description: form.description.trim(), leads, sensitivity: form.sensitivity })
      if (form.repoUrl.trim() || form.repoPath.trim()) {
        await api.addRepo(project.id, { url: form.repoUrl.trim(), local_path: form.repoPath.trim(), mode: form.repoMode })
      }
      if (form.jiraInstance && form.jiraKey.trim()) {
        await api.addJiraLink(project.id, { instance_name: form.jiraInstance, project_key: form.jiraKey.trim() })
      }
      let notice = null
      if (form.seed === 'scan' && form.repoPath.trim()) {
        const scan = await api.importRepoScan(project.id, { local_path: form.repoPath.trim(), apply: true })
        notice = `Repo scan proposed ${scan.created} elements.`
      } else if (form.seed === 'jira' && form.jiraInstance && form.jiraKey.trim()) {
        const imported = await api.importJira(project.id)
        notice = `Imported ${imported.created} Jira issues as proposed stories.`
      }
      onDone(project.id, notice)
    } catch (err) { setError(err); setBusy(false) }
  }

  const canNext = step !== 0 || form.name.trim().length > 0
  return <div className="m3-stepper">
    <div className="m3-page-title"><h1>New platform</h1></div>
    <div className="m3-steps">
      {STEPS.map((label, index) => <Fragment key={label}>
        <span className={`m3-step-dot ${index === step ? 'active' : index < step ? 'done' : ''}`}>
          {index < step ? <Check size={14} /> : index + 1}
        </span>
        <span className="m3-step-label">{label}</span>
        {index < STEPS.length - 1 && <span className="m3-step-line" />}
      </Fragment>)}
    </div>
    {error && <div className="m3-banner error">{String(error.message || error)}</div>}
    <div className="m3-card">
      {step === 0 && <>
        <label className="m3-field"><span>Platform name</span>
          <input value={form.name} onChange={set('name')} placeholder="Payments platform" autoFocus /></label>
        <label className="m3-field"><span>Description</span>
          <textarea rows={3} value={form.description} onChange={set('description')} placeholder="What this platform does and who uses it" /></label>
        <div className="m3-field"><span>Leads</span>
          <LeadsEditor leads={form.leads} onChange={(leads) => setForm({ ...form, leads })} /></div>
        <label className="m3-field"><span>Access sensitivity</span>
          <select value={form.sensitivity} onChange={set('sensitivity')}>
            <option value="standard">Standard — any signed-in user</option>
            <option value="restricted">Restricted — managers &amp; admins only</option>
          </select></label>
      </>}
      {step === 1 && <>
        <div className="m3-radio-row">
          <label className={form.repoMode === 'existing' ? 'selected' : ''}><input type="radio" checked={form.repoMode === 'existing'} onChange={pick('repoMode', 'existing')} /> Link existing repo</label>
          <label className={form.repoMode === 'new' ? 'selected' : ''}><input type="radio" checked={form.repoMode === 'new'} onChange={pick('repoMode', 'new')} /> Planned new repo</label>
        </div>
        <label className="m3-field"><span>Repository URL (optional)</span>
          <input value={form.repoUrl} onChange={set('repoUrl')} placeholder="https://github.com/org/repo.git" /></label>
        <label className="m3-field"><span>Local checkout path (optional — enables repo scan)</span>
          <input value={form.repoPath} onChange={set('repoPath')} placeholder="D:\\work\\my-repo" /></label>
      </>}
      {step === 2 && <>
        <label className="m3-field"><span>Jira instance (from backend .env)</span>
          <select value={form.jiraInstance} onChange={set('jiraInstance')}>
            <option value="">— skip Jira —</option>
            {instances.map((item) => <option key={item.name} value={item.name}>{item.name} ({item.auth_type})</option>)}
          </select></label>
        <label className="m3-field"><span>Jira project key</span>
          <input value={form.jiraKey} onChange={set('jiraKey')} placeholder="PAY" disabled={!form.jiraInstance} /></label>
      </>}
      {step === 3 && <>
        <div className="m3-radio-row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
          <label className={form.seed === 'blank' ? 'selected' : ''}><input type="radio" checked={form.seed === 'blank'} onChange={pick('seed', 'blank')} /> Blank canvas — I will draw the C4 model myself</label>
          <label className={form.seed === 'scan' ? 'selected' : ''}><input type="radio" checked={form.seed === 'scan'} onChange={pick('seed', 'scan')} disabled={!form.repoPath.trim()} /> Scan the local repo — propose containers and components from the code {!form.repoPath.trim() && '(needs a local path in step 2)'}</label>
          <label className={form.seed === 'jira' ? 'selected' : ''}><input type="radio" checked={form.seed === 'jira'} onChange={pick('seed', 'jira')} disabled={!form.jiraInstance || !form.jiraKey.trim()} /> Import Jira issues as proposed stories {(!form.jiraInstance || !form.jiraKey.trim()) && '(needs a Jira link in step 3)'}</label>
        </div>
      </>}
    </div>
    <div className="m3-wizard-actions">
      <button className="m3-btn text" onClick={step === 0 ? onCancel : () => setStep(step - 1)} disabled={busy}>
        <ArrowLeft size={16} /> {step === 0 ? 'Cancel' : 'Back'}</button>
      {step < STEPS.length - 1
        ? <button className="m3-btn filled" onClick={() => setStep(step + 1)} disabled={!canNext}>Next <ArrowRight size={16} /></button>
        : <button className="m3-btn filled" onClick={finish} disabled={busy || !form.name.trim()}>{busy ? 'Creating…' : 'Create platform'}</button>}
    </div>
  </div>
}
