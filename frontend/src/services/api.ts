/**
 * Tower Anime Production API Service Layer
 * Standardized API endpoints following /api/anime/* pattern
 */

import axios, { AxiosInstance, AxiosResponse } from 'axios'

// Base configuration - domain-agnostic URLs
const API_BASE = import.meta.env.VITE_API_URL || '/api/anime'
// Build WebSocket URL dynamically based on current protocol and host
const wsPath = import.meta.env.VITE_WS_URL || '/api/anime/ws'
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS_BASE = `${wsProtocol}//${window.location.host}${wsPath}`

// Types
export interface GenerationRequest {
  character_name: string
  prompt: string
  negative_prompt?: string
  content_type?: 'sfw' | 'nsfw' | 'artistic'
  generation_type?: 'single_image' | 'turnaround' | 'pose_sheet' | 'expression_sheet' | 'animation'
  model_name?: string
  seed?: number
  num_images?: number
  width?: number
  height?: number
  steps?: number
  cfg_scale?: number
}

export interface GenerationResponse {
  generation_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  message?: string
  outputs?: string[]
  metadata?: Record<string, any>
}

export interface SearchResult {
  id: number
  score: number
  character_name: string
  prompt: string
  job_id?: string
  checkpoint?: string
  created_at: string
}

export interface JobStatus {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress?: number
  message?: string
  result?: any
  error?: string
  created_at: string
  updated_at: string
}

export interface BatchRequest {
  character_id: number
  batch_type: 'poses' | 'expressions' | 'outfits'
  count?: number
  nsfw?: boolean
}

export interface VectorIndexRequest {
  character_id: number
  character_name: string
  prompt: string
  metadata?: Record<string, any>
}

// Create axios instance with defaults
const axiosInstance: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Add request interceptor for auth token if needed
axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Add response interceptor for error handling
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * Main API Service
 */
export const api = {
  // ==================== Character Generation ====================
  character: {
    // Generate new character
    generate: (data: GenerationRequest): Promise<AxiosResponse<GenerationResponse>> =>
      axiosInstance.post('/character/v2/generate', data),

    // Get character generation by ID
    getGeneration: (generationId: string) =>
      axiosInstance.get(`/character/v2/generation/${generationId}`),

    // Get all generations for a character
    getGenerations: (characterName: string) =>
      axiosInstance.get(`/character/v2/character/${characterName}/generations`),

    // Generate batch
    generateBatch: (data: GenerationRequest & { batch_size: number }) =>
      axiosInstance.post('/character/v2/generate-batch', data),

    // List all characters
    list: () =>
      axiosInstance.get('/character/list'),

    // Get character details
    getDetails: (characterId: number) =>
      axiosInstance.get(`/character/${characterId}`),

    // Get character image
    getImage: (characterId: number) =>
      axiosInstance.get(`/character/${characterId}/image`, { responseType: 'blob' })
  },

  // ==================== Vector Search ====================
  vector: {
    // Semantic search
    search: (query: string, limit: number = 10): Promise<AxiosResponse<{ results: SearchResult[] }>> =>
      axiosInstance.get('/vector/search', { params: { q: query, limit } }),

    // Find similar characters
    findSimilar: (characterId: number, limit: number = 10) =>
      axiosInstance.get(`/vector/similar/${characterId}`, { params: { limit } }),

    // Index character to vector DB
    index: (data: VectorIndexRequest) =>
      axiosInstance.post('/vector/index', data),

    // Delete from vector DB
    deleteVector: (characterId: number) =>
      axiosInstance.delete(`/vector/character/${characterId}`),

    // Get collection info
    getCollectionInfo: () =>
      axiosInstance.get('/vector/collection/info'),

    // Sync database
    syncDatabase: () =>
      axiosInstance.post('/vector/sync-database')
  },

  // ==================== Batch Operations ====================
  batch: {
    // Quick test generation
    quickTest: (characterId: number) =>
      axiosInstance.post(`/batch/quick-test/${characterId}`),

    // Generate all poses
    generatePoses: (characterId: number) =>
      axiosInstance.post(`/batch/generate-all-poses/${characterId}`),

    // NSFW batch generation
    generateNSFW: (data: BatchRequest) =>
      axiosInstance.post('/batch/nsfw-batch-generate', data),

    // Mass production
    massProduction: (characterId: number, count: number) =>
      axiosInstance.post(`/batch/mass-production/${characterId}`, { count }),

    // Get optimal settings
    getOptimalSettings: (contentType: string) =>
      axiosInstance.get(`/batch/optimal-settings/${contentType}`),

    // Get batch statistics
    getStats: () =>
      axiosInstance.get('/batch/quick-stats'),

    // Get model recommendations
    getModelRecommendations: () =>
      axiosInstance.get('/batch/model-recommendations')
  },

  // ==================== Animation ====================
  animation: {
    // Generate animation
    generate: (data: any) =>
      axiosInstance.post('/animation/generate', data),

    // Generate lip sync
    generateLipSync: (data: any) =>
      axiosInstance.post('/animation/lip-sync', data),

    // Generate pose sequence
    generatePoseSequence: (data: any) =>
      axiosInstance.post('/animation/pose-sequence', data),

    // Get animation sequences
    getSequences: (characterId: number) =>
      axiosInstance.get(`/animation/sequences/${characterId}`),

    // Get animation templates
    getTemplates: () =>
      axiosInstance.get('/animation/templates'),

    // Get animation status
    getStatus: (animationId: string) =>
      axiosInstance.get(`/animation/status/${animationId}`),

    // Delete animation
    deleteSequence: (animationId: string) =>
      axiosInstance.delete(`/animation/sequences/${animationId}`)
  },

  // ==================== Jobs & Status ====================
  jobs: {
    // Get job status
    getStatus: (jobId: string): Promise<AxiosResponse<JobStatus>> =>
      axiosInstance.get(`/jobs/${jobId}`),

    // Get job progress
    getProgress: (jobId: string) =>
      axiosInstance.get(`/jobs/${jobId}/progress`),

    // List all jobs
    list: () =>
      axiosInstance.get('/jobs'),

    // Cancel job
    cancel: (jobId: string) =>
      axiosInstance.post(`/generation/${jobId}/cancel`),

    // Retry failed job
    retry: (jobId: string) =>
      axiosInstance.post(`/error-recovery/jobs/${jobId}/retry`),

    // Get queue status
    getQueueStatus: () =>
      axiosInstance.get('/redis/queue/status')
  },

  // ==================== Projects & Episodes ====================
  projects: {
    // List projects
    list: () =>
      axiosInstance.get('/projects'),

    // Create project
    create: (data: any) =>
      axiosInstance.post('/projects', data),

    // Get project details
    get: (projectId: string) =>
      axiosInstance.get(`/projects/${projectId}`),

    // Delete project
    delete: (projectId: string) =>
      axiosInstance.delete(`/projects/${projectId}`),

    // Get project bible
    getBible: (projectId: string) =>
      axiosInstance.get(`/projects/${projectId}/bible`),

    // Update project bible
    updateBible: (projectId: string, data: any) =>
      axiosInstance.put(`/projects/${projectId}/bible`, data),

    // Generate from project
    generate: (projectId: string, data: any) =>
      axiosInstance.post(`/projects/${projectId}/generate`, data),

    // Get project history
    getHistory: (projectId: string) =>
      axiosInstance.get(`/projects/${projectId}/history`)
  },

  // ==================== Quality Control ====================
  quality: {
    // Assess quality
    assess: (data: any) =>
      axiosInstance.post('/quality/assess', data),

    // Assess current image
    assessCurrentImage: (data: any) =>
      axiosInstance.post('/quality/assess-current-image', data),

    // Get quality standards
    getStandards: () =>
      axiosInstance.get('/quality/standards'),

    // Get quality status
    getStatus: () =>
      axiosInstance.get('/quality/status')
  },

  // ==================== Music Integration ====================
  music: {
    // Analyze video for music
    analyzeVideo: (data: any) =>
      axiosInstance.post('/music/analyze-video', data),

    // Analyze music track
    analyzeTrack: (data: any) =>
      axiosInstance.post('/music/analyze-track', data),

    // Generate sync config
    generateConfig: (data: any) =>
      axiosInstance.post('/music-sync/generate-config', data),

    // Create video with music
    createVideo: (data: any) =>
      axiosInstance.post('/music-sync/create-video', data),

    // Get sync status
    getSyncStatus: (taskId: string) =>
      axiosInstance.get(`/music-sync/status/${taskId}`)
  },

  // ==================== System & Health ====================
  system: {
    // Health check
    health: () =>
      axiosInstance.get('/health'),

    // Get system status
    getStatus: () =>
      axiosInstance.get('/status'),

    // Get orchestration status
    getOrchestrationStatus: () =>
      axiosInstance.get('/orchestration/status'),

    // Get admin stats
    getAdminStats: () =>
      axiosInstance.get('/admin/stats'),

    // Emergency stop
    emergencyStop: () =>
      axiosInstance.post('/error-recovery/emergency-stop'),

    // Cleanup
    cleanup: () =>
      axiosInstance.delete('/error-recovery/cleanup')
  }
}

