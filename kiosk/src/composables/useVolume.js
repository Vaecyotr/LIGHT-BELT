import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'

export function useVolume() {
  const volume = ref(1.0)
  const muted = ref(false)

  async function refresh() {
    try {
      const res = await api.playbackState()
      if (!res.ok) return
      volume.value = res.data.audio?.volume ?? 1.0
      muted.value = res.data.audio?.muted ?? false
    } catch (_) {}
  }

  async function setVolume(v) {
    const result = await api.setVolume(v)
    if (result.ok) volume.value = result.data.volume ?? v
    else await refresh()
  }

  async function toggleMute() {
    const result = await api.setMuted(!muted.value)
    if (result.ok) muted.value = result.data.muted ?? !muted.value
  }

  let timer = null
  onMounted(() => { refresh(); timer = setInterval(refresh, 3000) })
  onUnmounted(() => clearInterval(timer))

  return { volume, muted, setVolume, toggleMute, refresh }
}
