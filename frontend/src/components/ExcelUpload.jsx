import { Download, FileSpreadsheet, UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'

export default function ExcelUpload({ onUpload, templateUrl, loading }) {
  const input = useRef(null)
  const [dragging, setDragging] = useState(false)
  const pick = (files) => files?.[0] && onUpload(files[0])
  return (
    <section className="input-card">
      <div className="section-heading"><div><span className="eyebrow">Many stories</span><h2>Import a spreadsheet</h2></div><a className="text-button" href={templateUrl}><Download size={16} /> Template</a></div>
      <div className={`drop-zone ${dragging ? 'dragging' : ''}`} role="button" tabIndex="0" onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && input.current?.click()} onClick={() => input.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); pick(event.dataTransfer.files) }}>
        <UploadCloud size={32} aria-hidden="true" /><strong>Drop Excel or CSV here</strong><span>or choose a file up to 15 MB</span>
        <input ref={input} hidden type="file" accept=".csv,.xlsx,.xls" disabled={loading} onChange={(event) => pick(event.target.files)} />
      </div>
      <p className="help"><FileSpreadsheet size={15} /> Headers can be anything. You will map them on the next screen.</p>
    </section>
  )
}
