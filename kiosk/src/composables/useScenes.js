import { ref, onMounted } from 'vue'
import { api } from '../api.js'

export function useScenes() {
  const scenes = ref([])
  const loading = ref(false)
  const applying = ref(null)

  async function load() {
    loading.value = true
    try {
      const res = await api.scenes()
      if (res.ok) scenes.value = res.data.scenes ?? []
    } catch (_) {}
    loading.value = false
  }

  async function applyScene(scene_id) {
    applying.value = scene_id
    try {
      await api.applyScene(scene_id, 500)
    } catch (_) {}
    applying.value = null
  }

  onMounted(load)

  return { scenes, loading, applying, applyScene, reload: load }
}
