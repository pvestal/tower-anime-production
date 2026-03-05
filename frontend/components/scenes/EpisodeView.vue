<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div style="font-size: 15px; font-weight: 500; color: var(--accent-primary);">Episodes</div>
      <button class="btn btn-primary" style="font-size: 12px;" @click="showCreateModal = true">+ New Episode</button>
    </div>

    <div v-if="loading" style="color: var(--text-muted); font-size: 13px;">Loading episodes...</div>
    <div v-else-if="episodes.length === 0" style="color: var(--text-muted); font-size: 13px;">
      No episodes yet. Create one to start assembling scenes into full episodes.
    </div>

    <!-- Episode Card Grid -->
    <div v-else class="episode-grid">
      <div
        v-for="ep in episodes"
        :key="ep.id"
        class="episode-card"
        :class="{ selected: selectedEpisodeId === ep.id }"
        @click="openEditor(ep)"
      >
        <!-- Cover Image -->
        <div class="episode-cover">
          <img
            v-if="ep.cover_frame_path || ep.thumbnail_path"
            :src="episodesApi.episodeCoverUrl(ep.id)"
            :alt="ep.title"
            @error="($event.target as HTMLImageElement).style.display = 'none'"
          />
          <div v-else class="episode-cover-placeholder">
            <span class="cover-number">E{{ ep.episode_number }}</span>
          </div>
          <span class="episode-status-badge" :class="statusClass(ep.status)">{{ ep.status }}</span>
        </div>

        <!-- Card Body -->
        <div class="episode-body">
          <div class="episode-title">E{{ ep.episode_number }} — {{ ep.title }}</div>
          <div v-if="ep.description" class="episode-desc">{{ ep.description }}</div>
          <div class="episode-meta">
            <span>{{ ep.scene_count }} scene{{ ep.scene_count !== 1 ? 's' : '' }}</span>
            <span v-if="ep.actual_duration_seconds">{{ formatDuration(ep.actual_duration_seconds) }}</span>
            <span v-if="ep.story_arc" class="story-arc-chip">{{ ep.story_arc }}</span>
          </div>
        </div>

        <!-- Action Buttons (visible on hover/selected) -->
        <div class="episode-actions" @click.stop>
          <button v-if="ep.final_video_path" class="action-btn play" title="Play" @click="$emit('play-episode', ep)">&#9654;</button>
          <button v-if="authStore.isAdvanced && ep.scene_count > 0" class="action-btn assemble" title="Assemble" @click="assembleEpisode(ep)">&#9881;</button>
          <button v-if="ep.status === 'assembled'" class="action-btn publish" title="Publish" @click="publishEpisode(ep)">&#8679;</button>
          <button class="action-btn delete" title="Delete" @click="deleteEpisode(ep)">&times;</button>
        </div>
      </div>
    </div>

    <!-- Expanded Scene Editor (slides in below selected card) -->
    <div v-if="selectedEpisodeId && selectedEpisode" class="scene-editor card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <div style="font-size: 13px; font-weight: 500;">
          Scenes in E{{ selectedEpisode.episode_number }} — {{ selectedEpisode.title }}
        </div>
        <button class="btn" style="font-size: 11px; padding: 2px 8px;" @click="selectedEpisodeId = ''; selectedEpisode = null">&times; Close</button>
      </div>

      <div v-if="selectedEpisode.scenes && selectedEpisode.scenes.length > 0" class="scene-list">
        <div v-for="(s, idx) in selectedEpisode.scenes" :key="s.scene_id" class="scene-row">
          <span class="scene-num">{{ idx + 1 }}</span>
          <span class="scene-title">{{ s.title || 'Untitled' }}</span>
          <span v-if="s.transition && s.transition !== 'cut'" class="scene-transition">{{ s.transition }}</span>
          <span :class="statusClass(s.generation_status)" class="scene-status">{{ s.generation_status }}</span>
          <span v-if="s.actual_duration_seconds" class="scene-duration">{{ s.actual_duration_seconds.toFixed(1) }}s</span>
          <button class="btn btn-danger" style="font-size: 10px; padding: 1px 6px;" @click="removeScene(selectedEpisode!, s.scene_id)">×</button>
        </div>
      </div>
      <div v-else style="color: var(--text-muted); font-size: 12px;">No scenes added yet.</div>

      <!-- Add scene picker -->
      <div style="margin-top: 10px; display: flex; gap: 6px; align-items: flex-end;">
        <div style="flex: 1;">
          <select v-model="addSceneId" class="field-input" style="font-size: 12px; padding: 4px 6px;">
            <option value="">Add a scene...</option>
            <option v-for="s in availableScenes" :key="s.id" :value="s.id">{{ s.title }} ({{ s.generation_status }})</option>
          </select>
        </div>
        <div style="width: 110px;">
          <select v-model="addTransition" class="field-input" style="font-size: 11px; padding: 4px 6px;">
            <option value="fadeblack">Fade Black</option>
            <option value="dissolve">Dissolve</option>
            <option value="fade">Fade</option>
            <option value="wipeleft">Wipe Left</option>
            <option value="cut">Cut</option>
          </select>
        </div>
        <button v-if="addSceneId" class="btn btn-primary" style="font-size: 11px; padding: 3px 10px;" @click="addScene(selectedEpisode!)">Add</button>
      </div>
    </div>

    <!-- Create Episode Modal -->
    <div v-if="showCreateModal" style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center;" @click.self="showCreateModal = false" @keydown.escape.window="showCreateModal = false">
      <div class="card" style="width: 400px;">
        <div style="font-size: 14px; font-weight: 500; margin-bottom: 16px;">New Episode</div>
        <div class="field-group">
          <label class="field-label">Episode Number</label>
          <input v-model.number="newEpisode.episode_number" type="number" min="1" class="field-input" />
        </div>
        <div class="field-group">
          <label class="field-label">Title</label>
          <input v-model="newEpisode.title" type="text" :placeholder="`Episode ${newEpisode.episode_number}`" class="field-input" />
        </div>
        <div class="field-group">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
            <label class="field-label" style="margin-bottom: 0;">Description</label>
            <EchoAssistButton
              context-type="description"
              :context-payload="{
                project_name: projectStore.currentProject?.name,
                project_genre: projectStore.currentProject?.genre || undefined,
                project_premise: projectStore.currentProject?.premise || undefined,
                storyline_summary: projectStore.currentProject?.storyline?.summary || undefined,
              }"
              :current-value="newEpisode.description"
              compact
              @accept="newEpisode.description = $event.suggestion"
            />
          </div>
          <textarea v-model="newEpisode.description" rows="2" placeholder="What happens in this episode..." class="field-input" style="resize: vertical;"></textarea>
        </div>
        <div class="field-group">
          <label class="field-label">Story Arc</label>
          <input v-model="newEpisode.story_arc" type="text" placeholder="Optional story arc tag" class="field-input" />
          <div v-if="storyArcs.length > 0" style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;">
            <button
              v-for="arc in storyArcs"
              :key="arc"
              type="button"
              class="arc-chip"
              :class="{ active: newEpisode.story_arc === arc }"
              @click="newEpisode.story_arc = newEpisode.story_arc === arc ? '' : arc"
            >{{ arc }}</button>
          </div>
        </div>
        <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px;">
          <button class="btn" @click="showCreateModal = false">Cancel</button>
          <button class="btn btn-primary" @click="createEpisode">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Episode, BuilderScene } from '@/types'
