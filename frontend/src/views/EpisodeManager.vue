<template>
  <TowerLayout title="Episode Manager">
    <template #actions>
      <div class="flex gap-2 items-center">
        <TowerButton @click="generateAllScenes" :disabled="isGenerating">
          {{ isGenerating ? 'Generating...' : '🎬 Generate All Scenes' }}
        </TowerButton>
        <TowerButton @click="refreshEpisodes">
          🔄 Refresh
        </TowerButton>
      </div>
    </template>

    <TowerNotification />

    <div class="p-4">
      <!-- Episodes List -->
      <div v-if="loading" class="text-center py-8">
        <div class="animate-spin inline-block w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
        <p class="mt-2">Loading episodes...</p>
      </div>

      <div v-else-if="episodes.length === 0" class="text-center py-8 text-gray-400">
        <p>No episodes found for this project</p>
      </div>

      <div v-else class="space-y-6">
        <!-- Episode Cards -->
        <TowerCard v-for="episode in episodes" :key="episode.id" class="p-6">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h3 class="text-xl font-semibold">
                Episode {{ episode.episode_number }}: {{ episode.title }}
              </h3>
              <p class="text-gray-400 mt-1">{{ episode.description }}</p>
              <div class="flex gap-4 mt-2 text-sm">
                <span class="px-2 py-1 rounded" :class="getStatusClass(episode.production_status)">
                  {{ episode.production_status }}
                </span>
                <span class="text-gray-400">
                  {{ episode.scenes?.length || 0 }} scenes
                </span>
              </div>
            </div>
            <TowerButton @click="toggleEpisode(episode.id)" size="sm">
              {{ expandedEpisodes.has(episode.id) ? '▼' : '▶' }}
            </TowerButton>
          </div>

          <!-- Scenes List (Expandable) -->
          <div v-if="expandedEpisodes.has(episode.id)" class="mt-4 space-y-2">
            <div class="text-sm text-gray-400 mb-2">Drag scenes to reorder</div>

            <draggable
              v-model="episode.scenes"
              @end="onSceneReorder(episode.id)"
              item-key="id"
              class="space-y-2"
            >
              <template #item="{element: scene}">
                <div class="bg-gray-800 rounded p-4 cursor-move hover:bg-gray-700 transition-colors">
                  <div class="flex justify-between items-start">
                    <div class="flex-1">
                      <div class="flex items-center gap-2">
                        <span class="text-sm font-semibold">Scene {{ scene.scene_number }}</span>
                        <span class="text-xs px-2 py-1 rounded" :class="getStatusClass(scene.status)">
                          {{ scene.status }}
                        </span>
                      </div>
                      <p class="text-sm text-gray-400 mt-1">{{ scene.prompt || scene.description }}</p>
                      <div class="text-xs text-gray-500 mt-2">
                        <span v-if="scene.frame_count">{{ scene.frame_count }} frames</span>
                        <span v-if="scene.fps" class="ml-2">@ {{ scene.fps }} fps</span>
                        <span v-if="scene.video_path" class="ml-2">✓ Generated</span>
                      </div>
                    </div>
                    <div class="flex gap-2 ml-4">
                      <TowerButton
                        @click="generateScene(scene.id)"
                        :disabled="scene.status === 'generating'"
                        size="sm"
                      >
                        {{ scene.status === 'generating' ? '⏳' : '🎬' }}
                      </TowerButton>
                      <TowerButton
                        v-if="scene.video_path"
                        @click="viewVideo(scene.video_path)"
                        size="sm"
                      >
                        👁️
                      </TowerButton>
                    </div>
                  </div>
                </div>
              </template>
            </draggable>

            <!-- Batch Actions -->
            <div class="mt-4 pt-4 border-t border-gray-700 flex justify-end gap-2">
              <TowerButton
                @click="generateEpisodeScenes(episode.id)"
                :disabled="isGenerating"
                size="sm"
              >
                Generate All Scenes in Episode
              </TowerButton>
            </div>
          </div>
        </TowerCard>
      </div>

      <!-- Generation Progress -->
      <div v-if="generationQueue.length > 0" class="fixed bottom-4 right-4 bg-gray-800 rounded-lg p-4 shadow-lg max-w-sm">
        <h4 class="font-semibold mb-2">Generation Queue</h4>
        <div class="space-y-1 text-sm">
          <div v-for="item in generationQueue" :key="item.id" class="flex justify-between">
            <span>{{ item.name }}</span>
            <span class="text-yellow-400">{{ item.status }}</span>
          </div>
        </div>
      </div>
    </div>
  </TowerLayout>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import draggable from 'vuedraggable'
import TowerLayout from '../components/TowerLayout.vue'
import TowerCard from '../components/TowerCard.vue'
import TowerButton from '../components/TowerButton.vue'
import TowerNotification from '../components/TowerNotification.vue'
import { useNotification } from '../composables/useNotification'

const route = useRoute()
const { showNotification } = useNotification()

const episodes = ref([])
const loading = ref(true)
const isGenerating = ref(false)
const expandedEpisodes = ref(new Set())
const generationQueue = ref([])

const projectId = computed(() => route.params.projectId || route.query.projectId)

const getStatusClass = (status) => {
  const classes = {
    'completed': 'bg-green-900 text-green-300',
    'in_progress': 'bg-yellow-900 text-yellow-300',
    'generating': 'bg-blue-900 text-blue-300',
    'pre-production': 'bg-gray-700 text-gray-300',
    'failed': 'bg-red-900 text-red-300'
  }
  return classes[status] || 'bg-gray-700 text-gray-300'
}

const toggleEpisode = (episodeId) => {
  if (expandedEpisodes.value.has(episodeId)) {
    expandedEpisodes.value.delete(episodeId)
  } else {
    expandedEpisodes.value.add(episodeId)
  }
}

