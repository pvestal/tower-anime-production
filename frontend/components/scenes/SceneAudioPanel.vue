<template>
  <div style="border-top: 1px solid var(--border-primary); padding-top: 12px; margin-top: 12px;">
    <button
      style="display: flex; align-items: center; gap: 6px; background: none; border: none; cursor: pointer; color: var(--text-secondary); font-size: 12px; font-family: var(--font-primary); padding: 0; width: 100%;"
      @click="panelOpen = !panelOpen"
    >
      <span style="font-size: 10px;">{{ panelOpen ? '\u25BC' : '\u25B6' }}</span>
      <span>Audio Track</span>
      <span v-if="currentAudio" style="margin-left: auto; font-size: 10px; padding: 1px 6px; border-radius: 3px; background: rgba(80, 160, 80, 0.2); color: var(--status-success);">assigned</span>
      <span v-else-if="musicAuthorized" style="margin-left: auto; font-size: 10px; padding: 1px 6px; border-radius: 3px; background: rgba(122, 162, 247, 0.15); color: var(--accent-primary);">ready</span>
    </button>

    <div v-if="panelOpen" style="margin-top: 10px;">

      <!-- Currently assigned track -->
      <div v-if="currentAudio" class="assigned-track">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
          <div style="font-size: 20px; line-height: 1;">&#9835;</div>
          <div style="min-width: 0; flex: 1;">
            <div style="font-size: 12px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ currentAudio.track_name }}</div>
            <div style="font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ currentAudio.track_artist }}</div>
          </div>
        </div>
        <!-- Preview player -->
        <audio
          :src="currentAudio.preview_url"
          controls
          preload="none"
          style="width: 100%; height: 28px; margin-bottom: 6px;"
        ></audio>
        <!-- Fade controls -->
        <div style="display: flex; gap: 6px; margin-bottom: 6px;">
          <div style="flex: 1;">
            <label style="font-size: 10px; color: var(--text-muted); display: block;">Fade In (s)</label>
            <input
              type="number" min="0" max="10" step="0.5"
              :value="currentAudio.fade_in"
              @change="updateFade('fade_in', +($event.target as HTMLInputElement).value)"
              style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            />
          </div>
          <div style="flex: 1;">
            <label style="font-size: 10px; color: var(--text-muted); display: block;">Fade Out (s)</label>
            <input
              type="number" min="0" max="10" step="0.5"
              :value="currentAudio.fade_out"
              @change="updateFade('fade_out', +($event.target as HTMLInputElement).value)"
              style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            />
          </div>
          <div style="flex: 1;">
            <label style="font-size: 10px; color: var(--text-muted); display: block;">Offset (s)</label>
            <input
              type="number" min="0" max="30" step="1"
              :value="currentAudio.start_offset"
              @change="updateFade('start_offset', +($event.target as HTMLInputElement).value)"
              style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            />
          </div>
        </div>
        <button class="btn-small btn-danger" @click="removeAudio" :disabled="removing">
          {{ removing ? 'Removing...' : 'Remove Track' }}
        </button>
      </div>

      <!-- Auth status check -->
      <div v-else-if="checkingAuth" style="font-size: 12px; color: var(--text-muted);">Checking Apple Music...</div>

      <!-- Not authorized -->
      <div v-else-if="!musicAuthorized" style="font-size: 12px;">
        <div style="color: var(--text-secondary); margin-bottom: 8px;">
          Connect Apple Music to assign tracks to scenes.
        </div>
        <a
          href="/apple-music-auth"
          target="_blank"
          class="btn-small btn-primary"
          style="display: inline-block; text-decoration: none;"
          @click="scheduleRecheck"
        >Connect Apple Music</a>
      </div>

      <!-- Authorized: playlist browser -->
      <div v-else>
        <!-- Playlist selector -->
        <div style="margin-bottom: 8px;">
          <label style="font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 3px;">Playlist</label>
          <select
            v-model="selectedPlaylistId"
            @change="loadTracks"
            style="width: 100%; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
          >
            <option value="">Select playlist...</option>
            <option v-for="pl in playlists" :key="pl.id" :value="pl.id">{{ pl.name }}</option>
          </select>
        </div>

        <!-- Loading -->
        <div v-if="loadingTracks" style="font-size: 11px; color: var(--text-muted); padding: 8px 0;">Loading tracks...</div>

        <!-- Track list -->
        <div v-else-if="tracks.length > 0" style="max-height: 200px; overflow-y: auto; border: 1px solid var(--border-primary); border-radius: 3px;">
          <div
            v-for="track in tracks"
            :key="track.catalog_id || track.library_id"
            class="track-row"
            @click="assignTrack(track)"
          >
            <div style="min-width: 0; flex: 1;">
              <div style="font-size: 11px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                {{ track.name }}
              </div>
              <div style="font-size: 10px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                {{ track.artist }}
                <span v-if="track.duration_ms"> &middot; {{ formatDuration(track.duration_ms) }}</span>
              </div>
            </div>
            <span v-if="track.preview_url" style="font-size: 10px; color: var(--accent-primary); flex-shrink: 0;">assign</span>
            <span v-else style="font-size: 10px; color: var(--text-muted); flex-shrink: 0;">no preview</span>
          </div>
        </div>

        <!-- Assigning indicator -->
        <div v-if="assigning" style="font-size: 11px; color: var(--accent-primary); margin-top: 6px;">Assigning track...</div>

        <!-- Error -->
        <div v-if="error" style="font-size: 11px; color: var(--status-error); margin-top: 6px;">{{ error }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { SceneAudio, AppleMusicTrack, AppleMusicPlaylist } from '@/types'
import { scenesApi } from '@/api/scenes'

const props = defineProps<{
  sceneId: string | null
  audio: SceneAudio | null | undefined
}>()

const emit = defineEmits<{
  'audio-changed': [audio: SceneAudio | null]
}>()

const panelOpen = ref(false)
const checkingAuth = ref(false)
const musicAuthorized = ref(false)
const playlists = ref<AppleMusicPlaylist[]>([])
const selectedPlaylistId = ref('')
const tracks = ref<AppleMusicTrack[]>([])
const loadingTracks = ref(false)
const assigning = ref(false)
const removing = ref(false)
const error = ref('')

const currentAudio = ref<SceneAudio | null>(props.audio ?? null)

watch(() => props.audio, (val) => {
  currentAudio.value = val ?? null
})

onMounted(() => {
  checkAuth()
})

async function checkAuth() {
  checkingAuth.value = true
  try {
    const status = await scenesApi.getAppleMusicStatus()
    musicAuthorized.value = status.authorized
    if (status.authorized) {
      await loadPlaylists()
    }
  } catch {
    musicAuthorized.value = false
  } finally {
    checkingAuth.value = false
  }
}

function scheduleRecheck() {
  // After user opens auth in new tab, recheck periodically
  const interval = setInterval(async () => {
    try {
      const status = await scenesApi.getAppleMusicStatus()
      if (status.authorized) {
        musicAuthorized.value = true
        await loadPlaylists()
        clearInterval(interval)
      }
    } catch { /* ignore */ }
  }, 5000)
  // Stop after 2 minutes
  setTimeout(() => clearInterval(interval), 120000)
}

async function loadPlaylists() {
  try {
    const result = await scenesApi.getAppleMusicPlaylists()
    const rawData = result.data || []
    // Apple Music API returns { id, attributes: { name } } — normalize to AppleMusicPlaylist
    playlists.value = rawData.map((pl) => ({
      id: pl.id,
      name: pl.name || 'Untitled',
    }))
  } catch (e) {
    error.value = `Failed to load playlists: ${(e as Error).message}`
  }
}

async function loadTracks() {
  if (!selectedPlaylistId.value) {
    tracks.value = []
    return
  }
  loadingTracks.value = true
  error.value = ''
  try {
    const result = await scenesApi.getPlaylistTracks(selectedPlaylistId.value)
    tracks.value = result.tracks
  } catch (e) {
    error.value = `Failed to load tracks: ${(e as Error).message}`
    tracks.value = []
  } finally {
    loadingTracks.value = false
  }
}

async function assignTrack(track: AppleMusicTrack) {
  if (!track.preview_url || !props.sceneId) return
  assigning.value = true
  error.value = ''
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: track.catalog_id || track.library_id || '',
      preview_url: track.preview_url,
      track_name: track.name,
      track_artist: track.artist,
    })
    const newAudio: SceneAudio = {
      track_id: track.catalog_id || track.library_id || '',
      track_name: track.name,
      track_artist: track.artist,
      preview_url: track.preview_url,
      fade_in: 1.0,
      fade_out: 2.0,
      start_offset: 0,
    }
    currentAudio.value = newAudio
    emit('audio-changed', newAudio)
  } catch (e) {
    error.value = `Assign failed: ${(e as Error).message}`
  } finally {
    assigning.value = false
  }
}

