import { Sparkles, Wand2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import PipelineView from '../components/PipelineView'
import ResultCard from '../components/ResultCard'

export default function EstimateDialog({ projectId, element, autoStart, cachedResult, onResult, onChanged, onClose }) {
  const [steps, setSteps] = useState([])
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(cachedResult || null)
  const [error, setError] = useState(null)
  const [refinement, setRefinement] = useState('')
  const controller = useRef(null)
  const startedRef = useRef(false)

  const run = async (withRefinement) => {
    setRunning(true); setError(null); setResult(null); setSteps([]); setRefinement('')
    controller.current = new AbortController()
    try {
      await api.estimateElement(projectId, element.id, { refinement: withRefinement || null }, (event, data) => {
        if (event === 'node') setSteps((current) => [...current, data.node])
        if (event === 'result') { setResult(data); onResult?.(data) }
        if (event === 'error') setError(new Error(data.message))
      }, controller.current.signal)
      onChanged?.()
    } catch (err) {
      if (err.name !== 'AbortError') setError(err)
    } finally { setRunning(false) }
  }

  useEffect(() => {
    if (autoStart && !cachedResult && !startedRef.current) { startedRef.current = true; run(null) }
    // Reset the guard on cleanup so React StrictMode's dev double-mount re-runs
    // the auto-start after its first pass is aborted, instead of leaving it blank.
    return () => { controller.current?.abort(); startedRef.current = false }
  }, [])

  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [running])

  const close = () => { controller.current?.abort(); onClose() }
  const lastPoints = (element.artifacts || []).find((item) => item.points != null)?.points

  return <div className="m3-dialog-scrim" onClick={close}>
    <div className="m3-estimate-dialog" onClick={(event) => event.stopPropagation()}
      role="dialog" aria-modal="true" aria-label={`Estimation for ${element.name}`}>
      <header className="m3-estimate-header">
        <div className="m3-estimate-title">
          <span className={`m3-chip level-${element.level}`}>{element.level}</span>
          <h2>{element.name}</h2>
        </div>
        <button className="m3-icon-btn" onClick={close} aria-label="Close"><X size={20} /></button>
      </header>
      <div className="m3-estimate-body">
        {error && <div className="m3-banner error">{String(error.message || error)}</div>}
        {running && <div className="m3-estimate-progress"><PipelineView steps={steps} active title={element.name} /></div>}
        {!running && !result && !error && <div className="m3-empty" style={{ padding: '30px 10px' }}>
          <h2>{lastPoints != null ? `Last estimate: ${lastPoints} points` : 'Not estimated yet'}</h2>
          <p>{lastPoints != null
            ? 'The full reasoning from the previous session is not cached in this browser — run a re-estimate to see it again.'
            : 'Run the pipeline to score, compare with anchors, and conclude a justified estimate.'}</p>
        </div>}
        {result && <ResultCard result={result} writeEnabled={false} />}
        {result?.hidden_tasks?.length > 0 && <div className="m3-banner info" style={{ marginTop: 12 }}>
          Hidden tasks were added under this element as proposed L4 tasks — review them on the canvas.</div>}
      </div>
      <footer className="m3-estimate-actions">
        {result && <input className="m3-refine-input" value={refinement} disabled={running}
          onChange={(event) => setRefinement(event.target.value)}
          placeholder="Refine: e.g. assume the rule engine is out of scope" />}
        {result && <button className="m3-btn tonal" onClick={() => run(refinement)} disabled={running || !refinement.trim()}>
          <Wand2 size={15} /> Refine</button>}
        <button className="m3-btn filled" onClick={() => run(null)} disabled={running}>
          <Sparkles size={15} /> {running ? 'Estimating…' : result || lastPoints != null ? 'Re-estimate' : 'Estimate'}</button>
        <button className="m3-btn text" onClick={close}>Close</button>
      </footer>
    </div>
  </div>
}
