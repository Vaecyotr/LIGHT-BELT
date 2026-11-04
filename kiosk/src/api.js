import { reactive } from 'vue'

const BASE = '/api/v1'
let accessToken = ''
let refreshToken = ''
let refreshPromise = null
let generation = 0

export const authState = reactive({ authenticated: false, needsPairing: true, error: '', errorPath: '' })

function clearSession() {
  generation += 1
  accessToken = ''
  refreshToken = ''
  authState.authenticated = false
  authState.needsPairing = true
}

function installTokens(data) {
  accessToken = data.access_token
  refreshToken = data.refresh_token
  authState.authenticated = true
  authState.needsPairing = false
}

async function request(method, path, body, token = '') {
  const opts = { method, headers: { 'Content-Type': 'application/json' } }
  if (token) opts.headers.Authorization = `Bearer ${token}`
  if (body !== undefined) opts.body = JSON.stringify(body)
  try {
    const response = await fetch(BASE + path, opts)
    return await response.json()
  } catch (_) {
    return { ok: false, error: { code: 'NETWORK_ERROR', message: '无法连接 Host，请检查服务和网络。' } }
  }
}

async function refreshSession() {
  if (!refreshToken) return false
  if (!refreshPromise) {
    const currentGeneration = generation
    refreshPromise = (async () => {
      const result = await request('POST', '/auth/refresh', { refresh_token: refreshToken })
      if (currentGeneration !== generation) return Boolean(accessToken)
      if (result.ok) {
        installTokens(result.data)
        if (authState.errorPath === '/auth/refresh') auth.clearError()
        return true
      }
      if (['TOKEN_EXPIRED', 'UNAUTHORIZED'].includes(result.error?.code)) {
        clearSession()
        authState.error = '会话已失效，请重新输入配对码。'
      } else {
        authState.error = result.error?.message || '刷新会话失败，请重试。'
      }
      authState.errorPath = '/auth/refresh'
      return false
    })().finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

export const auth = {
  clear: clearSession,
  clearError() {
    authState.error = ''
    authState.errorPath = ''
  },
  async pair(pairingCode) {
    const currentGeneration = ++generation
    const result = await request('POST', '/auth/pair', {
      pairing_code: pairingCode, client_id: 'local-kiosk', client_name: 'LIGHT-BELT Kiosk',
      client_type: 'tablet', app_version: '1.0',
    })
    if (currentGeneration === generation) {
      if (result.ok) {
        installTokens(result.data)
        auth.clearError()
      } else {
        clearSession()
        authState.error = result.error?.message || '配对失败。'
        authState.errorPath = '/auth/pair'
      }
    }
    return result
  },
}

async function call(method, path, body) {
  const isPublic = path === '/status'
  if (!isPublic && !accessToken && !(await refreshSession())) {
    return { ok: false, error: { code: 'UNAUTHORIZED', message: '请先输入配对码。' } }
  }
  const sentToken = accessToken
  const requestGeneration = generation
  let result = await request(method, path, body, isPublic ? '' : sentToken)
  if (requestGeneration !== generation) return result
  if (!isPublic && ['TOKEN_EXPIRED', 'UNAUTHORIZED'].includes(result.error?.code)) {
    if ((sentToken !== accessToken && accessToken) || await refreshSession()) {
      if (requestGeneration !== generation) return result
      const retryToken = accessToken
      result = await request(method, path, body, accessToken)
      if (requestGeneration !== generation) return result
      if (retryToken === accessToken && ['TOKEN_EXPIRED', 'UNAUTHORIZED'].includes(result.error?.code)) clearSession()
    } else {
      return result
    }
  }
  if (!result.ok) {
    authState.error = result.error?.message || '请求失败。'
    authState.errorPath = path
  } else if (authState.errorPath === path) {
    auth.clearError()
  }
  return result
}

export const api = {
  status: () => call('GET', '/status'),
  shows: () => call('GET', '/shows'),
  scenes: () => call('GET', '/scenes'),
  playbackState: () => call('GET', '/playback/state'),
  play: (show_id, start_position_ms = 0) => call('POST', '/playback/play', { show_id, start_position_ms }),
  pause: () => call('POST', '/playback/pause'),
  resume: () => call('POST', '/playback/resume'),
  stop: () => call('POST', '/playback/stop'),
  seek: (position_ms) => call('POST', '/playback/seek', { position_ms }),
  setBrightness: (brightness_scale) => call('POST', '/brightness/set', { brightness_scale }),
  setVolume: (volume) => call('POST', '/audio/set', { volume }),
  setMuted: (muted) => call('POST', '/audio/set', { muted }),
}
