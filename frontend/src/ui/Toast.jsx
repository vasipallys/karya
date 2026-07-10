import { CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const ToastContext = createContext(null)
let nextId = 1

const ICONS = { success: CheckCircle2, error: XCircle, info: Info }

/** App-wide snackbar system. `toast.success('Saved')`, `toast.error(err)`, `toast.info('…')`. */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => setToasts((current) => current.filter((item) => item.id !== id)), [])

  const push = useCallback((kind, message) => {
    const text = message?.message || String(message ?? '')
    if (!text) return
    const id = nextId++
    setToasts((current) => [...current, { id, kind, text }])
    setTimeout(() => dismiss(id), kind === 'error' ? 6000 : 3500)
  }, [dismiss])

  const toast = useMemo(() => ({
    success: (message) => push('success', message),
    error: (message) => push('error', message),
    info: (message) => push('info', message),
  }), [push])

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map(({ id, kind, text }) => {
          const Icon = ICONS[kind] || Info
          return (
            <div key={id} className={`toast toast-${kind}`}>
              <Icon size={18} />
              <span>{text}</span>
              <button className="toast-close" onClick={() => dismiss(id)} aria-label="Dismiss"><X size={15} /></button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within a ToastProvider')
  return context
}
