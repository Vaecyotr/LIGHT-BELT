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
    volume.value = v
    await api.setVolume(v)
  }

  async function toggleMute() {
    muted.value = !muted.value
    await api.setMuted(muted.value)
  }

  let timer = null
  onMounted(() => { refresh(); timer = setInterval(refresh, 3000) })
  onUnmounted(() => clearInterval(timer))

  return { volume, muted, setVolume, toggleMute }
}
