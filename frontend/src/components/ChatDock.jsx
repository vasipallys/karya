import { ArrowUpRight, Bot, Check, Code2, FileText, History, Image, Maximize2, MessageSquare, Mic, Minimize2, Paperclip, PanelRight, PanelRightClose, Plus, Search, Send, Sparkles, Trash2, Volume2, VolumeX, WandSparkles, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useToast } from '../ui/Toast'

const SUGGESTIONS = [
  "What's the project status?",
  'What should I do next?',
  'List L2 containers',
  'Create a tribe for this initiative',
]

const CHAT_MODES = [
  { key: 'auto', label: 'Auto', icon: WandSparkles, hint: 'Ask or instruct\u2026' },
  { key: 'chat', label: 'Chat', icon: MessageSquare, hint: 'Ask a question\u2026' },
  { key: 'code', label: 'Code', icon: Code2, hint: 'Describe code to write or review\u2026' },
  { key: 'research', label: 'Research', icon: Search, hint: 'What should I research?\u2026' },
  { key: 'image', label: 'Image', icon: Image, hint: 'Describe a visual, SVG, or diagram\u2026' },
  { key: 'document', label: 'Document', icon: FileText, hint: 'Write or review a document\u2026' },
]

// Floating conversational assistant: query / report over the project, and propose
// C4 changes that the user applies with one click (writes need platform.edit).
export default function ChatDock({ projectId, onChanged, onOpenElement, onNavigate, screenContext = null }) {
  const toast = useToast()
  const { can } = useAuth()
  const canEdit = can('platform.edit')
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([{ role: 'assistant', text: "Hi! Ask about this platform or instruct me to update its C4 model or operating plan—including tribes, squads, and team members. I’ll show a reviewable proposal before any write." }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [conversations, setConversations] = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const [attachments, setAttachments] = useState([])
  const [chatMode, setChatMode] = useState(() => {
    try { return window.localStorage.getItem('karya.chat.mode') || 'auto' } catch { return 'auto' }
  })
  const fileInput = useRef(null)
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  // Window mode: floating bubble, docked right-side panel, or maximized.
  const [mode, setMode] = useState(() => {
    try { return window.localStorage.getItem('karya.chatdock.mode') || 'float' } catch { return 'float' }
  })
  useEffect(() => { try { window.localStorage.setItem('karya.chatdock.mode', mode) } catch { /* ignore */ } }, [mode])
  useEffect(() => { try { window.localStorage.setItem('karya.chat.mode', chatMode) } catch { /* ignore */ } }, [chatMode])
  const scroller = useRef(null)
  const recognition = useRef(null)
  const speakingRef = useRef(false)
  const SpeechRec = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null

  useEffect(() => { if (open && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight }, [messages, open])
  useEffect(() => { speakingRef.current = speaking; if (!speaking) window.speechSynthesis?.cancel() }, [speaking])
  useEffect(() => () => { recognition.current?.stop?.(); window.speechSynthesis?.cancel() }, [])
  useEffect(() => {
    if (!open) return
    api.chatConversations?.(projectId).then(setConversations).catch(() => {})
  }, [open, projectId, messages.length])

  const newChat = async () => {
    const convo = await api.chatNewConversation(projectId)
    setConversationId(convo.id); setMessages([]); setAttachments([]); setShowHistory(false)
  }

  const openConversation = async (id) => {
    const convo = await api.chatConversation(projectId, id)
    setConversationId(id)
    setMessages(convo.messages.map((m) => ({ role: m.role, text: m.text, ...(m.payload || {}) })))
    setAttachments([]); setShowHistory(false)
  }

  const removeConversation = async (event, id) => {
    event.stopPropagation(); await api.chatDeleteConversation(projectId, id)
    setConversations((items) => items.filter((c) => c.id !== id))
    if (conversationId === id) { setConversationId(null); setMessages([]) }
  }

  const addFiles = async (event) => {
    const files = [...(event.target.files || [])]
    if (!files.length) return
    setBusy(true)
    try {
      let id = conversationId
      if (!id) { const convo = await api.chatNewConversation(projectId); id = convo.id; setConversationId(id) }
      for (const file of files.slice(0, 10 - attachments.length)) {
        const uploaded = await api.chatUpload(projectId, id, file)
        setAttachments((items) => [...items, uploaded])
      }
    } catch (err) { toast.error(err) } finally { setBusy(false); event.target.value = '' }
  }

  const say = (text) => {
    if (!speakingRef.current || !window.speechSynthesis) return
    const plain = String(text || '').replace(/\*\*/g, '').trim()
    if (!plain) return
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(plain))
  }

  const BRANCHES = { planner: 'Planner', retrieval: 'Retrieval', tools: 'Tools' }
  const [activity, setActivity] = useState(null) // { planner|retrieval|tools: {status, summary}, judge }

  const pushAssistant = (res) => {
    setMessages((m) => [...m, { role: 'assistant', text: res.reply, action: res.action, data: res.data, mutation: res.mutation, evidence: res.evidence }])
    say(res.reply)
  }

  const send = async (text) => {
    const message = (text ?? input).trim()
    if (!message || busy) return
    // Recent turns give the interpreter context for follow-up answers.
    const history = messages.slice(-8).map((m) => ({ role: m.role, text: String(m.text || '') }))
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: message }])
    setBusy(true)
    setActivity({ planner: { status: 'running' }, retrieval: { status: 'running' }, tools: { status: 'running' }, judge: null })
    let done = false
    try {
      // Concurrent-agent stream: branch partials land as they complete.
      const handleEvent = (event, data) => {
        if (event === 'branch') {
          const summary = data.branch === 'planner' ? `interpreted: ${data.plan?.action || '…'}`
            : data.branch === 'retrieval' ? (data.facts?.summary || 'model facts collected')
            : (data.tool_runs?.summary || 'tools ran')
          setActivity((a) => a && { ...a, [data.branch]: { status: 'done', summary } })
        } else if (event === 'judge') {
          setActivity((a) => a && { ...a, judge: data })
        } else if (event === 'result') {
          done = true
          setConversationId(data.conversation_id)
          setAttachments([])
          pushAssistant(data)
        } else if (event === 'error') {
          done = true
          setMessages((m) => [...m, { role: 'assistant', text: data.message, error: true }])
          say(data.message)
        }
      }
      if (chatMode === 'auto' && !conversationId && !attachments.length) {
        await api.chatStream(projectId, message, history, handleEvent, undefined, null, [], 'auto', screenContext)
      } else {
        await api.chatStream(projectId, message, history, handleEvent, undefined, conversationId,
          attachments.map((a) => a.id), chatMode, screenContext)
      }
      if (!done) throw new Error('The assistant stream ended unexpectedly.')
    } catch (err) {
      if (!done) {
        // Streaming unavailable — fall back to the plain endpoint.
        try {
          const result = chatMode === 'auto' && !conversationId && !attachments.length
            ? await api.chat(projectId, message, history, null, [], 'auto', screenContext)
            : await api.chat(projectId, message, history, conversationId, attachments.map((a) => a.id), chatMode, screenContext)
          setConversationId(result.conversation_id); setAttachments([]); pushAssistant(result)
        }
        catch (inner) {
          setMessages((m) => [...m, { role: 'assistant', text: String(inner.message || inner), error: true }])
          say(String(inner.message || inner))
        }
      }
    } finally { setBusy(false); setActivity(null) }
  }

  const toggleMic = () => {
    if (listening) { recognition.current?.stop(); return }
    const rec = new SpeechRec()
    rec.lang = navigator.language || 'en-US'
    rec.interimResults = false
    rec.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || ''
      if (transcript.trim()) send(transcript)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => { setListening(false); toast.error('Voice input failed — check the microphone permission.') }
    recognition.current = rec
    setListening(true)
    rec.start()
  }

  const apply = async (mutation, index) => {
    setBusy(true)
    try {
      const res = await api.chatApply(projectId, mutation)
      setMessages((m) => m.map((msg, i) => i === index ? { ...msg, mutation: null, applied: true } : msg))
      setMessages((m) => [...m, { role: 'assistant', text: res.reply, applied: true, result: res.result }])
      toast.success(res.reply)
      say(res.reply)
      onChanged?.()
    } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  const dismiss = (index) => setMessages((m) => m.map((msg, i) => i === index ? { ...msg, mutation: null, dismissed: true } : msg))

  return (
    <>
      {!open && (
        <button className="chatdock-fab" onClick={() => setOpen(true)} aria-label="Open assistant">
          <MessageSquare size={22} /> <span>Assistant</span>
        </button>
      )}
      {open && (
        <div className={`chatdock mode-${mode}`} role="dialog" aria-label="Assistant">
          <header className="chatdock-head">
            <span className="chatdock-title"><Bot size={17} /> Assistant</span>
            <button className="m3-icon-btn" onClick={newChat} aria-label="New chat" title="New chat"><Plus size={16} /></button>
            <button className="m3-icon-btn" onClick={() => setShowHistory((value) => !value)} aria-label="Chat history" title="Chat history"><History size={16} /></button>
            <button className="m3-icon-btn" onClick={() => setSpeaking((s) => !s)}
              aria-label={speaking ? 'Turn off spoken replies' : 'Read replies aloud'}
              title={speaking ? 'Spoken replies on' : 'Read replies aloud'}>
              {speaking ? <Volume2 size={16} /> : <VolumeX size={16} />}</button>
            <button className="m3-icon-btn" onClick={() => setMode(mode === 'docked' ? 'float' : 'docked')}
              aria-label={mode === 'docked' ? 'Undock assistant' : 'Dock assistant to the side'}
              title={mode === 'docked' ? 'Undock' : 'Dock to the side'}>
              {mode === 'docked' ? <PanelRightClose size={16} /> : <PanelRight size={16} />}</button>
            <button className="m3-icon-btn" onClick={() => setMode(mode === 'max' ? 'float' : 'max')}
              aria-label={mode === 'max' ? 'Restore assistant size' : 'Maximize assistant'}
              title={mode === 'max' ? 'Restore' : 'Maximize'}>
              {mode === 'max' ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
            <button className="m3-icon-btn" onClick={() => setOpen(false)} aria-label="Close assistant"><X size={17} /></button>
          </header>

          {showHistory && <aside className="chatdock-history">
            <div className="chatdock-history-head"><strong>Recent chats</strong><button className="m3-btn text small" onClick={newChat}><Plus size={14} /> New</button></div>
            {conversations.length === 0 && <p>No saved chats yet.</p>}
            {conversations.map((c) => <button key={c.id} className={c.id === conversationId ? 'active' : ''} onClick={() => openConversation(c.id)}>
              <span><strong>{c.title}</strong><small>{c.message_count} messages · {new Date(c.updated_at).toLocaleString()}</small></span>
              <Trash2 size={14} onClick={(event) => removeConversation(event, c.id)} aria-label="Delete chat" />
            </button>)}
          </aside>}

          <div className="chatdock-body" ref={scroller}>
            {messages.length === 0 && <div className="chatdock-empty"><MessageSquare size={32} /><h3>How can I help?</h3><p>Ask about this project, generate code, research the web, review a file, or propose an application change.</p></div>}
            {messages.map((m, i) => (
              <div key={i} className={`chatdock-msg ${m.role}`}>
                <div className={`chatdock-bubble${m.error ? ' error' : ''}${m.applied ? ' applied' : ''}`}>
                  <RichText text={m.text} />
                  {m.data && <DataView action={m.action} data={m.data} onOpen={onOpenElement} />}
                  {m.applied && m.result?.id && m.result?.level && onOpenElement && (
                    <button className="chatdock-link chatdock-open" onClick={() => onOpenElement(m.result)}>
                      <ArrowUpRight size={13} /> Open “{m.result.name}”</button>
                  )}
                  {m.applied && m.result?.workspace && onNavigate && (
                    <button className="chatdock-link chatdock-open" onClick={() => onNavigate(m.result)}>
                      <ArrowUpRight size={13} /> Open operating plan</button>
                  )}
                  {m.mutation && (
                    <div className="chatdock-propose">
                      <div className="chatdock-propose-head"><Sparkles size={13} /> Proposed change</div>
                      <p>{m.mutation.summary}</p>
                      {canEdit
                        ? <div className="chatdock-propose-actions">
                            <button className="m3-btn filled small" disabled={busy} onClick={() => apply(m.mutation, i)}><Check size={13} /> Apply</button>
                            <button className="m3-btn text small" disabled={busy} onClick={() => dismiss(i)}>Dismiss</button>
                          </div>
                        : <p className="chatdock-note">You need edit rights to apply changes.</p>}
                    </div>
                  )}
                  {m.dismissed && <p className="chatdock-note">Dismissed.</p>}
                  {m.evidence && <details className="chatdock-evidence">
                    <summary>Agent evidence</summary>
                    {m.evidence.retrieval?.summary && <p><strong>Model:</strong> {m.evidence.retrieval.summary}</p>}
                    {(m.evidence.tools || []).map((call, j) => <p key={j}><strong>{call.tool}:</strong> {call.summary}</p>)}
                    {m.evidence.verdict && <p><strong>Judge:</strong> {m.evidence.verdict.reason}</p>}
                  </details>}
                </div>
              </div>
            ))}
            {activity && <div className="chatdock-msg assistant"><div className="chatdock-bubble chatdock-activity" aria-label="Agent activity">
              {Object.entries(BRANCHES).map(([key, label]) => <div key={key} className={`chatdock-branch ${activity[key]?.status || 'running'}`}>
                <span className="chatdock-branch-dot" aria-hidden="true" />
                <strong>{label}</strong>
                <span>{activity[key]?.status === 'done' ? activity[key].summary : 'working…'}</span>
              </div>)}
              {activity.judge && <div className="chatdock-branch judge done"><span className="chatdock-branch-dot" aria-hidden="true" /><strong>Judge</strong><span>{activity.judge.reason}</span></div>}
            </div></div>}
            {busy && !activity && <div className="chatdock-msg assistant"><div className="chatdock-bubble chatdock-typing"><span></span><span></span><span></span></div></div>}
          </div>

          {messages.length <= 1 && (
            <div className="chatdock-suggest">
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
            </div>
          )}

          <div className="chatdock-input">
            <input ref={fileInput} type="file" multiple hidden onChange={addFiles} />
            <div className="chatdock-compose">
            {attachments.length > 0 && <div className="chatdock-files">{attachments.map((a) => <span key={a.id}>{a.filename}<button onClick={() => setAttachments((items) => items.filter((x) => x.id !== a.id))}>×</button></span>)}</div>}
            <input value={input} placeholder={listening ? 'Listening…' : CHAT_MODES.find((item) => item.key === chatMode)?.hint} disabled={busy}
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') send() }} />
            <div className="chatdock-compose-bar">
              <button className="m3-icon-btn" onClick={() => fileInput.current?.click()} disabled={busy} aria-label="Add files" title="Add files"><Paperclip size={16} /></button>
              <div className="chatdock-modes" role="group" aria-label="Assistant mode">
                {CHAT_MODES.map(({ key, label, icon: Icon }) => <button key={key} type="button"
                  className={chatMode === key ? 'active' : ''} aria-pressed={chatMode === key}
                  onClick={() => setChatMode(key)} disabled={busy} title={`${label} mode`}>
                  <Icon size={13} /><span>{label}</span></button>)}
              </div>
              {SpeechRec && <button className={`m3-icon-btn chatdock-mic${listening ? ' listening' : ''}`}
                onClick={toggleMic} disabled={busy} aria-label={listening ? 'Stop listening' : 'Speak your request'}
                title={listening ? 'Listening… click to stop' : 'Speak your request'}><Mic size={16} /></button>}
              <button className="m3-icon-btn chatdock-send" disabled={busy || !input.trim()} onClick={() => send()} aria-label="Send"><Send size={15} /></button>
            </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function RichText({ text }) {
  return <div className="chatdock-text"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
  }}>{String(text || '')}</ReactMarkdown></div>
}

function DataView({ action, data, onOpen }) {
  if (action === 'list_agile_units' && data.items) {
    if (data.items.length === 0) return null
    return <ul className="chatdock-list">{data.items.slice(0, 12).map((it) => (
      <li key={it.id}><span className="chatdock-lvl">{it.unit_type}</span>
        <span>{it.name}</span> <em>{it.members} people{it.lead_name ? ` · ${it.lead_name}` : ''} · {it.l1_name}</em></li>
    ))}{data.items.length > 12 && <li>…and {data.items.length - 12} more</li>}</ul>
  }
  if (action === 'list' && data.items) {
    if (data.items.length === 0) return null
    return <ul className="chatdock-list">{data.items.slice(0, 12).map((it, i) => (
      <li key={i}><span className="chatdock-lvl">{it.level}</span>
        {it.id && onOpen
          ? <button className="chatdock-link" title={`Open ${it.name} in its ${it.level} workspace`}
              onClick={() => onOpen(it)}>{it.name}</button>
          : <span>{it.name}</span>} <em>{it.status}</em></li>
    ))}{data.items.length > 12 && <li>…and {data.items.length - 12} more</li>}</ul>
  }
  if (action === 'readiness' && Array.isArray(data.items)) {
    if (data.items.length === 0) return null
    return <ul className="chatdock-list">{data.items.slice(0, 12).map((it) => (
      <li key={it.id}><span className="chatdock-lvl">{it.level}</span>
        {it.id && onOpen
          ? <button className="chatdock-link" title={`Open ${it.name} in its ${it.level} workspace`}
              onClick={() => onOpen(it)}>{it.name}</button>
          : <span>{it.name}</span>} <em>{it.score}% · {it.status_label}</em></li>
    ))}{data.items.length > 12 && <li>…and {data.items.length - 12} more</li>}</ul>
  }
  if (action === 'describe' && data.element) {
    const item = data.element
    return <div className="chatdock-score"><strong>{item.level}</strong> {item.status}
      {typeof data.readiness?.score === 'number' && <> · {data.readiness.score}% ready</>}
      {item.id && onOpen && <button className="chatdock-link" title={`Open ${item.name} in its ${item.level} workspace`}
        onClick={() => onOpen(item)}><ArrowUpRight size={12} /> open workspace</button>}</div>
  }
  if ((action === 'readiness' || action === 'overview') && typeof data.score === 'number') {
    return <div className="chatdock-score"><strong>{data.score}%</strong> {data.status_label}
      {data.id && data.level && onOpen && <button className="chatdock-link" title={`Open ${data.name} in its ${data.level} workspace`}
        onClick={() => onOpen(data)}><ArrowUpRight size={12} /> open workspace</button>}</div>
  }
  if (action === 'overview' && Array.isArray(data.levels)) {
    return <div className="chatdock-levels">{data.levels.map((l) => (
      <span key={l.level} className={`chatdock-chip status-${l.status}`}>{l.level} {l.avg_readiness}%</span>
    ))}</div>
  }
  return null
}
