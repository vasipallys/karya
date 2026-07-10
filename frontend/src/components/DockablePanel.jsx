import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

function loadState(key, defaultWidth) {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || '{}')
    return {
      width: typeof parsed.width === 'number' ? parsed.width : defaultWidth,
      collapsed: !!parsed.collapsed,
    }
  } catch {
    return { width: defaultWidth, collapsed: false }
  }
}

/**
 * A dockable sidebar wrapper: collapse to a thin reopen tab, drag the docking
 * edge to resize, and persist both bits of state per `id` in localStorage.
 * `side` is the edge the panel is docked against ("left" or "right"); the resize
 * gutter (and its collapse button) sits on the inner edge facing the content.
 */
export default function DockablePanel({
  id,
  side = 'right',
  title = 'Panel',
  children,
  defaultWidth = 360,
  minWidth = 220,
  maxWidth = 620,
}) {
  const storageKey = `sp.dock.${id}`
  const [{ width, collapsed }, setState] = useState(() => loadState(storageKey, defaultWidth))
  const boundedWidth = clamp(width, minWidth, maxWidth)

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ width: boundedWidth, collapsed }))
    } catch {
      /* storage unavailable (private mode, quota) — resizing still works in-session */
    }
  }, [storageKey, boundedWidth, collapsed])

  const startResize = useCallback((event) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = boundedWidth
    const direction = side === 'right' ? -1 : 1 // dragging toward the content shrinks
    const onMove = (moveEvent) => {
      const next = clamp(startWidth + (moveEvent.clientX - startX) * direction, minWidth, maxWidth)
      setState((prev) => ({ ...prev, width: next }))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.classList.remove('dockable-resizing')
    }
    document.body.classList.add('dockable-resizing')
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [boundedWidth, side, minWidth, maxWidth])

  const setCollapsed = (value) => setState((prev) => ({ ...prev, collapsed: value }))

  if (collapsed) {
    const OpenIcon = side === 'right' ? PanelRightOpen : PanelLeftOpen
    return (
      <button
        type="button"
        className={`dockable-reopen side-${side}`}
        onClick={() => setCollapsed(false)}
        aria-label={`Expand ${title}`}
        title={`Expand ${title}`}
      >
        <OpenIcon size={18} />
        <span className="dockable-reopen-label">{title}</span>
      </button>
    )
  }

  const CloseIcon = side === 'right' ? PanelRightClose : PanelLeftClose
  const gutter = (
    <div
      className="dockable-gutter"
      onPointerDown={startResize}
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${title}`}
    >
      <button
        type="button"
        className="dockable-collapse"
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => setCollapsed(true)}
        aria-label={`Collapse ${title}`}
        title={`Collapse ${title}`}
      >
        <CloseIcon size={14} />
      </button>
    </div>
  )

  return (
    <section className={`dockable side-${side}`} style={{ width: boundedWidth }} data-dock={id}>
      {side === 'right' && gutter}
      <div className="dockable-inner">{children}</div>
      {side === 'left' && gutter}
    </section>
  )
}
