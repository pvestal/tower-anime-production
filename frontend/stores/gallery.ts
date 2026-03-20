/**
 * Gallery store — async lazy-loaded image browsing with DB-enriched metadata.
 * Handles infinite scroll pagination, filter state, and filter options caching.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { visualApi } from '@/api/visual'

export interface GalleryItem {
  filename: string
  created_at: string
  size_kb: number
  project_name?: string
  checkpoint_model?: string
  character_slug?: string
  source?: string
  media_type?: 'image' | 'video'
}

export interface GalleryFilters {
  projects: string[]
  characters: string[]
  character_slugs: string[]
  checkpoints: string[]
  sources: string[]
}

const PAGE_SIZE = 60

export const useGalleryStore = defineStore('gallery', () => {
  // Image data
  const images = ref<GalleryItem[]>([])
  const total = ref(0)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadingMore = ref(false)

  // Filters
  const search = ref('')
  const selectedProject = ref('')
  const selectedCharacter = ref('')
  const selectedCheckpoint = ref('')
  const selectedPose = ref('')
  const selectedSource = ref('')
  const selectedMediaType = ref('')

  // Filter options (lazy loaded from DB)
  const filters = ref<GalleryFilters | null>(null)
  const filtersLoading = ref(false)
  const filtersLoaded = ref(false)

  const activeFilterCount = computed(() => {
    let c = 0
    if (selectedProject.value) c++
    if (selectedCharacter.value) c++
    if (selectedCheckpoint.value) c++
    if (selectedPose.value) c++
    if (selectedSource.value) c++
    if (selectedMediaType.value) c++
    return c
  })

  // --- Actions ---

  async function loadFilters() {
    if (filtersLoaded.value || filtersLoading.value) return
    filtersLoading.value = true
    try {
      filters.value = await visualApi.getGalleryFilters()
      filtersLoaded.value = true
    } catch (err) {
      console.error('Failed to load gallery filters:', err)
    } finally {
      filtersLoading.value = false
    }
  }

  async function loadImages(append = false) {
    if (append) {
      if (loadingMore.value || !hasMore.value) return
      loadingMore.value = true
    } else {
      if (loading.value) return
      loading.value = true
    }

    try {
      const offset = append ? images.value.length : 0
      const data = await visualApi.getGallery({
        limit: PAGE_SIZE,
        offset,
        search: search.value,
        character: selectedCharacter.value,
        project: selectedProject.value,
        checkpoint: selectedCheckpoint.value,
        pose: selectedPose.value,
        source: selectedSource.value,
        media_type: selectedMediaType.value,
      })

      if (append) {
        images.value.push(...data.images)
      } else {
        images.value = data.images
      }
      total.value = data.total
      hasMore.value = data.has_more
    } catch (err) {
      console.error('Gallery load failed:', err)
    } finally {
      loading.value = false
      loadingMore.value = false
    }
  }

  function resetAndLoad() {
    images.value = []
    total.value = 0
    hasMore.value = false
    loadImages(false)
  }

  function setSearch(q: string) {
    search.value = q
    resetAndLoad()
  }

  function setProject(p: string) {
    selectedProject.value = selectedProject.value === p ? '' : p
    resetAndLoad()
  }

  function setCharacter(c: string) {
    selectedCharacter.value = selectedCharacter.value === c ? '' : c
    resetAndLoad()
  }

  function setCheckpoint(c: string) {
    selectedCheckpoint.value = selectedCheckpoint.value === c ? '' : c
    resetAndLoad()
  }

  function setPose(p: string) {
    selectedPose.value = selectedPose.value === p ? '' : p
    resetAndLoad()
  }

  function setSource(s: string) {
    selectedSource.value = selectedSource.value === s ? '' : s
    resetAndLoad()
  }

  function setMediaType(t: string) {
    selectedMediaType.value = selectedMediaType.value === t ? '' : t
    resetAndLoad()
  }

  function clearFilters() {
    selectedProject.value = ''
    selectedCharacter.value = ''
    selectedCheckpoint.value = ''
    selectedPose.value = ''
    selectedSource.value = ''
    selectedMediaType.value = ''
    search.value = ''
    resetAndLoad()
  }

  return {
    // State
    images,
    total,
    hasMore,
    loading,
    loadingMore,
    search,
    selectedProject,
    selectedCharacter,
    selectedCheckpoint,
    selectedPose,
    selectedSource,
    selectedMediaType,
    filters,
    filtersLoading,
    filtersLoaded,
    activeFilterCount,
    // Actions
    loadFilters,
    loadImages,
    resetAndLoad,
    setSearch,
    setProject,
    setCharacter,
    setCheckpoint,
    setPose,
    setSource,
    setMediaType,
    clearFilters,
  }
})
