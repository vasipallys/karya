import { CheckCircle2, Plug, Send, Settings2, Sparkles, Unplug } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import PlanningDialog from '../../planning/PlanningDialog'
import { useToast } from '../../ui/Toast'

const STATUS_LABEL = { connected: 'Connected', adapter: 'In-app adapter', available: 'Available' }

export default function Integrations() {
  const toast = useToast()
  const { can } = useAuth()
  const canConfigure = can('admin.integrations')
  const [catalog, setCatalog] = useState(null)
  const [command, setCommand] = useState('')
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null) // { tool, config, draft, enabled, test }

  const loadCatalog = () => api.integrationCatalog().then(setCatalog).catch((err) => toast.error(err))
  useEffect(() => { loadCatalog() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const route = async () => {
    if (!command.trim()) return
    setBusy(true)
    try { setPlan(await api.aiOrchestrate(command)) } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  const openConfig = async (tool) => {
    try {
      const config = await api.integrationConfig(tool.key)
      const draft = {}
      config.fields.forEach((f) => { draft[f.key] = f.secret ? '' : (config.values[f.key] || '') })
      setDialog({ tool, config, draft, enabled: config.enabled, test: null })
    } catch (err) { toast.error(err) }
  }

  const setField = (key, value) => setDialog((d) => ({ ...d, draft: { ...d.draft, [key]: value }, test: null }))

  const save = async () => {
    setBusy(true)
    try {
      await api.saveIntegrationConfig(dialog.tool.key, { values: dialog.draft, enabled: dialog.enabled })
      toast.success(`${dialog.tool.name} saved`)
      setDialog(null); await loadCatalog()
    } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  const validate = async () => {
    setBusy(true)
    try {
      // Persist the current form first (so the validation reflects what's on screen), then test.
      await api.saveIntegrationConfig(dialog.tool.key, { values: dialog.draft, enabled: dialog.enabled })
      const test = await api.testIntegrationConfig(dialog.tool.key)
      const config = await api.integrationConfig(dialog.tool.key)
      setDialog((d) => ({ ...d, config, test }))
    } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  const disconnect = async () => {
    if (!window.confirm(`Remove the saved configuration for ${dialog.tool.name}?`)) return
    setBusy(true)
    try {
      await api.clearIntegrationConfig(dialog.tool.key)
      toast.success(`${dialog.tool.name} disconnected`)
      setDialog(null); await loadCatalog()
    } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  const active = catalog ? catalog.counts.connected + catalog.counts.adapter : 0

  return (
    <section className="admin-section">
      <div className="admin-section-head">
        <div><h2>Integrations</h2><p>Connect delivery, documentation, architecture, people, engineering and risk tools. Live adapters exist for a few; the rest are catalogued — configure a connector's URL and credentials to activate it.</p></div>
        {catalog && <span className="m3-chip"><Plug size={14} /> {active}/{catalog.total} active</span>}
      </div>

      <div className="ai-orchestrator">
        <div className="ai-orchestrator-head"><Sparkles size={15} /> AI command router — describe what you want, and it routes to the right capability</div>
        <div className="ai-orchestrator-row">
          <input value={command} placeholder="e.g. draft the vision and OKRs for this initiative" onChange={(e) => setCommand(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') route() }} />
          <button className="m3-btn filled small" disabled={busy || !command.trim()} onClick={route}><Send size={14} /> Route</button>
        </div>
        {plan && <div className="ai-orchestrator-plan">→ <strong>{plan.action.replace(/_/g, ' ')}</strong> · {plan.rationale}</div>}
      </div>

      {!catalog && <div className="login-empty">Loading catalog…</div>}
      {catalog && catalog.groups.map((group) => (
        <div key={group.category} className="admin-breakdown">
          <h3>{group.category}</h3>
          <div className="integration-grid">
            {group.tools.map((tool) => (
              <div key={tool.key} className={`integration-card status-${tool.status}`}>
                <div className="integration-card-head"><strong>{tool.name}</strong><span className={`res-pill int-${tool.status}`}>{STATUS_LABEL[tool.status]}</span></div>
                <p>{tool.purpose}</p>
                {tool.configurable
                  ? (canConfigure
                    ? <button className="m3-btn text small integration-config-btn" onClick={() => openConfig(tool)}>
                        <Settings2 size={14} /> {tool.status === 'connected' ? 'Manage' : 'Configure'}
                      </button>
                    : <span className="integration-config-hint">Admin configures this connector</span>)
                  : <span className="integration-config-hint">Built-in — no setup needed</span>}
              </div>
            ))}
          </div>
        </div>
      ))}

      {dialog && (
        <PlanningDialog
          title={`Configure ${dialog.tool.name}`}
          onClose={() => setDialog(null)}
          actions={<>
            {dialog.config.updated_at && <button className="m3-btn text small danger-ink" disabled={busy} onClick={disconnect}><Unplug size={14} /> Disconnect</button>}
            <button className="m3-btn text" disabled={busy} onClick={validate}>Validate</button>
            <button className="m3-btn text" onClick={() => setDialog(null)}>Cancel</button>
            <button className="m3-btn filled" disabled={busy} onClick={save}>Save</button>
          </>}
        >
          <p className="admin-muted" style={{ marginTop: 0 }}>{dialog.tool.purpose}</p>
          <div className="l1-form-grid">
            {dialog.config.fields.map((f) => {
              const savedSecret = f.secret && dialog.config.secrets_set.includes(f.key)
              return (
                <label key={f.key} className="m3-field">
                  <span>{f.label}{f.required ? ' *' : ''}</span>
                  <input
                    type={f.secret ? 'password' : 'text'}
                    value={dialog.draft[f.key] || ''}
                    autoComplete={f.secret ? 'new-password' : 'off'}
                    placeholder={savedSecret ? '•••••••• (saved — leave blank to keep)' : f.placeholder}
                    onChange={(e) => setField(f.key, e.target.value)}
                  />
                </label>
              )
            })}
          </div>
          <label className="integration-enable-row">
            <input type="checkbox" checked={dialog.enabled} onChange={(e) => setDialog((d) => ({ ...d, enabled: e.target.checked, test: null }))} />
            <span>Enabled — count this connector as connected</span>
          </label>
          {dialog.test && (
            <div className={`m3-banner ${dialog.test.ok ? 'info' : 'error'}`}>
              {dialog.test.ok ? <CheckCircle2 size={15} /> : null} {dialog.test.message}
            </div>
          )}
          <p className="ai-hint">Credentials are stored server-side and never sent back to the browser — leave a secret field blank to keep the saved value.</p>
        </PlanningDialog>
      )}
    </section>
  )
}
