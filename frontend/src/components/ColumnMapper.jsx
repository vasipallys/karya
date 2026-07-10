import { ArrowRight, CheckCircle2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

const fields = [
  ['title', 'Title', true], ['user_story', 'User story', false], ['acceptance_criteria', 'Acceptance criteria', false],
  ['technical_breakdown', 'Technical breakdown', false], ['existing_points', 'Existing points', false],
]

export default function ColumnMapper({ upload, onEstimate, loading }) {
  const [mapping, setMapping] = useState(upload.suggested_mapping)
  const selectableRows = upload.rows.slice(0, 100)
  const [selected, setSelected] = useState(() => new Set(selectableRows.map((_, index) => index)))
  useEffect(() => { setMapping(upload.suggested_mapping); setSelected(new Set(upload.rows.slice(0, 100).map((_, index) => index))) }, [upload])
  const previewColumns = useMemo(() => Object.values(mapping).filter(Boolean), [mapping])
  const toggle = (index) => setSelected((current) => { const next = new Set(current); next.has(index) ? next.delete(index) : next.add(index); return next })
  const selectedRows = selectableRows.filter((_, index) => selected.has(index))
  return (
    <section className="input-card mapping-card">
      <div className="section-heading"><div><span className="eyebrow">{upload.row_count} rows detected</span><h2>Match your columns</h2></div><CheckCircle2 className="success-icon" /></div>
      <div className="mapping-grid">
        {fields.map(([key, label, required]) => <div className="mapping-row" key={key}><span>{label}{required && <b> Required</b>}</span><ArrowRight size={16} /><select value={mapping[key] || ''} onChange={(event) => setMapping((current) => ({ ...current, [key]: event.target.value || null }))}><option value="">Not mapped</option>{upload.columns.map((column) => <option key={column} value={column}>{column}</option>)}</select></div>)}
      </div>
      <div className="preview-toolbar"><span>Select stories to estimate (maximum 100)</span><button className="text-button" onClick={() => setSelected(selected.size ? new Set() : new Set(selectableRows.map((_, index) => index)))}>{selected.size ? 'Clear selection' : 'Select all'}</button></div>
      <div className="table-wrap mapping-preview"><table className="preview-table"><thead><tr><th><span className="sr-only">Select</span></th>{previewColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{selectableRows.map((row, index) => <tr key={index}><td><input type="checkbox" aria-label={`Select row ${index + 2}`} checked={selected.has(index)} onChange={() => toggle(index)} /></td>{previewColumns.map((column) => <td key={column}>{String(row[column] ?? '').slice(0, 100)}</td>)}</tr>)}</tbody></table></div>
      {upload.row_count > 100 && <p className="help">Showing the first 100 rows. Split larger files into batches of 100 for reliable progress.</p>}
      <button className="button primary" disabled={!mapping.title || !selected.size || loading} onClick={() => onEstimate(selectedRows, mapping)}>Estimate selected ({selected.size})</button>
    </section>
  )
}
