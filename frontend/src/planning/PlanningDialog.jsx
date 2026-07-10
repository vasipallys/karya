import { X } from 'lucide-react'

export default function PlanningDialog({ title, children, onClose, actions, wide = false }) {
  return <div className="m3-dialog-scrim" onMouseDown={onClose}>
    <section
      className={`m3-dialog l1-dialog${wide ? ' wide' : ''}`}
      onMouseDown={(event) => event.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label={title}>
      <header className="l1-dialog-header">
        <h2>{title}</h2>
        <button className="m3-icon-btn" onClick={onClose} aria-label="Close"><X size={19} /></button>
      </header>
      <div>{children}</div>
      <footer className="m3-dialog-actions">{actions}</footer>
    </section>
  </div>
}
