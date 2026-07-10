export const DEFAULT_DIAGRAM_TYPE = 'architecture'

export const DIAGRAM_TYPE_GROUPS = [
  {
    label: 'Workspace views',
    types: [
      {
        id: 'architecture',
        label: 'Architecture flow',
        title: 'Solution architecture',
        template: `flowchart LR
    Brief@{ shape: doc, label: "Story brief" } --> Web["Web application"]
    Web --> API["Experience API"]
    API --> Decision{"Needs orchestration?"}
    Decision -- yes --> Domain["Domain services"]
    Decision -- no --> Adapter@{ shape: bolt, label: "Direct integration" }
    Domain --> Data[("Operational data")]
    Domain -. events .-> Bus{{"Event bus"}}
    Bus --> Analytics["Analytics platform"]`,
      },
      {
        id: 'infrastructure',
        label: 'Infrastructure flow',
        title: 'Infrastructure topology',
        template: `flowchart TB
    User(("User")) --> Edge["CDN / WAF"]
    Edge --> LB["Load balancer"]
    subgraph cloud["Production cloud"]
      LB --> App1["App instance A"]
      LB --> App2["App instance B"]
      App1 --> DB[("Managed database")]
      App2 --> DB
      App1 --> Cache[("Cache")]
      App2 --> Cache
      Queue@{ shape: lin-cyl, label: "Message queue" } --> Worker@{ shape: fork, label: "Worker pool" }
    end`,
      },
    ],
  },
  {
    label: 'Systems and delivery',
    types: [
      {
        id: 'architecture_beta',
        label: 'Architecture beta',
        title: 'Cloud architecture',
        template: `architecture-beta
  group cloud(cloud)[Production cloud]
  service web(internet)[Web app] in cloud
  service api(server)[Experience API] in cloud
  service db(database)[Operational database] in cloud
  service queue(server)[Event queue] in cloud
  web:R --> L:api
  api:R --> L:db
  api:B --> T:queue`,
      },
      {
        id: 'block',
        label: 'Block layout',
        title: 'Block diagram',
        template: `block-beta
  columns 3
  web["Web app"] api["API"] db[("Database")]
  web --> api
  api --> db`,
      },
      {
        id: 'kanban',
        label: 'Kanban board',
        title: 'Delivery kanban',
        template: `kanban
  backlog[Backlog]
    story1[Model C4 context]@{ priority: 'High', assigned: 'Architecture' }
    story2[Define rollout plan]
  delivery[In delivery]
    story3[Build estimator]@{ priority: 'Very High', assigned: 'Squad A' }
  done[Done]
    story4[Seed demo workspace]`,
      },
      {
        id: 'packet',
        label: 'Packet structure',
        title: 'Packet structure',
        template: `packet
  0-15: "Source port"
  16-31: "Destination port"
  32-63: "Sequence number"
  64-95: "Acknowledgement"
  96-99: "Header length"
  100-105: "Flags"
  106-127: "Window size"`,
      },
    ],
  },
  {
    label: 'Classic Mermaid',
    types: [
      {
        id: 'sequence',
        label: 'Sequence',
        title: 'Interaction sequence',
        template: `sequenceDiagram
  autonumber
  actor User
  participant Web
  participant API
  participant Service
  User->>Web: Submit request
  Web->>API: POST /estimate
  API->>Service: Evaluate evidence
  Service-->>API: Result
  API-->>Web: Response`,
      },
      {
        id: 'class',
        label: 'Class',
        title: 'Domain classes',
        template: `classDiagram
  class Story {
    +String title
    +String description
    +estimate()
  }
  class Estimator {
    +scoreDrivers()
    +derivePoints()
  }
  Story --> Estimator : analyzed by`,
      },
      {
        id: 'state',
        label: 'State',
        title: 'Lifecycle state',
        template: `stateDiagram-v2
  [*] --> Draft
  Draft --> InReview: submit
  InReview --> Approved: approve
  InReview --> Draft: request changes
  Approved --> [*]`,
      },
      {
        id: 'er',
        label: 'ER',
        title: 'Data model',
        template: `erDiagram
  PROJECT ||--o{ EPIC : contains
  EPIC ||--o{ STORY : breaks_down_into
  STORY ||--o{ TASK : proposes
  STORY {
    string title
    int points
  }`,
      },
      {
        id: 'requirement',
        label: 'Requirement',
        title: 'Requirement trace',
        template: `requirementDiagram
  performanceRequirement availability {
    id: NFR1
    text: "99.9 percent availability"
    risk: Medium
    verifymethod: Test
  }
  element platform {
    type: system
    docref: platform.md
  }
  platform - satisfies -> availability`,
      },
      {
        id: 'c4',
        label: 'C4 context',
        title: 'System context',
        template: `C4Context
  title System context
  Person(user, "User")
  System(app, "Story Pointer")
  System_Ext(jira, "Jira")
  Rel(user, app, "Estimates stories")
  Rel(app, jira, "Reads issues")`,
      },
      {
        id: 'gantt',
        label: 'Gantt',
        title: 'Initiative timeline',
        template: `gantt
  title Initiative plan
  dateFormat YYYY-MM-DD
  section Discovery
  Scope decisions :a1, 2026-07-01, 5d
  Architecture review :after a1, 3d
  section Delivery
  Build slice :2026-07-10, 10d
  Validation :after a1, 6d`,
      },
      {
        id: 'journey',
        label: 'User journey',
        title: 'User journey',
        template: `journey
  title Onboarding experience
  section Discover
    Open product page: 4: Customer
    Compare benefits: 3: Customer
  section Activate
    Submit application: 3: Customer
    Receive approval: 5: Customer`,
      },
      {
        id: 'timeline',
        label: 'Timeline',
        title: 'Release timeline',
        template: `timeline
  title Release path
  Discovery : Scope : Architecture
  Build : API : UI
  Launch : Pilot : Scale`,
      },
      {
        id: 'mindmap',
        label: 'Mindmap',
        title: 'Initiative mindmap',
        template: `mindmap
  root((Initiative))
    Experience
      Web journey
      Accessibility
    Platform
      API
      Data
    Operations
      Observability
      Runbook`,
      },
      {
        id: 'quadrant',
        label: 'Quadrant',
        title: 'Prioritization quadrant',
        template: `quadrantChart
  title Delivery prioritization
  x-axis Low effort --> High effort
  y-axis Low value --> High value
  "Checkout": [0.35, 0.82]
  "Reporting": [0.72, 0.58]
  "Admin cleanup": [0.28, 0.32]`,
      },
      {
        id: 'gitgraph',
        label: 'Git graph',
        title: 'Release branches',
        template: `gitGraph
  commit id: "init"
  branch feature
  checkout feature
  commit id: "build"
  checkout main
  merge feature
  commit id: "release"`,
      },
      {
        id: 'pie',
        label: 'Pie',
        title: 'Effort mix',
        template: `pie showData
  title Effort mix
  "Frontend" : 35
  "Backend" : 40
  "Testing" : 15
  "Coordination" : 10`,
      },
      {
        id: 'xychart',
        label: 'XY chart',
        title: 'Velocity trend',
        template: `xychart-beta
  title "Velocity trend"
  x-axis [Sprint 1, Sprint 2, Sprint 3, Sprint 4]
  y-axis "Points" 0 --> 50
  line [22, 28, 34, 39]`,
      },
      {
        id: 'sankey',
        label: 'Sankey',
        title: 'Capacity flow',
        template: `sankey-beta
  Discovery,Delivery,8
  Delivery,Testing,5
  Delivery,Operations,2
  Testing,Release,4`,
      },
    ],
  },
  {
    label: 'Mermaid 11 charts',
    types: [
      {
        id: 'radar',
        label: 'Radar',
        title: 'Capability radar',
        template: `radar-beta
  title Architecture readiness
  axis Security, Scalability, Operability, Delivery, Cost
  curve Current{70, 60, 75, 55, 65}
  curve Target{90, 85, 90, 80, 75}
  max 100`,
      },
      {
        id: 'treemap',
        label: 'Treemap',
        title: 'Scope treemap',
        template: `treemap-beta
  "Initiative"
    "Experience": 34
    "Platform"
      "API": 21
      "Data": 13
    "Operations": 8`,
      },
      {
        id: 'venn',
        label: 'Venn',
        title: 'Capability overlap',
        template: `venn-beta
  title "Team overlap"
  set Frontend["Frontend"]: 3
  set Backend["Backend"]: 3
  set Data["Data"]: 2
  union Frontend,Backend["API contracts"]: 1
  union Backend,Data["Persistence"]: 1`,
      },
    ],
  },
]

export const DIAGRAM_TYPES = DIAGRAM_TYPE_GROUPS.flatMap((group) => group.types)

export function getDiagramType(id) {
  return DIAGRAM_TYPES.find((type) => type.id === id) || DIAGRAM_TYPES.find((type) => type.id === DEFAULT_DIAGRAM_TYPE)
}

export function diagramTypeLabel(id) {
  return getDiagramType(id)?.label || id
}
