import { describe, expect, it } from 'vitest'
import { parseHash, routeToHash } from './routing'

describe('hash routing', () => {
  it('round-trips a project tab with its focused element', () => {
    const hash = routeToHash({ name: 'project', id: 'p 1' }, { tab: 'l2arch', elementId: 'e/2' })
    expect(hash).toBe('#/p/p%201/l2arch/e%2F2')
    expect(parseHash(hash)).toEqual({ route: { name: 'project', id: 'p 1' }, tab: { id: 'l2arch', elementId: 'e/2' } })
  })

  it('parses the top-level screens and falls back to home', () => {
    expect(parseHash('#/inbox/tasks').route).toEqual({ name: 'inbox', view: 'tasks' })
    expect(parseHash('#/admin/reporting/resources').route).toEqual({ name: 'admin', section: 'reporting', sectionTab: 'resources' })
    expect(parseHash('#/quick').route).toEqual({ name: 'quick' })
    expect(parseHash('').route).toEqual({ name: 'home' })
    expect(parseHash('#/nope').route).toEqual({ name: 'home' })
    expect(parseHash('#/p').route).toEqual({ name: 'home' })
  })

  it('never writes the transient wizard and omits empty parts', () => {
    expect(routeToHash({ name: 'wizard' })).toBeNull()
    expect(routeToHash({ name: 'home' })).toBe('#/')
    expect(routeToHash({ name: 'project', id: 'p1' }, { tab: 'rollup', elementId: null })).toBe('#/p/p1/rollup')
    expect(routeToHash({ name: 'admin' })).toBe('#/admin')
  })
})
