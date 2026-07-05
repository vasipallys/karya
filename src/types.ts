export type DiagramKind = "context" | "container" | "component" | "class" | "sequence" | "activity";
export type NodeKind = "person" | "system" | "external" | "database" | "component";
export type SyncState = "synced" | "modified" | "stale";
export type ThemeName = "soft" | "midnight" | "sand";

export interface DiagramNode {
  id: string;
  kind: NodeKind;
  title: string;
  subtitle: string;
  description: string;
  x: number;
  y: number;
  width: number;
  height: number;
  icon?: string;
  technology?: string;
  status: SyncState;
  source: {
    path: string;
    line: number;
    endLine: number;
    commit: string;
    author: string;
    message: string;
  };
}

export interface DiagramEdge {
  id: string;
  from: string;
  to: string;
  label: string;
  protocol: string;
}

export interface Agent {
  id: string;
  name: string;
  detail: string;
  progress: number;
  status: "idle" | "queued" | "working" | "complete" | "paused";
}

export interface AgentUpdate {
  agents: Agent[];
  log: string;
  complete: boolean;
}

export interface KaryaAPI {
  platform: string;
  listAgents: () => Promise<Agent[]>;
  runPipeline: (input: Record<string, unknown>) => Promise<{ started: boolean }>;
  stopPipeline: () => Promise<{ stopped: boolean }>;
  onAgentUpdate: (callback: (payload: AgentUpdate) => void) => () => void;
  saveDiagram: (diagram: Record<string, unknown>) => Promise<{ saved: boolean }>;
  loadDiagrams: () => Promise<Record<string, unknown>[]>;
  exportDiagram: (payload: { svg: string; suggestedName: string }) => Promise<{ path?: string; canceled?: boolean }>;
  openCode: (target: { path: string; line: number }) => Promise<{ opened: boolean }>;
  chooseRepository: () => Promise<string | null>;
  analyzeRepository: (root: string) => Promise<{
    files: Array<Record<string, unknown>>;
    symbols: Array<Record<string, unknown>>;
    dependencies: Array<Record<string, unknown>>;
  }>;
}

declare global {
  interface Window {
    karya?: KaryaAPI;
  }
}
