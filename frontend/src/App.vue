<template>
  <div class="dark-mode" style="height: 100vh; background: #0a0a0a; color: #e0e0e0;">
    <Toast />
    <ProgressBar v-if="isGenerating" mode="indeterminate" style="height: 4px; position: fixed; top: 0; left: 0; right: 0; z-index: 9999" />

    <Toolbar style="background: #1a1a1a; border-bottom: 1px solid #333; padding: 0.5rem 1rem;">
      <template #start>
        <h2 style="margin: 0; font-size: 1.5rem; font-weight: 600;">
          <i class="pi pi-video" style="margin-right: 0.5rem; color: #ff8c00;"></i>
          Tower Anime Production
        </h2>
      </template>
      <template #end>
        <div class="flex align-items-center gap-2">
          <Tag v-if="connectionStatus === 'connected'"
               value="Live" severity="success" icon="pi pi-circle-fill" />
          <Tag v-else-if="connectionStatus === 'connecting'"
               value="Connecting" severity="warning" icon="pi pi-spin pi-spinner" />
          <Tag v-else
               value="Offline" severity="danger" icon="pi pi-circle" />
          <Button label="New Project" icon="pi pi-plus" @click="showNewProjectDialog = true"
                  style="margin-left: 1rem;" />
        </div>
      </template>
    </Toolbar>

    <!-- Main Content with Tabs -->
    <div style="height: calc(100vh - 60px); display: flex;">
      <!-- Left Panel: Projects -->
      <div style="width: 250px; background: #111; border-right: 1px solid #333; overflow-y: auto;">
        <div style="padding: 1rem;">
          <h3 style="margin-top: 0; color: #ff8c00;">Projects</h3>
          <InputText v-model="projectSearch" placeholder="Search projects..."
                     style="width: 100%; margin-bottom: 1rem;" icon="pi pi-search" />

          <div v-for="project in filteredProjects" :key="project.id"
               @click="selectProject(project)"
               :class="['project-card', { 'selected': selectedProject?.id === project.id }]"
               style="padding: 0.75rem; margin-bottom: 0.5rem; border: 1px solid #333; border-radius: 6px; cursor: pointer; transition: all 0.2s;">
            <div style="font-weight: 600; margin-bottom: 0.25rem;">{{ project.name }}</div>
            <div class="flex gap-1 mt-1">
              <Tag :value="project.status" :severity="getStatusSeverity(project.status)" class="text-xs" />
              <Tag v-if="qualityGates[project.name]" value="QG" severity="warning"
                   class="text-xs" title="Quality Gate Configured" />
            </div>
            <div style="font-size: 0.75rem; color: #666; margin-top: 0.25rem;">{{ formatDate(project.created_at) }}</div>
          </div>

          <!-- Characters Section -->
          <div v-if="selectedProject" class="mt-3">
            <h4 style="color: #ff8c00;">Characters</h4>
            <div v-if="charactersLoading" class="text-center p-2">
              <ProgressSpinner style="width: 20px; height: 20px;" />
            </div>
            <div v-else-if="characters.length === 0" class="text-center text-500 p-2">
              No characters
            </div>
            <div v-else>
              <div v-for="char in characters" :key="char.id"
                   @click="selectedCharacter = char.name"
                   class="character-item p-2 mb-1"
                   :class="{ 'selected': selectedCharacter === char.name }">
                <div class="text-sm font-semibold">{{ char.name }}</div>
                <div class="text-xs text-500">{{ char.role || 'No role' }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Panel: Tab Content -->
      <div style="flex: 1; display: flex; flex-direction: column;">
        <!-- Tab Menu -->
        <TabMenu v-model:activeIndex="activeTab" :model="tabItems"
                 style="border-bottom: 1px solid #333;" />

        <!-- Tab Content -->
        <div style="flex: 1; overflow-y: auto;">
          <!-- Scenes Tab -->
          <div v-if="activeTab === 0" style="padding: 1rem;">

            <div class="flex justify-content-between align-items-center mb-3">
              <h3 class="m-0">Scenes</h3>
              <Button label="New Scene" icon="pi pi-plus" @click="showNewSceneDialog = true"
                      :disabled="!selectedProject" size="small" />
            </div>

            <DataTable :value="scenes" v-model:selection="selectedScene" selectionMode="single"
                       :paginator="true" :rows="10"
                       :rowHover="true"
                       @row-select="onSceneSelect">
              <Column field="scene_number" header="#" style="width: 60px;"></Column>
              <Column field="description" header="Description" style="max-width: 400px;"></Column>
              <Column field="characters" header="Characters" style="max-width: 200px;">
                <template #body="slotProps">
                  {{ slotProps.data.characters || 'None' }}
                </template>
              </Column>
              <Column field="status" header="Status" style="width: 120px;">
                <template #body="slotProps">
                  <Tag :value="slotProps.data.status" :severity="getStatusSeverity(slotProps.data.status)" />
                </template>
              </Column>
              <Column header="Actions" style="width: 150px;">
                <template #body="slotProps">
                  <Button icon="pi pi-play" @click="generateSceneById(slotProps.data.id)"
                          size="small" severity="success" text rounded />
                  <Button icon="pi pi-eye" v-if="slotProps.data.video_path"
                          @click="viewVideo(slotProps.data.video_path)" size="small" text rounded />
                </template>
              </Column>
            </DataTable>
          </div>

          <!-- Storylines Tab -->
          <div v-if="activeTab === 1" style="padding: 1rem;">
            <StorylineManager :selectedProject="selectedProject" />
          </div>

          <!-- Smart Feedback Tab -->
          <div v-if="activeTab === 2" style="padding: 1rem;">
            <SmartFeedback :selectedProject="selectedProject" :selectedCharacter="selectedCharacter" />
          </div>

          <!-- Episodes Tab -->
          <div v-if="activeTab === 3" style="padding: 1rem;">
            <EpisodeManager :selectedProject="selectedProject" />
          </div>

          <!-- Music Tab -->
          <div v-if="activeTab === 4" style="padding: 1rem;">
            <MusicManager :selectedProject="selectedProject" />
          </div>
        </div>
      </div>

      <!-- Properties Panel (conditional) -->
      <div v-if="showPropertiesPanel" style="width: 300px; background: #111; border-left: 1px solid #333; padding: 1rem; overflow-y: auto;">
        <div class="flex justify-content-between align-items-center mb-3">
          <h3 style="margin-top: 0; color: #ff8c00;">Properties</h3>
          <Button icon="pi pi-times" @click="showPropertiesPanel = false"
                  text rounded size="small" />
        </div>

        <div v-if="selectedProject && !selectedScene">
          <Card style="background: #1a1a1a; border: 1px solid #333;">
            <template #title>
              <span class="text-sm">{{ selectedProject.name }}</span>
            </template>
            <template #content>
              <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; font-size: 0.875rem;">Description</label>
                <Textarea v-model="selectedProject.description" rows="3" style="width: 100%;" />
              </div>
              <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; font-size: 0.875rem;">Status</label>
                <Dropdown v-model="selectedProject.status"
                         :options="['active', 'planning', 'completed', 'archived']"
                         style="width: 100%;" />
              </div>
              <Button label="Save" icon="pi pi-save" @click="saveProject" style="width: 100%;" size="small" />
            </template>
          </Card>
        </div>

        <div v-if="selectedScene">
          <Card style="background: #1a1a1a; border: 1px solid #333;">
            <template #title>
              <span class="text-sm">Scene {{ selectedScene.scene_number }}</span>
            </template>
            <template #content>
              <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; font-size: 0.875rem;">Description</label>
                <Textarea v-model="selectedScene.description" rows="3" style="width: 100%;" />
              </div>
              <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; font-size: 0.875rem;">Characters</label>
                <InputText v-model="selectedScene.characters" style="width: 100%;" />
              </div>
              <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; font-size: 0.875rem;">Status</label>
                <Tag :value="selectedScene.status" :severity="getStatusSeverity(selectedScene.status)" />
              </div>
              <Button label="Save" icon="pi pi-save" @click="saveScene" style="width: 100%; margin-bottom: 0.5rem;" size="small" />
              <Button label="Generate" icon="pi pi-play" @click="generateScene" severity="success" style="width: 100%;" :loading="isGenerating" size="small" />
              <div v-if="isGenerating" style="margin-top: 1rem;">
                <ProgressBar :value="generationProgress" :showValue="true" style="height: 20px;" />
                <p style="text-align: center; margin-top: 0.5rem; font-size: 0.75rem;">{{ generationProgress }}%</p>
              </div>
              <div v-if="previewUrl" style="margin-top: 1rem;">
                <label class="text-xs">Preview:</label>
                <video v-if="previewUrl.endsWith('.mp4')" :src="previewUrl" controls style="width: 100%; border-radius: 4px;" />
                <img v-else :src="previewUrl" style="width: 100%; border-radius: 4px;" />
              </div>
            </template>
          </Card>
        </div>

        <div v-if="!selectedProject && !selectedScene" style="text-align: center; color: #666; margin-top: 2rem;">
          <i class="pi pi-info-circle" style="font-size: 2rem; margin-bottom: 1rem;"></i>
          <p class="text-sm">Select an item</p>
        </div>
      </div>
    </div>

    <!-- New Project Dialog -->
    <Dialog v-model:visible="showNewProjectDialog" header="New Project" :modal="true" :style="{'width': '450px'}">
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Project Name</label>
        <InputText v-model="newProject.name" style="width: 100%;" />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Description</label>
        <Textarea v-model="newProject.description" rows="4" style="width: 100%;" />
      </div>
      <template #footer>
        <Button label="Cancel" @click="showNewProjectDialog = false" severity="secondary" />
        <Button label="Create" @click="createProject" />
      </template>
    </Dialog>

    <!-- New Scene Dialog -->
    <Dialog v-model:visible="showNewSceneDialog" header="New Scene" :modal="true" :style="{'width': '450px'}">
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Scene Number</label>
        <InputText v-model.number="newScene.scene_number" type="number" style="width: 100%;" />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Description</label>
        <Textarea v-model="newScene.description" rows="4" style="width: 100%;" />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Characters</label>
        <InputText v-model="newScene.characters" style="width: 100%;" />
      </div>
      <template #footer>
        <Button label="Cancel" @click="showNewSceneDialog = false" severity="secondary" />
        <Button label="Create" @click="createScene" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useAnimeStore } from './stores/anime'
