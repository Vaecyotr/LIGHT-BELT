import { reactive } from 'vue'

const BASE = '/api/v1'

export const requestError = reactive({ message: '', path: '' })

export function clearRequestError() {
  requestError.message = ''
  requestError.path = ''
}

async function call(method, path, body) {
  const options = { method, headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined) options.body = JSON.stringify(body)

  let result
  try {
    const response = await fetch(BASE + path, options)
    result = await response.json()
  } catch (_) {
    result = { ok: false, error: { code: 'NETWORK_ERROR', message: '无法连接 Host，请检查服务和网络。' } }
  }

  if (!result.ok) {
    requestError.message = result.error?.message || '请求失败。'
    requestError.path = path
  } else if (requestError.path === path) {
    clearRequestError()
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
