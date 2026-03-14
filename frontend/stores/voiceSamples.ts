import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import type { VoiceSample, VoiceSampleStats, Character } from '@/types'
import { voiceApi } from '@/api/voice'

export const useVoiceSamplesStore = defineStore('voiceSamples', () => {
  // --- State ---
  const allSamples = ref<VoiceSample[]>([])
  const selectedSamples = ref<Set<string>>(new Set())
  const transcripts = reactive<Record<string, string>>({})
  const stats = ref<VoiceSampleStats | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Track what we last loaded to avoid redundant fetches
  const loadedForCharacter = ref<string | null>(null)
  const loadedCharacterSlugs = ref<string[]>([])

  // --- Getters ---
  const selectedCount = computed(() => selectedSamples.value.size)
  const selectedArray = computed(() => [...selectedSamples.value])

  // --- Actions ---

  /**
   * Load samples for a specific character slug, or all characters.
   * Caches results — won't re-fetch if already loaded for the same character(s).
   */
  async function loadSamples(characters: Character[], characterSlug?: string) {
    const cacheKey = characterSlug || ''
    const slugs = characterSlug
      ? [characterSlug]
      : characters.map(c => c.slug)
    const slugsKey = slugs.sort().join(',')

    // Skip if already loaded for same selection
    if (loadedForCharacter.value === cacheKey && loadedCharacterSlugs.value.join(',') === slugsKey && allSamples.value.length > 0) {
      return
    }

    loading.value = true
    error.value = null
    allSamples.value = []

    try {
      const collected: VoiceSample[] = []
      for (const slug of slugs) {
        const resp = await voiceApi.getSamples(slug)
        for (const s of resp.samples) {
          if (!s.character_slug) s.character_slug = slug
          collected.push(s)
        }
      }
      allSamples.value = collected
      loadedForCharacter.value = cacheKey
      loadedCharacterSlugs.value = slugs

      // Load stats if filtering by a specific character
      if (characterSlug) {
        stats.value = await voiceApi.getSampleStats(characterSlug)
      } else {
        stats.value = null
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load samples'
    } finally {
      loading.value = false
    }
  }

  /** Force reload (invalidates cache) */
  async function reloadSamples(characters: Character[], characterSlug?: string) {
    loadedForCharacter.value = null
    loadedCharacterSlugs.value = []
    await loadSamples(characters, characterSlug)
  }

  /** Refresh stats for a character without reloading all samples */
  async function refreshStats(characterSlug: string) {
    try {
      stats.value = await voiceApi.getSampleStats(characterSlug)
    } catch {
      // non-fatal
    }
  }

  function selectSample(filename: string) {
    selectedSamples.value.add(filename)
  }

  function deselectSample(filename: string) {
    selectedSamples.value.delete(filename)
  }

  function toggleSample(filename: string) {
    if (selectedSamples.value.has(filename)) {
      selectedSamples.value.delete(filename)
    } else {
      selectedSamples.value.add(filename)
    }
  }

  function clearSelection() {
    selectedSamples.value.clear()
  }

  function updateTranscript(filename: string, text: string) {
    transcripts[filename] = text
  }

  /** Approve or reject a single sample, updating local state */
  async function approveSample(sample: VoiceSample, approved: boolean) {
    error.value = null
    try {
      await voiceApi.approveSample(sample.character_slug, sample.filename, approved, {
        transcript: transcripts[sample.filename] || undefined,
      })
      sample.approval_status = approved ? 'approved' : 'rejected'
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Approval failed'
      throw err
    }
  }

  /** Batch approve/reject selected samples */
  async function batchApprove(characterSlug: string, approved: boolean) {
    if (!characterSlug || selectedSamples.value.size === 0) return
    error.value = null
    try {
      const filenames = [...selectedSamples.value]
      await voiceApi.batchApproveSamples(characterSlug, filenames, approved)
      // Update local state
      for (const fname of filenames) {
        const s = allSamples.value.find(s => s.filename === fname)
        if (s) s.approval_status = approved ? 'approved' : 'rejected'
      }
      selectedSamples.value.clear()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Batch operation failed'
      throw err
    }
  }

  function clearError() {
    error.value = null
  }

  /** Reset store state completely */
  function $reset() {
    allSamples.value = []
    selectedSamples.value.clear()
    Object.keys(transcripts).forEach(k => delete transcripts[k])
    stats.value = null
    loading.value = false
    error.value = null
    loadedForCharacter.value = null
    loadedCharacterSlugs.value = []
  }

  return {
    // State
    allSamples,
    selectedSamples,
    transcripts,
    stats,
    loading,
    error,
    // Getters
    selectedCount,
    selectedArray,
    // Actions
    loadSamples,
    reloadSamples,
    refreshStats,
    selectSample,
    deselectSample,
    toggleSample,
    clearSelection,
    updateTranscript,
    approveSample,
    batchApprove,
    clearError,
    $reset,
  }
})
