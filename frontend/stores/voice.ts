import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { VoiceSpeaker, VoiceSample, VoiceTrainingJob, VoiceSampleStats } from '@/types'
import { voiceApi } from '@/api/voice'

export const useVoiceStore = defineStore('voice', () => {
  const speakers = ref<VoiceSpeaker[]>([])
  const samples = ref<Record<string, VoiceSample[]>>({})
  const sampleStats = ref<Record<string, VoiceSampleStats>>({})
  const trainingJobs = ref<VoiceTrainingJob[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const selectedProject = ref<string>('')

  const activeJobs = computed(() =>
    trainingJobs.value.filter(j => j.status === 'queued' || j.status === 'running')
  )

  const completedJobs = computed(() =>
    trainingJobs.value.filter(j => j.status === 'completed')
  )

  async function fetchSpeakers(projectName: string) {
    loading.value = true
    error.value = null
    try {
      const resp = await voiceApi.getSpeakers(projectName)
      speakers.value = resp.speakers
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch speakers'
    } finally {
      loading.value = false
    }
  }

  async function fetchSamples(characterSlug: string) {
    try {
      const resp = await voiceApi.getSamples(characterSlug)
      samples.value[characterSlug] = resp.samples
    } catch (err) {
      samples.value[characterSlug] = []
    }
  }

  async function fetchSampleStats(characterSlug: string) {
    try {
      const stats = await voiceApi.getSampleStats(characterSlug)
      sampleStats.value[characterSlug] = stats
    } catch {
      // ignore
    }
  }

  async function fetchTrainingJobs(params?: { project_name?: string; character_slug?: string }) {
    try {
      const resp = await voiceApi.getVoiceTrainingJobs(params)
      trainingJobs.value = resp.jobs
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch training jobs'
    }
  }

  async function approveSample(characterSlug: string, filename: string, approved: boolean, opts?: { feedback?: string; transcript?: string }) {
    try {
      await voiceApi.approveSample(characterSlug, filename, approved, opts)
      // Update local state
      const charSamples = samples.value[characterSlug]
      if (charSamples) {
        const idx = charSamples.findIndex(s => s.filename === filename)
        if (idx >= 0) {
          charSamples[idx].approval_status = approved ? 'approved' : 'rejected'
        }
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to approve sample'
      throw err
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    speakers,
    samples,
    sampleStats,
    trainingJobs,
    loading,
    error,
    selectedProject,
    activeJobs,
    completedJobs,
    fetchSpeakers,
    fetchSamples,
    fetchSampleStats,
    fetchTrainingJobs,
    approveSample,
    clearError,
  }
})
