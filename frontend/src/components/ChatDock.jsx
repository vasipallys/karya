import { Bot, Check, MessageSquare, Send, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useToast } from '../ui/Toast'

const SUGGESTIONS = [
  "What's the project status?",
  'What should I do next?',
  'List L2 containers',
  'Create an L2 container called payments',
]

// Floating conversational assistant: query / report over the project, and propose
// C4 changes that the user applies with one click (writes need platform.edit).
export default function ChatDock({ projectId, onChanged }) {
  const toast = useToast()
  const { can } = useAuth()
  const canEdit = can('platform.edit')
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([{ role: 'assistant', text: "Hi! Ask me about this platform, or tell me to create, rename or delete an element. I'll propose changes before anything is saved." }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scroller = useRef(null)

  useEffect(() => { if (open && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight }, [messages, open])

  const send = async (text) => {
    const message = (text ?? input).trim()
    if (!message || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: message }])
    setBusy(true)
    try {
      const res = await api.chat(projectId, message)
      setMessages((m) => [...m, { role: 'assistant', text: res.reply, action: res.action, data: res.data, mutation: res.mutation }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: String(err.message || err), error: true }])
    } finally { setBusy(false) }
  }

  const apply = async (mutation, index) => {
    setBusy(true)
    try {
      const res = await api.chatApply(projectId, mutation)
      setMessages((m) => m.map((msg, i) => i === index ? { ...msg, mutation: null, applied: true } : msg))
      setMessages((m) => [...m, { role: 'assistant', text: res.reply, applied: true }])
      toast.success(res.reply)
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
        <div className="chatdock" role="dialog" aria-label="Assistant">
          <header className="chatdock-head">
            <span className="chatdock-title"><Bot size={17} /> Assistant</span>
            <button className="m3-icon-btn" onClick={() => setOpen(false)} aria-label="Close assistant"><X size={17} /></button>
          </header>

          <div className="chatdock-body" ref={scroller}>
            {messages.map((m, i) => (
              <div key={i} className={`chatdock-msg ${m.role}`}>
                <div className={`chatdock-bubble${m.error ? ' error' : ''}${m.applied ? ' applied' : ''}`}>
                  <RichText text={m.text} />
                  {m.data && <DataView action={m.action} data={m.data} />}
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
                </div>
              </div>
            ))}
            {busy && <div className="chatdock-msg assistant"><div className="chatdock-bubble chatdock-typing"><span></span><span></span><span></span></div></div>}
          </div>

          {messages.length <= 1 && (
            <div className="chatdock-suggest">
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
            </div>
          )}

          <div className="chatdock-input">
            <input value={input} placeholder="Ask or instruct…" disabled={busy}
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') send() }} />
            <button className="m3-btn filled small" disabled={busy || !input.trim()} onClick={() => send()} aria-label="Send"><Send size={15} /></button>
          </div>
        </div>
      )}
    </>
  )
}

// Minimal **bold** renderer for chat bubbles (avoids pulling in a full markdown lib).
function RichText({ text }) {
  const parts = String(text || '').split(/(\*\*[^*]+\*\*)/g)
  return <p className="chatdock-text">{parts.map((p, i) => p.startsWith('**') && p.endsWith('**')
    ? <strong key={i}>{p.slice(2, -2)}</strong>
    : <span key={i}>{p}</span>)}</p>
}

function DataView({ action, data }) {
  if (action === 'list' && data.items) {
    if (data.items.length === 0) return null
    return <ul className="chatdock-list">{data.items.slice(0, 12).map((it, i) => (
      <li key={i}><span className="chatdock-lvl">{it.level}</span> {it.name} <em>{it.status}</em></li>
    ))}{data.items.length > 12 && <li>…and {data.items.length - 12} more</li>}</ul>
  }
  if ((action === 'readiness' || action === 'overview') && typeof data.score === 'number') {
    return <div className="chatdock-score"><strong>{data.score}%</strong> {data.status_label}</div>
  }
  if (action === 'overview' && Array.isArray(data.levels)) {
    return <div className="chatdock-levels">{data.levels.map((l) => (
      <span key={l.level} className={`chatdock-chip status-${l.status}`}>{l.level} {l.avg_readiness}%</span>
    ))}</div>
  }
  return null
}
