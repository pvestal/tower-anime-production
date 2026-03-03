import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api/client'
import { trainingApi } from '@/api/training'
import { useProjectStore } from './project'
import type {
  BuilderScene,
  BuilderShot,
  SceneGenerationStatus,
  SceneAudio,
  ShotRecommendation,
  ShotRecommendations,
  ImageWithMetadata,
  GapAnalysisResponse,
  GapAnalysisScene,
  GapAnalysisCharacter,
} from '@/types'

export const useSceneEditorStore = defineStore('sceneEditor', () => {
  // --- Core state ---
  const projects = ref<Array<{ id: number; name: string }>>([])
  const selectedProjectId = ref(0)
  const scenes = ref<BuilderScene[]>([])
  const currentView = ref<'library' | 'editor' | 'monitor'>('library')
  const librarySubView = ref<'scenes' | 'episodes'>('scenes')

  // Editor state
  const editScene = ref<Partial<BuilderScene>>({})
  const editShots = ref<Partial<BuilderShot>[]>([])
  const selectedShotIdx = ref(-1)
  const editSceneId = ref<string | null>(null)

  // Loading/progress flags
  const loading = ref(false)
  const saving = ref(false)
  const generating = ref(false)
  const generatingFromStory = ref(false)
  const generatingTraining = ref(false)
  const autoAssigning = ref(false)

  // Monitor
  const monitorStatus = ref<SceneGenerationStatus | null>(null)
  let monitorInterval: ReturnType<typeof setInterval> | null = null

  // Image picker
  const showImagePicker = ref(false)
  const loadingImages = ref(false)
  const approvedImages = ref<Record<string, { character_name: string; images: (string | ImageWithMetadata)[] }>>({})

  // Video player
  const showVideoPlayer = ref(false)
  const videoPlayerSrc = ref('')

  // Generate confirm
  const showGenerateConfirm = ref(false)

  // Recommendations & gap analysis
  const shotRecommendations = ref<ShotRecommendations[]>([])
  const gapAnalysis = ref<GapAnalysisResponse | null>(null)

  // --- Computed ---
  const selectedProjectName = computed(() => {
    const p = projects.value.find(p => p.id === selectedProjectId.value)
    return p?.name || ''
  })

  const gapBySceneId = computed((): Record<string, GapAnalysisScene> => {
    if (!gapAnalysis.value) return {}
    const map: Record<string, GapAnalysisScene> = {}
    for (const s of gapAnalysis.value.scenes) {
      map[s.id] = s
    }
    return map
  })

  const gapByCharSlug = computed((): Record<string, GapAnalysisCharacter> => {
    if (!gapAnalysis.value) return {}
    const map: Record<string, GapAnalysisCharacter> = {}
    for (const c of gapAnalysis.value.characters) {
      map[c.slug] = c
    }
    return map
  })

  const generationUnreadyChars = computed((): Array<{ slug: string; name: string; reason: string }> => {
    if (!gapAnalysis.value) return []
    const slugsSeen = new Set<string>()
    const result: Array<{ slug: string; name: string; reason: string }> = []
    for (const shot of editShots.value) {
      const chars = (shot.characters_present as string[]) || []
      for (const slug of chars) {
        if (slugsSeen.has(slug)) continue
        slugsSeen.add(slug)
        const gc = gapByCharSlug.value[slug]
        if (gc && !gc.has_lora) {
          const reason = gc.approved_count < 10
            ? `${gc.approved_count} images (need 10+)`
            : 'LoRA not yet trained'
          result.push({ slug, name: gc.name, reason })
        }
      }
    }
    return result
  })

  const currentShotCharacters = computed(() => {
    if (selectedShotIdx.value < 0) return []
    const shot = editShots.value[selectedShotIdx.value]
    return (shot?.characters_present as string[]) || []
  })

  const currentShotRecommendations = computed((): ShotRecommendation[] => {
    if (selectedShotIdx.value < 0) return []
    const shot = editShots.value[selectedShotIdx.value]
    if (!shot?.id) return []
    const match = shotRecommendations.value.find(r => r.shot_id === shot.id)
    return match?.recommendations || []
  })

  const currentShotType = computed((): string | undefined => {
    if (selectedShotIdx.value < 0) return undefined
    return editShots.value[selectedShotIdx.value]?.shot_type || undefined
  })

  const projectCharacters = computed(() => {
    return Object.entries(approvedImages.value).map(([slug, data]) => ({
      slug,
      name: data.character_name,
    }))
  })

  const sceneVideoSrc = computed(() => {
    if (!editSceneId.value) return ''
    return api.sceneVideoUrl(editSceneId.value)
  })

  const currentShotVideoSrc = computed(() => {
    if (selectedShotIdx.value < 0) return ''
    const shot = editShots.value[selectedShotIdx.value]
    if (!shot || !editSceneId.value || !shot.id) return ''
    return api.shotVideoUrl(editSceneId.value, shot.id)
  })

  // --- Actions ---
  async function loadProjects() {
    try {
      const data = await api.getProjects()
      projects.value = data.projects
    } catch (e) {
      console.error('Failed to load projects:', e)
    }
  }

  async function loadScenes() {
    if (!selectedProjectId.value) return
    loading.value = true
    try {
      const data = await api.listScenes(selectedProjectId.value)
      scenes.value = data.scenes
    } catch (e) {
      console.error('Failed to load scenes:', e)
    } finally {
      loading.value = false
    }
  }

  async function loadGapAnalysis() {
    if (!selectedProjectName.value) return
    try {
      gapAnalysis.value = await trainingApi.getGapAnalysis(selectedProjectName.value)
    } catch (e) {
      console.error('Gap analysis load failed (non-blocking):', e)
      gapAnalysis.value = null
    }
  }

  async function loadApprovedImagesBackground() {
    try {
      const data = await api.getApprovedImagesForScene(
        editSceneId.value || 'new',
        selectedProjectId.value,
      )
      approvedImages.value = data.characters
    } catch (e) {
      console.error('Failed to pre-load approved images:', e)
    }
  }

  async function loadRecommendations() {
    if (!editSceneId.value) return
    try {
      const data = await api.getShotRecommendations(editSceneId.value, 5)
      shotRecommendations.value = data.shots
    } catch (e) {
      console.error('Failed to load recommendations:', e)
      shotRecommendations.value = []
    }
  }

  function backToLibrary() {
    currentView.value = 'library'
    editSceneId.value = null
    stopMonitorPolling()
    loadScenes()
  }

  function openNewScene() {
    const projectStore = useProjectStore()
    const ws = projectStore.worldSettings
    editScene.value = {
      title: `Scene ${scenes.value.length + 1}`,
      description: '',
      location: ws?.world_location?.primary || '',
      time_of_day: '',
      weather: '',
      mood: '',
      target_duration_seconds: 30,
    }
    editShots.value = []
    editSceneId.value = null
    selectedShotIdx.value = -1
    currentView.value = 'editor'
  }

  async function openEditor(scene: BuilderScene) {
    try {
      const full = await api.getScene(scene.id)
      editScene.value = { ...full }
      editShots.value = (full.shots || []).map((s: BuilderShot) => ({ ...s }))
      editSceneId.value = scene.id
      selectedShotIdx.value = editShots.value.length > 0 ? 0 : -1
      currentView.value = 'editor'
      loadApprovedImagesBackground()
      loadRecommendations()
    } catch (e) {
      console.error('Failed to load scene:', e)
    }
  }

  function openMonitor(scene: BuilderScene) {
    editScene.value = { ...scene }
    editSceneId.value = scene.id
    currentView.value = 'monitor'
    startMonitorPolling()
  }

  function selectShot(idx: number) {
    selectedShotIdx.value = idx
  }

  function updateShotField(idx: number, field: string, value: unknown) {
    if (idx >= 0 && idx < editShots.value.length) {
      ;(editShots.value[idx] as Record<string, unknown>)[field] = value
    }
  }

  function addShot() {
    const nextNum = editShots.value.length + 1
    const newShot: Partial<BuilderShot> = {
      shot_number: nextNum,
      shot_type: 'medium',
      camera_angle: 'eye-level',
      duration_seconds: 3,
      motion_prompt: '',
      source_image_path: '',
      status: 'pending',
      use_f1: false,
      seed: null,
      steps: null,
    }
    editShots.value.push(newShot)
    selectedShotIdx.value = editShots.value.length - 1
  }

  async function removeShot(idx: number) {
    const shot = editShots.value[idx]
    if (shot.id && editSceneId.value) {
      try {
        await api.deleteShot(editSceneId.value, shot.id)
      } catch (e) {
        console.error('Failed to delete shot:', e)
      }
    }
    editShots.value.splice(idx, 1)
    editShots.value.forEach((s, i) => { s.shot_number = i + 1 })
    if (selectedShotIdx.value >= editShots.value.length) {
      selectedShotIdx.value = editShots.value.length - 1
    }
  }

  async function saveScene() {
    saving.value = true
    try {
      if (editSceneId.value) {
        await api.updateScene(editSceneId.value, {
          title: editScene.value.title,
          description: editScene.value.description,
          location: editScene.value.location,
          time_of_day: editScene.value.time_of_day,
          weather: editScene.value.weather,
          mood: editScene.value.mood,
          target_duration_seconds: editScene.value.target_duration_seconds,
        })
        for (const shot of editShots.value) {
          if (shot.id) {
            await api.updateShot(editSceneId.value, shot.id, {
              shot_number: shot.shot_number,
              source_image_path: shot.source_image_path || '',
              shot_type: shot.shot_type,
              camera_angle: shot.camera_angle,
              duration_seconds: shot.duration_seconds,
              generation_prompt: shot.generation_prompt || '',
              generation_negative: shot.generation_negative || '',
              motion_prompt: shot.motion_prompt || '',
              seed: shot.seed ?? undefined,
              steps: shot.steps ?? undefined,
              use_f1: shot.use_f1,
              video_engine: shot.video_engine ?? undefined,
              transition_type: shot.transition_type ?? undefined,
              transition_duration: shot.transition_duration ?? undefined,
              dialogue_text: shot.dialogue_text ?? undefined,
              dialogue_character_slug: shot.dialogue_character_slug ?? undefined,
            })
          } else {
            const result = await api.createShot(editSceneId.value, {
              shot_number: shot.shot_number || 1,
              source_image_path: shot.source_image_path || '',
              shot_type: shot.shot_type || 'medium',
              camera_angle: shot.camera_angle || 'eye-level',
              duration_seconds: shot.duration_seconds || 3,
              motion_prompt: shot.motion_prompt || '',
              seed: shot.seed ?? undefined,
              steps: shot.steps ?? undefined,
              use_f1: shot.use_f1 || false,
              dialogue_text: shot.dialogue_text ?? undefined,
              dialogue_character_slug: shot.dialogue_character_slug ?? undefined,
            })
            shot.id = result.id
          }
        }
      } else {
        const result = await api.createScene({
          project_id: selectedProjectId.value,
          title: editScene.value.title || 'Untitled Scene',
          description: editScene.value.description,
          location: editScene.value.location,
          time_of_day: editScene.value.time_of_day,
          weather: editScene.value.weather,
          mood: editScene.value.mood,
          target_duration_seconds: editScene.value.target_duration_seconds || 30,
        })
        editSceneId.value = result.id
        for (const shot of editShots.value) {
          const shotResult = await api.createShot(editSceneId.value, {
            shot_number: shot.shot_number || 1,
            source_image_path: shot.source_image_path || '',
            shot_type: shot.shot_type || 'medium',
            camera_angle: shot.camera_angle || 'eye-level',
            duration_seconds: shot.duration_seconds || 3,
            motion_prompt: shot.motion_prompt || '',
            seed: shot.seed ?? undefined,
            steps: shot.steps ?? undefined,
            use_f1: shot.use_f1 || false,
            dialogue_text: shot.dialogue_text ?? undefined,
            dialogue_character_slug: shot.dialogue_character_slug ?? undefined,
          })
          shot.id = shotResult.id
        }
      }
    } catch (e) {
      console.error('Save failed:', e)
    } finally {
      saving.value = false
    }
  }

  async function deleteScene(scene: BuilderScene) {
    if (!confirm(`Delete scene "${scene.title}"?`)) return
    try {
      await api.deleteScene(scene.id)
      await loadScenes()
    } catch (e) {
      console.error('Delete failed:', e)
    }
  }

  async function autoAssignAll() {
    if (!editSceneId.value) return
    autoAssigning.value = true
    try {
      if (shotRecommendations.value.length === 0) {
        await loadRecommendations()
      }
      let assigned = 0
      for (let i = 0; i < editShots.value.length; i++) {
        const shot = editShots.value[i]
        if (shot.source_image_path) continue
        const match = shotRecommendations.value.find(r => r.shot_id === shot.id)
        if (match && match.recommendations.length > 0) {
          const best = match.recommendations[0]
          shot.source_image_path = `${best.slug}/images/${best.image_name}`
          assigned++
        }
      }
      if (assigned > 0) {
        await saveScene()
      }
    } catch (e) {
      console.error('Auto-assign failed:', e)
    } finally {
      autoAssigning.value = false
    }
  }

  function onUpdateScene(scene: Partial<BuilderScene>) {
    editScene.value = scene
  }

  function onAudioChanged(audio: SceneAudio | null) {
    editScene.value = { ...editScene.value, audio }
  }

  async function openImagePickerAction() {
    showImagePicker.value = true
    loadingImages.value = true
    try {
      const sceneRef = editSceneId.value || 'new'
      let data
      try {
        data = await api.getApprovedImagesWithMetadata(sceneRef, selectedProjectId.value)
      } catch {
        data = await api.getApprovedImagesForScene(sceneRef, selectedProjectId.value)
      }
      approvedImages.value = data.characters
      if (editSceneId.value) {
        loadRecommendations()
      }
    } catch (e) {
      console.error('Failed to load approved images:', e)
    } finally {
      loadingImages.value = false
    }
  }

  function selectImage(slug: string, imageName: string) {
    if (selectedShotIdx.value >= 0) {
      editShots.value[selectedShotIdx.value].source_image_path = `${slug}/images/${imageName}`
    }
    showImagePicker.value = false
  }

  function imageUrl(slug: string, imageName: string): string {
    return api.imageUrl(slug, imageName)
  }

  function sourceImageUrl(path: string): string {
    const parts = path.split('/')
    if (parts.length >= 3) {
      return api.imageUrl(parts[0], parts[parts.length - 1])
    }
    return ''
  }

  // --- Generation ---
  function confirmGenerate() {
    showGenerateConfirm.value = true
  }

  async function startGeneration() {
    showGenerateConfirm.value = false
    if (!editSceneId.value) {
      await saveScene()
      if (!editSceneId.value) return
    } else {
      await saveScene()
    }

    generating.value = true
    try {
      await api.generateScene(editSceneId.value)
      currentView.value = 'monitor'
      startMonitorPolling()
    } catch (e) {
      console.error('Generation failed:', e)
    } finally {
      generating.value = false
    }
  }

  async function generateFromStory() {
    if (!selectedProjectId.value) return
    generatingFromStory.value = true
    try {
      const data = await api.generateScenesFromStory(selectedProjectId.value)
      await loadScenes()
      alert(`Created ${data.count} scenes from story! Open each scene to assign source images.`)
    } catch (e) {
      console.error('Story-to-scenes failed:', e)
      alert(`Failed to generate scenes: ${e}`)
    } finally {
      generatingFromStory.value = false
    }
  }

  async function generateTrainingFromScenes() {
    if (!selectedProjectName.value) return
    generatingTraining.value = true
    try {
      const result = await trainingApi.generateForScenes(selectedProjectName.value, 3)
      alert(`${result.message}\n\nPer character:\n${Object.entries(result.per_character).map(([k, v]) => `  ${k}: ${v} images`).join('\n')}`)
      loadGapAnalysis()
    } catch (e) {
      console.error('Scene training generation failed:', e)
      alert(`Failed: ${e}`)
    } finally {
      generatingTraining.value = false
    }
  }

  // --- Monitor polling ---
  function startMonitorPolling() {
    stopMonitorPolling()
    pollStatus()
    monitorInterval = setInterval(pollStatus, 5000)
  }

  function stopMonitorPolling() {
    if (monitorInterval) {
      clearInterval(monitorInterval)
      monitorInterval = null
    }
  }

  async function pollStatus() {
    if (!editSceneId.value) return
    try {
      monitorStatus.value = await api.getSceneStatus(editSceneId.value)
      if (monitorStatus.value.generation_status !== 'generating') {
        stopMonitorPolling()
      }
    } catch (e) {
      console.error('Status poll failed:', e)
    }
  }

  async function retryShot(shot: { id: string }) {
    if (!editSceneId.value) return
    try {
      await api.regenerateShot(editSceneId.value, shot.id)
      startMonitorPolling()
    } catch (e) {
      console.error('Retry failed:', e)
    }
  }

  async function reassemble() {
    if (!editSceneId.value) return
    try {
      await api.assembleScene(editSceneId.value)
      await pollStatus()
    } catch (e) {
      console.error('Assemble failed:', e)
    }
  }

  // --- Video player ---
  function playSceneVideo(scene: BuilderScene) {
    videoPlayerSrc.value = api.sceneVideoUrl(scene.id)
    showVideoPlayer.value = true
  }

  function playEpisodeVideo(ep: { id: string }) {
    videoPlayerSrc.value = api.episodeVideoUrl(ep.id)
    showVideoPlayer.value = true
  }

  function playShotVideo(shot: { id: string }) {
    if (!editSceneId.value) return
    videoPlayerSrc.value = api.shotVideoUrl(editSceneId.value, shot.id)
    showVideoPlayer.value = true
  }

  // --- Helpers ---
  function estimateMinutes(shots: Partial<BuilderShot>[]): number {
    return shots.reduce((sum, s) => {
      const dur = s.duration_seconds || 3
      if (dur <= 2) return sum + 20
      if (dur <= 3) return sum + 13
      if (dur <= 5) return sum + 25
      return sum + 30
    }, 0)
  }

  function cleanup() {
    stopMonitorPolling()
  }

  return {
    // State
    projects,
    selectedProjectId,
    scenes,
    currentView,
    librarySubView,
    editScene,
    editShots,
    selectedShotIdx,
    editSceneId,
    loading,
    saving,
    generating,
    generatingFromStory,
    generatingTraining,
    autoAssigning,
    monitorStatus,
    showImagePicker,
    loadingImages,
    approvedImages,
    showVideoPlayer,
    videoPlayerSrc,
    showGenerateConfirm,
    shotRecommendations,
    gapAnalysis,

    // Computed
    selectedProjectName,
    gapBySceneId,
    gapByCharSlug,
    generationUnreadyChars,
    currentShotCharacters,
    currentShotRecommendations,
    currentShotType,
    projectCharacters,
    sceneVideoSrc,
    currentShotVideoSrc,

    // Actions
    loadProjects,
    loadScenes,
    loadGapAnalysis,
    loadApprovedImagesBackground,
    loadRecommendations,
    backToLibrary,
    openNewScene,
    openEditor,
    openMonitor,
    selectShot,
    updateShotField,
    addShot,
    removeShot,
    saveScene,
    deleteScene,
    autoAssignAll,
    onUpdateScene,
    onAudioChanged,
    openImagePickerAction,
    selectImage,
    imageUrl,
    sourceImageUrl,
    confirmGenerate,
    startGeneration,
    generateFromStory,
    generateTrainingFromScenes,
    startMonitorPolling,
    stopMonitorPolling,
    retryShot,
    reassemble,
    playSceneVideo,
    playEpisodeVideo,
    playShotVideo,
    estimateMinutes,
    cleanup,
  }
})
