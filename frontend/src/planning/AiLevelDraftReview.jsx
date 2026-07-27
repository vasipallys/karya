import { CheckCircle2, Database, Trash2, TriangleAlert } from 'lucide-react'
import MermaidView from '../components/MermaidView'

export const AI_DRAFT_SECTIONS = {
  L1: [
    { key: 'vision', label: 'Vision & business context', fields: ['vision_statement', 'business_problem', 'target_users'] },
    { key: 'okrs', label: 'OKRs' },
    { key: 'stakeholders', label: 'Stakeholders & RACI' },
    { key: 'capabilities', label: 'Capabilities' },
    { key: 'risks', label: 'Risks & funding' },
  ],
  L2: [
    { key: 'summary', label: 'Summary & container diagram', fields: ['summary', 'container_diagram'], diagram: 'container_diagram' },
    { key: 'containers', label: 'Containers' },
    { key: 'apis', label: 'APIs & data contracts' },
    { key: 'nfrs', label: 'NFRs' },
    { key: 'integrations', label: 'Integrations' },
  ],
  L3: [
    { key: 'summary', label: 'Summary & component diagram', fields: ['summary', 'component_diagram'], diagram: 'component_diagram' },
    { key: 'components', label: 'Components' },
    { key: 'behavior_views', label: 'Behavior models' },
    { key: 'interfaces', label: 'Interfaces & contracts' },
    { key: 'dependencies', label: 'Dependencies' },
    { key: 'concerns', label: 'Design concerns' },
  ],
  L4: [
    { key: 'summary', label: 'Summary & implementation diagram', fields: ['summary', 'code_diagram'], diagram: 'code_diagram' },
    { key: 'code_units', label: 'Code units' },
    { key: 'test_cases', label: 'Test cases' },
    { key: 'delivery_assets', label: 'Deliverables' },
    { key: 'checklist', label: 'Definition of Done' },
  ],
}

const OPTIONS = {
  influence: ['high', 'medium', 'low'], interest: ['high', 'medium', 'low'],
  criticality: ['high', 'medium', 'low'], risk_level: ['high', 'medium', 'low'],
  complexity: ['high', 'medium', 'low'],
  raci: ['Responsible', 'Accountable', 'Consulted', 'Informed'],
  stakeholder_type: ['internal', 'external', 'vendor', 'regulator'],
  container_type: ['application', 'service', 'data_store', 'platform', 'cloud_resource', 'job', 'gateway'],
  security_classification: ['public', 'internal', 'confidential', 'restricted'],
  integration_type: ['API', 'Event', 'Batch', 'File', 'UI', 'Manual'],
  component_type: ['controller', 'service', 'repository', 'gateway', 'model', 'client', 'config', 'ui', 'other'],
  direction: ['provided', 'consumed'],
  dependency_type: ['internal', 'container', 'external', 'library'],
  view_type: ['user_journey', 'sequence_flow', 'bpmn', 'erd', 'test_scenario'],
  unit_type: ['class', 'interface', 'function', 'module', 'config', 'migration', 'test'],
  test_type: ['unit', 'integration', 'e2e', 'contract', 'manual'],
  asset_type: ['ci_pipeline', 'code_review', 'iac', 'release_package'],
}
const SECTION_OPTIONS = {
  'risks.category': ['delivery', 'architecture', 'security', 'compliance', 'operational', 'financial'],
  'nfrs.category': ['performance', 'security', 'availability', 'scalability', 'privacy', 'resilience'],
  'concerns.category': ['logging', 'caching', 'validation', 'security', 'error_handling', 'config', 'observability', 'resilience'],
  'checklist.category': ['code', 'tests', 'docs', 'security', 'review', 'deploy'],
  'apis.api_type': ['REST', 'GraphQL', 'gRPC', 'Event', 'Batch', 'File'],
  'interfaces.interface_type': ['REST', 'GraphQL', 'gRPC', 'Event', 'Function', 'Message'],
}

const MULTILINE = new Set([
  'summary', 'vision_statement', 'business_problem', 'target_users', 'description', 'responsibilities',
  'mitigation', 'key_result', 'contract', 'approach', 'scenario', 'expected', 'responsibility',
  'mermaid_source', 'container_diagram', 'component_diagram', 'code_diagram',
])

