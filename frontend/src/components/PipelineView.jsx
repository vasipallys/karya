import { Check, Circle, LoaderCircle } from 'lucide-react'

const labels = {
  score_parameters: 'Score parameters', identify_drivers: 'Identify drivers', compare_to_anchors: 'Compare anchors',
  derive_points: 'Derive points', spike_split_branch: 'Spike / split check', write_plain_language_reasoning: 'Write plain-language why',
  detect_hidden_tasks: 'Find hidden work', assess_risks: 'Assess risks', recommend_split: 'Recommend split',
}

export default function PipelineView({ steps, active = true, title }) {
  if (!active && !steps.length) return null
  return (
    <section className="pipeline-card" aria-live="polite">
      <div><span className="eyebrow">Live reasoning</span><h2>{title || 'Building the estimate'}</h2></div>
      <div className="pipeline-steps">
        {Object.entries(labels).map(([key, label]) => {
          const done = steps.includes(key)
          const current = !done && Object.keys(labels)[steps.length] === key
          return <div className={`pipeline-step ${done ? 'done' : current ? 'current' : ''}`} key={key}>{done ? <Check size={15} /> : current ? <LoaderCircle size={15} className="spin" /> : <Circle size={12} />}<span>{label}</span></div>
        })}
      </div>
    </section>
  )
}
