import { ArrowRight, Copy, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import PlanningDialog from '../planning/PlanningDialog'
import { useToast } from '../ui/Toast'
import { ACTION_LABELS } from './askAiRouting'

/**
 * Application-level AI entry point: routes a natural-language request through
 * the /ai/orchestrate endpoint to the best specialized agent, then offers to
 * take the user to the workspace that runs it.
 */
export default function AskAiDialog({ onClose, onNavigate }) {
  const toast = useToast()
  const [request, setRequest] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const ask = async () => {
    if (!request.trim() || busy) return
    setBusy(true)
    try { setResult(await api.aiOrchestrate(request.trim())) }
    catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  const copyPrompt = () => {
    navigator.clipboard?.writeText(result.suggested_prompt)
    toast.success('Prompt copied')
  }

  return <PlanningDialog title="Ask AI" onClose={onClose}
    actions={<>
      <button className="m3-btn text" onClick={onClose}>Cancel</button>
      <button className="m3-btn filled" disabled={busy || !request.trim()} onClick={ask}>
        <Sparkles size={15} /> {busy ? 'Thinking…' : 'Ask'}</button>
    </>}>
    <label className="m3-field"><span>What do you want to do?</span>
      <textarea autoFocus rows={3} value={request} onChange={(e) => setRequest(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }}
        placeholder="e.g. break the checkout epic into stories, or draft the vision and OKRs for this initiative" /></label>

    {result && <div className="ask-ai-result">
      <div className="m3-banner info"><strong>{ACTION_LABELS[result.action] || result.action}</strong> — {result.rationale}</div>
      {result.suggested_prompt && <div className="ask-ai-prompt">
        <pre>{result.suggested_prompt}</pre>
        <button className="m3-btn text small" onClick={copyPrompt}><Copy size={13} /> Copy prompt</button>
      </div>}
      {result.action !== 'none'
        ? <button className="m3-btn filled small" onClick={() => { onNavigate?.(result.action); onClose() }}>
          <ArrowRight size={14} /> Take me there</button>
        : <p className="ai-hint">No specific workspace action — try refining the request, or use the project assistant for questions about a platform.</p>}
    </div>}
  </PlanningDialog>
}
