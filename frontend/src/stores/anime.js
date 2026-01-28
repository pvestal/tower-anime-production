import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAnimeStore = defineStore('anime', () => {
  // Projects state
  const projects = ref([])
  const selectedProject = ref(null)
  const projectsLoading = ref(false)
  const projectError = ref(null)

  // Episodes state
  const episodes = ref([])
  const selectedEpisode = ref(null)
  const episodesLoading = ref(false)

  // Scenes state
  const scenes = ref([])
  const selectedScene = ref(null)
  const scenesLoading = ref(false)

  // Characters state
  const characters = ref([])
  const selectedCharacter = ref(null)
  const charactersLoading = ref(false)

  // LoRA models state
  const loraModels = ref([])
  const loraTrainingQueue = ref([])
  const loraTrainingStatus = ref({})

  // Quality Gates state
  const qualityGates = ref({
    'Super Mario Galaxy Anime Adventure': {
      model: 'realisticVision_v51.safetensors',
      style: 'Illumination Studios 3D movie style (2026 release)',
      minApprovedImages: 15,
      requirements: [
        'Realistic 3D character rendering',
        'Photorealistic textures and lighting',
        'Cinematic movie quality'
      ],
      notAllowed: ['Anime', 'cartoon', 'stylized', '2D', 'flat colors']
    },
    'Tokyo Debt Desire': {
      model: 'custom_anime_model.safetensors',
      style: 'Modern anime with realistic proportions',
      minApprovedImages: 12,
      requirements: [
        'Adult human proportions',
        'Detailed facial features',
        'Tokyo urban setting',
        'Contemporary clothing'
      ],
      notAllowed: ['Childish', 'cartoon', 'oversized eyes']
    },
    'Cyberpunk Goblin Slayer': {
      model: 'arcane_style_model.safetensors',
      style: 'Arcane (League of Legends) animation style',
      minApprovedImages: 10,
      requirements: [
        'Arcane painterly aesthetic',
        'Hand-painted textures',
        'Dramatic lighting with color contrast',
        'Fortiche Production visual style'
      ],
      notAllowed: ['Photorealistic', 'anime', 'flat shading', 'simple']
    }
  })

  // Approval tracking
  const characterApprovals = ref({})
  const pendingApprovals = ref([])

  // Generation state
  const activeGenerations = ref([])
  const generationHistory = ref([])

  // Computed properties
  const currentProjectName = computed(() => selectedProject.value?.name || 'No Project Selected')

  const currentQualityGate = computed(() => {
    if (!selectedProject.value) return null
    return qualityGates.value[selectedProject.value.name] || null
  })

  const currentCharacterApprovals = computed(() => {
    if (!selectedProject.value || !selectedCharacter.value) return 0
    const key = `${selectedProject.value.id}_${selectedCharacter.value.name}`
    return characterApprovals.value[key]?.approved || 0
  })

  const canStartLoRATraining = computed(() => {
    if (!currentQualityGate.value || !selectedCharacter.value) return false
    const approvedCount = currentCharacterApprovals.value
    return approvedCount >= currentQualityGate.value.minApprovedImages
  })

  const trainingReadiness = computed(() => {
    if (!currentQualityGate.value) return { ready: false, message: 'No quality gate defined' }

    const approved = currentCharacterApprovals.value
    const required = currentQualityGate.value.minApprovedImages

    if (approved >= required) {
      return { ready: true, message: `✅ Ready for training (${approved}/${required} approved)` }
    } else {
      return {
        ready: false,
        message: `⚠️ Need ${required - approved} more approved images (${approved}/${required})`
      }
    }
  })

  // Actions
  async function loadProjects() {
    projectsLoading.value = true
    projectError.value = null
    try {
      const response = await fetch('/api/anime/projects')
      const data = await response.json()
      projects.value = data.projects || []
    } catch (error) {
      projectError.value = error.message
      console.error('Failed to load projects:', error)
    } finally {
      projectsLoading.value = false
    }
  }

  async function loadEpisodes(projectId) {
    episodesLoading.value = true
    try {
      const response = await fetch(`/api/anime/episodes?project_id=${projectId}`)
      const data = await response.json()
      episodes.value = data.episodes || []
    } catch (error) {
      console.error('Failed to load episodes:', error)
      episodes.value = []
    } finally {
      episodesLoading.value = false
    }
  }

  async function loadScenes(episodeId) {
    scenesLoading.value = true
    try {
      const response = await fetch(`/api/anime/scenes?episode_id=${episodeId}`)
      const data = await response.json()
      scenes.value = data.scenes || []
    } catch (error) {
      console.error('Failed to load scenes:', error)
      scenes.value = []
    } finally {
      scenesLoading.value = false
    }
  }

  async function loadCharacters(projectId) {
    charactersLoading.value = true
    try {
      const response = await fetch(`/api/anime/characters?project_id=${projectId}`)
      const data = await response.json()
      characters.value = data.characters || []
    } catch (error) {
      console.error('Failed to load characters:', error)
      characters.value = []
    } finally {
      charactersLoading.value = false
    }
  }

  async function loadCharacterApprovals(projectId, characterName) {
    const key = `${projectId}_${characterName}`
    try {
      const response = await fetch(`/api/anime/approvals/${projectId}/${characterName}`)
      const data = await response.json()
      characterApprovals.value[key] = {
        approved: data.approved_count || 0,
        rejected: data.rejected_count || 0,
        pending: data.pending_count || 0,
        images: data.images || []
      }
    } catch (error) {
      console.error('Failed to load approvals:', error)
      characterApprovals.value[key] = { approved: 0, rejected: 0, pending: 0, images: [] }
    }
  }

  async function submitApproval(imagePath, characterName, approved, feedback = '') {
    try {
      const response = await fetch('/api/anime/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_path: imagePath,
          character_name: characterName,
          project_id: selectedProject.value?.id,
          approved,
          feedback
        })
      })

      if (response.ok) {
        // Reload approvals
        await loadCharacterApprovals(selectedProject.value.id, characterName)
        return true
      }
      return false
    } catch (error) {
      console.error('Failed to submit approval:', error)
      return false
    }
  }

  async function startLoRATraining(characterName, datasetPath, trainingSteps = 1500) {
    if (!canStartLoRATraining.value) {
      throw new Error('Cannot start training - quality gate not met')
    }

    try {
      const response = await fetch('/api/anime/lora/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: selectedProject.value.id,
          character_name: characterName,
          dataset_path: datasetPath,
          training_steps: trainingSteps,
          base_model: currentQualityGate.value.model
        })
      })

      const data = await response.json()
      if (data.training_id) {
        loraTrainingQueue.value.push({
          id: data.training_id,
          character: characterName,
          project: selectedProject.value.name,
          status: 'queued',
          progress: 0
        })
        return data.training_id
      }
      throw new Error(data.error || 'Failed to start training')
    } catch (error) {
      console.error('Failed to start LoRA training:', error)
      throw error
    }
  }

  async function generateCharacterImages(characterName, count = 20) {
    try {
      const response = await fetch('/api/anime/generate/character', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: selectedProject.value.id,
          character_name: characterName,
          count,
          style: currentQualityGate.value?.style,
          model: currentQualityGate.value?.model
        })
      })

      const data = await response.json()
      if (data.generation_id) {
        activeGenerations.value.push({
          id: data.generation_id,
          character: characterName,
          count,
          status: 'generating',
          progress: 0
        })
        return data.generation_id
      }
      throw new Error(data.error || 'Failed to start generation')
    } catch (error) {
      console.error('Failed to generate character images:', error)
      throw error
    }
  }

  function selectProject(project) {
    selectedProject.value = project
    selectedEpisode.value = null
    selectedScene.value = null
    selectedCharacter.value = null

    // Load related data
    if (project) {
      loadEpisodes(project.id)
      loadCharacters(project.id)
    }
  }

  function selectCharacter(character) {
    selectedCharacter.value = character
    if (character && selectedProject.value) {
      loadCharacterApprovals(selectedProject.value.id, character.name)
    }
  }

  function updateGenerationProgress(generationId, progress, status) {
    const generation = activeGenerations.value.find(g => g.id === generationId)
    if (generation) {
      generation.progress = progress
      generation.status = status

      if (status === 'completed' || status === 'failed') {
        // Move to history
        generationHistory.value.unshift(generation)
        activeGenerations.value = activeGenerations.value.filter(g => g.id !== generationId)
      }
    }
  }

  function updateTrainingProgress(trainingId, progress, status) {
    const training = loraTrainingQueue.value.find(t => t.id === trainingId)
    if (training) {
      training.progress = progress
      training.status = status
      loraTrainingStatus.value[trainingId] = { progress, status, updatedAt: new Date() }
    }
  }

  return {
    // State
    projects,
    selectedProject,
    projectsLoading,
    projectError,
    episodes,
    selectedEpisode,
    episodesLoading,
    scenes,
    selectedScene,
    scenesLoading,
    characters,
    selectedCharacter,
    charactersLoading,
    loraModels,
    loraTrainingQueue,
    loraTrainingStatus,
    qualityGates,
    characterApprovals,
    pendingApprovals,
    activeGenerations,
    generationHistory,

    // Computed
    currentProjectName,
    currentQualityGate,
    currentCharacterApprovals,
    canStartLoRATraining,
    trainingReadiness,

    // Actions
    loadProjects,
    loadEpisodes,
    loadScenes,
    loadCharacters,
    loadCharacterApprovals,
    submitApproval,
    startLoRATraining,
    generateCharacterImages,
    selectProject,
    selectCharacter,
    updateGenerationProgress,
    updateTrainingProgress
  }
})