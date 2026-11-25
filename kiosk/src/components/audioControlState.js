export const SNAPSHOT_MAX_AGE_MS = 5000

export function isControlSnapshotFresh(capturedAt, now = Date.now(), maxAge = SNAPSHOT_MAX_AGE_MS) {
  return Number.isFinite(capturedAt) && capturedAt <= now && now - capturedAt <= maxAge
}

export function challengeInputRequired(challenge) {
  return ['pin', 'pin_code', 'passkey'].includes(challenge?.kind)
}

export function describeOperation(operation, device = {}) {
  const status = operation?.state
  if (status === 'succeeded') return device.paired ? '已配对' : '配对请求已受理，等待设备确认'
  if (status === 'failed') return `配对失败${operation.reason ? `：${operation.reason}` : ''}`
  if (status === 'cancelled') return '配对已取消'
  if (status === 'waiting_user') return '等待右屏确认'
  if (status === 'running') return '正在配对'
  return '等待配对结果'
}

export function speakerDescription(speaker = {}) {
  if (speaker.status === 'fault') return '音响路由异常'
  if (speaker.status === 'waiting') {
    const audible = speaker.kind === 'phone' ? `手机 ${speaker.name || speaker.device}`
      : speaker.kind === 'program' ? (speaker.user_muted ? '节目已静音' : '节目原声') : '当前无声'
    return `${audible} · 等待 ${speaker.waiting_for || speaker.name || speaker.device} 开始播放`
  }
  if (speaker.status === 'routed' || speaker.kind === 'phone') {
    return `手机 ${speaker.name || speaker.device} 正在播放`
  }
  if (speaker.kind === 'program') return speaker.user_muted ? '节目已静音' : '节目原声'
  return '当前无声'
}
