import { describe, expect, it } from 'vitest'
import { buildDevHandoff, handoffFilename } from './devHandoff'

const workspace = {
  element: { id: 'l4-1', name: 'ClientController + request validation', description: 'REST controller with bean validation.' },
  parent: { id: 'l3-1', name: 'Client profile API' },
  arch: { summary: 'Thin controller delegating to the profile service.', code_diagram: 'classDiagram\n  class ClientController', status: 'draft' },
  code_units: [
    { name: 'ClientController', unit_type: 'class', responsibility: 'HTTP endpoints', tech: 'Spring Boot 3', path: 'src/main/java/ClientController.java', complexity: 'medium', status: 'todo' },
  ],
  test_cases: [
    { name: 'rejects malformed email', test_type: 'unit', scenario: 'PATCH with bad email', expected: '400 problem-details', status: 'planned' },
  ],
  checklist: [
    { id: 'c1', item: 'API docs updated', done: false },
    { id: 'c2', item: 'Idempotent under retry', done: true },
  ],
}

describe('buildDevHandoff', () => {
  it('renders every captured artifact into one self-contained brief', () => {
    const md = buildDevHandoff(workspace)

    expect(md).toContain('# Dev handoff — ClientController + request validation')
    expect(md).toContain('**Story (L3):** Client profile API')
    expect(md).toContain('REST controller with bean validation.')
    expect(md).toContain('## Implementation summary')
    expect(md).toContain('Thin controller delegating to the profile service.')
    expect(md).toContain('**ClientController** (class · Spring Boot 3 · src/main/java/ClientController.java · complexity: medium) — HTTP endpoints')
    expect(md).toContain('**rejects malformed email** [unit] — Given: PATCH with bad email → Expect: 400 problem-details')
    expect(md).toContain('- [ ] API docs updated')
    expect(md).toContain('- [x] Idempotent under retry')
    expect(md).toContain('```mermaid\nclassDiagram\n  class ClientController\n```')
    expect(md).toContain('Suggested branch: `feat/clientcontroller-request-validation`')
  })

  it('omits empty sections but always includes the working agreement', () => {
    const md = buildDevHandoff({ element: { id: 'x', name: 'Bare task' }, arch: {}, code_units: [], test_cases: [], checklist: [] })

    expect(md).toContain('# Dev handoff — Bare task')
    expect(md).not.toContain('## Code units to implement')
    expect(md).not.toContain('## Test cases to satisfy')
    expect(md).not.toContain('## Definition of Done')
    expect(md).not.toContain('```mermaid')
    expect(md).toContain('## Working agreement')
  })

  it('derives a safe filename from the task name', () => {
    expect(handoffFilename('ClientController + request validation')).toBe('dev-handoff-clientcontroller-request-validation.md')
  })
})
