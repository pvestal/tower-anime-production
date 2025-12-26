/**
 * Orchestration Store for Animation Production
 * Manages scene generation with real-time progress tracking
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { WebSocketService, ProgressUpdate } from '../services/websocket'
import type { AxiosInstance } from 'axios'
import axios from 'axios'

// API Configuration - domain-agnostic
const API_BASE = import.meta.env.VITE_API_URL || '/api/anime'
const axiosInstance: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Types
export interface SceneGenerationRequest {
  scene_id?: string
  storyline_text: string
  character_ids?: string[]
  conditions: GenerationCondition[]
  output_format?: 'video' | 'image' | 'image_sequence'
  resolution?: [number, number]
  duration_seconds?: number
  fps?: number
  style_preset?: string
  priority?: 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT'
  project_id?: string
  character_id?: string
}

export interface GenerationCondition {
  type: ConditionType
  data: Record<string, any>
  weight?: number
  metadata?: Record<string, any>
}

export enum ConditionType {
  TEXT_PROMPT = 'TEXT_PROMPT',
  CHARACTER_IDENTITY = 'CHARACTER_IDENTITY',
  POSE_CONTROL = 'POSE_CONTROL',
  CAMERA_MOTION = 'CAMERA_MOTION',
  STYLE_REFERENCE = 'STYLE_REFERENCE',
  EMOTION_EXPRESSION = 'EMOTION_EXPRESSION',
  SCENE_CONTEXT = 'SCENE_CONTEXT',
  TEMPORAL_CONSISTENCY = 'TEMPORAL_CONSISTENCY'
}

export interface GenerationJob {
  job_id: string
  status: string
  progress: number
  current_step?: string
  created_at: string
  started_at?: string
  completed_at?: string
  error?: string
  result?: any
  scene_request?: SceneGenerationRequest
}

export interface CharacterReference {
  character_id: string
  name: string
  description: string
  reference_images: string[]
  embedding_ids: string[]
  visual_traits: Record<string, any>
  style_preferences: string[]
}

export interface SemanticSearchResult {
  id: string
  score: number
  type: string
  metadata: Record<string, any>
  preview_url?: string
}

export const useOrchestrationStore = defineStore('orchestration', () => {
  // State
  const activeJobs = ref<Map<string, GenerationJob>>(new Map())
  const completedJobs = ref<GenerationJob[]>([])
  const characterLibrary = ref<CharacterReference[]>([])
  const searchResults = ref<SemanticSearchResult[]>([])
  const selectedCharacter = ref<CharacterReference | null>(null)
  const selectedConditions = ref<GenerationCondition[]>([])
  const isGenerating = ref(false)
  const isSearching = ref(false)
  const error = ref<string | null>(null)
  const currentJobId = ref<string | null>(null)
  const wsService = ref<WebSocketService | null>(null)
  const queueStatus = ref({
    queue_size: 0,
    processing_count: 0,
    max_concurrent: 3,
    worker_count: 2
  })

  // Computed
  const activeJobsList = computed(() => {
    return Array.from(activeJobs.value.values())
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  })

  const currentJob = computed(() => {
    return currentJobId.value ? activeJobs.value.get(currentJobId.value) : null
  })

  const isProcessing = computed(() => {
    return activeJobsList.value.some(job =>
      job.status === 'processing' || job.status === 'executing'
    )
  })

  // Actions
  async function generateScene(request: SceneGenerationRequest): Promise<string> {
    isGenerating.value = true
    error.value = null

    try {
      // Add selected character if available
      if (selectedCharacter.value && !request.character_ids?.includes(selectedCharacter.value.character_id)) {
        request.character_ids = [...(request.character_ids || []), selectedCharacter.value.character_id]

        // Add character identity condition
        const hasCharacterCondition = request.conditions.some(
          c => c.type === ConditionType.CHARACTER_IDENTITY
        )

        if (!hasCharacterCondition && selectedCharacter.value.reference_images.length > 0) {
          request.conditions.push({
            type: ConditionType.CHARACTER_IDENTITY,
            data: {
              reference_image: selectedCharacter.value.reference_images[0],
              character_name: selectedCharacter.value.name
            },
            weight: 1.0
          })
        }
      }

      // Add selected conditions
      for (const condition of selectedConditions.value) {
        if (!request.conditions.some(c => c.type === condition.type)) {
          request.conditions.push(condition)
        }
      }

      // Submit generation request
      const response = await axiosInstance.post('/api/anime/orchestration/generate', request)
      const { job_id } = response.data

      // Create job entry
      const job: GenerationJob = {
        job_id,
        status: 'queued',
        progress: 0,
        created_at: new Date().toISOString(),
        scene_request: request
      }

      activeJobs.value.set(job_id, job)
      currentJobId.value = job_id

      // Connect WebSocket for real-time updates
      await connectWebSocket(job_id)

      return job_id

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Generation failed'
      error.value = message
      throw err
    } finally {
      isGenerating.value = false
    }
  }

  async function connectWebSocket(jobId: string) {
    // Disconnect existing connection
    if (wsService.value) {
      wsService.value.disconnect()
    }

    // Create new WebSocket service - domain-agnostic URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    wsService.value = new WebSocketService({
      url: `${protocol}//${window.location.host}/api/anime/ws`
    })

    // Set up event listeners
    wsService.value.on('progress', (update: ProgressUpdate) => {
      updateJobProgress(update)
    })

    wsService.value.on('complete', (data: any) => {
      handleJobComplete(data)
    })

    wsService.value.on('error', (data: any) => {
      console.error('WebSocket error:', data)
      error.value = data.error || 'Connection error'
    })

    // Try WebSocket first, fall back to SSE
    try {
      await wsService.value.connect(jobId)
    } catch (err) {
      console.warn('WebSocket connection failed, trying SSE...', err)
      wsService.value.connectSSE(jobId)
    }
  }

  function updateJobProgress(update: ProgressUpdate) {
    const job = activeJobs.value.get(update.job_id)
    if (job) {
      job.status = update.status
      job.progress = update.progress
      job.current_step = update.current_step

      if (update.error) {
        job.error = update.error
      }

      if (update.result) {
        job.result = update.result
      }

      // Force reactivity update
      activeJobs.value.set(update.job_id, { ...job })
    }
  }

  function handleJobComplete(data: any) {
    const job = activeJobs.value.get(data.job_id)
    if (job) {
      job.status = data.status
      job.completed_at = new Date().toISOString()

      if (data.status === 'completed') {
        job.progress = 100
        // Move to completed list
        completedJobs.value.unshift(job)
        activeJobs.value.delete(data.job_id)
      }

      // Clear current job if it's the one that completed
      if (currentJobId.value === data.job_id) {
        currentJobId.value = null
      }
    }

    // Disconnect WebSocket
    if (wsService.value) {
      wsService.value.disconnect()
      wsService.value = null
    }
  }

  async function searchBySemantic(query: string, limit: number = 10): Promise<void> {
    isSearching.value = true
    error.value = null

    try {
      const response = await axiosInstance.get('/api/anime/vector/search', {
        params: { query, limit }
      })

      searchResults.value = response.data.results.map((result: any) => ({
        id: result.id || result.generation_id,
        score: result.score,
        type: result.type || 'character',
        metadata: result.metadata || {
          character_name: result.character_name,
          prompt: result.prompt,
          checkpoint: result.checkpoint
        },
        preview_url: result.image_url
      }))

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Search failed'
      error.value = message
      console.error('Semantic search error:', err)
    } finally {
      isSearching.value = false
    }
  }

  async function loadCharacterLibrary(): Promise<void> {
    try {
      const response = await axiosInstance.get('/api/anime/characters/library')
      characterLibrary.value = response.data.characters || []
    } catch (err) {
      console.error('Failed to load character library:', err)
    }
  }

  async function selectCharacterBySearch(resultId: string): Promise<void> {
    const result = searchResults.value.find(r => r.id === resultId)
    if (!result) return

    // Try to find in library first
    const libraryChar = characterLibrary.value.find(
      c => c.character_id === resultId || c.name === result.metadata.character_name
    )

    if (libraryChar) {
      selectedCharacter.value = libraryChar
    } else {
      // Create temporary character reference from search result
      selectedCharacter.value = {
        character_id: resultId,
        name: result.metadata.character_name || 'Unknown',
        description: result.metadata.prompt || '',
        reference_images: result.preview_url ? [result.preview_url] : [],
        embedding_ids: [],
        visual_traits: {},
        style_preferences: []
      }
    }
  }

  function addCondition(condition: GenerationCondition): void {
    // Remove existing condition of same type
    selectedConditions.value = selectedConditions.value.filter(
      c => c.type !== condition.type
    )
    selectedConditions.value.push(condition)
  }

  function removeCondition(type: ConditionType): void {
    selectedConditions.value = selectedConditions.value.filter(
      c => c.type !== type
    )
  }

  function clearConditions(): void {
    selectedConditions.value = []
  }

  async function getJobStatus(jobId: string): Promise<GenerationJob | null> {
    try {
      const response = await axiosInstance.get(`/api/anime/orchestration/job/${jobId}`)
      const job = response.data

      // Update local state
      if (job.status === 'completed') {
        if (activeJobs.value.has(jobId)) {
          completedJobs.value.unshift(job)
          activeJobs.value.delete(jobId)
        }
      } else {
        activeJobs.value.set(jobId, job)
      }

      return job
    } catch (err) {
      console.error('Failed to get job status:', err)
      return null
    }
  }

  async function cancelJob(jobId: string): Promise<boolean> {
    try {
      await axiosInstance.post(`/api/anime/orchestration/job/${jobId}/cancel`)

      const job = activeJobs.value.get(jobId)
      if (job) {
        job.status = 'cancelled'
        activeJobs.value.delete(jobId)
      }

      if (currentJobId.value === jobId) {
        currentJobId.value = null
        if (wsService.value) {
          wsService.value.disconnect()
          wsService.value = null
        }
      }

      return true
    } catch (err) {
      console.error('Failed to cancel job:', err)
      return false
    }
  }

  async function updateQueueStatus(): Promise<void> {
    try {
      const response = await axiosInstance.get('/api/anime/orchestration/queue/status')
      queueStatus.value = response.data
    } catch (err) {
      console.error('Failed to update queue status:', err)
    }
  }

  function clearError(): void {
    error.value = null
  }

  // Cleanup on unmount
  function cleanup(): void {
    if (wsService.value) {
      wsService.value.disconnect()
      wsService.value = null
    }
  }

  return {
    // State
    activeJobs: computed(() => activeJobs.value),
    activeJobsList,
    completedJobs: computed(() => completedJobs.value),
    characterLibrary: computed(() => characterLibrary.value),
    searchResults: computed(() => searchResults.value),
    selectedCharacter: computed(() => selectedCharacter.value),
    selectedConditions: computed(() => selectedConditions.value),
    isGenerating: computed(() => isGenerating.value),
    isSearching: computed(() => isSearching.value),
    error: computed(() => error.value),
    currentJob,
    currentJobId: computed(() => currentJobId.value),
    isProcessing,
    queueStatus: computed(() => queueStatus.value),

    // Actions
    generateScene,
    searchBySemantic,
    loadCharacterLibrary,
    selectCharacterBySearch,
    addCondition,
    removeCondition,
    clearConditions,
    getJobStatus,
    cancelJob,
    updateQueueStatus,
    clearError,
    cleanup
  }
})