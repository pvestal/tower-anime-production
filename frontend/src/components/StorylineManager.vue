<template>
  <div class="storyline-manager">
    <Card class="mb-3">
      <template #header>
        <div class="flex justify-content-between align-items-center p-3">
          <div class="flex align-items-center gap-2">
            <i class="pi pi-book" style="font-size: 1.5rem; color: #ff8c00;"></i>
            <h3 class="m-0">Storyline Management</h3>
            <Tag v-if="selectedProject" :value="selectedProject.name" severity="info" />
          </div>
          <div class="flex gap-2">
            <Button
              label="New Storyline"
              icon="pi pi-plus"
              @click="showNewStorylineDialog = true"
              :disabled="!selectedProject"
              size="small"
            />
            <Button
              label="Quality Gates"
              icon="pi pi-check-square"
              @click="showQualityGatesDialog = true"
              severity="warning"
              size="small"
            />
          </div>
        </div>
      </template>

      <template #content>
        <div class="grid">
          <!-- Storylines List -->
          <div class="col-12 md:col-4">
            <div class="storylines-list">
              <h4 class="mb-3">Storylines</h4>
              <div v-if="storylinesLoading" class="text-center p-3">
                <ProgressSpinner style="width:30px;height:30px" />
              </div>
              <div v-else-if="storylines.length === 0" class="text-center text-500 p-3">
                No storylines yet
              </div>
              <div v-else class="storylines-container">
                <div
                  v-for="storyline in storylines"
                  :key="storyline.id"
                  class="storyline-card p-3 mb-2 cursor-pointer"
                  :class="{ 'selected': selectedStoryline?.id === storyline.id }"
                  @click="selectStoryline(storyline)"
                >
                  <div class="flex justify-content-between align-items-start">
                    <div class="flex-1">
                      <h5 class="m-0 mb-1">{{ storyline.title }}</h5>
                      <p class="text-sm text-500 m-0 mb-2">{{ storyline.summary }}</p>
                      <div class="flex gap-2">
                        <Tag :value="storyline.genre" severity="secondary" class="text-xs" />
                        <Tag :value="storyline.status" :severity="getStatusSeverity(storyline.status)" class="text-xs" />
                        <Tag v-if="storyline.episodes?.length"
                             :value="`${storyline.episodes.length} episodes`"
                             severity="info"
                             class="text-xs" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Episodes -->
          <div class="col-12 md:col-4">
            <div class="episodes-section">
              <h4 class="mb-3">Episodes</h4>
              <div v-if="!selectedStoryline" class="text-center text-500 p-3">
                Select a storyline
              </div>
              <div v-else-if="episodesLoading" class="text-center p-3">
                <ProgressSpinner style="width:30px;height:30px" />
              </div>
              <div v-else>
                <div class="mb-2">
                  <Button
                    label="Add Episode"
                    icon="pi pi-plus"
                    @click="showNewEpisodeDialog = true"
                    size="small"
                    outlined
                    class="w-full"
                  />
                </div>
                <div v-if="episodes.length === 0" class="text-center text-500 p-3">
                  No episodes in this storyline
                </div>
                <div v-else class="episodes-list">
                  <div
                    v-for="(episode, index) in episodes"
                    :key="episode.id"
                    class="episode-card p-2 mb-2"
                    :class="{ 'selected': selectedEpisode?.id === episode.id }"
                    @click="selectEpisode(episode)"
                  >
                    <div class="flex align-items-center gap-2 mb-1">
                      <Badge :value="index + 1" severity="info" />
                      <span class="font-semibold text-sm">{{ episode.title }}</span>
                    </div>
                    <p class="text-xs text-500 m-0">{{ episode.description }}</p>
                    <div class="flex gap-1 mt-2">
                      <Tag :value="episode.status" :severity="getStatusSeverity(episode.status)" class="text-xs" />
                      <Tag v-if="episode.scene_count" :value="`${episode.scene_count} scenes`" class="text-xs" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Style Requirements & Quality Gates -->
          <div class="col-12 md:col-4">
            <div class="quality-section">
              <h4 class="mb-3">Style Requirements</h4>
              <div v-if="!selectedProject" class="text-center text-500 p-3">
                Select a project to view requirements
              </div>
              <div v-else>
                <Card class="quality-gate-card">
                  <template #content>
                    <div v-if="currentQualityGate">
                      <div class="mb-3">
                        <label class="text-xs text-500">Style</label>
                        <div class="font-semibold">{{ currentQualityGate.style }}</div>
                      </div>
                      <div class="mb-3">
                        <label class="text-xs text-500">Model</label>
                        <div class="text-sm font-mono">{{ currentQualityGate.model }}</div>
                      </div>
                      <div class="mb-3">
                        <label class="text-xs text-500">Min Approved Images</label>
                        <div class="flex align-items-center gap-2">
                          <Badge :value="currentQualityGate.minApprovedImages" severity="danger" />
                          <span class="text-sm">per character</span>
                        </div>
                      </div>
                      <div class="mb-3">
                        <label class="text-xs text-500">Requirements</label>
                        <ul class="pl-3 m-0">
                          <li v-for="req in currentQualityGate.requirements" :key="req" class="text-sm">
                            {{ req }}
                          </li>
                        </ul>
                      </div>
                      <div>
                        <label class="text-xs text-500">Not Allowed</label>
                        <div class="flex flex-wrap gap-1 mt-1">
                          <Tag v-for="item in currentQualityGate.notAllowed"
                               :key="item"
                               :value="item"
                               severity="danger"
                               class="text-xs" />
                        </div>
                      </div>
                    </div>
                    <div v-else class="text-center text-500">
                      No quality gate configured for this project
                    </div>
                  </template>
                </Card>

                <!-- Character Approval Status -->
                <Card class="mt-3" v-if="characters.length > 0">
                  <template #header>
                    <h5 class="m-0 p-2">Character Approval Status</h5>
                  </template>
                  <template #content>
                    <div v-for="character in characters" :key="character.id" class="mb-3">
                      <div class="flex justify-content-between align-items-center mb-1">
                        <span class="font-semibold text-sm">{{ character.name }}</span>
                        <Tag
                          :value="getApprovalStatus(character).text"
                          :severity="getApprovalStatus(character).severity"
                          class="text-xs"
                        />
                      </div>
                      <ProgressBar
                        :value="getApprovalProgress(character)"
                        :showValue="false"
                        style="height: 6px"
                      />
                      <div class="text-xs text-500 mt-1">
                        {{ characterApprovals[character.name]?.approved || 0 }} / {{ currentQualityGate?.minApprovedImages || 0 }} approved
                      </div>
                    </div>
                  </template>
                </Card>
              </div>
            </div>
          </div>
        </div>
      </template>
    </Card>

    <!-- New Storyline Dialog -->
    <Dialog v-model:visible="showNewStorylineDialog" header="Create New Storyline" :modal="true" :style="{width: '500px'}">
      <div class="p-fluid">
        <div class="field">
          <label>Title</label>
          <InputText v-model="newStoryline.title" />
        </div>
        <div class="field">
          <label>Summary</label>
          <Textarea v-model="newStoryline.summary" rows="3" />
        </div>
        <div class="field">
          <label>Genre</label>
          <Dropdown v-model="newStoryline.genre" :options="genreOptions" />
        </div>
        <div class="field">
          <label>Theme</label>
          <InputText v-model="newStoryline.theme" />
        </div>
        <div class="field">
          <label>Target Audience</label>
          <Dropdown v-model="newStoryline.target_audience" :options="audienceOptions" />
        </div>
      </div>
      <template #footer>
        <Button label="Cancel" @click="showNewStorylineDialog = false" severity="secondary" />
        <Button label="Create" @click="createStoryline" />
      </template>
    </Dialog>

    <!-- New Episode Dialog -->
    <Dialog v-model:visible="showNewEpisodeDialog" header="Add Episode" :modal="true" :style="{width: '450px'}">
      <div class="p-fluid">
        <div class="field">
          <label>Title</label>
          <InputText v-model="newEpisode.title" />
        </div>
        <div class="field">
          <label>Description</label>
          <Textarea v-model="newEpisode.description" rows="3" />
        </div>
      </div>
      <template #footer>
        <Button label="Cancel" @click="showNewEpisodeDialog = false" severity="secondary" />
        <Button label="Add" @click="addEpisodeToStoryline" />
      </template>
    </Dialog>

    <!-- Quality Gates Overview Dialog -->
    <Dialog v-model:visible="showQualityGatesDialog" header="Quality Gates Overview" :modal="true" :style="{width: '700px'}">
      <DataTable :value="Object.entries(qualityGatesData)" responsiveLayout="scroll">
        <Column header="Project">
          <template #body="slotProps">
            <span class="font-semibold">{{ slotProps.data[0] }}</span>
          </template>
        </Column>
        <Column header="Style">
          <template #body="slotProps">
            <span class="text-sm">{{ slotProps.data[1].style }}</span>
          </template>
        </Column>
        <Column header="Min Images">
          <template #body="slotProps">
            <Badge :value="slotProps.data[1].minApprovedImages" severity="warning" />
          </template>
        </Column>
        <Column header="Model">
          <template #body="slotProps">
            <span class="text-xs font-mono">{{ slotProps.data[1].model.split('.')[0] }}</span>
          </template>
        </Column>
      </DataTable>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useAnimeStore } from '../stores/anime'
