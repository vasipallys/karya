import { AlertTriangle, Anchor, Braces, ChevronDown, Download, GitFork, ShieldAlert, Target } from 'lucide-react'
import Scorecard from './Scorecard'
import EffortBar from './EffortBar'

const fibonacci = [1, 2, 3, 5, 8, 13]

function Detail({ title, icon: Icon, children, open = false }) {
  return <details className="result-detail" open={open}><summary><span><Icon size={18} />{title}</span><ChevronDown size={18} /></summary><div className="detail-body">{children}</div></details>
}

function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url)
}

function markdown(result) {
  return `# ${result.story.title}\n\n## ${result.points} points\n\n**${result.tldr}**\n\n${result.plain_language_why}\n\n## Anchor comparison\n${result.anchor_comparison}\n\n## Risks\n${result.risks.map((item) => `- ${item.risk}: ${item.mitigation_or_assumption}`).join('\n')}\n`
}

export default function ResultCard({ result, writeEnabled, onWrite }) {
  if (!result?.plain_language_why || !result?.tldr) return <div className="error-card">An estimate was withheld because its required explanation is missing.</div>
  const story = result.story || {}
  const split = result.split_recommendation || {}
  return (
    <article className="result-card">
      {(split.split_recommended || result.spike_recommended) && <div className="recommend-banner"><AlertTriangle size={18} /><strong>{split.split_recommended ? 'SPLIT' : 'SPIKE'} recommended</strong><span>{split.split_recommended ? split.rationale : result.spike_reason}</span></div>}
      <header className="result-headline">
        <div className="points-block"><span>Story points</span><strong>{result.points}</strong>{story.existing_points != null && <small>was {story.existing_points} <b>{result.points - story.existing_points > 0 ? '+' : ''}{result.points - story.existing_points}</b></small>}</div>
        <div className="headline-copy"><span className="eyebrow">{story.key ? `${story.key} · ` : ''}{story.title}</span><h2>{result.tldr}</h2><p>{result.plain_language_why}</p></div>
      </header>
      <div className="fib-scale" aria-label={`Fibonacci scale, ${result.points} selected`}>{fibonacci.map((point) => <span className={point === result.points ? 'selected' : point < result.points ? 'passed' : ''} key={point}>{point}</span>)}</div>
      <div className="result-actions"><button className="text-button" onClick={() => download(`${story.key || 'estimate'}.md`, markdown(result), 'text/markdown')}><Download size={15} /> Markdown</button><button className="text-button" onClick={() => download(`${story.key || 'estimate'}.json`, JSON.stringify(result, null, 2), 'application/json')}><Braces size={15} /> JSON</button>{writeEnabled && story.source === 'jira' && <button className="button secondary small" onClick={() => onWrite(result)}>Write {result.points} to Jira</button>}</div>
      <div className="details-stack">
        <Detail title="Scorecard and drivers" icon={Target}><p className="callout"><strong>What drives this:</strong> {result.drivers_explanation}</p><Scorecard scores={result.scorecard} drivers={result.drivers} /></Detail>
        <Detail title="Calibration anchor comparison" icon={Anchor}><p>{result.anchor_comparison}</p><p className="muted">Point derivation: {result.points_derivation}</p></Detail>
        <Detail title="Layer effort and range" icon={Target}><EffortBar effort={result.effort} /></Detail>
        <Detail title={`Hidden sub-tasks (${result.hidden_tasks?.length || 0})`} icon={ShieldAlert}>{result.hidden_tasks?.length ? <ul className="reason-list">{result.hidden_tasks.map((item, index) => <li key={index}><strong>{item.task}</strong><span>{item.weight}</span></li>)}</ul> : <p>No hidden work was evidenced in the criteria.</p>}</Detail>
        <Detail title="Risks and assumptions" icon={AlertTriangle}><ul className="reason-list">{result.risks?.map((item, index) => <li key={index}><strong>{item.risk}</strong><span>{item.mitigation_or_assumption}</span></li>)}</ul><h4>Assumptions</h4><ul>{result.assumptions?.map((item, index) => <li key={index}>{item}</li>)}</ul></Detail>
        <Detail title="Split recommendation" icon={GitFork}><p>{split.rationale}</p>{split.proposed_stories?.length > 0 && <ol>{split.proposed_stories.map((item, index) => <li key={index}>{item}</li>)}</ol>}</Detail>
      </div>
    </article>
  )
}
