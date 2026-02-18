import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import type { Character, DatasetImage } from '@/types'
import { api } from '@/api/client'

export const useCharactersStore = defineStore('characters', () => {
  const characters = ref<Character[]>([])
  const datasets = reactive(new Map<string, DatasetImage[]>())
  const loading = ref(false)
  const error = ref<string | null>(null)

  const totalImages = computed(() => {
    return characters.value.reduce((sum, c) => sum + c.image_count, 0)
  })

  const getCharacterStats = computed(() => (characterName: string) => {
    const images = datasets.get(characterName) || []
    const approved = images.filter(img => img.status === 'approved').length
    const pending = images.filter(img => img.status === 'pending').length
    return {
      total: images.length,
      approved,
      pending,
      canTrain: approved >= 10,
    }
  })

  async function fetchCharacters() {
    loading.value = true
    error.value = null
    try {
      const response = await api.getCharacters()
      characters.value = response.characters
      // Fetch all datasets in parallel
      await Promise.all(
        characters.value.map(c => fetchCharacterDataset(c.slug || c.name))
      )
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch characters'
    } finally {
      loading.value = false
    }
  }

  async function fetchCharacterDataset(characterName: string) {
    try {
      const response = await api.getCharacterDataset(characterName)
      datasets.set(characterName, response.images)
    } catch (err) {
      datasets.set(characterName, [])
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    characters,
    datasets,
    loading,
    error,
    totalImages,
    getCharacterStats,
    fetchCharacters,
    fetchCharacterDataset,
    clearError,
  }
})
