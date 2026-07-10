import { Blocks, Download, FileCode2, PencilRuler, Plus, Save, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import DockablePanel from '../components/DockablePanel'
import MermaidView from '../components/MermaidView'
import { DEFAULT_DIAGRAM_TYPE, DIAGRAM_TYPE_GROUPS, diagramTypeLabel, getDiagramType } from './diagramCatalog'
import DiagramStudio from './DiagramStudio'
import PlanningDialog from './PlanningDialog'

function DiagramTypeOptions() {
  return DIAGRAM_TYPE_GROUPS.map((group) => (
    <optgroup key={group.label} label={group.label}>
      {group.types.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
    </optgroup>
  ))
}

function MermaidPreview({ source, onError, svgRef }) {
  return <MermaidView source={source} onError={onError} onSvg={(svg) => { svgRef.current = svg }} className="l1-mermaid-preview" />
}

export default function ArchitecturePlanning({ projectId, l1Id, plan, refresh, setError }) {
  const [selectedId, setSelectedId] = useState(plan.diagrams[0]?.id || null)
  const selected = plan.diagrams.find((item) => item.id === selectedId) || plan.diagrams[0] || null
  const [draft, setDraft] = useState(null)
  const [previewError, setPreviewError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [studioOpen, setStudioOpen] = useState(false)
  const [savingStudio, setSavingStudio] = useState(false)
  const [promptOpen, setPromptOpen] = useState(false)
  const [promptText, setPromptText] = useState('')
  const [promptType, setPromptType] = useState(DEFAULT_DIAGRAM_TYPE)
  const [newType, setNewType] = useState(DEFAULT_DIAGRAM_TYPE)
  const [generating, setGenerating] = useState(false)
  const svgRef = useRef('')

  // Re-sync the inline draft when a different diagram is selected AND when the
  // selected diagram's saved version changes (e.g. after the studio saves), so
  // the inline source + preview reflect edits made in the studio.
  useEffect(() => {
    if (selected) setDraft({ title: selected.title, diagram_type: selected.diagram_type, mermaid_source: selected.mermaid_source })
    else setDraft(null)
  }, [selected?.id, selected?.updated_at])

  const choose = (diagram) => { setSelectedId(diagram.id); setPreviewError(null) }
  const create = async (type) => {
    const diagramType = getDiagramType(type)
    setBusy(true)
    try {
      const created = await api.createDiagram(projectId, l1Id, { diagram_type: diagramType.id, title: diagramType.title, mermaid_source: diagramType.template })
      await refresh(); setSelectedId(created.id)
    } catch (error) { setError(error) } finally { setBusy(false) }
  }
  const save = async () => {
    if (!selected || previewError) return
    setBusy(true)
    try { await api.updateDiagram(projectId, selected.id, draft); await refresh() }
    catch (error) { setError(error) } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!selected || !window.confirm(`Delete diagram "${selected.title}"?`)) return
    try { await api.deleteDiagram(projectId, selected.id); setSelectedId(null); await refresh() } catch (error) { setError(error) }
  }
  const saveFromStudio = async (payload) => {
    if (!selected) return
    setSavingStudio(true)
    try { await api.updateDiagram(projectId, selected.id, payload); await refresh() }
    catch (error) { setError(error) } finally { setSavingStudio(false) }
  }
  const generate = async () => {
    if (!promptText.trim()) return
    setGenerating(true)
    try {
      const created = await api.generateDiagram(projectId, l1Id, { prompt: promptText.trim(), diagram_type: promptType })
      setPromptOpen(false); setPromptText('')
      await refresh()
      setSelectedId(created.id)
      setStudioOpen(true)
    } catch (error) { setError(error) } finally { setGenerating(false) }
  }
  const assist = (payload) => api.assistDiagram(projectId, l1Id, payload)
  const downloadSvg = () => {
    if (!svgRef.current) return
    const blob = new Blob([svgRef.current], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${draft.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.svg`; anchor.click()
    URL.revokeObjectURL(url)
  }
  const dirty = selected && draft && (draft.title !== selected.title || draft.diagram_type !== selected.diagram_type || draft.mermaid_source !== selected.mermaid_source)

  return <section>
    <div className="l1-section-heading">
      <div><h2>Architecture & infrastructure</h2><p>Edit Mermaid source and see the system view update live. Diagrams remain portable, reviewable, and version-control friendly.</p></div>
      <div className="l1-heading-actions">
        <label className="l1-template-picker"><span>Template</span><select value={newType} onChange={(event) => setNewType(event.target.value)}><DiagramTypeOptions /></select></label>
        <button className="m3-btn tonal small" disabled={busy} onClick={() => { setPromptType(newType); setPromptOpen(true) }}><Sparkles size={15} /> Generate with AI</button>
        <button className="m3-btn filled small" disabled={busy} onClick={() => create(newType)}><Plus size={15} /> New view</button>
      </div>
    </div>

    {plan.diagrams.length === 0
      ? <div className="l1-empty-panel"><Blocks size={32} /><h3>Create a living technical view</h3><p>Describe the system in plain language and let AI draft it, or start from a Mermaid template - then edit the source and visual view live.</p><div className="l1-heading-actions"><label className="l1-template-picker"><span>Template</span><select value={newType} onChange={(event) => setNewType(event.target.value)}><DiagramTypeOptions /></select></label><button className="m3-btn tonal" onClick={() => { setPromptType(newType); setPromptOpen(true) }}><Sparkles size={16} /> Generate with AI</button><button className="m3-btn filled" onClick={() => create(newType)}><Plus size={16} /> New view</button></div></div>
      : <div className="l1-diagram-layout">
        <DockablePanel id="l1-diagram-list" side="left" title="Saved views" defaultWidth={220} minWidth={170} maxWidth={360}>
          <aside className="l1-diagram-list">
            <span className="l1-eyebrow">Saved views</span>
            {plan.diagrams.map((diagram) => <button key={diagram.id} className={selected?.id === diagram.id ? 'active' : ''} onClick={() => choose(diagram)}><span className={`l1-unit-mark ${diagram.diagram_type}`}><FileCode2 size={16} /></span><span><strong>{diagram.title}</strong><small>{diagramTypeLabel(diagram.diagram_type)} · {new Date(diagram.updated_at).toLocaleDateString()}</small></span></button>)}
          </aside>
        </DockablePanel>
        {draft && <div className="l1-diagram-studio">
          <header className="l1-studio-toolbar">
            <label><span>Diagram name</span><input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
            <label><span>View</span><select value={draft.diagram_type} onChange={(event) => setDraft({ ...draft, diagram_type: event.target.value })}><DiagramTypeOptions /></select></label>
            <span className="l1-save-state">{dirty ? 'Unsaved changes' : 'Saved'}</span>
            <button className="m3-btn tonal small" onClick={() => setStudioOpen(true)}><PencilRuler size={15} /> Open studio</button>
            <button className="m3-btn text small" onClick={downloadSvg} disabled={!!previewError}><Download size={15} /> SVG</button>
            <button className="m3-btn filled small" onClick={save} disabled={busy || !dirty || !!previewError || !draft.title.trim()}><Save size={15} /> Save</button>
            <button className="m3-icon-btn danger-ink" onClick={remove} aria-label="Delete diagram"><Trash2 size={17} /></button>
          </header>
          <div className="l1-studio-body">
            <div className="l1-code-pane"><header><FileCode2 size={15} /> Mermaid source</header><textarea spellCheck="false" value={draft.mermaid_source} onChange={(event) => setDraft({ ...draft, mermaid_source: event.target.value })} aria-label="Mermaid diagram source" /></div>
            <div className="l1-preview-pane"><header><Blocks size={15} /> Live preview</header>{previewError && <div className="l1-diagram-error"><strong>Diagram needs attention</strong><span>{String(previewError.message || previewError).split('\n')[0]}</span></div>}<MermaidPreview source={draft.mermaid_source} svgRef={svgRef} onError={setPreviewError} /></div>
          </div>
        </div>}
      </div>}

    {studioOpen && selected && <DiagramStudio key={selected.id} diagram={selected} saving={savingStudio}
      onSave={saveFromStudio} onAssist={assist} onClose={() => setStudioOpen(false)} />}

    {promptOpen && <PlanningDialog
      title="Generate a diagram with AI"
      onClose={() => setPromptOpen(false)}
      actions={<>
        <button className="m3-btn text" onClick={() => setPromptOpen(false)}>Cancel</button>
        <button className="m3-btn filled" disabled={generating || !promptText.trim()} onClick={generate}><Sparkles size={15} /> {generating ? 'Generating…' : 'Generate'}</button>
      </>}>
      <label className="m3-field"><span>View</span>
        <select value={promptType} onChange={(event) => setPromptType(event.target.value)}>
          <DiagramTypeOptions />
        </select></label>
      <label className="m3-field"><span>Describe the system or requirement</span>
        <textarea autoFocus rows={5} value={promptText} onChange={(event) => setPromptText(event.target.value)}
          placeholder="e.g. A React web app calls an experience API, which uses domain services backed by PostgreSQL and publishes events to Kafka for an analytics platform." /></label>
      <p className="req-dialog-note">The assistant drafts editable Mermaid for the selected view. You can refine flowcharts visually, and every type remains editable as text.</p>
    </PlanningDialog>}
  </section>
}
