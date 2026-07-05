import { useState } from "react";
import {
  ArrowUpRight, Braces, Check, ChevronRight, CircleX, Cloud, Code2,
  ExternalLink, FileCode2, FolderGit2, GitCommitHorizontal, History,
  KeyRound, Link2, Network, Pencil, Play, RotateCcw, Save, Settings2, ShieldCheck,
  SlidersHorizontal, Sparkles, TestTube2, Trash2, Users,
} from "lucide-react";
import type { DiagramEdge, DiagramNode, ThemeName } from "../types";

export function Inspector({ node, onClose, onOpenCode, onEdit, onDelete }: {
  node: DiagramNode;
  onClose: () => void;
  onOpenCode: (node: DiagramNode) => void;
  onEdit: (node: DiagramNode) => void;
  onDelete: (node: DiagramNode) => void;
}) {
  return (
    <aside className="inspector">
      <div className="inspector-head">
        <div><span className="eyebrow">ELEMENT DETAILS</span><h2>{node.title}</h2></div>
        <button onClick={onClose} aria-label="Close inspector"><CircleX size={19} /></button>
      </div>
      <div className="status-banner">
        <span className={`status-icon ${node.status}`}><Check size={14} /></span>
        <div><strong>{node.status === "synced" ? "In sync with source" : "Source has changed"}</strong><small>Verified against main · 2m ago</small></div>
      </div>
      <div className="inspector-section">
        <span className="section-title">PURPOSE</span>
        <p>{node.description}</p>
      </div>
      <div className="inspector-section">
        <span className="section-title">SOURCE LINK</span>
        <button className="source-link" onClick={() => onOpenCode(node)}>
          <span><FileCode2 size={17} /></span>
          <span><strong>{node.source.path.split("/").at(-1)}</strong><small>{node.source.path}<br />Lines {node.source.line}–{node.source.endLine}</small></span>
          <ExternalLink size={15} />
        </button>
      </div>
      <div className="inspector-section">
        <span className="section-title">LATEST CHANGE</span>
        <div className="commit-card">
          <GitCommitHorizontal size={18} />
          <div><strong>{node.source.message}</strong><span>{node.source.author} · {node.source.commit}</span></div>
        </div>
      </div>
      <div className="inspector-actions">
        <button className="edit-action" onClick={() => onEdit(node)}><Pencil size={16} /> Edit node</button>
        <button><History size={16} /> Git history</button>
        <button><TestTube2 size={16} /> Tests</button>
        <button><Network size={16} /> Dependents</button>
        <button className="delete-action" onClick={() => onDelete(node)}><Trash2 size={16} /> Delete node</button>
      </div>
    </aside>
  );
}