import { useToast } from 'primevue/usetoast'

const store = useAnimeStore()
const toast = useToast()

// Props
const props = defineProps({
  selectedProject: Object
})

// State
const storylines = ref([])
const selectedStoryline = ref(null)
const storylinesLoading = ref(false)

const episodes = ref([])
const selectedEpisode = ref(null)
const episodesLoading = ref(false)

const characters = ref([])
const characterApprovals = ref({})

const showNewStorylineDialog = ref(false)
const showNewEpisodeDialog = ref(false)
const showQualityGatesDialog = ref(false)

const newStoryline = ref({
  title: '',
  summary: '',
  genre: 'Anime Adventure',
  theme: '',
  target_audience: 'All Ages'
})

const newEpisode = ref({
  title: '',
  description: ''
})

const genreOptions = ref([
  'Anime Adventure',
  'Sci-Fi Anime',
  'Fantasy Anime',
  'Cyberpunk',
  'Slice of Life',
  'Mystery'
])

const audienceOptions = ref([
  'All Ages',
  'Teen',
  'Young Adult',
  'Mature'
])

// Quality gates data from store
const qualityGatesData = computed(() => store.qualityGates)
const currentQualityGate = computed(() => {
  if (!props.selectedProject) return null
  return store.qualityGates[props.selectedProject.name] || null
})