const label = (key) => key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

function Field({ field, value, onChange, section = '' }) {
  const configuredOptions = SECTION_OPTIONS[`${section}.${field}`] || OPTIONS[field]
  if (configuredOptions) {
    const options = [...new Set([value, ...configuredOptions].filter(Boolean))]
    return <select value={value || ''} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => <option key={option} value={option}>{label(option)}</option>)}
    </select>
  }
  if (MULTILINE.has(field) || String(value || '').length > 100) {
    return <textarea rows={field.includes('diagram') || field === 'mermaid_source' ? 7 : 2}
      value={value || ''} onChange={(event) => onChange(event.target.value)} />
  }
  return <input value={value || ''} onChange={(event) => onChange(event.target.value)} />
}

export default function AiLevelDraftReview({ level, draft, selected, onSelectedChange, onDraftChange }) {
  const sections = AI_DRAFT_SECTIONS[level]
  const updateField = (key, value) => onDraftChange({ ...draft, [key]: value })
  const updateItem = (section, index, key, value) => {
    const items = [...(draft[section] || [])]
    items[index] = { ...items[index], [key]: value }
    updateField(section, items)
  }
  const removeItem = (section, index) => updateField(section, (draft[section] || []).filter((_, itemIndex) => itemIndex !== index))
  const toggle = (key) => onSelectedChange(
    selected.includes(key) ? selected.filter((item) => item !== key) : [...selected, key],
  )
  const context = draft.context

  return <div className="ai-level-review">
    <div className="m3-banner info">
      <CheckCircle2 size={17} />
      <span>This is a non-persistent AI draft. Edit it, choose the sections to keep, then save it as a draft or submit it for formal review.</span>
    </div>

    {context && <section className="ai-context-evidence">
      <header><Database size={16} /><div><strong>Grounded in {context.source_level} context</strong>
        <small>{context.source_name || 'Available workspace evidence'} → {context.target_level} {context.target_name}</small></div></header>
      <div className="ai-context-chips">
        {context.inherited_items.map((item) => <span key={item}>{item}</span>)}
        {!context.inherited_items.length && <em>No upstream items available</em>}
      </div>
      {context.assumptions.map((item) => <p className="ai-context-warning" key={item}><TriangleAlert size={14} /> {item}</p>)}
    </section>}

    <div className="ai-draft-sections">
      {sections.map((section) => {
        const active = selected.includes(section.key)
        const items = section.fields ? null : (draft[section.key] || [])
        return <section key={section.key} className={`ai-draft-section ${active ? 'selected' : 'excluded'}`}>
          <header>
            <label><input type="checkbox" checked={active} onChange={() => toggle(section.key)} />
              <strong>{section.label}</strong></label>
            <small>{items ? `${items.length} item${items.length === 1 ? '' : 's'}` : 'Editable'}</small>
          </header>
          {active && section.fields && <div className="ai-draft-scalar-grid">
            {section.fields.map((field) => <label key={field}><span>{label(field)}</span>
              <Field field={field} value={draft[field]} section={section.key} onChange={(value) => updateField(field, value)} />
            </label>)}
            {section.diagram && draft[section.diagram] && <div className="ai-draft-diagram"><MermaidView source={draft[section.diagram]} fit="width" /></div>}
          </div>}
          {active && items && <div className="ai-draft-items">
            {items.map((item, index) => <article key={`${section.key}-${index}`}>
              <button className="m3-icon-btn danger-ink" onClick={() => removeItem(section.key, index)}
                aria-label={`Remove ${item.name || item.item || label(section.key)}`}><Trash2 size={14} /></button>
              <div className="ai-draft-item-grid">
                {Object.entries(item).filter(([, value]) => typeof value !== 'object').map(([field, value]) =>
                  <label key={field}><span>{label(field)}</span>
                    <Field field={field} value={value} section={section.key} onChange={(next) => updateItem(section.key, index, field, next)} />
                  </label>)}
              </div>
            </article>)}
            {!items.length && <p className="l1-node-empty">No items proposed in this section.</p>}
          </div>}
        </section>
      })}
    </div>
  </div>
}
