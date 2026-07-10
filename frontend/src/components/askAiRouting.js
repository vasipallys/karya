// Maps an AI-orchestrator action to a place in the app. Pure module so the
// mapping is unit-testable without rendering the shell.
export const AI_DESTINATIONS = {
  generate_l1_baseline: { screen: 'project', tab: 'planning' },
  auto_staffing: { screen: 'project', tab: 'planning' },
  decompose_story: { screen: 'project', tab: 'canvas' },
  scaffold_c4: { screen: 'project', tab: 'canvas' },
  review_readiness: { screen: 'project', tab: 'rollup' },
  reporting_narrative: { screen: 'admin' },
}

export const ACTION_LABELS = {
  generate_l1_baseline: 'Generate an L1 baseline',
  auto_staffing: 'Propose squad staffing',
  decompose_story: 'Decompose a story',
  scaffold_c4: 'Scaffold a C4 model',
  review_readiness: 'Review readiness',
  reporting_narrative: 'Draft a reporting narrative',
  none: 'No matching action',
}

export function resolveAiDestination(action, hasOpenProject) {
  const destination = AI_DESTINATIONS[action]
  if (!destination) return { kind: 'none' }
  if (destination.screen === 'admin') return { kind: 'admin' }
  return hasOpenProject ? { kind: 'tab', tab: destination.tab } : { kind: 'need-project' }
}
