import { FileSpreadsheet, Keyboard, PanelsTopLeft } from 'lucide-react'

const options = [
  { id: 'jira', label: 'From Jira', Icon: PanelsTopLeft },
  { id: 'manual', label: 'Manual entry', Icon: Keyboard },
  { id: 'upload', label: 'Upload Excel / CSV', Icon: FileSpreadsheet },
]

export default function SourceSwitcher({ value, onChange }) {
  return (
    <div className="source-switcher" role="tablist" aria-label="Story source">
      {options.map(({ id, label, Icon }) => (
        <button key={id} role="tab" aria-selected={value === id} className={value === id ? 'active' : ''} onClick={() => onChange(id)}>
          <Icon size={18} aria-hidden="true" />{label}
        </button>
      ))}
    </div>
  )
}
