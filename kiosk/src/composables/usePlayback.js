import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'

export function usePlayback() {
  const state = ref('idle')
  const show = ref(null)
  const positionMs = ref(0)
  const durationMs = ref(0)
  const brightnessScale = ref(1.0)

  const isPlaying = computed(() => state.value === 'playing')
  const isPaused = computed(() => state.value === 'paused')
  const isActive = computed(() => isPlaying.value || isPaused.value)

  const progress = computed(() => {
    if (!durationMs.value) return 0
    return Math.min(positionMs.value / durationMs.value, 1)
  })

  async function refresh() {
    try {
      const res = await api.playbackState()
      if (!res.ok) return
      const d = res.data
      state.value = d.playback_state ?? 'idle'
      show.value = d.show ?? null
      positionMs.value = d.position_ms ?? 0
      durationMs.value = d.duration_ms ?? 0
      brightnessScale.value = d.brightness_scale ?? 1.0
    } catch (_) {}
  }

  let timer = null
  onMounted(() => {
    refresh()
    timer = setInterval(refresh, 1000)
  })
  onUnmounted(() => clearInterval(timer))

  async function play(show_id) {
    await api.play(show_id, 0)
    await refresh()
  }

  async function pause() {
    if (isPlaying.value) await api.pause()
    else if (isPaused.value) await api.resume()
    await refresh()
  }

  async function stop() {
    await api.stop()
    await refresh()
  }

  async function setBrightness(scale) {
    brightnessScale.value = scale
    await api.setBrightness(scale)
  }

  return { state, show, positionMs, durationMs, brightnessScale, progress, isPlaying, isPaused, isActive, play, pause, stop, setBrightness, refresh }
}
