import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bell, Check, ChevronDown, CloudDownload, Code2, Command, FileJson2, FileOutput,
  GitCompareArrows, HelpCircle, Menu, MoreHorizontal, PanelRightOpen, RefreshCw,
  Settings, Share2, Sparkles, WandSparkles, X, Network,
} from "lucide-react";
import AgentConsole from "./components/AgentConsole";
import DiagramCanvas from "./components/DiagramCanvas";
import MermaidStudio from "./components/MermaidStudio";
import { Inspector, NodeEditorModal, RelationshipModal, SettingsPanel, SourceModal } from "./components/Panels";
import Sidebar from "./components/Sidebar";
import { diagramEdges, diagramNodes, initialAgents } from "./data";
import type { Agent, AgentUpdate, DiagramEdge, DiagramNode, ThemeName } from "./types";

const diagramTitles: Record<string, { title: string; subtitle: string }> = {
  context: { title: "System context", subtitle: "C4 · Level 1" },
  container: { title: "Container landscape", subtitle: "C4 · Level 2" },
  component: { title: "Component map", subtitle: "C4 · Level 3" },
  code: { title: "Code architecture", subtitle: "C4 · Level 4" },
  class: { title: "Domain class model", subtitle: "UML · Class" },
  sequence: { title: "Repository analysis", subtitle: "UML · Sequence" },
  activity: { title: "Generation workflow", subtitle: "UML · Activity" },
  state: { title: "Agent lifecycle", subtitle: "UML · State" },
};

function fallbackRun(onUpdate: (update: AgentUpdate) => void) {
  let tick = 0;
  const timer = window.setInterval(() => {
    tick += 1;
    const agents = initialAgents.map((agent, index): Agent => {
      const progress = Math.max(0, Math.min(100, (tick - index * 2) * 8));
      return {
        ...agent,
        progress,
        status: progress === 100 ? "complete" : progress > 0 ? "working" : "queued",
        detail: progress === 100 ? "Task completed" : agent.detail,
      };
    });
    const complete = agents.every((agent) => agent.status === "complete");
    onUpdate({ agents, complete, log: complete ? "Living architecture is ready" : "Agents are refining the architecture graph" });
    if (complete) window.clearInterval(timer);
  }, 330);
  return timer;
}