import StorylineManager from './components/StorylineManager.vue'
import SmartFeedback from './components/SmartFeedback.vue'
import EpisodeManager from './views/EpisodeManager.vue'
import MusicManager from './components/MusicManager.vue'

const toast = useToast()
const store = useAnimeStore()
const API_BASE = '/api/anime'

// State
const projects = ref([])
const scenes = ref([])
const characters = ref([])
const selectedProject = ref(null)
const selectedScene = ref(null)
const selectedCharacter = ref(null)
const projectSearch = ref('')
const showNewProjectDialog = ref(false)
const showNewSceneDialog = ref(false)
const showPropertiesPanel = ref(true)
const isGenerating = ref(false)
const generationProgress = ref(0)
const previewUrl = ref(null)
const charactersLoading = ref(false)

// Tab state
const activeTab = ref(0)
const tabItems = ref([
  { label: 'Scenes', icon: 'pi pi-video' },
  { label: 'Storylines', icon: 'pi pi-book' },
  { label: 'Smart Feedback', icon: 'pi pi-check-circle' },
  { label: 'Episodes', icon: 'pi pi-list' },
  { label: 'Music', icon: 'pi pi-volume-up' }
])

// WebSocket state
const websocket = ref(null)
const connectionStatus = ref('disconnected')

