import { ArrowDownUp, Download } from 'lucide-react'
import { useMemo, useState } from 'react'

export default function BatchTable({ results, onSelect }) {
  const [sort, setSort] = useState('title')
  const sorted = useMemo(() => [...results].sort((a, b) => sort === 'points' ? a.points - b.points : (a.story?.title || '').localeCompare(b.story?.title || '')), [results, sort])
  const exportCsv = () => {
    const rows = [['Item', 'Points', 'Why', 'Split'], ...sorted.map((result) => [result.story.title, result.points, result.tldr, result.split_recommendation?.split_recommended ? 'Yes' : 'No'])]
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const link = document.createElement('a'); link.href = url; link.download = 'story-estimates.csv'; link.click(); URL.revokeObjectURL(url)
  }
  return <section className="batch-card"><div className="section-heading"><div><span className="eyebrow">Batch complete</span><h2>{results.length} justified estimates</h2></div><div className="result-actions"><button className="text-button" onClick={() => setSort(sort === 'points' ? 'title' : 'points')}><ArrowDownUp size={15} /> Sort by {sort === 'points' ? 'title' : 'points'}</button><button className="text-button" onClick={exportCsv}><Download size={15} /> Export all</button></div></div><div className="table-wrap"><table className="batch-table"><thead><tr><th>Item</th><th>Estimate and reason</th><th>Action</th></tr></thead><tbody>{sorted.map((result, index) => <tr key={result.story.key || index}><td><strong>{result.story.key || result.story.title}</strong><span>{result.story.key && result.story.title}</span></td><td><div className="batch-estimate"><b>{result.points}</b><span>{result.tldr}</span>{result.split_recommendation?.split_recommended && <i>SPLIT</i>}</div></td><td><button className="text-button" onClick={() => onSelect(result)}>Open reasoning</button></td></tr>)}</tbody></table></div></section>
}