import { episodesApi } from '@/api/episodes'
import { useProjectStore } from '@/stores/project'
import { useAuthStore } from '@/stores/auth'
import EchoAssistButton from '../EchoAssistButton.vue'

const projectStore = useProjectStore()
const authStore = useAuthStore()

const props = defineProps<{
  projectId: number
  scenes: BuilderScene[]
}>()

const emit = defineEmits<{
  'play-episode': [ep: Episode]
}>()

const loading = ref(false)
const episodes = ref<Episode[]>([])
const selectedEpisodeId = ref('')
const selectedEpisode = ref<Episode | null>(null)
const showCreateModal = ref(false)
const addSceneId = ref('')
const addTransition = ref('fadeblack')

const newEpisode = ref({
  episode_number: 1,
  title: '',
  description: '',
  story_arc: '',
})

const availableScenes = ref<BuilderScene[]>([])

const storyArcs = computed(() => projectStore.currentProject?.storyline?.story_arcs || [])

watch(() => props.projectId, async (pid) => {
  if (pid) await loadEpisodes()
}, { immediate: true })

watch(() => props.scenes, (s) => {
  availableScenes.value = s.filter(sc => sc.generation_status === 'completed' || sc.generation_status === 'partial')
}, { immediate: true })

async function loadEpisodes() {
  loading.value = true
  try {
    const data = await episodesApi.listEpisodes(props.projectId)
    episodes.value = data.episodes
    const maxNum = episodes.value.reduce((m, e) => Math.max(m, e.episode_number), 0)
    newEpisode.value.episode_number = maxNum + 1
  } catch (e) {
    console.error('Failed to load episodes:', e)
  } finally {
    loading.value = false
  }
}

