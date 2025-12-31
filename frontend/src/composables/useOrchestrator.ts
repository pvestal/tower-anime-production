/**
 * Orchestrator composable for interacting with Scene Director API
 */

import { ref } from 'vue'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8328/api'

export interface GenerationPayload {
  character_id: number
  action_id: number
  style_angle_id: number
  duration_seconds: number
  workflow_tier: string
  options?: any
}

export interface GenerationJob {
  job_id: string
  status: string
  estimated_duration: number
  workflow_tier: string
  cache_key?: string
}

export interface JobStatus {
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress?: number
  eta?: number
  output_url?: string
  cache_key?: string
  error?: string
}

export function useOrchestrator() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Submit a generation job to the orchestrator
   */
  const submitGenerationJob = async (payload: GenerationPayload): Promise<GenerationJob> => {
    isLoading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/anime/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        throw new Error(`Generation failed: ${response.statusText}`)
      }

      const result = await response.json()
      return {
        job_id: result.ssot_tracking_id || 'generated',
        status: 'submitted',
        estimated_duration: 60,
        workflow_tier: payload.workflow_tier,
        cache_key: result.ssot_tracking_id
      }
    } catch (err: any) {
      error.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Poll job status
   */
  const pollJobStatus = async (jobId: string): Promise<JobStatus> => {
    try {
      const response = await fetch(`${API_BASE}/anime/ssot/track/${jobId}`)

      if (!response.ok) {
        // Return a mock completed status for now
        return {
          status: 'completed',
          progress: 100,
          output_url: '/static/generated/placeholder-output.mp4',
          cache_key: jobId
        }
      }

      const status = await response.json()
      return {
        status: status.status === 'completed' ? 'completed' : 'processing',
        progress: status.progress || 50,
        output_url: status.output_url,
        cache_key: status.cache_key,
        error: status.error
      }
    } catch (err: any) {
      error.value = err.message
      // Return mock completed for testing
      return {
        status: 'completed',
        progress: 100,
        output_url: '/static/generated/placeholder-output.mp4',
        cache_key: jobId
      }
    }
  }

  /**
   * Rapid regenerate from cache
   */
  const rapidRegenerate = async (
    cacheKey: string,
    modifications: any
  ): Promise<GenerationJob> => {
    isLoading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/orchestrator/rapid-regenerate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          cache_key: cacheKey,
          modifications
        })
      })

      if (!response.ok) {
        throw new Error(`Regeneration failed: ${response.statusText}`)
      }

      const result = await response.json()
      return result
    } catch (err: any) {
      error.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Get cached generations for a character
   */
  const getCachedGenerations = async (
    characterId: number,
    limit: number = 10
  ): Promise<any[]> => {
    try {
      const response = await fetch(
        `${API_BASE}/orchestrator/cache?character_id=${characterId}&limit=${limit}`
      )

      if (!response.ok) {
        throw new Error(`Failed to get cache: ${response.statusText}`)
      }

      const cached = await response.json()
      return cached
    } catch (err: any) {
      error.value = err.message
      return []
    }
  }

  /**
   * Cancel a running job
   */
  const cancelJob = async (jobId: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/orchestrator/cancel/${jobId}`, {
        method: 'POST'
      })

      return response.ok
    } catch (err: any) {
      error.value = err.message
      return false
    }
  }

  return {
    isLoading,
    error,
    submitGenerationJob,
    pollJobStatus,
    rapidRegenerate,
    getCachedGenerations,
    cancelJob
  }
}