import {
  Activity, Box, Boxes, Braces, ChevronDown, ChevronRight, CircleUserRound,
  GitBranch, GitPullRequestArrow, LayoutDashboard, Network, Plus, Search,
  Workflow,
} from "lucide-react";
import { navSections } from "../data";
import type { Agent } from "../types";

interface Props {
  activeDiagram: string;
  onDiagramChange: (id: string) => void;
  onAddSource: () => void;
  agents: Agent[];
}

const itemIcons: Record<string, typeof Box> = {
  context: Network, container: Boxes, component: Box, code: Braces,
  class: LayoutDashboard, sequence: Workflow, activity: Activity, state: GitPullRequestArrow,
};

function MiniRing({ value }: { value: number }) {
  const r = 13;
  const circumference = Math.PI * 2 * r;
  return (
    <svg className="mini-ring" viewBox="0 0 32 32">
      <circle cx="16" cy="16" r={r} />
      <circle className="value" cx="16" cy="16" r={r} strokeDasharray={circumference} strokeDashoffset={circumference * (1 - value / 100)} />
    </svg>
  );
}

export default function Sidebar({ activeDiagram, onDiagramChange, onAddSource, agents }: Props) {
  const activeAgents = agents.filter((agent) => agent.status === "working").length;
  const progress = Math.round(agents.reduce((sum, agent) => sum + agent.progress, 0) / agents.length);
  return (
    <aside className="sidebar">
      <div className="source-label">CURRENT SOURCE</div>
      <button className="repo-card">
        <span className="repo-icon"><GitBranch size={18} /></span>
        <span className="repo-copy">
          <strong>karya / desktop</strong>
          <small><i /> main · 8c41e2a</small>
        </span>
        <ChevronDown size={16} />
      </button>

      <button className="new-source-button" onClick={onAddSource}><Plus size={17} /> Add source</button>

      <div className="sidebar-search">
        <Search size={16} />
        <input aria-label="Search architecture" placeholder="Search architecture" />
        <kbd>⌘ K</kbd>
      </div>

      <nav className="diagram-nav">
        {navSections.map((section) => (
          <div className="nav-section" key={section.label}>
            <div className="nav-label">{section.label}</div>
            {section.items.map((item) => {
              const Icon = itemIcons[item.id];
              return (
                <button
                  key={item.id}
                  className={activeDiagram === item.id ? "active" : ""}
                  onClick={() => onDiagramChange(item.id)}
                >
                  <Icon size={16} />
                  <span>{item.label}</span>
                  <em>{item.count}</em>
                  <ChevronRight className="nav-arrow" size={14} />
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-spacer" />
      <div className="agent-summary">
        <div className="agent-summary-head">
          <div>
            <span className="live-dot" />
            <strong>Agent activity</strong>
          </div>
          <small>{activeAgents || 2} active</small>
        </div>
        <div className="agent-summary-body">
          <MiniRing value={progress} />
          <div><strong>{progress}%</strong><span>Architecture indexed</span></div>
          <button aria-label="Open agent console"><ChevronRight size={15} /></button>
        </div>
      </div>
      <button className="profile">
        <span><CircleUserRound size={21} /></span>
        <span><strong>Siva Reddy</strong><small>Workspace owner</small></span>
        <ChevronRight size={14} />
      </button>
    </aside>
  );
}
