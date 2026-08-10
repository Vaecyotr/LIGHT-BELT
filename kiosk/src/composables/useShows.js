import { ref, onMounted } from 'vue'
import { api } from '../api.js'

export function useShows() {
  const shows = ref([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const res = await api.shows()
      if (res.ok) shows.value = res.data.shows ?? []
    } catch (_) {}
    loading.value = false
  }

  const DEMO_SHOW = { show_id: 'demo', name: 'Demo', description: '（暂无节目）', duration_ms: 0 }

  onMounted(load)

  return { shows, loading, reload: load, DEMO_SHOW }
}
