import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, consumeSSE } from './client'

describe('API client production boundaries', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('flushes the final SSE event when the stream closes without a blank line', async () => {
    const bytes = new TextEncoder().encode('event: result\ndata: {"points":5}')
    let read = false
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (read) return { value: undefined, done: true }
            read = true
            return { value: bytes, done: false }
          },
        }),
      },
      headers: { get: () => null },
    }))
    const events = []

    await consumeSSE('/estimate', {}, (event, data) => events.push({ event, data }))

    expect(events).toEqual([{ event: 'result', data: { points: 5 } }])
  })

  it('downloads the protected spreadsheet template with identity headers', async () => {
    localStorage.setItem('karya.auth.user', JSON.stringify({ staff_id: 'staff-1', role: 'manager' }))
    const blob = new Blob(['template'])
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: (name) => name === 'Content-Disposition' ? 'attachment; filename="karya-template.xlsx"' : null },
      blob: async () => blob,
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await api.downloadTemplate()

    expect(result.filename).toBe('karya-template.xlsx')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/upload/template',
      expect.objectContaining({ headers: expect.objectContaining({ 'X-User-Id': 'staff-1', 'X-User-Role': 'manager' }) }),
    )
  })

  it('signals the auth layer when the server rejects a stale identity', async () => {
    const unauthorized = vi.fn()
    window.addEventListener('karya:unauthorized', unauthorized, { once: true })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: { get: () => 'request-401' },
      json: async () => ({ error: { code: 'unauthorized', message: 'Sign in again.' } }),
    }))

    await expect(api.listProjects()).rejects.toThrow('Sign in again.')

    expect(unauthorized).toHaveBeenCalledOnce()
  })
})
