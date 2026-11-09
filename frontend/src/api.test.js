import { afterEach, expect, it, vi } from 'vitest'
import { api, closed } from './api'
afterEach(() => vi.unstubAllGlobals())
it('uses scoped cookies without a Bearer token', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) })
  vi.stubGlobal('fetch', fetch)
  await api('/calls/one/action', { action: 'accept' })
  const [url, options] = fetch.mock.calls[0]
  expect(url).toBe('/voice/calls/one/action')
  expect(options.credentials).toBe('same-origin')
  expect(options.headers.Authorization).toBeUndefined()
})
it('surfaces safe API failures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: 'Access expired' }) }))
  await expect(api('/me')).rejects.toThrow('Access expired')
})
it('recognizes terminal calls', () => {
  for (const status of ['completed', 'cancelled', 'failed', 'rejected']) expect(closed({ status })).toBe(true)
  expect(closed({ status: 'active' })).toBe(false)
})

it('stops reconnecting when a refused WebSocket handshake has expired auth', async () => {
  const { signaling } = await import('./api')
  const sockets = []
  class Socket {
    constructor() { sockets.push(this) }
    close() {}
  }
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('location', { origin: 'https://localhost:5173' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 401 }))
  const status = vi.fn()
  const stop = signaling('receiver', vi.fn(), status)
  await sockets[0].onclose({ code: 1006 })
  expect(status).toHaveBeenCalledWith('Access expired. Rejoin or sign in again.')
  stop()
})
