import type { Agent, DiagramEdge, DiagramNode } from "./types";

export const initialAgents: Agent[] = [
  { id: "agent-0", name: "Repo Parser", detail: "142 files indexed", progress: 100, status: "complete" },
  { id: "agent-1", name: "Requirements", detail: "8 capabilities found", progress: 100, status: "complete" },
  { id: "agent-2", name: "C4 Modeler", detail: "Model is up to date", progress: 100, status: "complete" },
  { id: "agent-3", name: "UML Generator", detail: "3 views generated", progress: 100, status: "complete" },
  { id: "agent-4", name: "Linker", detail: "96% code coverage", progress: 96, status: "working" },
  { id: "agent-5", name: "Layout", detail: "Layout optimized", progress: 100, status: "complete" },
  { id: "agent-6", name: "Validation", detail: "Checking 2 changes", progress: 72, status: "working" },
];

export const diagramNodes: DiagramNode[] = [
  {
    id: "architect",
    kind: "person",
    title: "Software Architect",
    subtitle: "Primary user",
    description: "Explores, validates, and evolves the architecture.",
    x: 72, y: 213, width: 132, height: 146, status: "synced",
    source: { path: "src/features/workspace/Workspace.tsx", line: 28, endLine: 94, commit: "8c41e2a", author: "Siva Reddy", message: "Refine workspace navigation" },
  },
  {
    id: "karya",
    kind: "system",
    title: "Karya Desktop",
    subtitle: "Living architecture workspace",
    description: "Turns requirements and code into navigable software architecture.",
    x: 326, y: 168, width: 268, height: 168, status: "synced", technology: "Electron · React",
    source: { path: "electron/main.cjs", line: 49, endLine: 160, commit: "8c41e2a", author: "Siva Reddy", message: "Add desktop agent orchestration" },
  },
  {
    id: "git",
    kind: "external",
    title: "Git Platform",
    subtitle: "GitHub · Bitbucket · GitLab",
    description: "Provides repositories, branches, pull requests, and source history.",
    x: 735, y: 71, width: 218, height: 126, status: "modified", technology: "HTTPS · SSH",
    source: { path: "src/connectors/git/adapter.ts", line: 17, endLine: 118, commit: "54fa90c", author: "Mira Chen", message: "Support branch-aware indexing" },
  },
  {
    id: "llm",
    kind: "external",
    title: "AI Providers",
    subtitle: "Cloud or local models",
    description: "Provides structured reasoning for analysis and model generation.",
    x: 744, y: 278, width: 208, height: 126, status: "synced", technology: "OpenAI · Ollama",
    source: { path: "src/services/llm/provider.ts", line: 42, endLine: 130, commit: "17ea0b3", author: "Theo Martins", message: "Add local provider fallback" },
  },
  {
    id: "analysis",
    kind: "database",
    title: "Analysis Cache",
    subtitle: "Metadata & code mappings",
    description: "Stores diagram versions, AST metadata, and exact source links.",
    x: 358, y: 434, width: 222, height: 128, status: "synced", technology: "SQLite · Tree-sitter",
    source: { path: "python/analysis_service.py", line: 17, endLine: 58, commit: "8c41e2a", author: "Siva Reddy", message: "Bundle static analysis service" },
  },
];

export const diagramEdges: DiagramEdge[] = [
  { id: "e1", from: "architect", to: "karya", label: "Explores architecture", protocol: "Desktop UI" },
  { id: "e2", from: "karya", to: "git", label: "Indexes source & history", protocol: "Git / OAuth" },
  { id: "e3", from: "karya", to: "llm", label: "Generates models", protocol: "Encrypted API" },
  { id: "e4", from: "karya", to: "analysis", label: "Persists living links", protocol: "Local IPC" },
];

export const navSections = [
  {
    label: "C4 MODEL",
    items: [
      { id: "context", label: "System Context", count: 1 },
      { id: "container", label: "Containers", count: 5 },
      { id: "component", label: "Components", count: 18 },
      { id: "code", label: "Code", count: 42 },
    ],
  },
  {
    label: "UML VIEWS",
    items: [
      { id: "class", label: "Domain classes", count: 12 },
      { id: "sequence", label: "Sequence flows", count: 4 },
      { id: "activity", label: "Activities", count: 3 },
      { id: "state", label: "State machines", count: 2 },
    ],
  },
];
