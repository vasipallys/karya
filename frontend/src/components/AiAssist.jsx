import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../ui/Toast'

/**
 * Control-level AI assist: a small tonal button that summarizes/drafts text for
 * a single field via the /ai/summarize endpoint. The result is handed back
 * through onResult for the user to review — it never persists anything itself.
 *
 * getSource is a function (not a string) so callers can assemble the source
 * from live component state at click time.
 */
export default function AiAssist({
  getSource,
  field = 'default',
  onResult,
  label = 'AI summarize → field',
  busyLabel = 'Summarizing…',
  emptyMessage = 'Add some details first, then summarize.',
  disabled = false,
}) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)

  const run = async () => {
    const source = (getSource?.() || '').trim()
    if (!source) { toast.info(emptyMessage); return }
    setBusy(true)
    try {
      const { summary } = await api.aiSummarize(source, field)
      onResult?.(summary)
      toast.success('Summary generated — review and save')
    } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  return <button type="button" className="m3-btn tonal small" disabled={disabled || busy} onClick={run}>
    <Sparkles size={13} /> {busy ? busyLabel : label}
  </button>
}
