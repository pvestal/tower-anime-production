import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  interactiveApi,
  type DirectorResult,
  type DirectorConversation,
  type InteractiveScene,
  type InteractiveImageStatus,
} from '@/api/interactive'

export interface ChatMessage {
  id: number
  role: 'user' | 'director' | 'system'
  text: string
  suggestions?: string[]
  scene?: InteractiveScene & { director_note?: string }
  timestamp: number
}

export interface PipelineStep {
  label: string
  status: 'pending' | 'active' | 'done'
  timestamp: number
}

export const useDirectorStore = defineStore('director', () => {
  // Session
  const sessionId = ref<string | null>(null)
  const projectId = ref<number | null>(null)
  const projectName = ref('')
  const characters = ref<{ name: string; slug: string; role: string }[]>([])
  const isEnded = ref(false)

  // Chat
  const messages = ref<ChatMessage[]>([])
  let nextMsgId = 1

  // Scenes & images
  const currentScene = ref<(InteractiveScene & { director_note?: string }) | null>(null)
  const sceneHistory = ref<InteractiveScene[]>([])
  const imageStatus = ref<InteractiveImageStatus>({ status: 'pending', progress: 0, url: null })
  const relationships = ref<Record<string, number>>({})
  const preferences = ref<Record<string, string>>({})

  // Pipeline
  const pipelineSteps = ref<PipelineStep[]>([])

  // UI
  const loading = ref(false)
  const thinking = ref(false)
  const error = ref<string | null>(null)

  // SSE
  let eventSource: EventSource | null = null
  let imagePollingTimer: ReturnType<typeof setInterval> | null = null

  // Computed
  const isPlaying = computed(() => sessionId.value !== null && !isEnded.value)
  const sceneCount = computed(() => sceneHistory.value.length)
  const hasScene = computed(() => currentScene.value !== null)

  // --- Actions ---

  async function startSession(pid: number, characterSlugs?: string[]) {
    loading.value = true
    error.value = null
    try {
      const resp = await interactiveApi.startDirectorSession(pid, characterSlugs)
      sessionId.value = resp.session_id
      projectId.value = pid
      projectName.value = resp.project_name
      characters.value = resp.characters
      isEnded.value = false
      messages.value = []
      sceneHistory.value = []
      currentScene.value = null
      relationships.value = {}
      preferences.value = {}

      // Add greeting
      addDirectorMessage(resp.greeting)

      // Connect SSE
      connectSSE(resp.session_id)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start session'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function sendMessage(text: string) {
    if (!sessionId.value || thinking.value) return
    thinking.value = true
    error.value = null

    // Add user message
    addMessage('user', text)
    setPipeline([{ label: 'Processing...', status: 'active', timestamp: Date.now() }])

    try {
      const resp = await interactiveApi.sendMessage(sessionId.value, text)
      handleDirectorResult(resp.result, resp)
      isEnded.value = resp.session_ended
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to send message'
      addMessage('system', 'Something went wrong. Try again.')
    } finally {
      thinking.value = false
      setPipeline([])
    }
  }

  async function submitChoice(choiceIndex: number) {
    if (!sessionId.value || thinking.value) return
    thinking.value = true
    error.value = null

    const scene = currentScene.value
    const choiceText = scene?.choices?.[choiceIndex]?.text || `Choice ${choiceIndex + 1}`
    addMessage('user', choiceText)
    setPipeline([{ label: 'Processing choice...', status: 'active', timestamp: Date.now() }])

    try {
      const resp = await interactiveApi.directorChoose(sessionId.value, choiceIndex)
      handleDirectorResult(resp.result, resp)
      isEnded.value = resp.session_ended
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to submit choice'
    } finally {
      thinking.value = false
      setPipeline([])
    }
  }

  async function editScene(sceneIndex: number, field: string, value: string) {
    if (!sessionId.value) return
    try {
      const resp = await interactiveApi.editScene(sessionId.value, sceneIndex, field, value)
      if (resp.result.regenerating_image && resp.image) {
        imageStatus.value = resp.image
        startImagePolling(sceneIndex)
      }
      addMessage('system', `Updated ${field} for scene ${sceneIndex + 1}`)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to edit scene'
    }
  }

  async function endSession() {
    if (sessionId.value) {
      try {
        await interactiveApi.endDirectorSession(sessionId.value)
      } catch { /* ignore */ }
    }
    disconnectSSE()
    stopImagePolling()
    resetState()
  }

  function resetState() {
    disconnectSSE()
    stopImagePolling()
    sessionId.value = null
    projectId.value = null
    projectName.value = ''
    characters.value = []
    isEnded.value = false
    messages.value = []
    currentScene.value = null
    sceneHistory.value = []
    imageStatus.value = { status: 'pending', progress: 0, url: null }
    relationships.value = {}
    preferences.value = {}
    pipelineSteps.value = []
    error.value = null
    thinking.value = false
    loading.value = false
    nextMsgId = 1
  }

  // --- Helpers ---

  function handleDirectorResult(result: DirectorResult, resp?: any) {
    if (result.type === 'conversation') {
      addDirectorMessage(result as DirectorConversation)
    } else if (result.type === 'scene') {
      const sceneResult = result as { type: 'scene'; scene: InteractiveScene & { director_note?: string }; director_note: string }
      currentScene.value = sceneResult.scene
      sceneHistory.value.push(sceneResult.scene)

      addMessage('director', sceneResult.director_note || 'A new scene unfolds...', {
        scene: sceneResult.scene,
      })

      if (resp?.image) {
        imageStatus.value = resp.image
        startImagePolling(sceneResult.scene.scene_index)
      }
      if (resp?.relationships) {
        relationships.value = resp.relationships
      }
    } else if (result.type === 'error') {
      addMessage('system', (result as { type: 'error'; message: string }).message)
    }
  }

  function addDirectorMessage(conv: DirectorConversation) {
    addMessage('director', conv.message, { suggestions: conv.suggestions })
    if (conv.detected_preferences) {
      for (const pref of conv.detected_preferences) {
        if (pref.key && pref.value) {
          preferences.value[pref.key] = pref.value
        }
      }
    }
  }

  function addMessage(role: ChatMessage['role'], text: string, extra?: Partial<ChatMessage>) {
    messages.value.push({
      id: nextMsgId++,
      role,
      text,
      timestamp: Date.now(),
      ...extra,
    })
  }

  function setPipeline(steps: PipelineStep[]) {
    pipelineSteps.value = steps
  }

  // --- SSE ---

  function connectSSE(sid: string) {
    disconnectSSE()
    const url = interactiveApi.directorEventsUrl(sid)
    eventSource = new EventSource(url)

    eventSource.addEventListener('thinking', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      setPipeline([{ label: data.step, status: 'active', timestamp: Date.now() }])
    })

    eventSource.addEventListener('director_message', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      if (data.message) {
        addMessage('director', data.message, { suggestions: data.suggestions })
      }
    })

    eventSource.addEventListener('scene_ready', (e: MessageEvent) => {
      const scene = JSON.parse(e.data)
      // Scene data arrives via SSE — update if we haven't already
      if (!currentScene.value || currentScene.value.scene_index !== scene.scene_index) {
        currentScene.value = scene
        sceneHistory.value.push(scene)
      }
    })

    eventSource.addEventListener('image_status', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      imageStatus.value = { ...imageStatus.value, status: data.status }
    })

    eventSource.addEventListener('echo_brain', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      addMessage('system', `Echo Brain: ${data.step}`)
    })

    eventSource.addEventListener('preference_saved', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      preferences.value[data.key] = data.value
    })

    eventSource.onerror = () => {
      // SSE reconnects automatically, no need to handle
    }
  }

  function disconnectSSE() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  // --- Image polling ---

  function startImagePolling(sceneIdx: number) {
    stopImagePolling()
    if (!sessionId.value) return
    if (imageStatus.value.status === 'ready') return

    const sid = sessionId.value
    imagePollingTimer = setInterval(async () => {
      try {
        const status = await interactiveApi.getImageStatus(sid, sceneIdx)
        imageStatus.value = status
        if (status.status === 'ready' || status.status === 'failed') {
          stopImagePolling()
        }
      } catch {
        stopImagePolling()
      }
    }, 2000)
  }

  function stopImagePolling() {
    if (imagePollingTimer) {
      clearInterval(imagePollingTimer)
      imagePollingTimer = null
    }
  }

  return {
    // State
    sessionId, projectId, projectName, characters, isEnded,
    messages, currentScene, sceneHistory, imageStatus,
    relationships, preferences, pipelineSteps,
    loading, thinking, error,
    // Computed
    isPlaying, sceneCount, hasScene,
    // Actions
    startSession, sendMessage, submitChoice, editScene,
    endSession, resetState,
  }
})
