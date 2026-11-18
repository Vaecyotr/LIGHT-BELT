import test from 'node:test'
import assert from 'node:assert/strict'
import { api, clearRequestError, requestError } from '../src/api.js'

test.beforeEach(() => clearRequestError())

function mockHost(t, ...responses) {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    const response = responses.shift()
    if (response instanceof Error) throw response
    return { json: async () => response }
  })
  return calls
}

test('Kiosk loads and controls the Host directly without a session', async (t) => {
  const shows = { ok: true, data: { shows: [] } }
  const brightness = { ok: true, data: { brightness_scale: 0.17 } }
  const calls = mockHost(t, shows, brightness)

  assert.deepEqual(await api.shows(), shows)
  assert.deepEqual(await api.setBrightness(0.17), brightness)
  assert.deepEqual(calls.map(({ url }) => url), ['/api/v1/shows', '/api/v1/brightness/set'])
  assert.ok(calls.every(({ options }) => !('Authorization' in options.headers)))
  assert.equal(calls[1].options.method, 'POST')
  assert.deepEqual(JSON.parse(calls[1].options.body), { brightness_scale: 0.17 })
})

test('Host rejection is visible until dismissed or the same request succeeds', async (t) => {
  const rejected = { ok: false, error: { code: 'MPV_UNAVAILABLE', message: 'mpv command failed' } }
  mockHost(t, rejected, { ok: true, data: {} }, rejected, { ok: true, data: {} })

  assert.deepEqual(await api.play('show'), rejected)
  await api.playbackState()
  assert.equal(requestError.message, 'mpv command failed')

  clearRequestError()
  assert.equal(requestError.message, '')
  await api.play('show')
  assert.equal(requestError.message, 'mpv command failed')
  await api.play('show')
  assert.equal(requestError.message, '')
})

test('a network failure produces an error result and recovers after a successful request', async (t) => {
  mockHost(t, new TypeError('Failed to fetch'), { ok: true, data: {} })

  const failure = await api.playbackState()
  assert.equal(failure.ok, false)
  assert.equal(failure.error.code, 'NETWORK_ERROR')
  assert.equal(requestError.message, failure.error.message)
  await api.playbackState()
  assert.equal(requestError.message, '')
})
