/**
 * Trailer store — manages trailer list, current trailer, and scorecard state.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { trailersApi } from '@/api/trailers'

export const useTrailerStore = defineStore('trailer', () => {
  const trailers = ref<any[]>([])
  const currentTrailer = ref<any | null>(null)
  const scorecard = ref<any | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const overallPass = computed(() => scorecard.value?.overall_pass ?? null)

  const dimensions = computed(() => scorecard.value?.dimensions ?? [])

  const failedDimensions = computed(() =>
    dimensions.value.filter((d: any) => !d.passed && d.score !== null)
  )

  const recommendations = computed(() => scorecard.value?.recommendations ?? [])

  const shotScores = computed(() => scorecard.value?.shot_scores ?? [])

  // Actions
  async function fetchTrailers(projectId: number) {
    loading.value = true
    error.value = null
    try {
      trailers.value = await trailersApi.listTrailers(projectId)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchTrailer(id: string) {
    loading.value = true
    error.value = null
    try {
      currentTrailer.value = await trailersApi.getTrailer(id)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchScorecard(id: string, refresh = false) {
    try {
      scorecard.value = await trailersApi.getScorecard(id, refresh)
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function refreshScorecard(id: string) {
    return fetchScorecard(id, true)
  }

  async function shotAction(trailerId: string, shotId: string, action: string, value?: string) {
    try {
      const result = await trailersApi.shotAction(trailerId, shotId, action, value)
      // Refresh scorecard after action
      await fetchScorecard(trailerId, true)
      return result
    } catch (e: any) {
      error.value = e.message
      throw e
    }
  }

  async function approveTrailer(id: string, notes = '') {
    try {
      const result = await trailersApi.approveTrailer(id, notes)
      if (currentTrailer.value) {
        currentTrailer.value.status = 'approved'
      }
      return result
    } catch (e: any) {
      error.value = e.message
      throw e
    }
  }

  return {
    trailers, currentTrailer, scorecard, loading, error,
    overallPass, dimensions, failedDimensions, recommendations, shotScores,
    fetchTrailers, fetchTrailer, fetchScorecard, refreshScorecard,
    shotAction, approveTrailer,
  }
})