export default function App() {
  const [nodes, setNodes] = useState<DiagramNode[]>(() => {
    try { return JSON.parse(localStorage.getItem("karya:nodes") || "") || diagramNodes; } catch { return diagramNodes; }
  });
  const [edges, setEdges] = useState<DiagramEdge[]>(() => {
    try { return JSON.parse(localStorage.getItem("karya:edges") || "") || diagramEdges; } catch { return diagramEdges; }
  });
  const [activeDiagram, setActiveDiagram] = useState("context");
  const [renderMode, setRenderMode] = useState<"living" | "mermaid">("living");
  const [agents, setAgents] = useState(initialAgents);
  const [selectedNode, setSelectedNode] = useState<DiagramNode | null>(null);
  const [consoleCollapsed, setConsoleCollapsed] = useState(false);
  const [running, setRunning] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [log, setLog] = useState("Linker mapped 384 symbols to source");
  const [toast, setToast] = useState<string | null>(null);
  const [theme, setTheme] = useState<ThemeName>(() => (localStorage.getItem("karya:theme") as ThemeName) || "soft");
  const [nodeEditor, setNodeEditor] = useState<{ node: DiagramNode; isNew: boolean } | null>(null);
  const [connectMode, setConnectMode] = useState(false);
  const [connectFrom, setConnectFrom] = useState<string | null>(null);
  const [relationshipDraft, setRelationshipDraft] = useState<{ from: DiagramNode; to: DiagramNode } | null>(null);
  const fallbackTimer = useRef<number | null>(null);
  const title = diagramTitles[activeDiagram] || diagramTitles.context;

  const driftCount = useMemo(() => nodes.filter((node) => node.status !== "synced").length, [nodes]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("karya:theme", theme);
  }, [theme]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      localStorage.setItem("karya:nodes", JSON.stringify(nodes));
      localStorage.setItem("karya:edges", JSON.stringify(edges));
      window.karya?.saveDiagram({
        id: `workspace-${activeDiagram}`,
        name: title.title,
        type: activeDiagram,
        nodes,
        edges,
        commitSha: "8c41e2a",
      });
    }, 650);
    return () => window.clearTimeout(timer);
  }, [nodes, edges, activeDiagram, title.title]);

  useEffect(() => {
    if (!window.karya) return;
    const unsubscribe = window.karya.onAgentUpdate((update) => {
      setAgents(update.agents);
      setLog(update.log);
      setRunning(!update.complete);
      if (update.complete) {
        setToast("Architecture regenerated and linked to source");
        window.setTimeout(() => setToast(null), 3400);
      }
    });
    return unsubscribe;
  }, []);

  useEffect(() => () => {
    if (fallbackTimer.current) window.clearInterval(fallbackTimer.current);
  }, []);

  const runPipeline = async (payload: Record<string, unknown> = { mode: "repository" }) => {
    setSourceOpen(false);
    setRunning(true);
    setConsoleCollapsed(false);
    setSelectedNode(null);
    setAgents(initialAgents.map((agent) => ({ ...agent, progress: 0, status: "queued" })));
    setLog("Starting secure analysis pipeline…");
    if (window.karya) await window.karya.runPipeline(payload);
    else fallbackTimer.current = fallbackRun((update) => {
      setAgents(update.agents);
      setLog(update.log);
      setRunning(!update.complete);
      if (update.complete) {
        setToast("Architecture regenerated and linked to source");
        window.setTimeout(() => setToast(null), 3400);
      }
    });
  };

  const stopPipeline = async () => {
    if (window.karya) await window.karya.stopPipeline();
    if (fallbackTimer.current) window.clearInterval(fallbackTimer.current);
    setRunning(false);
    setAgents((current) => current.map((agent) => agent.status === "working" ? { ...agent, status: "paused", detail: "Paused by user" } : agent));
    setLog("Pipeline paused — progress is preserved");
  };

  const openCode = async (node: DiagramNode) => {
    if (window.karya) {
      await window.karya.openCode({ path: node.source.path, line: node.source.line });
      setToast(`Opening ${node.source.path}:${node.source.line}`);
    } else {
      setToast(`Source link: ${node.source.path}:${node.source.line}`);
    }
    window.setTimeout(() => setToast(null), 2800);
  };

  const exportSvg = async () => {
    const element = document.getElementById("architecture-canvas");
    if (!element) return;
    const clone = element.cloneNode(true) as SVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const svg = new XMLSerializer().serializeToString(clone);
    if (window.karya) {
      const result = await window.karya.exportDiagram({ svg, suggestedName: `karya-${activeDiagram}` });
      if (result.path) setToast(`Exported to ${result.path}`);
    } else {
      const blob = new Blob([svg], { type: "image/svg+xml" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `karya-${activeDiagram}.svg`;
      link.click();
      URL.revokeObjectURL(link.href);
      setToast("SVG export created");
    }
    setExportOpen(false);
    window.setTimeout(() => setToast(null), 3000);
  };

  const requestAddNode = () => {
    const id = `node-${Date.now()}`;
    setNodeEditor({
      isNew: true,
      node: {
        id,
        kind: "component",
        title: "New component",
        subtitle: "Describe this element",
        description: "Explain what this element is responsible for in the architecture.",
        x: 520,
        y: 360,
        width: 220,
        height: 128,
        status: "modified",
        technology: "",
        source: { path: "src/", line: 1, endLine: 1, commit: "working", author: "You", message: "New architecture element" },
      },
    });
  };

  const saveNode = (node: DiagramNode, isNew: boolean) => {
    const sized = isNew ? {
      ...node,
      width: node.kind === "person" ? 132 : node.kind === "system" ? 268 : 220,
      height: node.kind === "person" ? 146 : node.kind === "system" ? 168 : 128,
    } : node;
    setNodes((current) => isNew ? [...current, sized] : current.map((item) => item.id === sized.id ? sized : item));
    setSelectedNode(sized);
    setNodeEditor(null);
    setToast(isNew ? `${sized.title} added to the diagram` : `${sized.title} updated`);
    window.setTimeout(() => setToast(null), 2600);
  };

  const deleteNode = (node: DiagramNode) => {
    setNodes((current) => current.filter((item) => item.id !== node.id));
    setEdges((current) => current.filter((edge) => edge.from !== node.id && edge.to !== node.id));
    setSelectedNode(null);
    setToast(`${node.title} removed`);
    window.setTimeout(() => setToast(null), 2600);
  };

  const activateNode = (node: DiagramNode) => {
    if (!connectMode) {
      setSelectedNode(node);
      return;
    }
    if (!connectFrom) {
      setConnectFrom(node.id);
      return;
    }
    if (connectFrom === node.id) {
      setToast("Choose a different target node");
      window.setTimeout(() => setToast(null), 1800);
      return;
    }
    const source = nodes.find((item) => item.id === connectFrom);
    if (source) setRelationshipDraft({ from: source, to: node });
  };

  return (
    <div className="app-shell">
      <header className="titlebar">
        <div className="brand">
          <span className="brand-mark"><i /><i /><i /></span>
          <strong>karya</strong>
          <em>living architecture</em>
        </div>
        <div className="titlebar-drag" />
        <button className="command-button"><Command size={14} /><span>Quick find</span><kbd>⌘ K</kbd></button>
        <button className="header-icon" aria-label="Help"><HelpCircle size={18} /></button>
        <button className="header-icon notification" aria-label="Notifications"><Bell size={18} /><i /></button>
        <button className="avatar">SR</button>
      </header>

      <div className="workspace">
        <Sidebar
          activeDiagram={activeDiagram}
          onDiagramChange={(id) => { setActiveDiagram(id); setSelectedNode(null); }}
          onAddSource={() => setSourceOpen(true)}
          agents={agents}
        />
        <main className="main-content">
          <div className="view-header">
            <div className="view-title">
              <div><span>{title.subtitle}</span><h1>{title.title}</h1></div>
              <button className="view-menu"><MoreHorizontal size={18} /></button>
            </div>
            <div className="header-actions">
              <div className="engine-toggle" aria-label="Diagram engine">
                <button className={renderMode === "living" ? "active" : ""} onClick={() => setRenderMode("living")}><Network size={14} /> Living</button>
                <button className={renderMode === "mermaid" ? "active" : ""} onClick={() => { setRenderMode("mermaid"); setSelectedNode(null); }}><Code2 size={14} /> Mermaid</button>
              </div>
              <button className="drift-button"><GitCompareArrows size={16} /><span>Drift</span><em>{driftCount}</em></button>
              <button title="Regenerate architecture" className={running ? "spin" : ""} onClick={() => runPipeline()}><RefreshCw size={16} /></button>
              <button aria-label="Workspace settings" onClick={() => setSettingsOpen(true)}><Settings size={16} /></button>
              {renderMode === "living" && <div className="export-wrap">
                <button className="export-button" onClick={() => setExportOpen(!exportOpen)}><Share2 size={16} /> Export <ChevronDown size={13} /></button>
                {exportOpen && (
                  <div className="export-menu">
                    <button onClick={exportSvg}><FileOutput size={16} /><span><strong>SVG diagram</strong><small>Preserve living links</small></span></button>
                    <button onClick={exportSvg}><CloudDownload size={16} /><span><strong>Interactive HTML</strong><small>Portable architecture</small></span></button>
                    <button onClick={exportSvg}><FileJson2 size={16} /><span><strong>Model JSON</strong><small>Structured graph data</small></span></button>
                  </div>
                )}
              </div>}
              <button className="generate-button" onClick={() => setSourceOpen(true)}><WandSparkles size={16} /> Generate</button>
            </div>
          </div>

          <div className="content-stack">
            {renderMode === "living" ? <DiagramCanvas
              nodes={nodes}
              edges={edges}
              selectedId={selectedNode?.id || null}
              onSelect={setSelectedNode}
              onMoveNode={(id, dx, dy) => setNodes((current) => current.map((node) => node.id === id ? {
                ...node,
                x: Math.max(10, Math.min(1010 - node.width, node.x + dx)),
                y: Math.max(10, Math.min(620 - node.height, node.y + dy)),
              } : node))}
              onRequestAdd={requestAddNode}
              connectMode={connectMode}
              connectFrom={connectFrom}
              onToggleConnect={() => { setConnectMode(!connectMode); setConnectFrom(null); setRelationshipDraft(null); }}
              onNodeActivate={activateNode}
            /> : <MermaidStudio theme={theme} onToast={(message) => {
              setToast(message);
              window.setTimeout(() => setToast(null), 2600);
            }} />}
            <AgentConsole
              agents={agents}
              collapsed={consoleCollapsed}
              running={running}
              log={log}
              onToggle={() => setConsoleCollapsed(!consoleCollapsed)}
              onRun={() => runPipeline()}
              onStop={stopPipeline}
            />
          </div>
        </main>
      </div>

      {selectedNode && <Inspector node={selectedNode} onClose={() => setSelectedNode(null)} onOpenCode={openCode} onEdit={(node) => setNodeEditor({ node, isNew: false })} onDelete={deleteNode} />}
      {sourceOpen && <SourceModal onClose={() => setSourceOpen(false)} onAnalyze={(payload) => runPipeline(payload)} />}
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} theme={theme} onThemeChange={setTheme} />}
      {nodeEditor && <NodeEditorModal initial={nodeEditor.node} isNew={nodeEditor.isNew} onClose={() => setNodeEditor(null)} onSave={(node) => saveNode(node, nodeEditor.isNew)} />}
      {relationshipDraft && <RelationshipModal from={relationshipDraft.from} to={relationshipDraft.to} onClose={() => { setRelationshipDraft(null); setConnectFrom(null); }} onSave={(edge) => {
        setEdges((current) => [...current, edge]);
        setRelationshipDraft(null);
        setConnectFrom(null);
        setConnectMode(false);
        setToast(`Connected ${relationshipDraft.from.title} to ${relationshipDraft.to.title}`);
        window.setTimeout(() => setToast(null), 2800);
      }} />}
      {toast && <div className="toast"><span><Check size={15} /></span>{toast}<button onClick={() => setToast(null)}><X size={14} /></button></div>}
    </div>
  );
}