// Quality gates from store
const qualityGates = computed(() => store.qualityGates)

const newProject = ref({ name: '', description: '' })
const newScene = ref({ scene_number: 1, description: '', characters: '' })

// Computed
const filteredProjects = computed(() => {
  if (!projectSearch.value) return projects.value
  return projects.value.filter(p =>
    p.name.toLowerCase().includes(projectSearch.value.toLowerCase())
  )
})

// Methods
function connectWebSocket() {
  const wsUrl = `ws://localhost:8328/ws/director-studio`
  websocket.value = new WebSocket(wsUrl)
  connectionStatus.value = 'connecting'

  websocket.value.onopen = () => {
    connectionStatus.value = 'connected'
    toast.add({ severity: 'success', summary: 'Connected', detail: 'Real-time updates enabled', life: 2000 })
  }

  websocket.value.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      handleWebSocketMessage(message)
    } catch (e) {
      console.error('WebSocket message parse error:', e)
    }
  }

  websocket.value.onclose = () => {
    connectionStatus.value = 'disconnected'
    setTimeout(() => {
      if (connectionStatus.value === 'disconnected') {
        connectWebSocket()
      }
    }, 3000)
  }

  websocket.value.onerror = (error) => {
    console.error('WebSocket error:', error)
    connectionStatus.value = 'disconnected'
  }
}

function handleWebSocketMessage(message) {
  switch (message.type) {
    case 'generation_update':
      if (message.data) {
        generationProgress.value = message.data.progress || 0
        if (message.data.status === 'completed') {
          isGenerating.value = false
          loadScenes(selectedProject.value.id)
          toast.add({ severity: 'success', summary: 'Complete', detail: message.data.message, life: 3000 })
        }
      }
      break
    case 'project_update':
      loadProjects()
      break
  }
}

async function loadProjects() {
  try {
    const response = await fetch(`${API_BASE}/projects`)
    if (response.ok) {
      projects.value = await response.json()
    } else if (response.status === 401) {
      toast.add({
        severity: 'warn',
        summary: 'Guest Mode',
        detail: 'Viewing in guest mode - authentication required for full features',
        life: 5000
      })
    } else {
      throw new Error(`HTTP ${response.status}`)
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: `Failed to load projects: ${error.message}`,
      life: 3000
    })
  }
}

async function selectProject(project) {
  selectedProject.value = project
  selectedScene.value = null
  selectedCharacter.value = null
  store.selectProject(project)
  await loadScenes(project.id)
  await loadCharacters(project.id)
}