async function removeAudio() {
  if (!props.sceneId) return
  removing.value = true
  try {
    await scenesApi.removeSceneAudio(props.sceneId)
    currentAudio.value = null
    emit('audio-changed', null)
  } catch (e) {
    error.value = `Remove failed: ${(e as Error).message}`
  } finally {
    removing.value = false
  }
}

async function updateFade(field: 'fade_in' | 'fade_out' | 'start_offset', value: number) {
  if (!props.sceneId || !currentAudio.value) return
  const updated = { ...currentAudio.value, [field]: value }
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: updated.track_id,
      preview_url: updated.preview_url,
      track_name: updated.track_name,
      track_artist: updated.track_artist,
      fade_in: updated.fade_in,
      fade_out: updated.fade_out,
      start_offset: updated.start_offset,
    })
    currentAudio.value = updated
    emit('audio-changed', updated)
  } catch { /* silent — user can retry */ }
}

function formatDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return `${min}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.assigned-track {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 8px;
}
.track-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-primary);
}
.track-row:last-child {
  border-bottom: none;
}
.track-row:hover {
  background: var(--bg-tertiary);
}
.btn-small {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 3px;
  border: none;
  cursor: pointer;
  font-family: var(--font-primary);
}
.btn-primary {
  background: var(--accent-primary);
  color: white;
}
.btn-danger {
  background: rgba(160, 80, 80, 0.8);
  color: white;
}
.btn-danger:hover {
  background: rgba(180, 60, 60, 0.9);
}
.btn-small:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
