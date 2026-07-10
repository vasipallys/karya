const display = (value) => value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

export default function Scorecard({ scores = [], drivers = [] }) {
  return <div className="table-wrap"><table className="scorecard"><thead><tr><th>Parameter</th><th>Score</th><th>Why</th></tr></thead><tbody>{scores.map((item) => <tr key={item.parameter}><td>{display(item.parameter)}{drivers.includes(item.parameter) && <span className="driver-badge">Driver</span>}</td><td><span className={`score-chip ${item.score.toLowerCase()}`}>{item.score}</span></td><td>{item.reason}</td></tr>)}</tbody></table></div>
}
