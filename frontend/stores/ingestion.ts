/**
 * Ingestion store — manages all content ingestion state and actions.
 * Handles YouTube, image upload, video upload, ComfyUI scan, movie upload/extract,
 * progress polling, and context synthesis.
 */
import { defineStore } from 'pinia'
import { ref, onUnmounted } from 'vue'
import { trainingApi } from '@/api/training'
import { useCharactersStore } from './characters'

export const useIngestionStore = defineStore('ingestion', () => {
  // --- Target selection ---
  const ingestTargetMode = ref<'character' | 'project'>('project')
  const ingestSelectedCharacter = ref('')
  const ingestSelectedProject = ref('')
  const ingestProjects = ref<Array<{ id: number; name: string; default_style: string; character_count: number }>>([])

  // --- Quick-create character (inline) ---
  const showIngestNewChar = ref(false)
  const newCharName = ref('')
  const newCharProject = ref('')
  const newCharDesignPrompt = ref('')
  const newCharError = ref('')
  const creatingCharacter = ref(false)

  // --- YouTube ---
  const youtubeUrl = ref('')
  const maxFrames = ref(60)
  const youtubeFps = ref(4)
  const youtubeLoading = ref(false)
  const youtubeResult = ref<{ frames_extracted: number; characters_seeded?: number } | null>(null)

  // --- Image upload ---
  const imageLoading = ref(false)
  const imageResult = ref<{ image: string } | null>(null)

  // --- Video upload ---
  const videoFps = ref(0.5)
  const videoLoading = ref(false)
  const videoResult = ref<{ frames_extracted: number } | null>(null)
  const localVideoPath = ref('')
  const localVideoMaxFrames = ref(200)

  // --- ComfyUI scan ---
  const scanLoading = ref(false)
  const scanResult = ref<{ new_images: number; matched: Record<string, number>; unmatched_count: number } | null>(null)

  // --- Movie upload ---
  const movieUploading = ref(false)
  const movieUploadPct = ref(0)
  const movieUploaded = ref(false)
  const movieUploadResult = ref('')
  const uploadedMovies = ref<Array<{ filename: string; path: string; size_mb: number }>>([])
  const movieExtractPath = ref('')
  const movieMaxFrames = ref(500)
  const movieExtracting = ref(false)

  // --- Progress ---
  const ingestProgress = ref<Record<string, any>>({})
  const ingestError = ref('')
  let progressPollTimer: ReturnType<typeof setInterval> | null = null

  // --- Synthesis ---
  const synthesizing = ref(false)
  const synthesisResult = ref<Record<string, any> | null>(null)

  // --- Progress polling ---

  function startProgressPolling() {
    stopProgressPolling()
    progressPollTimer = setInterval(async () => {
      try {
        const resp = await fetch('/api/training/ingest/progress')
        const data = await resp.json()
        ingestProgress.value = data
        if (data.stage === 'complete' || data.stage === 'error') {
          if (data.stage === 'complete' && data.per_character) {
            youtubeResult.value = { frames_extracted: data.frame_total, characters_seeded: Object.keys(data.per_character).length }
          }
          setTimeout(() => stopProgressPolling(), 30000)
        }
      } catch { /* ignore */ }
    }, 2000)
  }

  function stopProgressPolling() {
    if (progressPollTimer) {
      clearInterval(progressPollTimer)
      progressPollTimer = null
    }
  }

  // --- Actions ---

  async function loadIngestProjects(projects: Array<{ id: number; name: string; default_style: string; character_count: number }>) {
    ingestProjects.value = projects
  }

  async function checkActiveIngestion() {
    try {
      const resp = await fetch('/api/training/ingest/progress')
      const data = await resp.json()
      if (data.active) {
        ingestProgress.value = data
        startProgressPolling()
      } else if (data.stage === 'complete' || data.stage === 'error') {
        ingestProgress.value = data
      }
    } catch { /* ignore */ }
  }

  async function startYoutubeIngest() {
    youtubeLoading.value = true
    youtubeResult.value = null
    ingestError.value = ''
    try {
      if (ingestTargetMode.value === 'project') {
        await trainingApi.ingestYoutubeProject(youtubeUrl.value, ingestSelectedProject.value, maxFrames.value, youtubeFps.value)
      } else {
        await trainingApi.ingestYoutube(youtubeUrl.value, ingestSelectedCharacter.value, maxFrames.value, youtubeFps.value)
      }
      youtubeUrl.value = ''
      startProgressPolling()
    } catch (e: any) {
      ingestError.value = e.message || 'YouTube ingestion failed'
    } finally {
      youtubeLoading.value = false
    }
  }

  async function startImageIngest(file: File) {
    imageLoading.value = true
    imageResult.value = null
    ingestError.value = ''
    try {
      imageResult.value = await trainingApi.ingestImage(file, ingestSelectedCharacter.value)
    } catch (e: any) {
      ingestError.value = e.message || 'Image upload failed'
    } finally {
      imageLoading.value = false
    }
  }

  async function startVideoIngest(videoFile: File | null) {
    if (!videoFile && !localVideoPath.value) return
    videoLoading.value = true
    videoResult.value = null
    ingestError.value = ''
    try {
      if (localVideoPath.value) {
        const charactersStore = useCharactersStore()
        const projectName = ingestTargetMode.value === 'project'
          ? ingestSelectedProject.value
          : charactersStore.characters.find(c => c.slug === ingestSelectedCharacter.value)?.project_name || ''
        videoResult.value = await trainingApi.ingestLocalVideo(
          localVideoPath.value, projectName, localVideoMaxFrames.value, videoFps.value
        )
        localVideoPath.value = ''
      } else if (videoFile) {
        videoResult.value = await trainingApi.ingestVideo(videoFile, ingestSelectedCharacter.value, videoFps.value)
      }
    } catch (e: any) {
      ingestError.value = e.message || 'Video ingestion failed'
    } finally {
      videoLoading.value = false
    }
  }

  async function scanComfyUI() {
    scanLoading.value = true
    scanResult.value = null
    ingestError.value = ''
    try {
      scanResult.value = await trainingApi.scanComfyUI()
    } catch (e: any) {
      ingestError.value = e.message || 'ComfyUI scan failed'
    } finally {
      scanLoading.value = false
    }
  }

  async function uploadMovie(file: File) {
    if (!file || !ingestSelectedProject.value) return
    movieUploading.value = true
    movieUploadPct.value = 0
    movieUploadResult.value = ''
    ingestError.value = ''
    // Health check before upload
    try {
      const health = await fetch('/api/training/ingest/movies', { signal: AbortSignal.timeout(5000) })
      if (!health.ok) throw new Error(`API returned ${health.status}`)
    } catch {
      ingestError.value = 'Anime Studio API is not responding. Check if the service is running.'
      movieUploading.value = false
      return
    }
    try {
      const result = await trainingApi.uploadMovie(file, ingestSelectedProject.value, (pct) => {
        movieUploadPct.value = pct
      })
      movieUploaded.value = true
      movieUploadResult.value = `Uploaded ${result.filename} (${result.size_mb} MB) — starting extraction...`
      movieExtractPath.value = result.path
      await loadMoviesList()
      // Auto-start extraction immediately after upload
      await trainingApi.extractMovie(result.path, ingestSelectedProject.value, movieMaxFrames.value)
      movieUploadResult.value = `Uploaded ${result.filename} (${result.size_mb} MB)`
      startProgressPolling()
    } catch (e: any) {
      ingestError.value = e.message || 'Movie upload failed'
    } finally {
      movieUploading.value = false
    }
  }

  async function extractMovie() {
    if (!movieExtractPath.value || !ingestSelectedProject.value) return
    movieExtracting.value = true
    ingestError.value = ''
    try {
      await trainingApi.extractMovie(movieExtractPath.value, ingestSelectedProject.value, movieMaxFrames.value)
      startProgressPolling()
    } catch (e: any) {
      ingestError.value = e.message || 'Movie extraction failed'
    } finally {
      movieExtracting.value = false
    }
  }

  async function loadMoviesList() {
    try {
      const result = await trainingApi.listMovies()
      uploadedMovies.value = result.movies
    } catch { /* ignore */ }
  }

  async function synthesizeContext() {
    if (!ingestSelectedProject.value) return
    synthesizing.value = true
    synthesisResult.value = null
    try {
      const result = await trainingApi.synthesizeContext(ingestSelectedProject.value)
      synthesisResult.value = result.synthesis || {}
    } catch (e: any) {
      ingestError.value = e.message || 'Context synthesis failed'
    } finally {
      synthesizing.value = false
    }
  }

  async function createNewCharacter(createFn: (params: any) => Promise<any>, fetchCharacters: () => Promise<void>) {
    if (!newCharName.value.trim() || !newCharProject.value) return
    creatingCharacter.value = true
    newCharError.value = ''
    try {
      const result = await createFn({
        name: newCharName.value.trim(),
        project_name: newCharProject.value,
        design_prompt: newCharDesignPrompt.value.trim() || undefined,
      })
      showIngestNewChar.value = false
      ingestSelectedCharacter.value = result.slug
      newCharName.value = ''
      newCharProject.value = ''
      newCharDesignPrompt.value = ''
      await fetchCharacters()
    } catch (error: any) {
      newCharError.value = error.message || 'Failed to create character'
    } finally {
      creatingCharacter.value = false
    }
  }

  function dismissError() {
    ingestError.value = ''
  }

  function cleanup() {
    stopProgressPolling()
  }

  return {
    // Target selection
    ingestTargetMode,
    ingestSelectedCharacter,
    ingestSelectedProject,
    ingestProjects,

    // Quick-create character
    showIngestNewChar,
    newCharName,
    newCharProject,
    newCharDesignPrompt,
    newCharError,
    creatingCharacter,

    // YouTube
    youtubeUrl,
    maxFrames,
    youtubeFps,
    youtubeLoading,
    youtubeResult,

    // Image upload
    imageLoading,
    imageResult,

    // Video upload
    videoFps,
    videoLoading,
    videoResult,
    localVideoPath,
    localVideoMaxFrames,

    // ComfyUI scan
    scanLoading,
    scanResult,

    // Movie upload
    movieUploading,
    movieUploadPct,
    movieUploaded,
    movieUploadResult,
    uploadedMovies,
    movieExtractPath,
    movieMaxFrames,
    movieExtracting,

    // Progress & errors
    ingestProgress,
    ingestError,

    // Synthesis
    synthesizing,
    synthesisResult,

    // Actions
    startProgressPolling,
    stopProgressPolling,
    loadIngestProjects,
    checkActiveIngestion,
    startYoutubeIngest,
    startImageIngest,
    startVideoIngest,
    scanComfyUI,
    uploadMovie,
    extractMovie,
    loadMoviesList,
    synthesizeContext,
    createNewCharacter,
    dismissError,
    cleanup,
  }
})
