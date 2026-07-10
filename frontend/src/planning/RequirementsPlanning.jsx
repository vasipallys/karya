import {
  Check,
  CheckCircle2,
  ChevronRight,
  Code2,
  Download,
  FilePlus2,
  FileText,
  History,
  MessageSquareText,
  Plus,
  RotateCcw,
  Save,
  Send,
  Sparkles,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import DockablePanel from '../components/DockablePanel'
import MarkdownEditor, { MERMAID_BLOCK_TEMPLATE, renderMermaidImages } from '../components/MarkdownEditor'
import { DIAGRAM_TYPE_GROUPS } from './diagramCatalog'
import DiagramStudio from './DiagramStudio'
import PlanningDialog from './PlanningDialog'

const STARTER = `# Executive summary

Describe the business outcome, customer value, and the reason this initiative matters.

## Goals

- Measurable outcome
- Target user or business capability

## Functional requirements

1. Describe the primary user journey.
2. Capture business rules and acceptance conditions.

## Non-functional requirements

| Quality attribute | Requirement | Measure |
| --- | --- | --- |
| Availability | Define the service objective | 99.9% |
| Performance | Define the response target | p95 under 500 ms |

## Requirement flow

\`\`\`mermaid
flowchart LR
  Need["Business need"] --> Capability["Required capability"]
  Capability --> Outcome["Measurable outcome"]
\`\`\`

## Assumptions and constraints

- Add assumptions, dependencies, constraints, and open decisions.
`

function DiagramTypeOptions() {
  return DIAGRAM_TYPE_GROUPS.map((group) => (
    <optgroup key={group.label} label={group.label}>
      {group.types.map((type) => <option key={type.id} value={type.id}>{type.label}</option>)}
    </optgroup>
  ))
}

function headingsFrom(content) {
  const seen = new Map()
  return content.split('\n').flatMap((line) => {
    const match = /^(#{1,4})\s+(.+)$/.exec(line)
    if (!match) return []
    const base = match[2].toLowerCase().replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-')
    const count = seen.get(base) || 0
    seen.set(base, count + 1)
    return [{ level: match[1].length, text: match[2], id: count ? `${base}-${count + 1}` : base }]
  })
}

function statusLabel(status) {
  return status?.replace('_', ' ') || 'draft'
}

function saveDownload({ blob, filename }) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function AuditPanel({ document, actor, reload, setError, onOpenVersion }) {
  const [panel, setPanel] = useState('comments')
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  const addComment = async () => {
    if (!comment.trim()) return
    setBusy(true)
    try {
      await api.addRequirementComment(document.project_id, document.id, { body: comment.trim(), actor })
      setComment('')
      await reload()
    } catch (error) { setError(error) } finally { setBusy(false) }
  }
  const act = async (commentId, action) => {
    setBusy(true)
    try {
      await api.actOnRequirementComment(document.project_id, commentId, { action, actor })
      await reload()
    } catch (error) { setError(error) } finally { setBusy(false) }
  }

  return <aside className="req-review-panel">
    <nav>
      <button className={panel === 'comments' ? 'active' : ''} onClick={() => setPanel('comments')}><MessageSquareText size={15} /> Comments <span>{document.comments.length}</span></button>
      <button className={panel === 'history' ? 'active' : ''} onClick={() => setPanel('history')}><History size={15} /> Audit</button>
    </nav>
    {panel === 'comments' ? <div className="req-comments">
      <label><span>Add review comment</span><textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Leave a question, recommendation, or approval note…" /></label>
      <button className="m3-btn tonal small" disabled={busy || !comment.trim()} onClick={addComment}><Send size={14} /> Comment</button>
      <div className="req-comment-list">
        {document.comments.length === 0 && <p className="req-muted">No comments yet. Review decisions will remain attached to the document version.</p>}
        {document.comments.map((item) => <article key={item.id}>
          <header><span className="l1-avatar">{item.author.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()}</span><div><strong>{item.author}</strong><small>v{item.document_version} · {new Date(item.created_at).toLocaleString()}</small></div><span className={`req-comment-status ${item.status}`}>{item.status}</span></header>
          <p>{item.body}</p>
          <footer>
            {item.status !== 'approved' && <button disabled={busy} onClick={() => act(item.id, 'approve')}><Check size={13} /> Approve</button>}
            {item.status !== 'resolved' && <button disabled={busy} onClick={() => act(item.id, 'resolve')}>Resolve</button>}
            {item.status !== 'open' && <button disabled={busy} onClick={() => act(item.id, 'reopen')}><RotateCcw size={13} /> Reopen</button>}
            {item.acted_by && <small>{item.acted_by} · {new Date(item.acted_at).toLocaleString()}</small>}
          </footer>
        </article>)}
      </div>
    </div> : <div className="req-audit-list">
      <div className="req-version-list">
        <span className="l1-eyebrow">Saved versions</span>
        {document.versions.map((version) => <button key={version.id} onClick={() => onOpenVersion(version.version)}>
          <span>v{version.version}</span><strong>{version.change_summary || version.title}</strong><small>{version.changed_by}</small>
        </button>)}
      </div>
      {document.audit.map((event) => <article key={event.id}>
        <span className="req-audit-dot" />
        <div><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{event.actor} · version {event.document_version}</p><small>{new Date(event.created_at).toLocaleString()}</small>{event.detail?.note && <blockquote>{event.detail.note}</blockquote>}</div>
      </article>)}
    </div>}
  </aside>
}

export default function RequirementsPlanning({ projectId, l1Id, setError }) {
  const [documents, setDocuments] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [document, setDocument] = useState(null)
  const [draft, setDraft] = useState(null)
  const [mode, setMode] = useState('split')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [changeSummary, setChangeSummary] = useState('')
  const [viewVersion, setViewVersion] = useState(null)
  const [actor, setActor] = useState(() => localStorage.getItem('storypointer.requirements.actor') || 'Plan contributor')
  const [mermaidDialog, setMermaidDialog] = useState(null) // null | 'choose' | 'ai'
  const [mermaidPrompt, setMermaidPrompt] = useState('')
  const [mermaidType, setMermaidType] = useState('architecture')
  const [mermaidBusy, setMermaidBusy] = useState(false)
  const [markdownStudio, setMarkdownStudio] = useState(null)
  const editorRef = useRef(null)

  const loadList = useCallback(async (preferredId) => {
    const next = await api.listRequirements(projectId, l1Id)
    setDocuments(next)
    setSelectedId((current) => preferredId || (next.some((item) => item.id === current) ? current : next[0]?.id || null))
  }, [projectId, l1Id])
  const loadDocument = useCallback(async () => {
    if (!selectedId) { setDocument(null); setDraft(null); return }
    const next = await api.getRequirement(projectId, selectedId)
    setDocument(next)
    setDraft({ title: next.title, content: next.content })
    setViewVersion(null)
  }, [projectId, selectedId])
  const reload = useCallback(async () => {
    await loadList(selectedId)
    await loadDocument()
  }, [loadDocument, loadList, selectedId])

  useEffect(() => {
    setLoading(true)
    setSelectedId(null)
    setDocument(null)
    loadList().catch(setError).finally(() => setLoading(false))
  }, [loadList, setError])
  useEffect(() => { loadDocument().catch(setError) }, [loadDocument, setError])
  useEffect(() => {
    const normalized = actor.trim() || 'Plan contributor'
    localStorage.setItem('storypointer.requirements.actor', normalized)
  }, [actor])

  const dirty = !!(document && draft && (document.title !== draft.title || document.content !== draft.content))
  const headings = useMemo(() => headingsFrom(viewVersion?.content ?? draft?.content ?? ''), [draft?.content, viewVersion])

  const create = async () => {
    if (!newTitle.trim()) return
    setBusy(true)
    try {
      const created = await api.createRequirement(projectId, l1Id, { title: newTitle.trim(), content: STARTER, actor: actor.trim() || 'Plan contributor' })
      setCreateOpen(false)
      setNewTitle('')
      await loadList(created.id)
    } catch (error) { setError(error) } finally { setBusy(false) }
  }
  const save = async () => {
    if (!dirty || !draft.title.trim()) return
    setBusy(true)
    try {
      const updated = await api.updateRequirement(projectId, document.id, {
        title: draft.title.trim(),
        content: draft.content,
        actor: actor.trim() || 'Plan contributor',
        change_summary: changeSummary.trim(),
        expected_version: document.version,
      })
      setDocument(updated)
      setDraft({ title: updated.title, content: updated.content })
      setChangeSummary('')
      await loadList(updated.id)
    } catch (error) { setError(error) } finally { setBusy(false) }
  }
  const review = async (action) => {
    setBusy(true)
    try {
      const note = action === 'approve' ? window.prompt('Approval note (optional)', '') ?? '' : ''
      const updated = await api.reviewRequirement(projectId, document.id, { action, actor: actor.trim() || 'Plan contributor', note })
      setDocument(updated)
      await loadList(updated.id)
    } catch (error) { setError(error) } finally { setBusy(false) }
  }
  const exportAs = async (format) => {
    setBusy(true)
    try {
      const diagramImages = await renderMermaidImages(document.content)
      saveDownload(await api.exportRequirement(projectId, document.id, format, { diagram_images: diagramImages }))
    }
    catch (error) { setError(error) } finally { setBusy(false) }
  }
  const insertDiagram = () => {
    editorRef.current?.insertSnippet(MERMAID_BLOCK_TEMPLATE)
    setMode('split')
  }
  const insertSkeleton = () => { insertDiagram(); setMermaidDialog(null) }
  const generateMermaid = async () => {
    if (!mermaidPrompt.trim()) return
    setMermaidBusy(true)
    try {
      const reply = await api.assistDiagram(projectId, l1Id, { prompt: mermaidPrompt.trim(), current_source: '', diagram_type: mermaidType })
      editorRef.current?.insertMermaidSource(reply.mermaid)
      setMermaidDialog(null); setMermaidPrompt('')
    } catch (error) { setError(error) } finally { setMermaidBusy(false) }
  }
  const saveMarkdownDiagram = (payload) => {
    const replaced = editorRef.current?.replaceMermaidBlock(markdownStudio.index, payload.mermaid_source)
    if (replaced) setMode('split')
    setMarkdownStudio(null)
  }
  const openVersion = async (version) => {
    try { setViewVersion(await api.getRequirementVersion(projectId, document.id, version)) }
    catch (error) { setError(error) }
  }

  if (loading) return <div className="l1-loading">Loading requirements…</div>

  return <section>
    <div className="l1-section-heading">
      <div><h2>Detailed requirements</h2><p>Create multiple living Markdown documents, embed editable Mermaid diagrams, review with comments and approvals, and preserve every decision in an audit trail.</p></div>
      <div className="req-heading-actions">
        <label><span>Working as</span><input value={actor} onChange={(event) => setActor(event.target.value)} aria-label="Audit actor name" /></label>
        <button className="m3-btn filled small" onClick={() => setCreateOpen(true)}><FilePlus2 size={15} /> New document</button>
      </div>
    </div>

    {documents.length === 0
      ? <div className="l1-empty-panel"><FileText size={34} /><h3>Turn the initiative into reviewable requirements</h3><p>Start a Markdown document with goals, functional and non-functional requirements, assumptions, and an editable Mermaid flow.</p><button className="m3-btn filled" onClick={() => setCreateOpen(true)}><Plus size={16} /> Create requirements</button></div>
      : <div className="req-workspace">
        <DockablePanel id="req-doc-list" side="left" title="Documents" defaultWidth={210} minWidth={170} maxWidth={340}>
          <aside className="req-document-list">
            <header><span className="l1-eyebrow">Documents</span><button className="m3-icon-btn" onClick={() => setCreateOpen(true)} aria-label="New requirement document"><Plus size={17} /></button></header>
            {documents.map((item) => <button key={item.id} className={selectedId === item.id ? 'active' : ''} onClick={() => setSelectedId(item.id)}>
              <span className="req-doc-icon"><FileText size={16} /></span>
              <span><strong>{item.title}</strong><small>v{item.version} · {statusLabel(item.status)}{item.open_comments ? ` · ${item.open_comments} open` : ''}</small></span>
              <ChevronRight size={15} />
            </button>)}
            {headings.length > 0 && <div className="req-toc"><span className="l1-eyebrow">On this page</span>{headings.map((heading, index) => <a key={`${heading.id}-${index}`} style={{ paddingLeft: `${8 + (heading.level - 1) * 10}px` }} href={`#${heading.id}`}>{heading.text}</a>)}</div>}
          </aside>
        </DockablePanel>

        {document && draft && <main className="req-editor-shell">
          <header className="req-editor-toolbar">
            <div className="req-title-field"><input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} aria-label="Requirement document title" /><span className={`req-status ${document.status}`}>{statusLabel(document.status)}</span><small>v{document.version}</small></div>
            <div className="req-export-menu">
              <button className="m3-btn text small" disabled={busy || dirty} onClick={() => exportAs('docx')}><Download size={14} /> Word</button>
              <button className="m3-btn text small" disabled={busy || dirty} onClick={() => exportAs('pptx')}><Download size={14} /> PPT</button>
            </div>
          </header>

          {viewVersion && <div className="req-version-banner"><History size={15} /> Viewing version {viewVersion.version} from {new Date(viewVersion.created_at).toLocaleString()}<button onClick={() => setViewVersion(null)}>Back to current</button><button onClick={() => { setDraft({ title: viewVersion.title, content: viewVersion.content }); setViewVersion(null) }}>Restore into editor</button></div>}
          <MarkdownEditor
            ref={editorRef}
            value={draft.content}
            onChange={(content) => setDraft((current) => ({ ...current, content }))}
            previewValue={viewVersion?.content ?? draft.content}
            mode={mode}
            onModeChange={setMode}
            onInsertMermaid={() => setMermaidDialog('choose')}
            onEditMermaid={viewVersion ? null : ({ index, source }) => setMarkdownStudio({ index, source })}
            placeholder="Capture requirements, assumptions, decisions, and Mermaid diagrams..."
          />

          <footer className="req-document-actions">
            <label><span>Change summary</span><input value={changeSummary} onChange={(event) => setChangeSummary(event.target.value)} placeholder="What changed in this version?" /></label>
            <span>{dirty ? 'Unsaved changes' : `Saved ${new Date(document.updated_at).toLocaleString()}`}</span>
            {document.status === 'draft' && <button className="m3-btn tonal small" disabled={busy || dirty} onClick={() => review('submit')}><Send size={14} /> Submit review</button>}
            {document.status !== 'approved' && <button className="m3-btn tonal small success" disabled={busy || dirty} onClick={() => review('approve')}><CheckCircle2 size={14} /> Approve document</button>}
            {document.status === 'approved' && <button className="m3-btn text small" disabled={busy} onClick={() => review('revoke')}><RotateCcw size={14} /> Revoke approval</button>}
            <button className="m3-btn filled small" disabled={busy || !dirty || !draft.title.trim()} onClick={save}><Save size={14} /> Save version</button>
          </footer>
        </main>}

        {document && <DockablePanel id="req-review" side="right" title="Review" defaultWidth={300} minWidth={240} maxWidth={460}>
          <AuditPanel document={document} actor={actor.trim() || 'Plan contributor'} reload={reload} setError={setError} onOpenVersion={openVersion} />
        </DockablePanel>}
      </div>}

    {createOpen && <PlanningDialog
      title="Create requirement document"
      onClose={() => setCreateOpen(false)}
      actions={<><button className="m3-btn text" onClick={() => setCreateOpen(false)}>Cancel</button><button className="m3-btn filled" disabled={busy || !newTitle.trim()} onClick={create}>Create document</button></>}>
      <label className="m3-field"><span>Document title</span><input autoFocus value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="Customer onboarding requirements" /></label>
      <p className="req-dialog-note">A structured starter with an editable Mermaid requirement flow will be added automatically.</p>
    </PlanningDialog>}

    {mermaidDialog && <PlanningDialog
      title={mermaidDialog === 'ai' ? 'Generate a diagram with AI' : 'Insert a Mermaid diagram'}
      onClose={() => { setMermaidDialog(null); setMermaidPrompt('') }}
      actions={mermaidDialog === 'ai'
        ? <>
            <button className="m3-btn text" onClick={() => setMermaidDialog('choose')}>Back</button>
            <button className="m3-btn filled" disabled={mermaidBusy || !mermaidPrompt.trim()} onClick={generateMermaid}><Sparkles size={15} /> {mermaidBusy ? 'Generating…' : 'Generate & insert'}</button>
          </>
        : <button className="m3-btn text" onClick={() => setMermaidDialog(null)}>Cancel</button>}>
      {mermaidDialog === 'choose' && <div className="req-mermaid-choices">
        <button type="button" className="req-mermaid-choice" onClick={insertSkeleton}>
          <Code2 size={22} />
          <strong>Start from a skeleton</strong>
          <span>Insert an editable flowchart template you can adapt by hand.</span>
        </button>
        <button type="button" className="req-mermaid-choice" onClick={() => setMermaidDialog('ai')}>
          <Sparkles size={22} />
          <strong>Generate with AI</strong>
          <span>Describe the diagram in words and let AI draft the Mermaid for you.</span>
        </button>
      </div>}
      {mermaidDialog === 'ai' && <>
        <label className="m3-field"><span>Diagram style</span>
          <select value={mermaidType} onChange={(event) => setMermaidType(event.target.value)}>
            <DiagramTypeOptions />
          </select></label>
        <label className="m3-field"><span>Describe the diagram</span>
          <textarea autoFocus rows={5} value={mermaidPrompt} onChange={(event) => setMermaidPrompt(event.target.value)}
            placeholder="e.g. A user signs in through the web app, which calls the auth service and a session store, then redirects to the dashboard." /></label>
        <p className="req-dialog-note">The generated Mermaid block is inserted at your cursor. You can edit it afterwards or refine it in the diagram studio.</p>
      </>}
    </PlanningDialog>}

    {markdownStudio && <DiagramStudio
      key={`markdown-diagram-${markdownStudio.index}`}
      diagram={{
        id: `markdown-diagram-${markdownStudio.index}`,
        title: 'Markdown diagram',
        diagram_type: 'architecture',
        mermaid_source: markdownStudio.source,
        metadata: { nodes: {}, positions: {} },
      }}
      onSave={saveMarkdownDiagram}
      onAssist={(payload) => api.assistDiagram(projectId, l1Id, payload)}
      onClose={() => setMarkdownStudio(null)}
    />}
  </section>
}
