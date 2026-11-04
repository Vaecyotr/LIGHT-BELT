import test from 'node:test'
import assert from 'node:assert/strict'
import { api, auth, authState } from '../src/api.js'

const success = (data) => ({ ok: true, data })
const denied = { ok: false, error: { code: 'TOKEN_EXPIRED', message: 'expired' } }
const pairData = { access_token: 'access-1', refresh_token: 'refresh-1' }

function responses(values, calls) {
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    const result = values.shift()
    assert.ok(result, 'unexpected fetch')
    return { json: async () => result, status: result.ok ? 200 : 401 }
  }
}

test('anonymous control requests require pairing without fetching a write', async () => {
  auth.clear()
  const calls = []
  responses([], calls)
  const result = await api.setBrightness(0.17)
  assert.equal(result.ok, false)
  assert.equal(authState.needsPairing, true)
  assert.equal(calls.length, 0)
})

test('pairing adds Bearer to controls and keeps pairing code out of control requests', async () => {
  auth.clear()
  const calls = []
  responses([success(pairData), success({ brightness_scale: 0.17 })], calls)
  assert.equal((await auth.pair('test-code')).ok, true)
  await api.setBrightness(0.17)
  assert.equal(calls[1].options.headers.Authorization, 'Bearer access-1')
  assert.equal(calls[1].options.body, JSON.stringify({ brightness_scale: 0.17 }))
  assert.equal(authState.authenticated, true)
})

test('concurrent expired requests share one rotating refresh', async () => {
  auth.clear()
  const calls = []
  responses([success(pairData)], calls)
  await auth.pair('test-code')
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith('/auth/refresh')) {
      await new Promise(resolve => setTimeout(resolve, 5))
      return { status: 200, json: async () => success({ access_token: 'access-2', refresh_token: 'refresh-2' }) }
    }
    const result = options.headers.Authorization === 'Bearer access-1' ? denied : success({})
    return { status: result.ok ? 200 : 401, json: async () => result }
  }
  const results = await Promise.all([api.playbackState(), api.shows()])
  assert.ok(results.every(result => result.ok))
  assert.equal(calls.filter(call => call.url.endsWith('/auth/refresh')).length, 1)
  assert.ok(calls.slice(-2).every(call => call.options.headers.Authorization === 'Bearer access-2'))
})

test('invalid refresh clears the session and exposes re-pairing', async () => {
  auth.clear()
  const calls = []
  responses([success(pairData), denied, denied], calls)
  await auth.pair('test-code')
  const result = await api.shows()
  assert.equal(result.ok, false)
  assert.equal(authState.authenticated, false)
  assert.equal(authState.needsPairing, true)
})

test('a rejected command is visible to the page', async () => {
  auth.clear()
  const calls = []
  responses([success(pairData), { ok: false, error: { code: 'MPV_UNAVAILABLE', message: 'mpv command failed' } }], calls)
  await auth.pair('test-code')
  const result = await api.play('show')
  assert.equal(result.ok, false)
  assert.match(authState.error, /mpv command failed/)
})

test('an old rejected retry cannot clear a newly paired session', async () => {
  auth.clear()
  const calls = []
  responses([success(pairData)], calls)
  await auth.pair('test-code')
  let rejectOldRetry
  let retryStarted
  const started = new Promise(resolve => { retryStarted = resolve })
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/auth/pair')) return { json: async () => success({ access_token: 'new-session', refresh_token: 'new-refresh' }) }
    if (url.endsWith('/auth/refresh')) return { json: async () => success({ access_token: 'old-refreshed', refresh_token: 'old-refresh' }) }
    if (options.headers.Authorization === 'Bearer access-1') return { json: async () => denied }
    retryStarted()
    return new Promise(resolve => { rejectOldRetry = () => resolve({ json: async () => denied }) })
  }
  const oldRequest = api.shows()
  await started
  await auth.pair('replacement-code')
  rejectOldRetry()
  await oldRequest
  assert.equal(authState.authenticated, true)
  assert.equal(authState.needsPairing, false)
  responses([success({})], calls)
  await api.playbackState()
  assert.equal(calls.at(-1).options.headers.Authorization, 'Bearer new-session')
})

test('a transient refresh failure preserves credentials for retry', async () => {
  auth.clear()
  const calls = []
  responses([
    success(pairData), denied,
    { ok: false, error: { code: 'NETWORK_ERROR', message: 'offline' } },
    denied, success({ access_token: 'recovered', refresh_token: 'recovered-refresh' }), success({}),
  ], calls)
  await auth.pair('test-code')
  assert.equal((await api.shows()).ok, false)
  assert.equal(authState.authenticated, true)
  assert.equal((await api.shows()).ok, true)
  assert.equal(authState.error, '')
})

test('successful recovery clears the failed request message', async () => {
  auth.clear()
  const calls = []
  responses([success(pairData), { ok: false, error: { code: 'NETWORK_ERROR', message: 'offline' } }, success({})], calls)
  await auth.pair('test-code')
  await api.playbackState()
  assert.equal(authState.error, 'offline')
  await api.playbackState()
  assert.equal(authState.error, '')
})

test('a polling token refresh preserves an unrelated command failure', async () => {
  auth.clear()
  const calls = []
  responses([
    success(pairData), { ok: false, error: { code: 'MPV_UNAVAILABLE', message: 'command failed' } },
    denied, success({ access_token: 'renewed', refresh_token: 'rotated' }), success({}),
  ], calls)
  await auth.pair('test-code')
  await api.play('show')
  await api.playbackState()
  assert.equal(authState.error, 'command failed')
})

test('a command waiting for refresh cannot cross into a newly paired session', async () => {
  auth.clear()
  const calls = []
  responses([success(pairData)], calls)
  await auth.pair('test-code')
  let finishRefresh
  let refreshStarted
  const started = new Promise(resolve => { refreshStarted = resolve })
  let writes = 0
  globalThis.fetch = async (url) => {
    if (url.endsWith('/auth/pair')) return { json: async () => success({ access_token: 'new-session', refresh_token: 'new-refresh' }) }
    if (url.endsWith('/auth/refresh')) {
      refreshStarted()
      return new Promise(resolve => {
        finishRefresh = () => resolve({ json: async () => success({ access_token: 'old-token', refresh_token: 'old-refresh' }) })
      })
    }
    writes += 1
    return { json: async () => denied }
  }
  const oldCommand = api.setBrightness(0.17)
  await started
  await auth.pair('replacement-code')
  finishRefresh()
  await oldCommand
  assert.equal(writes, 1)
  assert.equal(authState.authenticated, true)
})
