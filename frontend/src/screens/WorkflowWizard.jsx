import { ArrowRight, Boxes, Check, ChevronLeft, ChevronRight, Code2, Compass, Landmark, Puzzle, Sigma, Sparkles, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../ui/Toast'

const LEVEL_ICON = { L1: Landmark, L2: Boxes, L3: Puzzle, L4: Code2 }
const STATUS = {
  not_started: { label: 'Not started', cls: 'todo' },
  in_progress: { label: 'In progress', cls: 'wip' },
  ready: { label: 'Ready', cls: 'ok' },
}

// A guided top-down tour of the C4 workflow (L1 → L2 → L3 → L4 → estimation).
// Each step shows the level's live status + readiness and the next-best actions;
// acting on one navigates straight to the relevant workspace tab.
export default function WorkflowWizard({ projectId, onNavigate, onClose }) {
  const toast = useToast()
  const [guide, setGuide] = useState(null)
  const [step, setStep] = useState(0)

  useEffect(() => { api.workflowGuide(projectId).then(setGuide).catch((err) => toast.error(err)) }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const steps = useMemo(() => {
    if (!guide) return []
    return [
      ...guide.levels.map((lvl) => ({ kind: 'level', ...lvl })),
      { kind: 'estimate', level: 'EST', ...guide.estimation },
    ]
  }, [guide])

  const go = (tab) => { onNavigate(tab); onClose() }

  if (!guide) {
    return <Scrim onClose={onClose}><div className="wf-wizard"><div className="l1-loading">Building your workflow guide…</div></div></Scrim>
  }

  const current = steps[step]
  const Icon = current.kind === 'estimate' ? Sigma : (LEVEL_ICON[current.level] || Compass)
  const status = current.kind === 'estimate'
    ? STATUS[current.status]
    : STATUS[current.status]
  const readiness = current.kind === 'estimate' ? current.pct : current.avg_readiness

  return (
    <Scrim onClose={onClose}>
      <div className="wf-wizard" role="dialog" aria-modal="true" aria-label="Workflow guide">
        <header className="wf-head">
          <div className="wf-head-title"><Compass size={18} /> <strong>Workflow guide</strong> · {guide.project.name}</div>
          <button className="m3-icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>

        <div className="wf-overall">
          <div className="wf-overall-bar"><span style={{ width: `${guide.overall_pct}%` }} /></div>
          <div className="wf-overall-meta">
            <span><strong>{guide.overall_pct}%</strong> overall</span>
            <span className="wf-stage">Stage: {guide.stage}</span>
          </div>
          {guide.next_action && guide.next_action.tab && (
            <button className="m3-btn filled small wf-next" onClick={() => go(guide.next_action.tab)}>
              <Sparkles size={14} /> Next best step: {guide.next_action.text} <ArrowRight size={13} />
            </button>
          )}
        </div>

        <ol className="wf-stepper">
          {steps.map((s, i) => {
            const st = STATUS[s.status]
            return (
              <li key={s.level} className={`${i === step ? 'current' : ''} step-${st.cls}`}>
                <button onClick={() => setStep(i)} title={s.label}>
                  <span className="wf-dot">{s.status === 'ready' ? <Check size={13} /> : s.level}</span>
                  <span className="wf-step-label">{s.level === 'EST' ? 'Est.' : s.level}</span>
                </button>
              </li>
            )
          })}
        </ol>

        <div className="wf-body">
          <div className="wf-body-head">
            <span className="wf-body-icon"><Icon size={22} /></span>
            <div>
              <h3>{current.label} <span className={`res-pill ${status.cls === 'ok' ? 'ok' : status.cls === 'wip' ? '' : 'sub-partiallyallocated'}`}>{status.label}</span></h3>
              <p>{current.kind === 'estimate'
                ? 'Estimate stories with the evidence-led pipeline; points roll up to epics and initiatives.'
                : current.purpose}</p>
            </div>
          </div>

          <div className="wf-stats">
            {current.kind === 'estimate' ? <>
              <Stat label="Stories" value={current.total} />
              <Stat label="Estimated" value={`${current.estimated}/${current.total}`} />
              <Stat label="Rolled-up points" value={current.points} />
              <Stat label="Coverage" value={`${current.pct}%`} />
            </> : <>
              <Stat label={`${current.level} elements`} value={current.count} />
              <Stat label="Ready" value={`${current.ready}/${current.count}`} />
              <Stat label="Avg readiness" value={`${readiness}%`} />
              {current.proposed > 0 && <Stat label="Proposed" value={current.proposed} />}
            </>}
          </div>
          <div className="wf-readiness-bar"><span style={{ width: `${readiness}%` }} /></div>

          <div className="wf-actions">
            <h4>Recommended next actions</h4>
            {current.actions.length === 0
              ? <p className="l1-node-empty">Nothing to do here right now.</p>
              : current.actions.map((a, i) => (
                <button key={i} className={`wf-action tone-${a.tone}`} onClick={() => go(a.tab)}>
                  <span>{a.text}</span><ArrowRight size={14} />
                </button>
              ))}
          </div>
        </div>

        <footer className="wf-foot">
          <button className="m3-btn text" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}><ChevronLeft size={15} /> Back</button>
          <span className="wf-foot-count">{step + 1} / {steps.length}</span>
          {step < steps.length - 1
            ? <button className="m3-btn tonal" onClick={() => setStep((s) => Math.min(steps.length - 1, s + 1))}>Next <ChevronRight size={15} /></button>
            : <button className="m3-btn filled" onClick={onClose}>Done</button>}
        </footer>
      </div>
    </Scrim>
  )
}

function Stat({ label, value }) {
  return <div className="wf-stat"><strong>{value}</strong><span>{label}</span></div>
}

function Scrim({ children, onClose }) {
  return <div className="wf-scrim" onMouseDown={onClose}><div onMouseDown={(e) => e.stopPropagation()}>{children}</div></div>
}
