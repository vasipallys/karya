import { GitBranchPlus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import PlanningDialog from '../planning/PlanningDialog'
import { useToast } from '../ui/Toast'

/**
 * "Flow forward" bridge: turns the work already captured at one level into
 * proposed children one level down (vision → epics, requirements → epics,
 * epic → stories, story → tasks) so nothing has to be re-typed.
 *
 * Runs /ai/decompose with the caller's context as guidance, shows the
 * proposals for review (all preselected, deselectable), and applies the
 * chosen ones as `proposed` elements — they stay out of roll-ups until
 * accepted, matching the app's proposal-first AI principle.
 */
export default function FlowForward({
  projectId,
  elementId,
  label,
  childLabel = 'children',
  guidance,
  onApplied,
  disabled = false,
}) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [proposal, setProposal] = useState(null) // { result, selected:Set }

  const propose = async () => {
    setBusy(true)
    try {
      const result = await api.aiDecompose(projectId, elementId, (guidance?.() || '').trim())
      if (!result.stories?.length) { toast.info('The assistant found nothing to propose — add more detail first.'); return }
      setProposal({ result, selected: new Set(result.stories.map((_, index) => index)) })
    } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  const toggle = (index) => setProposal((current) => {
    const selected = new Set(current.selected)
    selected.has(index) ? selected.delete(index) : selected.add(index)
    return { ...current, selected }
  })

  const apply = async () => {
    const chosen = proposal.result.stories.filter((_, index) => proposal.selected.has(index))
    if (chosen.length === 0) { setProposal(null); return }
    setBusy(true)
    try {
      await api.applyDecompose(projectId, elementId, chosen)
      setProposal(null)
      toast.success(`Created ${chosen.length} proposed ${childLabel} — review and accept them`)
      onApplied?.()
    } catch (err) { toast.error(err) } finally { setBusy(false) }
  }

  return <>
    <button type="button" className="m3-btn tonal small" disabled={disabled || busy} onClick={propose}>
      <GitBranchPlus size={14} /> {busy && !proposal ? 'Thinking…' : label}
    </button>

    {proposal && <PlanningDialog wide title={`Proposed ${childLabel}`} onClose={() => setProposal(null)}
      actions={<>
        <button className="m3-btn text" onClick={() => setProposal(null)}>Cancel</button>
        <button className="m3-btn filled" disabled={busy || proposal.selected.size === 0} onClick={apply}>
          <Sparkles size={15} /> Create {proposal.selected.size} proposed</button>
      </>}>
      {proposal.result.summary && <div className="m3-banner info">{proposal.result.summary}</div>}
      <ul className="flow-forward-list">
        {proposal.result.stories.map((story, index) => <li key={index}>
          <label>
            <input type="checkbox" checked={proposal.selected.has(index)} onChange={() => toggle(index)} />
            <span><strong>{story.name}</strong>
              {story.description && <small>{story.description}</small>}
              {story.rationale && <em>{story.rationale}</em>}</span>
          </label>
        </li>)}
      </ul>
      <p className="ai-hint">Created items arrive as <code>proposed</code> and stay out of roll-ups until you accept them on the canvas.</p>
    </PlanningDialog>}
  </>
}
