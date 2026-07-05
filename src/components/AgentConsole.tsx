import {
  Bot, Check, ChevronDown, ChevronUp, CircleStop, Pause, Play, Sparkles,
} from "lucide-react";
import type { Agent } from "../types";

interface Props {
  agents: Agent[];
  collapsed: boolean;
  running: boolean;
  log: string;
  onToggle: () => void;
  onRun: () => void;
  onStop: () => void;
}

function AgentRing({ agent }: { agent: Agent }) {
  const radius = 17;
  const length = Math.PI * 2 * radius;
  return (
    <div className={`agent-ring ${agent.status}`}>
      <svg viewBox="0 0 42 42">
        <circle cx="21" cy="21" r={radius} />
        <circle className="ring-value" cx="21" cy="21" r={radius} strokeDasharray={length} strokeDashoffset={length * (1 - agent.progress / 100)} />
      </svg>
      {agent.status === "complete" ? <Check size={13} /> : <span>{Math.round(agent.progress)}</span>}
    </div>
  );
}

export default function AgentConsole({ agents, collapsed, running, log, onToggle, onRun, onStop }: Props) {
  return (
    <section className={`agent-console ${collapsed ? "collapsed" : ""}`}>
      <div className="console-head">
        <button className="console-title" onClick={onToggle}>
          <span className="console-icon"><Bot size={17} /></span>
          <strong>Agent console</strong>
          <span className={running ? "console-status running" : "console-status"}>{running ? "Pipeline running" : "Architecture current"}</span>
          {collapsed ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {!collapsed && (
          <div className="console-actions">
            <span className="console-log"><Sparkles size={13} /> {log}</span>
            <button title="Pause pipeline" disabled={!running}><Pause size={15} /></button>
            <button title={running ? "Stop pipeline" : "Run pipeline"} onClick={running ? onStop : onRun}>
              {running ? <CircleStop size={15} /> : <Play size={15} />}
            </button>
          </div>
        )}
      </div>
      {!collapsed && (
        <div className="agent-grid">
          {agents.map((agent) => (
            <article className={`agent-card ${agent.status}`} key={agent.id}>
              <AgentRing agent={agent} />
              <div className="agent-copy">
                <strong>{agent.name}</strong>
                <span>{agent.detail}</span>
              </div>
              {agent.status === "working" && <i className="thinking-dots"><b /><b /><b /></i>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
