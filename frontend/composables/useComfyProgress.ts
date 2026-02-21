import { ref, computed, type Ref, onUnmounted } from 'vue'
import { api } from '@/api/client'

export type FramePackStatus = 'idle' | 'loading' | 'sampling' | 'decoding' | 'done' | 'error'

export function useComfyProgress(
  promptId: Ref<string>,
  samplerNodeId: Ref<string>,
  totalSections: Ref<number>,
) {
  const ws = ref<WebSocket | null>(null)
  const currentSection = ref(0)
  const currentStep = ref(0)
  const stepsPerSection = ref(0)
  const activeNode = ref('')
  const phaseLabel = ref('')
  const status = ref<FramePackStatus>('idle')
  const startTime = ref(0)
  const outputFiles = ref<string[]>([])
  const errorMessage = ref('')

  // Track previous step value for section boundary detection
  let previousStep = 0

  const globalStep = computed(() =>
    currentSection.value * stepsPerSection.value + currentStep.value
  )

  const totalGlobalSteps = computed(() =>
    totalSections.value * stepsPerSection.value
  )

  const percent = computed(() =>
    totalGlobalSteps.value > 0 ? globalStep.value / totalGlobalSteps.value : 0
  )

  const elapsedSeconds = computed(() => {
    if (!startTime.value) return 0
    return Math.round((Date.now() - startTime.value) / 1000)
  })

  const etaSeconds = computed(() => {
    if (globalStep.value === 0 || !startTime.value) return null
    const elapsed = (Date.now() - startTime.value) / 1000
    const rate = elapsed / globalStep.value
    return Math.round((totalGlobalSteps.value - globalStep.value) * rate)
  })

  function connect() {
    if (ws.value) disconnect()

    status.value = 'loading'
    startTime.value = Date.now()
    currentSection.value = 0
    currentStep.value = 0
    stepsPerSection.value = 0
    previousStep = 0
    outputFiles.value = []
    errorMessage.value = ''

    const url = api.comfyWsUrl()
    const socket = new WebSocket(url)
    ws.value = socket

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        handleMessage(msg)
      } catch {
        // Binary or unparseable message — ignore
      }
    }

    socket.onerror = () => {
      status.value = 'error'
      errorMessage.value = 'WebSocket connection error'
    }

    socket.onclose = () => {
      ws.value = null
    }
  }

  function handleMessage(msg: { type: string; data: Record<string, any> }) {
    if (!msg.type || !msg.data) return

    // Only process messages for our prompt
    if (msg.data.prompt_id && msg.data.prompt_id !== promptId.value) return

    switch (msg.type) {
      case 'executing': {
        const nodeId = msg.data.node
        if (!nodeId) {
          // null node means execution complete for this prompt
          if (status.value === 'sampling' || status.value === 'decoding') {
            // Wait for executed message with output
          }
          return
        }
        activeNode.value = nodeId
        // Try to determine phase from the node — ComfyUI doesn't send class_type
        // in executing messages, but we know the sampler node ID
        if (nodeId === samplerNodeId.value) {
          status.value = 'sampling'
          phaseLabel.value = 'Sampling...'
        } else if (status.value === 'sampling' && nodeId !== samplerNodeId.value) {
          // Past the sampler — likely decoding
          status.value = 'decoding'
          phaseLabel.value = 'Decoding video...'
        }
        break
      }

      case 'progress': {
        const { value, max, node } = msg.data
        if (node === samplerNodeId.value || !samplerNodeId.value) {
          // Detect section boundary: value dropped back near 0 after being high
          if (value === 0 && previousStep > max * 0.5 && stepsPerSection.value > 0) {
            currentSection.value++
          }
          currentStep.value = value
          stepsPerSection.value = max
          previousStep = value
          status.value = 'sampling'
          phaseLabel.value = 'Sampling...'
          if (!startTime.value) startTime.value = Date.now()
        }
        break
      }

      case 'executed': {
        const output = msg.data.output
        if (output) {
          const files: string[] = []
          for (const key of ['videos', 'gifs', 'images']) {
            if (output[key]) {
              for (const item of output[key]) {
                if (item.filename) files.push(item.filename)
              }
            }
          }
          if (files.length > 0) {
            outputFiles.value = files
            status.value = 'done'
            disconnect()
          }
        }
        break
      }

      case 'execution_error': {
        status.value = 'error'
        errorMessage.value = msg.data.exception_message || 'Generation failed'
        disconnect()
        break
      }
    }
  }

  function disconnect() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    currentSection,
    currentStep,
    stepsPerSection,
    activeNode,
    phaseLabel,
    status,
    outputFiles,
    errorMessage,
    globalStep,
    totalGlobalSteps,
    percent,
    etaSeconds,
    elapsedSeconds,
    connect,
    disconnect,
  }
}
