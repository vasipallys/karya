import { Blocks, Check, Code2, Columns2, Copy, Download, FileText, PencilRuler, Save, Sparkles, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api } from '../api/client'
import { DIAGRAM_TYPE_GROUPS } from '../planning/diagramCatalog'
import MermaidView from './MermaidView'

const MODES = [
  { id: 'edit', label: 'Edit', icon: Code2 },
  { id: 'split', label: 'Split', icon: Columns2 },
  { id: 'preview', label: 'Preview', icon: FileText },
]

function TypeOptions() {
  return DIAGRAM_TYPE_GROUPS.map((group) => <optgroup key={group.label} label={group.label}>
    {group.types.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
  </optgroup>)
}

export default function MermaidWorkbench({
  projectId, source = '', onChange, onSave, saving = false, onOpenStudio,
  title = 'Mermaid diagram', diagramType = 'architecture', placeholder = 'flowchart LR\n  A --> B',
  aiContext = '', emptyText = 'Write Mermaid source or generate a diagram with AI.',
}) {
  const [mode, setMode] = useState('split')
  const [error, setError] = useState(null)
  const [svg, setSvg] = useState('')
  const [promptOpen, setPromptOpen] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [promptType, setPromptType] = useState(diagramType)
  const [generating, setGenerating] = useState(false)
  const [aiMessage, setAiMessage] = useState('')
  const downloadRef = useRef(null)

  const copy = async () => navigator.clipboard?.writeText(source)
  const download = () => {
    if (!svg) return
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'diagram'}.svg`; anchor.click()
    URL.revokeObjectURL(url)
  }
  const generate = async () => {
    if (!prompt.trim()) return
    setGenerating(true); setAiMessage('')
    try {
      const contextualPrompt = [prompt.trim(), aiContext && `Workspace context:\n${aiContext}`].filter(Boolean).join('\n\n')
      const result = await api.assistProjectDiagram(projectId, {
        prompt: contextualPrompt, diagram_type: promptType, current_source: source, history: [],
      })
      onChange(result.mermaid); setAiMessage(result.message || 'Diagram updated.'); setPromptOpen(false)
    } catch (nextError) { setAiMessage(String(nextError.message || nextError)) }
    finally { setGenerating(false) }
  }

  return <section className={`mermaid-workbench mode-${mode}`}>
    <header className="mermaid-workbench-toolbar">
      <span className="mermaid-workbench-title"><Blocks size={15} /> {title}</span>
      <div className="mermaid-workbench-actions">
        <button type="button" className="m3-btn tonal small" onClick={() => setPromptOpen((value) => !value)}><Sparkles size={14} /> AI generate/edit</button>
        <button type="button" className="m3-icon-btn" onClick={copy} disabled={!source.trim()} title="Copy source" aria-label="Copy Mermaid source"><Copy size={15} /></button>
        <button ref={downloadRef} type="button" className="m3-icon-btn" onClick={download} disabled={!svg || !!error} title="Download SVG" aria-label="Download SVG"><Download size={15} /></button>
        {onOpenStudio && <button type="button" className="m3-btn outlined small" onClick={onOpenStudio}><PencilRuler size={14} /> Studio</button>}
        {onSave && <button type="button" className="m3-btn filled small" disabled={saving || !!error || !source.trim()} onClick={onSave}><Save size={14} /> {saving ? 'Saving…' : 'Save'}</button>}
        <div className="mermaid-mode-toggle">{MODES.map((item) => <button key={item.id} type="button" className={mode === item.id ? 'active' : ''} onClick={() => setMode(item.id)}><item.icon size={13} /> {item.label}</button>)}</div>
      </div>
    </header>
    {promptOpen && <div className="mermaid-ai-bar">
      <select value={promptType} onChange={(event) => setPromptType(event.target.value)} aria-label="AI diagram type"><TypeOptions /></select>
      <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={2} autoFocus
        placeholder={source.trim() ? 'Describe how to improve or change this diagram…' : 'Describe the diagram to generate…'} />
      <button className="m3-btn filled small" disabled={generating || !prompt.trim()} onClick={generate}><Sparkles size={14} /> {generating ? 'Working…' : source.trim() ? 'Apply edit' : 'Generate'}</button>
      <button className="m3-icon-btn" onClick={() => setPromptOpen(false)} aria-label="Close AI diagram tools"><X size={15} /></button>
    </div>}
    {aiMessage && <div className={`mermaid-ai-message${aiMessage.toLowerCase().includes('error') ? ' error' : ''}`}><Check size={13} /> {aiMessage}</div>}
    <div className="mermaid-workbench-grid">
      {mode !== 'preview' && <section className="mermaid-source-pane"><header>Mermaid source</header>
        <textarea spellCheck="false" value={source} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} aria-label="Mermaid diagram source" />
      </section>}
      {mode !== 'edit' && <section className="mermaid-preview-pane"><header>Live preview</header>
        {source.trim() ? <MermaidView source={source} onError={setError} onSvg={setSvg} /> : <p className="l1-node-empty">{emptyText}</p>}
      </section>}
    </div>
  </section>
}
