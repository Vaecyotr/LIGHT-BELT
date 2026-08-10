const BASE = '/api/v1'

async function call(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opts)
  const json = await res.json()
  return json
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