async function createEpisode() {
  try {
    await episodesApi.createEpisode({
      project_id: props.projectId,
      episode_number: newEpisode.value.episode_number,
      title: newEpisode.value.title || `Episode ${newEpisode.value.episode_number}`,
      description: newEpisode.value.description || undefined,
      story_arc: newEpisode.value.story_arc || undefined,
    })
    showCreateModal.value = false
    newEpisode.value = { episode_number: newEpisode.value.episode_number + 1, title: '', description: '', story_arc: '' }
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to create episode:', e)
  }
}

async function openEditor(ep: Episode) {
  if (selectedEpisodeId.value === ep.id) {
    selectedEpisodeId.value = ''
    selectedEpisode.value = null
    return
  }
  try {
    selectedEpisode.value = await episodesApi.getEpisode(ep.id)
    selectedEpisodeId.value = ep.id
  } catch (e) {
    console.error('Failed to load episode:', e)
  }
}

async function addScene(ep: Episode) {
  if (!addSceneId.value) return
  const pos = (selectedEpisode.value?.scenes?.length ?? 0) + 1
  try {
    await episodesApi.addSceneToEpisode(ep.id, addSceneId.value, pos, addTransition.value)
    addSceneId.value = ''
    addTransition.value = 'fadeblack'
    selectedEpisode.value = await episodesApi.getEpisode(ep.id)
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to add scene:', e)
  }
}

async function removeScene(ep: Episode, sceneId: string) {
  try {
    await episodesApi.removeSceneFromEpisode(ep.id, sceneId)
    selectedEpisode.value = await episodesApi.getEpisode(ep.id)
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to remove scene:', e)
  }
}

async function assembleEpisode(ep: Episode) {
  try {
    const result = await episodesApi.assembleEpisode(ep.id)
    alert(`Episode assembled: ${result.scenes_included} scenes, ${result.duration_seconds?.toFixed(1)}s${result.scenes_missing.length ? `\nMissing: ${result.scenes_missing.join(', ')}` : ''}`)
    await loadEpisodes()
  } catch (e) {
    console.error('Assembly failed:', e)
    alert(`Assembly failed: ${e}`)
  }
}

async function publishEpisode(ep: Episode) {
  if (!confirm(`Publish "${ep.title}" to Jellyfin?`)) return
  try {
    const result = await episodesApi.publishEpisode(ep.id)
    alert(`Published: ${result.published_path}\nJellyfin scan: ${result.jellyfin_scan}`)
    await loadEpisodes()
  } catch (e) {
    console.error('Publish failed:', e)
    alert(`Publish failed: ${e}`)
  }
}

async function deleteEpisode(ep: Episode) {
  if (!confirm(`Delete episode "${ep.title}"?`)) return
  try {
    await episodesApi.deleteEpisode(ep.id)
    if (selectedEpisodeId.value === ep.id) {
      selectedEpisodeId.value = ''
      selectedEpisode.value = null
    }
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to delete episode:', e)
  }
}

