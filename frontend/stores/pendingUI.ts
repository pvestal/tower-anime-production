/**
 * Pending UI store — persists filter, selection, and replenishment state
 * across tab navigation so users don't lose context when switching views.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApprovalStore } from '@/stores/approval'
import { learningApi } from '@/api/learning'
import type { ReplenishmentStatus, ReadinessResponse } from '@/types'

export const usePendingUIStore = defineStore('pendingUI', () => {
  // --- Selection state ---
  const selectedImages = ref<Set<string>>(new Set())
  const expandedCharacters = ref<Set<string>>(new Set())

  // --- Filter state ---
  const filterSource = ref('')
  const filterModel = ref('')
  const sortBy = ref('newest')

  // --- Replenishment state ---
  const replenishStatus = ref<ReplenishmentStatus | null>(null)
  const readinessData = ref<ReadinessResponse | null>(null)

  const activeGenCount = computed(() => {
    if (!replenishStatus.value) return 0
    return Object.values(replenishStatus.value.active_generations).filter(Boolean).length
  })

  // --- Selection actions ---

  function toggleImageSelection(imageId: string) {
    if (selectedImages.value.has(imageId)) {
      selectedImages.value.delete(imageId)
    } else {
      selectedImages.value.add(imageId)
    }
    selectedImages.value = new Set(selectedImages.value)
  }

  function selectAllForCharacter(images: { id: string }[]) {
    const allSelected = images.every(img => selectedImages.value.has(img.id))
    if (allSelected) {
      for (const img of images) {
        selectedImages.value.delete(img.id)
      }
    } else {
      for (const img of images) {
        selectedImages.value.add(img.id)
      }
    }
    selectedImages.value = new Set(selectedImages.value)
  }

  function removeFromSelection(imageId: string) {
    selectedImages.value.delete(imageId)
    selectedImages.value = new Set(selectedImages.value)
  }

  function clearSelection() {
    selectedImages.value = new Set()
  }

  // --- Character expand ---

  function toggleCharacterExpand(charName: string) {
    if (expandedCharacters.value.has(charName)) {
      expandedCharacters.value.delete(charName)
    } else {
      expandedCharacters.value.add(charName)
    }
    expandedCharacters.value = new Set(expandedCharacters.value)
  }

  // --- Filter actions ---

  function setFilter(key: 'source' | 'model' | 'sort', value: string) {
    switch (key) {
      case 'source': filterSource.value = value; break
      case 'model': filterModel.value = value; break
      case 'sort': sortBy.value = value; break
    }
  }

  // --- Replenishment actions ---

  async function refreshReplenishStatus(projectFilter?: string) {
    try {
      const [status, readiness] = await Promise.all([
        learningApi.getReplenishmentStatus(),
        learningApi.getCharacterReadiness(projectFilter || undefined),
      ])
      replenishStatus.value = status
      readinessData.value = readiness
    } catch (e) {
      console.warn('Failed to fetch replenishment data:', e)
    }
  }

  return {
    // State
    selectedImages,
    expandedCharacters,
    filterSource,
    filterModel,
    sortBy,
    replenishStatus,
    readinessData,
    activeGenCount,
    // Actions
    toggleImageSelection,
    selectAllForCharacter,
    removeFromSelection,
    clearSelection,
    toggleCharacterExpand,
    setFilter,
    refreshReplenishStatus,
  }
})
