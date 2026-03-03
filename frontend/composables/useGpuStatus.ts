/**
 * Singleton composable for GPU status polling.
 * Polls /api/system/gpu/status every 5s.
 * Shared state — multiple consumers don't cause double-polling.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createRequest } from '@/api/base'
import type { GpuStatus } from '@/types'

const systemRequest = createRequest('/api/system')

// Module-level shared state
const gpuStatus = ref<GpuStatus | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null
let consumerCount = 0

async function fetchGpuStatus() {
  try {
    gpuStatus.value = await systemRequest<GpuStatus>('/gpu/status')
  } catch {
    // GPU endpoint optional — don't crash
  }
}

function startPolling() {
  if (pollTimer) return
  fetchGpuStatus()
  pollTimer = setInterval(fetchGpuStatus, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

export function useGpuStatus() {
  onMounted(() => {
    consumerCount++
    if (consumerCount === 1) startPolling()
  })

  onUnmounted(() => {
    consumerCount--
    if (consumerCount <= 0) {
      consumerCount = 0
      stopPolling()
    }
  })

  const nvidiaBusy = computed(() => {
    if (!gpuStatus.value?.comfyui) return false
    return gpuStatus.value.comfyui.queue_running > 0 || gpuStatus.value.comfyui.queue_pending > 0
  })

  const comfyQueue = computed(() =>
    gpuStatus.value?.comfyui ?? { queue_running: 0, queue_pending: 0 }
  )

  const ollamaModels = computed(() =>
    gpuStatus.value?.ollama?.loaded_models?.map(m => m.name) ?? []
  )

  return {
    gpuStatus,
    nvidiaBusy,
    comfyQueue,
    ollamaModels,
  }
}
