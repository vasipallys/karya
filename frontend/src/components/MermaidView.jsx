import { Maximize2, Scan, X, ZoomIn, ZoomOut } from 'lucide-react'
import mermaid from 'mermaid'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// Shared Mermaid preview used everywhere in the app: auto-fits the diagram to
// its container and offers a maximize popup with zoom + pan. Keeping this in one
// place makes the preview behaviour consistent across markdown, the diagram
// studio, and the L1 architecture views.
mermaid.initialize({
  startOnLoad: false, securityLevel: 'strict', theme: 'base',
  themeVariables: {
    primaryColor: '#d3e3fd', primaryTextColor: '#1f1f1f', primaryBorderColor: '#0b57d0',
    lineColor: '#5f6368', secondaryColor: '#e6f4ea', tertiaryColor: '#fef7e0', fontFamily: 'Roboto, sans-serif',
  },
})

let seq = 0

function useMermaidSvg(source, delay = 150) {
  const [svg, setSvg] = useState('')
  const [error, setError] = useState(null)
  useEffect(() => {
    let active = true
    const timer = setTimeout(async () => {
      try {
        const id = `mv-${Date.now()}-${(seq += 1)}`
        const { svg: rendered } = await mermaid.render(id, source || 'graph TD; Empty;')
        if (active) { setSvg(rendered); setError(null) }
      } catch (nextError) {
        if (active) setError(nextError)
      }
    }, delay)
    return () => { active = false; clearTimeout(timer) }
  }, [source, delay])
  return { svg, error }
}

// Strip Mermaid's inline sizing so the SVG scales to fill its box (fit-to-window).
function fitSvg(host, mode) {
  const el = host?.querySelector('svg')
  if (!el) return
  el.removeAttribute('width')
  el.removeAttribute('height')
  el.style.maxWidth = 'none'
  el.setAttribute('preserveAspectRatio', 'xMidYMid meet')
  if (mode === 'width') { el.style.width = '100%'; el.style.height = 'auto' }
  else { el.style.width = '100%'; el.style.height = '100%' }
}

export default function MermaidView({ source, fit = 'contain', className = '', onError, onSvg }) {
  const host = useRef(null)
  const { svg, error } = useMermaidSvg(source)
  const [maximized, setMaximized] = useState(false)

  useEffect(() => {
    if (error) { onError?.(error); return }
    if (svg && host.current) {
      host.current.innerHTML = svg
      fitSvg(host.current, fit)
      onSvg?.(svg)
      onError?.(null)
    }
  }, [svg, error, fit]) // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return <div className="mv-error"><strong>Diagram needs attention</strong><span>{String(error.message || error).split('\n')[0]}</span></div>
  }

  return (
    <div className={`mv ${fit === 'width' ? 'mv-width' : ''} ${className}`}>
      <div ref={host} className="mv-canvas" />
      <button type="button" className="mv-max-btn" title="Maximize (fit to window)" aria-label="Maximize diagram" onClick={() => setMaximized(true)}>
        <Maximize2 size={15} />
      </button>
      {maximized && <MermaidModal svg={svg} onClose={() => setMaximized(false)} />}
    </div>
  )
}

function MermaidModal({ svg, onClose }) {
  const stage = useRef(null)
  const [transform, setTransform] = useState({ scale: 1, x: 0, y: 0 })
  const drag = useRef(null)

  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (stage.current) { stage.current.innerHTML = svg; fitSvg(stage.current, 'contain') }
  }, [svg])

  const zoom = (factor) => setTransform((prev) => ({ ...prev, scale: Math.min(8, Math.max(0.2, prev.scale * factor)) }))
  const fitToWindow = () => setTransform({ scale: 1, x: 0, y: 0 })
  const onWheel = (event) => { event.preventDefault(); zoom(event.deltaY < 0 ? 1.1 : 1 / 1.1) }
  const onDown = (event) => { drag.current = { x: event.clientX - transform.x, y: event.clientY - transform.y } }
  const onMove = (event) => { if (drag.current) setTransform((prev) => ({ ...prev, x: event.clientX - drag.current.x, y: event.clientY - drag.current.y })) }
  const onUp = () => { drag.current = null }

  return createPortal(
    <div className="mv-modal-scrim" onMouseDown={onClose}>
      <div className="mv-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Diagram">
        <div className="mv-modal-toolbar">
          <button type="button" onClick={() => zoom(1.2)} title="Zoom in" aria-label="Zoom in"><ZoomIn size={16} /></button>
          <button type="button" onClick={() => zoom(1 / 1.2)} title="Zoom out" aria-label="Zoom out"><ZoomOut size={16} /></button>
          <button type="button" onClick={fitToWindow} title="Fit to window" aria-label="Fit to window"><Scan size={16} /></button>
          <span className="mv-zoom-label">{Math.round(transform.scale * 100)}%</span>
          <button type="button" className="mv-modal-close" onClick={onClose} title="Close" aria-label="Close"><X size={18} /></button>
        </div>
        <div className="mv-modal-stage" onWheel={onWheel} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
          <div ref={stage} className="mv-modal-inner" style={{ transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})` }} />
        </div>
      </div>
    </div>,
    document.body,
  )
}
