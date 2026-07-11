// Builds the developer handoff pack for an L4 task: everything captured up the
// chain (story context, implementation design, code units, test cases, DoD)
// rendered as one self-contained Markdown brief that can be pasted straight
// into a coding agent (Claude Code, Cursor, …) or attached to a ticket — the
// "task → code generation" link of the value chain. Pure function, no I/O.

const slug = (text) => (text || 'task').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '').slice(0, 60)

export function buildDevHandoff(ws) {
  const { element, parent, arch = {}, code_units = [], test_cases = [], checklist = [] } = ws
  const lines = []

  lines.push(`# Dev handoff — ${element.name}`)
  lines.push('')
  if (parent?.name) lines.push(`**Story (L3):** ${parent.name}`)
  lines.push(`**Task (L4):** ${element.name}`)
  if (element.description) lines.push('', element.description)
  if (arch.summary) lines.push('', '## Implementation summary', '', arch.summary)

  if (code_units.length) {
    lines.push('', '## Code units to implement', '')
    for (const unit of code_units) {
      const meta = [unit.unit_type, unit.tech, unit.path, `complexity: ${unit.complexity}`].filter(Boolean).join(' · ')
      lines.push(`- **${unit.name}** (${meta})${unit.responsibility ? ` — ${unit.responsibility}` : ''}`)
    }
  }

  if (test_cases.length) {
    lines.push('', '## Test cases to satisfy', '')
    for (const test of test_cases) {
      lines.push(`- **${test.name}** [${test.test_type}]${test.scenario ? ` — Given: ${test.scenario}` : ''}${test.expected ? ` → Expect: ${test.expected}` : ''}`)
    }
  }

  if (checklist.length) {
    lines.push('', '## Definition of Done', '')
    for (const entry of checklist) lines.push(`- [${entry.done ? 'x' : ' '}] ${entry.item}`)
  }

  if ((arch.code_diagram || '').trim()) {
    lines.push('', '## Design diagram (Mermaid)', '', '```mermaid', arch.code_diagram.trim(), '```')
  }

  lines.push('', '## Working agreement', '')
  lines.push(`- Suggested branch: \`feat/${slug(element.name)}\``)
  lines.push('- Implement the code units above, keeping names and paths as specified unless they conflict with repository conventions.')
  lines.push('- Write the listed test cases first (or alongside) and make them pass; do not remove or weaken existing tests.')
  lines.push('- Every Definition-of-Done item must hold before the change is considered complete.')
  lines.push('- Run the full test suite and linting before raising the pull request; include this handoff in the PR description.')

  return lines.join('\n')
}

export function handoffFilename(elementName) {
  return `dev-handoff-${slug(elementName)}.md`
}