export function SourceModal({ onClose, onAnalyze }: {
  onClose: () => void;
  onAnalyze: (payload: { mode: "requirements" | "repository"; value: string }) => void;
}) {
  const [mode, setMode] = useState<"requirements" | "repository">("requirements");
  const [requirements, setRequirements] = useState(
    "As a software architect, I want to connect a code repository and explore its system context, containers, and components. Every architecture element should link back to the exact source code and remain synchronized as the code evolves."
  );
  const [repo, setRepo] = useState("https://bitbucket.org/acme/payments-platform.git");
  const [branch, setBranch] = useState("main");

  const chooseLocal = async () => {
    const path = await window.karya?.chooseRepository();
    if (path) setRepo(path);
  };

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="source-modal" role="dialog" aria-modal="true" aria-labelledby="source-title">
        <div className="modal-head">
          <div><span className="modal-icon"><Sparkles size={20} /></span><div><h2 id="source-title">Create living architecture</h2><p>Start with a story or connect a codebase.</p></div></div>
          <button onClick={onClose}><CircleX size={21} /></button>
        </div>
        <div className="mode-tabs">
          <button className={mode === "requirements" ? "active" : ""} onClick={() => setMode("requirements")}><Braces size={17} /> Requirements</button>
          <button className={mode === "repository" ? "active" : ""} onClick={() => setMode("repository")}><FolderGit2 size={17} /> Repository</button>
        </div>
        {mode === "requirements" ? (
          <div className="modal-content">
            <label>
              <span>Describe what you’re building</span>
              <textarea value={requirements} onChange={(event) => setRequirements(event.target.value)} />
              <small>{requirements.length} characters · Be specific about actors, systems, and processes</small>
            </label>
            <div className="extract-preview">
              <span><Users size={15} /> 1 actor</span><span><Network size={15} /> 3 systems</span><span><Code2 size={15} /> 5 capabilities</span>
            </div>
          </div>
        ) : (
          <div className="modal-content repo-fields">
            <label><span>Repository URL or local path</span><div className="input-with-icon"><FolderGit2 size={17} /><input value={repo} onChange={(event) => setRepo(event.target.value)} /></div></label>
            <div className="field-row">
              <label><span>Branch / tag</span><div className="input-with-icon"><GitCommitHorizontal size={17} /><input value={branch} onChange={(event) => setBranch(event.target.value)} /></div></label>
              <label><span>Authentication</span><button className="select-field"><KeyRound size={16} /> OS keychain <ChevronRight size={14} /></button></label>
            </div>
            <button className="local-repo" onClick={chooseLocal}><FolderGit2 size={17} /> Choose local repository</button>
            <div className="secure-note"><ShieldCheck size={16} /> Credentials stay in your operating system keychain.</div>
          </div>
        )}
        <div className="modal-footer">
          <button className="ghost-button" onClick={onClose}>Cancel</button>
          <button className="primary-button" onClick={() => onAnalyze({ mode, value: mode === "requirements" ? requirements : `${repo}#${branch}` })}>
            <Play size={16} fill="currentColor" /> Analyze & generate
          </button>
        </div>
      </section>
    </div>
  );
}

export function SettingsPanel({ onClose, theme, onThemeChange }: {
  onClose: () => void;
  theme: ThemeName;
  onThemeChange: (theme: ThemeName) => void;
}) {
  const [concurrency, setConcurrency] = useState(4);
  const [localFirst, setLocalFirst] = useState(true);
  const [drift, setDrift] = useState(true);
  return (
    <aside className="settings-panel">
      <div className="settings-head">
        <div><span className="settings-icon"><Settings2 size={19} /></span><div><h2>Workspace settings</h2><p>Agents, models, and appearance</p></div></div>
        <button onClick={onClose}><CircleX size={20} /></button>
      </div>
      <div className="settings-content">
        <section>
          <span className="section-title">WORKSPACE THEME</span>
          <div className="theme-grid">
            {([
              ["soft", "Soft cloud", ["#f0f4f8", "#e3eaf2", "#4fc3f7"]],
              ["midnight", "Midnight", ["#202a35", "#293746", "#57c7ff"]],
              ["sand", "Warm sand", ["#f3eee5", "#e9dfd0", "#e7a85c"]],
            ] as const).map(([id, label, colors]) => (
              <button key={id} className={`theme-choice ${theme === id ? "active" : ""}`} onClick={() => onThemeChange(id)}>
                <span>{colors.map((color) => <i key={color} style={{ background: color }} />)}</span>
                <strong>{label}</strong>
                {theme === id && <Check size={13} />}
              </button>
            ))}
          </div>
        </section>
        <section>
          <span className="section-title">MODEL PROVIDER</span>
          <button className="provider-card active"><span><Cloud size={19} /></span><div><strong>OpenAI</strong><small>Connected · Remote</small></div><Check size={16} /></button>
          <button className="provider-card"><span><Braces size={19} /></span><div><strong>Ollama</strong><small>Local · Not running</small></div><ChevronRight size={15} /></button>
        </section>
        <section>
          <label className="range-label"><span><SlidersHorizontal size={16} /> Agent concurrency</span><strong>{concurrency}</strong></label>
          <input className="range" type="range" min="1" max="7" value={concurrency} onChange={(event) => setConcurrency(Number(event.target.value))} />
        </section>
        <section className="toggle-list">
          <label><span><strong>Local analysis first</strong><small>Keep source code on this device</small></span><input type="checkbox" checked={localFirst} onChange={() => setLocalFirst(!localFirst)} /><i /></label>
          <label><span><strong>Drift monitoring</strong><small>Watch active branch for changes</small></span><input type="checkbox" checked={drift} onChange={() => setDrift(!drift)} /><i /></label>
        </section>
        <button className="reset-button"><RotateCcw size={15} /> Restore defaults</button>
      </div>
    </aside>
  );
}

