import { Network } from 'lucide-react'

const LEVELS = [
  { level: 'L1', focus: 'Value' },
  { level: 'L2', focus: 'Structure' },
  { level: 'L3', focus: 'Behavior' },
  { level: 'L4', focus: 'Change' },
]

// The element at targetLevel on the same branch as elementId (its ancestor, or
// its nearest descendant), or null when the branch has none at that level.
function lineageTarget(elements, elementId, targetLevel) {
  const byId = new Map(elements.map((element) => [element.id, element]))
  const current = byId.get(elementId)
  if (!current) return null

  for (let node = current; node; node = byId.get(node.parent_id)) {
    if (node.level === targetLevel) return node
  }

  const childrenByParent = new Map()
  for (const element of elements) {
    if (!element.parent_id) continue
    const children = childrenByParent.get(element.parent_id) || []
    children.push(element)
    childrenByParent.set(element.parent_id, children)
  }
  const queue = [...(childrenByParent.get(current.id) || [])]
  while (queue.length) {
    const candidate = queue.shift()
    if (candidate.level === targetLevel) return candidate
    queue.push(...(childrenByParent.get(candidate.id) || []))
  }
  return null
}

function relatedTarget(elements, elementId, targetLevel) {
  return lineageTarget(elements, elementId, targetLevel)
    || elements.find((element) => element.level === targetLevel) || null
}

/**
 * Always-visible navigation between the C4 model and the four delivery levels.
 * The nearest element in the active hierarchy wins; the first element at that
 * level is a deliberate fallback when the current branch has no descendant.
 */
export default function LevelNavigator({
  elements = [],
  elementId,
  activeLevel,
  onNavigate,
  onOpenCanvas,
}) {
  return <nav className="level-switcher" aria-label="C4 and architecture level navigation">
    <button type="button" className="level-switcher-canvas" onClick={() => onOpenCanvas?.(elementId)}>
      <Network size={15} aria-hidden="true" />
      <span><strong>C4</strong><small>Canvas</small></span>
    </button>
    <span className="level-switcher-divider" aria-hidden="true" />
    {LEVELS.map(({ level, focus }) => {
      const target = relatedTarget(elements, elementId, level)
      const active = activeLevel === level
      return <button key={level} type="button" className={`level-switcher-link level-${level}${active ? ' active' : ''}`}
        aria-current={active ? 'page' : undefined}
        disabled={active || !target}
        title={target ? `${active ? 'Current' : 'Open'} ${level} ${focus}: ${target.name}` : `${level} ${focus} has not been created yet`}
        onClick={() => onNavigate?.(target)}>
        <span className="level-switcher-badge">{level}</span>
        <span><strong>{focus}</strong><small>{target?.name || 'Not created'}</small></span>
      </button>
    })}
  </nav>
}

export { lineageTarget, relatedTarget }