async function loadCharacters(projectId) {
  charactersLoading.value = true
  try {
    const response = await fetch(`${API_BASE}/characters?project_id=${projectId}`)
    if (response.ok) {
      const data = await response.json()
      characters.value = data.characters || []
    }
  } catch (error) {
    console.error('Failed to load characters:', error)
  } finally {
    charactersLoading.value = false
  }
}

async function loadScenes(projectId) {
  try {
    const response = await fetch(`${API_BASE}/episodes/${projectId}/scenes`)
    scenes.value = await response.json()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to load scenes', life: 3000 })
  }
}

function onSceneSelect(event) {
  selectedScene.value = event.data
}

async function createProject() {

  try {
    const response = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newProject.value)
    })


    const project = await response.json()
    projects.value.push(project)
    showNewProjectDialog.value = false
    newProject.value = { name: '', description: '' }
    toast.add({ severity: 'success', summary: 'Success', detail: 'Project created', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to create project', life: 3000 })
  }
}

async function createScene() {
  if (!selectedProject.value) return

  try {
    const response = await fetch(`${API_BASE}/episodes/${selectedProject.value.id}/scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newScene.value)
    })


    const scene = await response.json()
    scenes.value.push(scene)
    showNewSceneDialog.value = false
    newScene.value = { scene_number: scenes.value.length + 1, description: '', characters: '' }
    toast.add({ severity: 'success', summary: 'Success', detail: 'Scene created', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to create scene', life: 3000 })
  }
}

async function saveProject() {
  if (!selectedProject.value) return

  try {
    await fetch(`${API_BASE}/episodes/${selectedProject.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedProject.value)
    })
    toast.add({ severity: 'success', summary: 'Success', detail: 'Project saved', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to save project', life: 3000 })
  }
}

async function saveScene() {
  if (!selectedScene.value || !selectedProject.value) return

  try {
    await fetch(`${API_BASE}/scenes/${selectedScene.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedScene.value)
    })
    toast.add({ severity: 'success', summary: 'Success', detail: 'Scene saved', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to save scene', life: 3000 })
  }
}

async function generateScene() {
  if (!selectedScene.value) return

  isGenerating.value = true
  generationProgress.value = 0
  previewUrl.value = null

  try {
    const response = await fetch(`${API_BASE}/projects/${selectedProject.value?.id || 1}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: selectedScene.value.description || 'anime scene',
        generation_type: 'video'
      })
    })


    const result = await response.json()
    toast.add({ severity: 'success', summary: 'Generation Started', detail: `Job ID: ${result.job_id}`, life: 5000 })

    // Simulate progress updates
    const progressInterval = setInterval(() => {
      generationProgress.value = Math.min(generationProgress.value + Math.random() * 20, 100)

      if (generationProgress.value >= 100) {
        clearInterval(progressInterval)
        isGenerating.value = false
        previewUrl.value = `/api/anime/output/${result.job_id}.mp4`
        loadScenes(selectedProject.value.id)
      }
    }, 1000)
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Generation failed', life: 3000 })
    isGenerating.value = false
  }
}

function generateSceneById(sceneId) {
  toast.add({ severity: 'info', summary: 'Generation Started', detail: `Scene ${sceneId} generation queued`, life: 3000 })
}

function viewVideo(videoPath) {
  toast.add({ severity: 'info', summary: 'Video', detail: `Video: ${videoPath}`, life: 3000 })
}

function getStatusSeverity(status) {
  const statusMap = {
    'active': 'success',
    'pending': 'warning',
    'processing': 'info',
    'completed': 'success',
    'failed': 'danger'
  }
  return statusMap[status] || 'secondary'
}

function formatDate(dateString) {
  if (!dateString) return ''
  return new Date(dateString).toLocaleDateString()
}

// Initialize
onMounted(async () => {
  connectWebSocket()
  await loadProjects()
  await store.loadProjects()
})

onUnmounted(() => {
  if (websocket.value) {
    websocket.value.close()
  }
})
</script>

<style scoped>
.project-card:hover {
  background: #222;
  border-color: #555 !important;
}

.project-card.selected {
  background: #2a2a2a;
  border-color: #ff8c00 !important;
}

.character-item {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.character-item:hover {
  background: #222;
}

.character-item.selected {
  background: #2a2a2a;
  border-color: #667eea;
}

:deep(.p-tabmenu) {
  background: #1a1a1a;
}

:deep(.p-tabmenu .p-tabmenu-nav) {
  background: transparent;
  border: none;
}

:deep(.p-tabmenu .p-menuitem-link) {
  background: transparent;
  color: #999;
}

:deep(.p-tabmenu .p-menuitem-link:hover) {
  background: #222;
  color: #fff;
}

:deep(.p-tabmenu .p-menuitem-link.p-menuitem-link-active) {
  background: #222;
  color: #ff8c00;
  border-bottom: 2px solid #ff8c00;
}
</style>
