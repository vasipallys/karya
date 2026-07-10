import { describe, expect, it } from 'vitest'
import { resolveAiDestination } from './askAiRouting'

describe('resolveAiDestination', () => {
  it('routes every project-scoped action to its workspace tab when a project is open', () => {
    expect(resolveAiDestination('generate_l1_baseline', true)).toEqual({ kind: 'tab', tab: 'planning' })
    expect(resolveAiDestination('auto_staffing', true)).toEqual({ kind: 'tab', tab: 'planning' })
    expect(resolveAiDestination('decompose_story', true)).toEqual({ kind: 'tab', tab: 'canvas' })
    expect(resolveAiDestination('scaffold_c4', true)).toEqual({ kind: 'tab', tab: 'canvas' })
    expect(resolveAiDestination('review_readiness', true)).toEqual({ kind: 'tab', tab: 'rollup' })
  })

  it('asks for an open project when a project-scoped action arrives without one', () => {
    expect(resolveAiDestination('decompose_story', false)).toEqual({ kind: 'need-project' })
    expect(resolveAiDestination('generate_l1_baseline', false)).toEqual({ kind: 'need-project' })
  })

  it('routes reporting to admin regardless of project context', () => {
    expect(resolveAiDestination('reporting_narrative', true)).toEqual({ kind: 'admin' })
    expect(resolveAiDestination('reporting_narrative', false)).toEqual({ kind: 'admin' })
  })

  it('returns none for the none action and unknown strings', () => {
    expect(resolveAiDestination('none', true)).toEqual({ kind: 'none' })
    expect(resolveAiDestination('made_up_action', true)).toEqual({ kind: 'none' })
    expect(resolveAiDestination(undefined, true)).toEqual({ kind: 'none' })
  })
})
