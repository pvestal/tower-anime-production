/**
 * Singleton composable for GPU status polling.
 * Polls /api/system/gpu/status every 5s (includes arbiter data).
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
    gpuStatus.value?.ollama?.loaded_models ?? []
  )

  // Ollama models on NVIDIA (partial or full offload)
  const ollamaNvidiaModels = computed(() =>
    ollamaModels.value
      .filter(m => m.gpu === 'nvidia' || m.gpu === 'nvidia_partial')
      .map(m => m.name)
  )

  // Ollama models on CPU only
  const ollamaCpuModels = computed(() =>
    ollamaModels.value
      .filter(m => m.gpu === 'cpu')
      .map(m => m.name)
  )

  // NVIDIA VRAM percentage
  const nvidiaUsedPct = computed(() => {
    const n = gpuStatus.value?.nvidia
    if (!n || !n.total_mb) return 0
    return Math.round((n.used_mb / n.total_mb) * 100)
  })

  // AMD VRAM percentage
  const amdUsedPct = computed(() => {
    const a = gpuStatus.value?.amd
    if (!a || !a.total_mb) return 0
    return Math.round((a.used_mb / a.total_mb) * 100)
  })

  // AMD busy state (ComfyUI-ROCm or vision)
  const amdBusy = computed(() => {
    const arb = gpuStatus.value?.arbiter
    if (!arb) return false
    return arb.comfyui_rocm.busy || arb.vision_model.warm || Object.keys(arb.claims).length > 0
  })

  // What's actively using each GPU
  const nvidiaServices = computed(() => {
    const services: string[] = []
    const cq = comfyQueue.value
    if (cq.queue_running > 0) services.push('ComfyUI')
    if (cq.queue_pending > 0) services.push(`${cq.queue_pending}Q`)
    return services
  })

  const amdServices = computed(() => {
    const services: string[] = []
    const arb = gpuStatus.value?.arbiter
    if (!arb) return services
    if (arb.comfyui_rocm.busy) services.push('ComfyUI-ROCm')
    // Only show models actually using AMD VRAM (none with HIP_VISIBLE_DEVICES=-1)
    for (const c of Object.values(arb.claims)) {
      services.push(c.type)
    }
    return services
  })

  return {
    gpuStatus,
    nvidiaBusy,
    comfyQueue,
    ollamaModels,
    ollamaNvidiaModels,
    ollamaCpuModels,
    nvidiaUsedPct,
    amdUsedPct,
    amdBusy,
    nvidiaServices,
    amdServices,
  }
}
