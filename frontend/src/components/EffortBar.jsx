export default function EffortBar({ effort }) {
  if (!effort) return null
  const days = effort.person_days
  const max = Math.max(days.pessimistic, 1)
  return <div className="effort"><div className="layer-grid"><div><span>React</span><p>{effort.react}</p></div><div><span>Spring</span><p>{effort.spring}</p></div><div><span>Existing code</span><p>{effort.existing_code}</p></div></div><div className="effort-scale"><div className="effort-track"><span style={{ width: `${(days.optimistic / max) * 100}%` }} /><i style={{ left: `${(days.likely / max) * 100}%` }} /></div><div className="effort-labels"><span>{days.optimistic}d optimistic</span><strong>{days.likely}d likely</strong><span>{days.pessimistic}d pessimistic</span></div></div></div>
}