export function NodeEditorModal({ initial, isNew, onClose, onSave }: {
  initial: DiagramNode;
  isNew: boolean;
  onClose: () => void;
  onSave: (node: DiagramNode) => void;
}) {
  const [draft, setDraft] = useState(initial);
  const update = <K extends keyof DiagramNode>(key: K, value: DiagramNode[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="node-editor-modal" role="dialog" aria-modal="true" aria-labelledby="node-editor-title">
        <div className="modal-head">
          <div><span className="modal-icon"><Pencil size={19} /></span><div><h2 id="node-editor-title">{isNew ? "Add architecture node" : "Edit architecture node"}</h2><p>Describe its role in the system.</p></div></div>
          <button onClick={onClose}><CircleX size={21} /></button>
        </div>
        <div className="editor-form">
          <div className="field-row">
            <label><span>Node name</span><input value={draft.title} onChange={(event) => update("title", event.target.value)} /></label>
            <label><span>Type</span><select value={draft.kind} onChange={(event) => update("kind", event.target.value as DiagramNode["kind"])}><option value="system">System</option><option value="person">Person / actor</option><option value="external">External system</option><option value="database">Data store</option><option value="component">Component</option></select></label>
          </div>
          <label><span>Short explanation</span><input value={draft.subtitle} onChange={(event) => update("subtitle", event.target.value)} /></label>
          <label><span>Detailed responsibility</span><textarea value={draft.description} onChange={(event) => update("description", event.target.value)} /></label>
          <div className="field-row">
            <label><span>Technology</span><input value={draft.technology || ""} onChange={(event) => update("technology", event.target.value)} placeholder="React · Node.js" /></label>
            <label><span>Sync state</span><select value={draft.status} onChange={(event) => update("status", event.target.value as DiagramNode["status"])}><option value="synced">In sync</option><option value="modified">Modified</option><option value="stale">Stale</option></select></label>
          </div>
          <label><span>Source file</span><input value={draft.source.path} onChange={(event) => setDraft((current) => ({ ...current, source: { ...current.source, path: event.target.value } }))} placeholder="src/path/to/file.ts" /></label>
        </div>
        <div className="modal-footer">
          <button className="ghost-button" onClick={onClose}>Cancel</button>
          <button className="primary-button" disabled={!draft.title.trim()} onClick={() => onSave({ ...draft, title: draft.title.trim() })}><Save size={16} /> {isNew ? "Add node" : "Save changes"}</button>
        </div>
      </section>
    </div>
  );
}

export function RelationshipModal({ from, to, onClose, onSave }: {
  from: DiagramNode;
  to: DiagramNode;
  onClose: () => void;
  onSave: (edge: DiagramEdge) => void;
}) {
  const [label, setLabel] = useState("Uses");
  const [protocol, setProtocol] = useState("HTTPS");
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="relationship-modal" role="dialog" aria-modal="true" aria-labelledby="relationship-title">
        <div className="modal-head">
          <div><span className="modal-icon"><Link2 size={19} /></span><div><h2 id="relationship-title">Explain this connection</h2><p>{from.title} → {to.title}</p></div></div>
          <button onClick={onClose}><CircleX size={21} /></button>
        </div>
        <div className="connection-preview"><strong>{from.title}</strong><span><i /><i /><i /></span><strong>{to.title}</strong></div>
        <div className="editor-form">
          <label><span>Relationship explanation</span><input autoFocus value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Sends architecture requests to" /></label>
          <label><span>Protocol / mechanism</span><input value={protocol} onChange={(event) => setProtocol(event.target.value)} placeholder="HTTPS, events, local IPC…" /></label>
        </div>
        <div className="modal-footer">
          <button className="ghost-button" onClick={onClose}>Cancel</button>
          <button className="primary-button" disabled={!label.trim()} onClick={() => onSave({ id: `edge-${Date.now()}`, from: from.id, to: to.id, label: label.trim(), protocol: protocol.trim() || "Direct" })}><Link2 size={16} /> Join nodes</button>
        </div>
      </section>
    </div>
  );
}
