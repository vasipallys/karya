export interface MermaidDiagramDefinition {
  id: string;
  name: string;
  category: "Software" | "Process" | "Data" | "Planning" | "Strategy";
  description: string;
  experimental?: boolean;
  template: string;
}

export const mermaidCatalog: MermaidDiagramDefinition[] = [
  { id: "flowchart", name: "Flowchart", category: "Process", description: "Processes, decisions, and routing.", template: `flowchart LR
  A[Requirements] --> B{Source type?}
  B -->|Story| C[Analyze requirements]
  B -->|Repository| D[Parse source]
  C --> E[Generate architecture]
  D --> E
  E --> F[Validate model]` },
  { id: "swimlane", name: "Swimlanes", category: "Process", description: "Cross-team ownership and handoffs.", experimental: true, template: `swimlane-beta LR
  subgraph Architect
    A[Describe system]
    D[Review model]
  end
  subgraph Karya
    B[Analyze input]
    C[Generate diagrams]
  end
  A --> B --> C --> D` },
  { id: "sequence", name: "Sequence", category: "Software", description: "Messages exchanged over time.", template: `sequenceDiagram
  autonumber
  actor Architect
  participant UI as Karya Desktop
  participant Agent as Modeler Agent
  participant Cache as Analysis Cache
  Architect->>UI: Analyze repository
  UI->>Agent: Generate architecture
  Agent->>Cache: Store code mappings
  Cache-->>Agent: Mapping IDs
  Agent-->>UI: Living diagram
  UI-->>Architect: Interactive model` },
  { id: "class", name: "Class", category: "Software", description: "Types, members, and relationships.", template: `classDiagram
  class Diagram {
    +String id
    +String type
    +render()
  }
  class Node {
    +String title
    +String sourcePath
  }
  class Relationship {
    +String label
    +String protocol
  }
  Diagram "1" *-- "*" Node
  Diagram "1" *-- "*" Relationship` },
  { id: "state", name: "State", category: "Software", description: "Lifecycle states and transitions.", template: `stateDiagram-v2
  [*] --> Idle
  Idle --> Parsing: analyze
  Parsing --> Modeling: index complete
  Modeling --> Validating: diagrams ready
  Validating --> Current: no drift
  Validating --> Stale: drift found
  Stale --> Parsing: regenerate
  Current --> [*]` },
  { id: "er", name: "Entity relationship", category: "Data", description: "Entities, fields, and cardinality.", template: `erDiagram
  DIAGRAM ||--o{ NODE : contains
  DIAGRAM ||--o{ RELATIONSHIP : contains
  NODE ||--o{ CODE_LINK : maps_to
  DIAGRAM {
    string id PK
    string name
    string type
  }
  NODE {
    string id PK
    string title
    string status
  }
  CODE_LINK {
    string file_path
    int line_start
    string commit_sha
  }` },
  { id: "journey", name: "User journey", category: "Process", description: "Experience stages and satisfaction.", template: `journey
  title Architecture discovery journey
  section Connect
    Add repository: 5: Architect
    Select branch: 4: Architect
  section Understand
    Generate diagrams: 5: Karya
    Explore relationships: 4: Architect
  section Maintain
    Review drift: 3: Architect, Karya
    Update model: 5: Karya` },
  { id: "gantt", name: "Gantt", category: "Planning", description: "Schedules, dependencies, and milestones.", template: `gantt
  title Architecture modernization
  dateFormat YYYY-MM-DD
  section Discovery
  Repository analysis :done, a1, 2026-07-01, 3d
  Context model       :a2, after a1, 2d
  section Design
  Container model     :a3, after a2, 3d
  Component review    :a4, after a3, 2d
  section Delivery
  Drift baseline      :milestone, after a4, 0d` },
  { id: "pie", name: "Pie chart", category: "Data", description: "Part-to-whole comparisons.", template: `pie showData
  title Architecture elements
  "Containers" : 5
  "Components" : 18
  "Code symbols" : 42
  "External systems" : 4` },
  { id: "quadrant", name: "Quadrant", category: "Strategy", description: "Items on two strategic dimensions.", template: `quadrantChart
  title Architecture priorities
  x-axis Low effort --> High effort
  y-axis Low impact --> High impact
  quadrant-1 Plan carefully
  quadrant-2 Quick wins
  quadrant-3 Defer
  quadrant-4 Reconsider
  Living links: [0.35, 0.88]
  Drift detection: [0.62, 0.82]
  Theme polish: [0.22, 0.45]
  Code-level model: [0.82, 0.65]` },
  { id: "requirement", name: "Requirement", category: "Software", description: "Requirements and verification links.", template: `requirementDiagram
  requirement traceability {
    id: REQ101
    text: Every diagram element links to source
    risk: high
    verifymethod: test
  }
  element linker {
    type: service
    docref: src/agents/linker.ts
  }
  linker - satisfies -> traceability` },
  { id: "gitgraph", name: "Git graph", category: "Planning", description: "Branches, commits, and merges.", template: `gitGraph
  commit id: "bootstrap"
  branch feature/agents
  checkout feature/agents
  commit id: "worker pipeline"
  commit id: "living links"
  checkout main
  merge feature/agents
  commit id: "release 0.1"` },
  { id: "c4", name: "C4 model", category: "Software", description: "Context, container, component, and dynamic views.", experimental: true, template: `C4Context
  title System Context for Karya
  Person(architect, "Software Architect", "Explores living architecture")
  System(karya, "Karya Desktop", "Generates C4 and UML models")
  System_Ext(git, "Git Platform", "Source and history")
  System_Ext(ai, "AI Provider", "Architecture reasoning")
  Rel(architect, karya, "Explores")
  Rel(karya, git, "Indexes", "Git")
  Rel(karya, ai, "Generates models", "HTTPS")` },
  { id: "mindmap", name: "Mindmap", category: "Planning", description: "Hierarchical ideation and decomposition.", template: `mindmap
  root((Karya))
    Inputs
      Requirements
      Git repositories
    Models
      C4
      UML
      Mermaid
    Intelligence
      Parsing
      Linking
      Drift detection
    Outputs
      SVG
      HTML
      Markdown` },
  { id: "timeline", name: "Timeline", category: "Planning", description: "Events across chronological periods.", template: `timeline
  title Karya evolution
  2026 Q1 : Repository parser
          : C4 context models
  2026 Q2 : UML generation
          : Living source links
  2026 Q3 : Architecture drift
          : Mermaid studio
  2026 Q4 : Collaborative reviews` },
  { id: "zenuml", name: "ZenUML", category: "Software", description: "Code-like sequence notation.", template: `zenuml
  title Repository analysis
  @Actor Architect
  Architect->Karya: analyze(repository) {
    Karya->Parser: indexSource()
    Parser->Modeler: dependencyGraph
    Modeler->Linker: generatedModel
    Linker->Karya: livingDiagram
  }` },
  { id: "sankey", name: "Sankey", category: "Data", description: "Weighted flow between stages.", template: `sankey-beta
Requirements,Analysis,12
Source code,Analysis,28
Analysis,C4 models,18
Analysis,UML views,14
Analysis,Traceability,8` },
  { id: "xychart", name: "XY chart", category: "Data", description: "Bar and line series on numeric axes.", template: `xychart-beta
  title "Architecture coverage"
  x-axis [Context, Container, Component, Code]
  y-axis "Mapped elements" 0 --> 50
  bar [5, 12, 25, 42]
  line [5, 10, 22, 38]` },
  { id: "block", name: "Block diagram", category: "Software", description: "Structured system blocks and ports.", template: `block-beta
  columns 3
  Input["Requirements / Code"] space Parser["Analysis agents"]
  space:3
  C4["C4 Modeler"] UML["UML Generator"] Linker["Living Linker"]
  Input --> Parser
  Parser --> C4
  Parser --> UML
  C4 --> Linker
  UML --> Linker` },
  { id: "packet", name: "Packet", category: "Data", description: "Bit-level network packet layouts.", template: `packet-beta
  0-7: "Version"
  8-15: "Message Type"
  16-31: "Payload Length"
  32-63: "Diagram ID"
  64-95: "Commit SHA"
  96-127: "Payload"` },
  { id: "kanban", name: "Kanban", category: "Planning", description: "Work organized into status columns.", template: `kanban
  backlog[Backlog]
    task1[Add PR preview]
    task2[Improve blame insights]
  doing[In progress]
    task3[Mermaid diagram studio]
  review[Review]
    task4[Architecture validation]
  done[Done]
    task5[Living source links]` },
  { id: "architecture", name: "Architecture", category: "Software", description: "Services, groups, and infrastructure.", template: `architecture-beta
  group karya(cloud)[Karya Platform]
  service ui(internet)[Desktop UI] in karya
  service agents(server)[Agent Workers] in karya
  service parser(server)[AST Parser] in karya
  service cache(database)[SQLite Cache] in karya
  ui:R --> L:agents
  agents:B --> T:parser
  agents:B --> T:cache` },
  { id: "radar", name: "Radar", category: "Data", description: "Compare entities across dimensions.", template: `radar-beta
  title Architecture quality
  axis clarity["Clarity"], coverage["Coverage"], freshness["Freshness"], trace["Traceability"], stability["Stability"]
  curve current["Current"]{82, 76, 91, 88, 79}
  curve target["Target"]{95, 95, 95, 95, 90}
  max 100
  min 0
  graticule polygon` },
  { id: "eventmodeling", name: "Event modeling", category: "Software", description: "Commands, events, views, and timelines.", experimental: true, template: `eventmodeling
  tf 01 ui GenerationForm
  tf 02 cmd AnalyzeRepository
  tf 03 evt RepositoryIndexed
  tf 04 cmd GenerateModels
  tf 05 evt ModelsGenerated
  tf 06 rmo ArchitectureCanvas` },
  { id: "treemap", name: "Treemap", category: "Data", description: "Hierarchical proportions as nested rectangles.", experimental: true, template: `treemap-beta
  "Architecture"
    "C4"
      "Context": 5
      "Containers": 12
      "Components": 25
    "UML"
      "Classes": 18
      "Sequences": 8
      "Activities": 6` },
  { id: "venn", name: "Venn", category: "Data", description: "Overlapping sets and intersections.", experimental: true, template: `venn-beta
  set R["Requirements"]:30
  set C["Source Code"]:40
  union R,C["Living Architecture"]:18` },
  { id: "ishikawa", name: "Ishikawa", category: "Strategy", description: "Cause-and-effect fishbone analysis.", experimental: true, template: `ishikawa
  Architecture drift
    People
      Ownership unclear
      Reviews delayed
    Process
      Manual updates
      Missing checks
    Technology
      Dynamic dependencies
      Untracked services
    Information
      Stale documentation
      Missing code links` },
  { id: "wardley", name: "Wardley map", category: "Strategy", description: "Value chains and component evolution.", experimental: true, template: `wardley-beta
  title Architecture Intelligence
  anchor Architect [0.95, 0.95]
  component Karya [0.82, 0.62]
  component AI reasoning [0.62, 0.45]
  component Source parsing [0.55, 0.72]
  component Git [0.35, 0.88]
  Architect -> Karya
  Karya -> AI reasoning
  Karya -> Source parsing
  Source parsing -> Git` },
  { id: "cynefin", name: "Cynefin", category: "Strategy", description: "Decisions across complexity domains.", experimental: true, template: `cynefin-beta
  title Architecture decisions
  complex
    "Discover service boundaries"
  complicated
    "Select database strategy"
  clear
    "Run static checks"
  chaotic
    "Respond to production outage"
  confusion
    "Unclassified legacy behavior"
  complex --> complicated : "Pattern identified"
  complicated --> clear : "Practice codified"` },
  { id: "treeview", name: "TreeView", category: "Data", description: "Directory-like hierarchical structures.", experimental: true, template: `treeView-beta
  karya/
    electron/
      main.cjs ## Desktop orchestration
      agent-worker.cjs
    src/
      components/
        DiagramCanvas.tsx
        MermaidStudio.tsx
      App.tsx
    python/
      analysis_service.py
    package.json` },
];

export const mermaidCategories = ["Software", "Process", "Data", "Planning", "Strategy"] as const;
