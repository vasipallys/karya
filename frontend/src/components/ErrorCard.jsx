import { AlertCircle, RotateCcw } from 'lucide-react'

export default function ErrorCard({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="error-card" role="alert">
      <AlertCircle size={20} aria-hidden="true" />
      <div><strong>Something needs attention</strong><p>{error.message || String(error)}</p></div>
      {onRetry && <button className="button secondary small" onClick={onRetry}><RotateCcw size={15} /> Retry</button>}
    </div>
  )
}
