<template>
  <div class="music-manager">
    <div class="flex justify-content-between align-items-center mb-4">
      <h3 class="m-0">Apple Music Integration</h3>
      <div class="flex gap-2">
        <Button
          label="Connect Apple Music"
          icon="pi pi-link"
          @click="connectAppleMusic"
          :disabled="appleAuthStatus === 'connected'"
          size="small"
        />
        <Button
          label="Refresh Playlists"
          icon="pi pi-refresh"
          @click="loadPlaylists"
          :loading="playlistsLoading"
          :disabled="appleAuthStatus !== 'connected'"
          size="small"
        />
      </div>
    </div>

    <!-- Apple Music Connection Status -->
    <Card class="mb-4" style="background: #1a1a1a; border: 1px solid #333;">
      <template #content>
        <div class="flex align-items-center gap-3">
          <i class="pi pi-apple" style="font-size: 2rem; color: #999;"></i>
          <div>
            <div class="font-semibold">
              Apple Music Status:
              <Tag
                :value="appleAuthStatus"
                :severity="appleAuthStatus === 'connected' ? 'success' : 'warning'"
              />
            </div>
            <div class="text-sm text-500 mt-1">
              {{ appleAuthMessage }}
            </div>
          </div>
        </div>
      </template>
    </Card>

    <!-- Playlists Section -->
    <div v-if="appleAuthStatus === 'connected'">
      <div class="flex justify-content-between align-items-center mb-3">
        <h4 class="m-0">Your Playlists</h4>
        <div class="flex align-items-center gap-2">
          <InputText
            v-model="playlistSearch"
            placeholder="Search playlists..."
            style="width: 250px;"
            icon="pi pi-search"
          />
          <Button
            icon="pi pi-plus"
            label="Create Anime Playlist"
            @click="showCreatePlaylistDialog = true"
            size="small"
            severity="success"
          />
        </div>
      </div>

      <!-- Playlists Loading -->
      <div v-if="playlistsLoading" class="text-center p-4">
        <ProgressSpinner style="width: 30px; height: 30px;" />
        <p class="mt-2">Loading playlists...</p>
      </div>

      <!-- Playlists Grid -->
      <div v-else class="grid">
        <div
          v-for="playlist in filteredPlaylists"
          :key="playlist.id"
          class="col-12 md:col-6 lg:col-4"
        >
          <Card
            class="playlist-card cursor-pointer"
            :class="{ 'selected': selectedPlaylist?.id === playlist.id }"
            @click="selectPlaylist(playlist)"
            style="background: #1a1a1a; border: 1px solid #333;"
          >
            <template #header>
              <img
                v-if="playlist.artwork"
                :src="playlist.artwork"
                :alt="playlist.name"
                style="width: 100%; height: 200px; object-fit: cover;"
              />
              <div
                v-else
                class="placeholder-artwork"
                style="width: 100%; height: 200px; background: #333; display: flex; align-items: center; justify-content: center;"
              >
                <i class="pi pi-music" style="font-size: 3rem; color: #666;"></i>
              </div>
            </template>
            <template #title>
              <span class="text-sm">{{ playlist.name }}</span>
            </template>
            <template #content>
              <div class="text-xs text-500 mb-2">
                {{ playlist.description || 'No description' }}
              </div>
              <div class="flex align-items-center gap-2">
                <Tag
                  :value="`${playlist.trackCount || 0} tracks`"
                  severity="info"
                  class="text-xs"
                />
                <Tag
                  v-if="playlist.isAnimeRelated"
                  value="Anime"
                  severity="success"
                  class="text-xs"
                />
              </div>
            </template>
            <template #footer>
              <div class="flex gap-1">
                <Button
                  icon="pi pi-play"
                  @click.stop="previewPlaylist(playlist)"
                  size="small"
                  text
                  rounded
                  title="Preview"
                />
                <Button
                  icon="pi pi-link"
                  @click.stop="linkToProject(playlist)"
                  :disabled="!selectedProject"
                  size="small"
                  text
                  rounded
                  title="Link to Project"
                />
                <Button
                  icon="pi pi-cog"
                  @click.stop="analyzeForAnime(playlist)"
                  size="small"
                  text
                  rounded
                  title="Analyze for Anime"
                />
              </div>
            </template>
          </Card>
        </div>
      </div>

      <!-- No Playlists -->
      <div v-if="!playlistsLoading && playlists.length === 0" class="text-center p-4">
        <i class="pi pi-music" style="font-size: 3rem; color: #666; margin-bottom: 1rem;"></i>
        <p class="text-500">No playlists found</p>
        <Button
          label="Create Your First Anime Playlist"
          icon="pi pi-plus"
          @click="showCreatePlaylistDialog = true"
          size="small"
        />
      </div>
    </div>

    <!-- Selected Playlist Details -->
    <div v-if="selectedPlaylist" class="mt-4">
      <Card style="background: #1a1a1a; border: 1px solid #333;">
        <template #title>
          <span class="text-lg">{{ selectedPlaylist.name }}</span>
        </template>
        <template #content>
          <div class="mb-3">
            <div class="text-sm text-500 mb-2">Tracks ({{ selectedPlaylist.trackCount }})</div>
            <DataTable
              :value="selectedPlaylistTracks"
              :paginator="true"
              :rows="5"
              :loading="tracksLoading"
            >
              <Column field="name" header="Track" style="width: 40%;"></Column>
              <Column field="artist" header="Artist" style="width: 30%;"></Column>
              <Column field="album" header="Album" style="width: 20%;"></Column>
              <Column header="Actions" style="width: 10%;">
                <template #body="slotProps">
                  <Button
                    icon="pi pi-waveform"
                    @click="analyzeBPM(slotProps.data)"
                    size="small"
                    text
                    rounded
                    title="Analyze BPM"
                  />
                </template>
              </Column>
            </DataTable>
          </div>

          <div v-if="selectedProject" class="flex gap-2">
            <Button
              label="Generate Anime Video with Music"
              icon="pi pi-video"
              @click="generateAnimeWithMusic"
              :disabled="!selectedPlaylist"
              severity="success"
            />
            <Button
              label="Sync to Scene BPM"
              icon="pi pi-sync"
              @click="syncToSceneBPM"
              :disabled="!selectedPlaylist"
            />
          </div>
        </template>
      </Card>
    </div>

    <!-- Create Playlist Dialog -->
    <Dialog
      v-model:visible="showCreatePlaylistDialog"
      header="Create Anime Playlist"
      :modal="true"
      :style="{'width': '500px'}"
    >
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Playlist Name</label>
        <InputText v-model="newPlaylist.name" style="width: 100%;" placeholder="e.g., Mario Galaxy Soundtrack" />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Description</label>
        <Textarea v-model="newPlaylist.description" rows="3" style="width: 100%;" placeholder="Music for anime production..." />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Anime Project</label>
        <Dropdown
          v-model="newPlaylist.projectId"
          :options="projectOptions"
          optionLabel="label"
          optionValue="value"
          style="width: 100%;"
          placeholder="Select project to link"
        />
      </div>
      <template #footer>
        <Button label="Cancel" @click="showCreatePlaylistDialog = false" severity="secondary" />
        <Button label="Create Playlist" @click="createPlaylist" :loading="creatingPlaylist" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useToast } from 'primevue/usetoast'

