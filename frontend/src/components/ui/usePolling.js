import { ref, onMounted, onUnmounted } from 'vue'
import { buildUrl } from '@/config/api'

/**
 * Polling composable for real-time data updates
 * @param {string} endpoint - API endpoint to poll
 * @param {object} options - Configuration options
 * @param {number} options.interval - Polling interval in ms (default: 5000)
 * @param {boolean} options.immediate - Start polling immediately (default: true)
 */
export function usePolling(endpoint, options = {}) {
  const { interval = 5000, immediate = true } = options

  const data = ref(null)
  const loading = ref(true)
  const error = ref(null)

  let timer = null

  async function fetchData() {
    try {
      const response = await fetch(buildUrl(endpoint))
      if (response.ok) {
        data.value = await response.json()
        error.value = null
      } else {
        error.value = `HTTP ${response.status}`
      }
    } catch (err) {
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  function start() {
    fetchData()
    timer = setInterval(fetchData, interval)
  }

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onMounted(() => {
    if (immediate) {
      start()
    }
  })

  onUnmounted(() => {
    stop()
  })

  return {
    data,
    loading,
    error,
    refresh: fetchData,
    start,
    stop
  }
}

export default usePolling