/**
 * WebSocket Service for real-time updates
 */
export class WebSocketService {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 3000
  private listeners: Map<string, Set<Function>> = new Map()

  constructor(private generationId?: string) {
    if (generationId) {
      this.connect(generationId)
    }
  }

  connect(generationId: string) {
    const wsUrl = `${WS_BASE}/generation/${generationId}`

    try {
      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        console.log('WebSocket connected:', generationId)
        this.reconnectAttempts = 0
        this.emit('connected', { generationId })
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          this.handleMessage(data)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        this.emit('error', error)
      }

      this.ws.onclose = () => {
        console.log('WebSocket disconnected')
        this.emit('disconnected', {})
        this.attemptReconnect(generationId)
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      this.attemptReconnect(generationId)
    }
  }

  private attemptReconnect(generationId: string) {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)

      setTimeout(() => {
        this.connect(generationId)
      }, this.reconnectDelay)
    } else {
      console.error('Max reconnection attempts reached')
      this.emit('reconnect_failed', {})
    }
  }

  private handleMessage(data: any) {
    const { type, payload } = data

    switch (type) {
      case 'progress':
        this.emit('progress', payload)
        break

      case 'status':
        this.emit('status', payload)
        break

      case 'completed':
        this.emit('completed', payload)
        break

      case 'error':
        this.emit('error', payload)
        break

      case 'log':
        this.emit('log', payload)
        break

      default:
        this.emit('message', data)
    }
  }

  on(event: string, callback: Function) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(callback)
  }

  off(event: string, callback: Function) {
    const eventListeners = this.listeners.get(event)
    if (eventListeners) {
      eventListeners.delete(callback)
    }
  }

  private emit(event: string, data: any) {
    const eventListeners = this.listeners.get(event)
    if (eventListeners) {
      eventListeners.forEach(callback => callback(data))
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    } else {
      console.error('WebSocket is not connected')
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}

export default api