// Load storylines when project changes
watch(() => props.selectedProject, async (newProject) => {
  if (newProject) {
    await loadStorylines(newProject.id)
    await loadCharacters(newProject.id)
  } else {
    storylines.value = []
    characters.value = []
  }
})

async function loadStorylines(projectId) {
  storylinesLoading.value = true
  try {
    const response = await fetch(`/api/anime/storylines?project_id=${projectId}`)
    if (response.ok) {
      const data = await response.json()
      storylines.value = data.storylines || []
    }
  } catch (error) {
    console.error('Failed to load storylines:', error)
  } finally {
    storylinesLoading.value = false
  }
}

async function loadCharacters(projectId) {
  try {
    const response = await fetch(`/api/anime/characters?project_id=${projectId}`)
    if (response.ok) {
      const data = await response.json()
      characters.value = data.characters || []

      // Load approval status for each character
      for (const character of characters.value) {
        await loadCharacterApproval(projectId, character.name)
      }
    }
  } catch (error) {
    console.error('Failed to load characters:', error)
  }
}

async function loadCharacterApproval(projectId, characterName) {
  try {
    const response = await fetch(`/api/anime/approvals/${projectId}/${characterName}`)
    if (response.ok) {
      const data = await response.json()
      characterApprovals.value[characterName] = {
        approved: data.approved_count || 0,
        rejected: data.rejected_count || 0,
        pending: data.pending_count || 0
      }
    }
  } catch (error) {
    console.error('Failed to load approval for', characterName, error)
  }
}