function statusClass(status: string): string {
  const map: Record<string, string> = {
    draft: 'badge-draft', planning: 'badge-draft', planned: 'badge-draft',
    assembled: 'badge-completed', published: 'badge-published',
    completed: 'badge-completed', partial: 'badge-partial',
    generating: 'badge-generating', failed: 'badge-failed',
  }
  return map[status] || 'badge-draft'
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m > 0 ? `${m}m${s}s` : `${s}s`
}
</script>

<style scoped>
/* ---- Card Grid ---- */
.episode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}

.episode-card {
  position: relative;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.episode-card:hover {
  border-color: var(--accent-primary);
  box-shadow: 0 2px 12px rgba(122, 162, 247, 0.15);
}
.episode-card.selected {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(122, 162, 247, 0.25);
}

/* ---- Cover Image ---- */
.episode-cover {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  background: var(--bg-tertiary);
  overflow: hidden;
}
.episode-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.episode-cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-primary) 100%);
}
.cover-number {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-muted);
  opacity: 0.4;
}
.episode-status-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  font-weight: 500;
}

/* ---- Card Body ---- */
.episode-body {
  padding: 10px 12px 12px;
}
.episode-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.episode-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.episode-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-secondary);
}
.story-arc-chip {
  padding: 0 6px;
  background: rgba(122, 162, 247, 0.1);
  color: var(--accent-primary);
  border-radius: 8px;
  font-size: 10px;
}

/* ---- Action Buttons (hover overlay) ---- */
.episode-actions {
  position: absolute;
  top: 6px;
  left: 6px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 150ms ease;
}
.episode-card:hover .episode-actions { opacity: 1; }

.action-btn {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-primary);
  backdrop-filter: blur(4px);
}
.action-btn.play { background: rgba(80, 160, 80, 0.85); color: #fff; }
.action-btn.assemble { background: rgba(122, 162, 247, 0.85); color: #fff; }
.action-btn.publish { background: rgba(122, 200, 247, 0.85); color: #fff; }
.action-btn.delete { background: rgba(160, 80, 80, 0.85); color: #fff; font-size: 16px; }
.action-btn:hover { opacity: 0.9; transform: scale(1.05); }

/* ---- Scene Editor ---- */
.scene-editor {
  margin-top: 14px;
  animation: slideIn 150ms ease;
}
@keyframes slideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.scene-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.scene-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  font-size: 12px;
}
.scene-num { color: var(--text-muted); min-width: 20px; }
.scene-title { flex: 1; }
.scene-transition { font-size: 10px; color: var(--text-muted); padding: 1px 4px; }
.scene-status { font-size: 10px; padding: 1px 6px; border-radius: 3px; }
.scene-duration { color: var(--text-muted); }

/* ---- Badges ---- */
.badge-draft { background: var(--bg-tertiary); color: var(--text-secondary); }
.badge-generating { background: rgba(122, 162, 247, 0.2); color: var(--accent-primary); }
.badge-completed { background: rgba(80, 160, 80, 0.2); color: var(--status-success); }
.badge-partial { background: rgba(160, 128, 80, 0.2); color: var(--status-warning); }
.badge-failed { background: rgba(160, 80, 80, 0.2); color: var(--status-error); }
.badge-published { background: rgba(122, 200, 247, 0.2); color: #7ac8f7; }

/* ---- Form Elements ---- */
.field-group { margin-bottom: 10px; }
.field-label { font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px; }
.field-input {
  width: 100%; padding: 6px 8px; font-size: 13px;
  background: var(--bg-primary); color: var(--text-primary);
  border: 1px solid var(--border-primary); border-radius: 3px;
  font-family: var(--font-primary);
}
.arc-chip {
  padding: 2px 8px;
  font-size: 11px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
  cursor: pointer;
  font-family: var(--font-primary);
}
.arc-chip.active {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: rgba(122, 162, 247, 0.1);
}
</style>