const refreshEpisodes = async () => {
  loading.value = true
  try {
    // First get all episodes for the project
    const response = await fetch(`/api/anime/episodes/${projectId.value}`)
    if (!response.ok) throw new Error('Failed to fetch episodes')

    const data = await response.json()

    // For each episode, get its scenes
    for (const episode of data.episodes || [data]) {
      const scenesResponse = await fetch(`/api/anime/episodes/${projectId.value}/scenes`)
      if (scenesResponse.ok) {
        const scenesData = await scenesResponse.json()
        episode.scenes = scenesData.scenes || []
      } else {
        episode.scenes = []
      }
    }

    episodes.value = data.episodes || [data]

    // Auto-expand first episode
    if (episodes.value.length > 0 && expandedEpisodes.value.size === 0) {
      expandedEpisodes.value.add(episodes.value[0].id)
    }
  } catch (error) {
    console.error('Error fetching episodes:', error)
    showNotification('Failed to load episodes', 'error')
  } finally {
    loading.value = false
  }
}

const generateScene = async (sceneId) => {
  try {
    const response = await fetch(`/api/anime/scenes/${sceneId}/generate`, {
      method: 'POST'
    })

    if (!response.ok) throw new Error('Failed to start generation')

    const result = await response.json()
    showNotification(`Scene generation started: ${result.job_id}`, 'success')

    // Add to queue
    generationQueue.value.push({
      id: sceneId,
      name: `Scene ${sceneId}`,
      status: 'generating'
    })

    // Poll for status
    pollGenerationStatus(result.job_id, sceneId)
  } catch (error) {
    console.error('Error generating scene:', error)
    showNotification('Failed to generate scene', 'error')
  }
}

const generateEpisodeScenes = async (episodeId) => {
  isGenerating.value = true
  try {
    const response = await fetch(`/api/anime/episodes/${episodeId}/generate-all`, {
      method: 'POST'
    })

    if (!response.ok) throw new Error('Failed to start batch generation')

    const result = await response.json()
    showNotification(`Batch generation started for episode`, 'success')

    // Add all scenes to queue
    const episode = episodes.value.find(e => e.id === episodeId)
    if (episode) {
      episode.scenes.forEach(scene => {
        generationQueue.value.push({
          id: scene.id,
          name: `Scene ${scene.scene_number}`,
          status: 'queued'
        })
      })
    }

    // Start polling
    if (result.job_ids) {
      result.job_ids.forEach((jobId, index) => {
        setTimeout(() => {
          pollGenerationStatus(jobId, episode.scenes[index].id)
        }, index * 1000) // Stagger polling
      })
    }
  } catch (error) {
    console.error('Error generating episode:', error)
    showNotification('Failed to generate episode', 'error')
  } finally {
    isGenerating.value = false
  }
}

const generateAllScenes = async () => {
  isGenerating.value = true
  try {
    for (const episode of episodes.value) {
      await generateEpisodeScenes(episode.id)
    }
  } finally {
    isGenerating.value = false
  }
}

const pollGenerationStatus = async (jobId, sceneId) => {
  const maxAttempts = 60 // 5 minutes max
  let attempts = 0

  const poll = async () => {
    try {
      const response = await fetch(`/api/anime/jobs/${jobId}/status`)
      if (!response.ok) throw new Error('Failed to get status')

      const status = await response.json()

      // Update queue status
      const queueItem = generationQueue.value.find(item => item.id === sceneId)
      if (queueItem) {
        queueItem.status = status.status
      }

      if (status.status === 'completed') {
        showNotification(`Scene ${sceneId} generated successfully`, 'success')
        generationQueue.value = generationQueue.value.filter(item => item.id !== sceneId)
        await refreshEpisodes()
      } else if (status.status === 'failed') {
        showNotification(`Scene ${sceneId} generation failed`, 'error')
        generationQueue.value = generationQueue.value.filter(item => item.id !== sceneId)
      } else if (attempts < maxAttempts) {
        attempts++
        setTimeout(poll, 5000) // Poll every 5 seconds
      } else {
        showNotification(`Scene ${sceneId} generation timed out`, 'error')
        generationQueue.value = generationQueue.value.filter(item => item.id !== sceneId)
      }
    } catch (error) {
      console.error('Error polling status:', error)
      if (attempts < maxAttempts) {
        attempts++
        setTimeout(poll, 5000)
      }
    }
  }

  poll()
}

const onSceneReorder = async (episodeId) => {
  const episode = episodes.value.find(e => e.id === episodeId)
  if (!episode) return

  // Update scene numbers based on new order
  const reorderedScenes = episode.scenes.map((scene, index) => ({
    id: scene.id,
    scene_number: index + 1
  }))

  try {
    const response = await fetch('/api/anime/scenes/reorder', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenes: reorderedScenes })
    })

    if (!response.ok) throw new Error('Failed to reorder scenes')

    showNotification('Scenes reordered successfully', 'success')
  } catch (error) {
    console.error('Error reordering scenes:', error)
    showNotification('Failed to reorder scenes', 'error')
    // Refresh to restore original order
    await refreshEpisodes()
  }
}

const viewVideo = (videoPath) => {
  // Open video in new tab or modal
  window.open(videoPath, '_blank')
}

onMounted(() => {
  refreshEpisodes()

  // Auto-refresh every 30 seconds if there are items in queue
  setInterval(() => {
    if (generationQueue.value.length > 0) {
      refreshEpisodes()
    }
  }, 30000)
})
</script>

<style scoped>
/* Draggable styles */
.sortable-ghost {
  opacity: 0.5;
}

.sortable-drag {
  background-color: #1f2937 !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
}
</style>