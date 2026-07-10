import { ChevronRight, CornerDownRight } from 'lucide-react'

/**
 * Cross-level hierarchy navigation for the L1–L4 workspaces: a clickable
 * ancestor trail (L1 › L2 › … › current) plus drill-down chips for the
 * element's children. Navigation goes through onNavigate(element), which the
 * workspace shell routes to the right level tab with the element preselected.
 */
export default function LevelBreadcrumb({ elements = [], elementId, onNavigate }) {
  const byId = new Map(elements.map((element) => [element.id, element]))
  const current = byId.get(elementId)
  if (!current) return null

  const ancestors = []
  for (let node = byId.get(current.parent_id); node; node = byId.get(node.parent_id)) ancestors.unshift(node)
  const children = elements.filter((element) => element.parent_id === current.id)
  if (ancestors.length === 0 && children.length === 0) return null

  return <nav className="level-nav" aria-label="Level navigation">
    <div className="level-crumbs">
      {ancestors.map((ancestor) => <span key={ancestor.id} className="level-crumb-step">
        <button type="button" className="crumb" title={`Open ${ancestor.name} (${ancestor.level})`}
          onClick={() => onNavigate?.(ancestor)}>
          <span className={`m3-chip level-${ancestor.level}`}>{ancestor.level}</span>{ancestor.name}
        </button>
        <ChevronRight size={13} aria-hidden="true" />
      </span>)}
      <span className="crumb current" aria-current="location">
        <span className={`m3-chip level-${current.level}`}>{current.level}</span>{current.name}
      </span>
    </div>
    {children.length > 0 && <div className="level-drill">
      <span className="level-drill-label"><CornerDownRight size={12} aria-hidden="true" /> Drill down</span>
      {children.map((child) => <button key={child.id} type="button" className={`drill-chip level-${child.level}`}
        title={`Open ${child.name} (${child.level})`} onClick={() => onNavigate?.(child)}>{child.name}</button>)}
    </div>}
  </nav>
}