const props = defineProps({
  selectedProject: {
    type: Object,
    default: null
  }
})

const toast = useToast()

// State
const appleAuthStatus = ref('disconnected')
const appleAuthMessage = ref('Connect your Apple Music account to access playlists')
const playlists = ref([])
const selectedPlaylist = ref(null)
const selectedPlaylistTracks = ref([])
const playlistsLoading = ref(false)
const tracksLoading = ref(false)
const playlistSearch = ref('')
const showCreatePlaylistDialog = ref(false)
const creatingPlaylist = ref(false)

const newPlaylist = ref({
  name: '',
  description: '',
  projectId: null
})

// Computed
const filteredPlaylists = computed(() => {
  if (!playlistSearch.value) return playlists.value
  return playlists.value.filter(p =>
    p.name.toLowerCase().includes(playlistSearch.value.toLowerCase()) ||
    (p.description && p.description.toLowerCase().includes(playlistSearch.value.toLowerCase()))
  )
})

const projectOptions = computed(() => {
  // This would be populated with available projects
  return props.selectedProject ? [
    { label: props.selectedProject.name, value: props.selectedProject.id }
  ] : []
})

// Methods
async function connectAppleMusic() {
  try {
    // This would trigger Apple Music authentication flow
    // For now, we'll simulate successful connection
    appleAuthStatus.value = 'connecting'
    appleAuthMessage.value = 'Connecting to Apple Music...'

    // Simulate auth flow
    setTimeout(() => {
      appleAuthStatus.value = 'connected'
      appleAuthMessage.value = 'Connected to Apple Music successfully'
      loadPlaylists()
      toast.add({
        severity: 'success',
        summary: 'Connected',
        detail: 'Apple Music account connected successfully',
        life: 3000
      })
    }, 2000)
  } catch (error) {
    appleAuthStatus.value = 'error'
    appleAuthMessage.value = 'Failed to connect to Apple Music'
    toast.add({
      severity: 'error',
      summary: 'Connection Failed',
      detail: error.message,
      life: 3000
    })
  }
}