async function selectStoryline(storyline) {
  selectedStoryline.value = storyline
  selectedEpisode.value = null

  if (storyline.episodes && storyline.episodes.length > 0) {
    episodesLoading.value = true
    try {
      // Load episode details for UUIDs
      const episodePromises = storyline.episodes.map(async (episodeId) => {
        const response = await fetch(`/api/anime/episodes/${episodeId}`)
        if (response.ok) {
          return await response.json()
        }
        return null
      })

      const loadedEpisodes = await Promise.all(episodePromises)
      episodes.value = loadedEpisodes.filter(e => e !== null)
    } catch (error) {
      console.error('Failed to load episodes:', error)
      episodes.value = []
    } finally {
      episodesLoading.value = false
    }
  } else {
    episodes.value = []
  }
}

function selectEpisode(episode) {
  selectedEpisode.value = episode
  // Could load scenes here if needed
}

async function createStoryline() {
  if (!props.selectedProject) return

  try {
    const response = await fetch('/api/anime/storylines', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...newStoryline.value,
        project_id: props.selectedProject.id,
        status: 'active'
      })
    })

    if (response.ok) {
      toast.add({ severity: 'success', summary: 'Success', detail: 'Storyline created', life: 3000 })
      showNewStorylineDialog.value = false
      newStoryline.value = {
        title: '',
        summary: '',
        genre: 'Anime Adventure',
        theme: '',
        target_audience: 'All Ages'
      }
      await loadStorylines(props.selectedProject.id)
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to create storyline', life: 3000 })
  }
}

async function addEpisodeToStoryline() {
  if (!selectedStoryline.value || !props.selectedProject) return

  try {
    // First create the episode
    const episodeResponse = await fetch('/api/anime/episodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...newEpisode.value,
        project_id: props.selectedProject.id,
        status: 'planning'
      })
    })

    if (episodeResponse.ok) {
      const episode = await episodeResponse.json()

      // Then add it to the storyline
      const updatedEpisodes = [...(selectedStoryline.value.episodes || []), episode.id]
      const updateResponse = await fetch(`/api/anime/storylines/${selectedStoryline.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          episodes: updatedEpisodes
        })
      })

      if (updateResponse.ok) {
        toast.add({ severity: 'success', summary: 'Success', detail: 'Episode added', life: 3000 })
        showNewEpisodeDialog.value = false
        newEpisode.value = { title: '', description: '' }
        await selectStoryline(selectedStoryline.value)
      }
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to add episode', life: 3000 })
  }
}

function getApprovalStatus(character) {
  const approved = characterApprovals.value[character.name]?.approved || 0
  const required = currentQualityGate.value?.minApprovedImages || 0

  if (approved >= required) {
    return { text: 'Ready', severity: 'success' }
  } else if (approved > 0) {
    return { text: `${required - approved} more`, severity: 'warning' }
  } else {
    return { text: 'Not Started', severity: 'danger' }
  }
}

function getApprovalProgress(character) {
  const approved = characterApprovals.value[character.name]?.approved || 0
  const required = currentQualityGate.value?.minApprovedImages || 1
  return Math.min((approved / required) * 100, 100)
}

function getStatusSeverity(status) {
  const map = {
    'active': 'success',
    'planning': 'info',
    'pending': 'warning',
    'completed': 'success',
    'failed': 'danger',
    'archived': 'secondary'
  }
  return map[status] || 'secondary'
}

onMounted(() => {
  if (props.selectedProject) {
    loadStorylines(props.selectedProject.id)
    loadCharacters(props.selectedProject.id)
  }
})
</script>

<style scoped>
.storyline-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  transition: all 0.2s;
}

.storyline-card:hover {
  background: #222;
  border-color: #555;
}

.storyline-card.selected {
  background: #2a2a2a;
  border-color: #ff8c00;
}

.episode-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.episode-card:hover {
  background: #222;
}

.episode-card.selected {
  background: #2a2a2a;
  border-color: #667eea;
}

.quality-gate-card {
  background: #1a1a1a;
  border: 1px solid #333;
}

.storylines-container {
  max-height: 400px;
  overflow-y: auto;
}

.episodes-list {
  max-height: 400px;
  overflow-y: auto;
}
</style>