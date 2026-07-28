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

  onMounted(load)

  return { shows, loading, reload: load }
}