async function loadPlaylists() {
  if (appleAuthStatus.value !== 'connected') return

  playlistsLoading.value = true
  try {
    // Call the anime service music API
    const projectParam = props.selectedProject ? `?project_id=${props.selectedProject.id}` : ''
    const response = await fetch(`/api/anime/music/playlists${projectParam}`)

    if (response.ok) {
      const data = await response.json()
      playlists.value = data.data || []

      toast.add({
        severity: 'success',
        summary: 'Loaded',
        detail: `${playlists.value.length} playlists loaded`,
        life: 3000
      })
    } else {
      throw new Error('Failed to load playlists')
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load playlists: ' + error.message,
      life: 3000
    })
  } finally {
    playlistsLoading.value = false
  }
}

function isAnimeRelated(playlist) {
  const animeKeywords = ['anime', 'soundtrack', 'ost', 'opening', 'ending', 'theme', 'mario', 'galaxy', 'adventure']
  const name = playlist.name.toLowerCase()
  const description = (playlist.description || '').toLowerCase()

  return animeKeywords.some(keyword =>
    name.includes(keyword) || description.includes(keyword)
  )
}

async function selectPlaylist(playlist) {
  selectedPlaylist.value = playlist
  await loadPlaylistTracks(playlist)
}

async function loadPlaylistTracks(playlist) {
  tracksLoading.value = true
  try {
    const response = await fetch(`/api/anime/music/playlists/${playlist.id}/tracks`)

    if (response.ok) {
      const data = await response.json()
      selectedPlaylistTracks.value = data.data || []
    } else {
      console.error('Failed to load tracks:', response.statusText)
    }
  } catch (error) {
    console.error('Failed to load tracks:', error)
  } finally {
    tracksLoading.value = false
  }
}

async function createPlaylist() {
  if (!newPlaylist.value.name) return

  creatingPlaylist.value = true
  try {
    // This would create playlist via Apple Music API
    const playlist = {
      id: Date.now().toString(),
      name: newPlaylist.value.name,
      description: newPlaylist.value.description,
      trackCount: 0,
      isAnimeRelated: true,
      projectId: newPlaylist.value.projectId
    }

    playlists.value.push(playlist)
    showCreatePlaylistDialog.value = false
    newPlaylist.value = { name: '', description: '', projectId: null }

    toast.add({
      severity: 'success',
      summary: 'Created',
      detail: 'Playlist created successfully',
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to create playlist',
      life: 3000
    })
  } finally {
    creatingPlaylist.value = false
  }
}

async function previewPlaylist(playlist) {
  toast.add({
    severity: 'info',
    summary: 'Preview',
    detail: `Playing preview of ${playlist.name}`,
    life: 3000
  })
}

async function linkToProject(playlist) {
  if (!props.selectedProject) return

  toast.add({
    severity: 'success',
    summary: 'Linked',
    detail: `${playlist.name} linked to ${props.selectedProject.name}`,
    life: 3000
  })
}

async function analyzeForAnime(playlist) {
  toast.add({
    severity: 'info',
    summary: 'Analyzing',
    detail: `Analyzing ${playlist.name} for anime compatibility`,
    life: 3000
  })
}

async function analyzeBPM(track) {
  toast.add({
    severity: 'info',
    summary: 'BPM Analysis',
    detail: `${track.name}: ${track.bpm || 'Unknown'} BPM`,
    life: 3000
  })
}

async function generateAnimeWithMusic() {
  if (!selectedPlaylist.value || !props.selectedProject) return

  try {
    const response = await fetch('/api/anime/music/sync/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        playlist_id: selectedPlaylist.value.id,
        project_id: props.selectedProject.id,
        sync_mode: 'auto'
      })
    })

    if (response.ok) {
      const result = await response.json()
      toast.add({
        severity: 'success',
        summary: 'Generation Started',
        detail: `Music-synced video generation started: ${result.job_id}`,
        life: 5000
      })
    } else {
      throw new Error('Failed to start generation')
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to start music-synced generation',
      life: 3000
    })
  }
}

async function syncToSceneBPM() {
  toast.add({
    severity: 'info',
    summary: 'Syncing',
    detail: 'Synchronizing music to scene timing',
    life: 3000
  })
}

// Watch for project changes
watch(() => props.selectedProject, (newProject) => {
  if (newProject && appleAuthStatus.value === 'connected') {
    // Filter playlists for current project
    console.log('Project changed:', newProject.name)
  }
})

// Initialize
onMounted(() => {
  // Check if we have stored Apple Music credentials/tokens
  // For now, start in disconnected state
})
</script>

<style scoped>
.playlist-card {
  transition: all 0.2s;
}

.playlist-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.3);
}

.playlist-card.selected {
  border-color: #ff8c00 !important;
}

:deep(.p-card-header) {
  padding: 0;
}

:deep(.p-card-body) {
  padding: 1rem;
}

:deep(.p-card-title) {
  margin-bottom: 0.5rem;
}

:deep(.p-card-content) {
  padding-top: 0;
}

:deep(.p-card-footer) {
  padding-top: 0;
}
</style>