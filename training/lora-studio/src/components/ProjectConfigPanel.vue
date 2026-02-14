<template>
  <div class="card" style="margin-bottom: 24px;">
    <!-- Header row: always visible -->
    <div
      style="display: flex; align-items: center; justify-content: space-between; cursor: pointer; user-select: none;"
      @click="expanded = !expanded"
    >
      <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 11px; color: var(--text-muted); transition: transform 150ms;" :style="{ transform: expanded ? 'rotate(90deg)' : '' }">&#9654;</span>
        <h3 style="font-size: 15px; font-weight: 500; margin: 0;">Project Configuration</h3>
        <!-- Collapsed summary -->
        <span v-if="!expanded && projectStore.currentProject" style="font-size: 12px; color: var(--text-secondary);">
          {{ projectStore.currentProject.name }}
          <template v-if="projectStore.currentProject.style">
            &mdash; {{ projectStore.currentProject.style.checkpoint_model || 'no checkpoint' }},
            {{ projectStore.currentProject.style.steps || '?' }} steps,
            {{ projectStore.currentProject.style.width || '?' }}x{{ projectStore.currentProject.style.height || '?' }}
          </template>
        </span>
      </div>
      <span style="font-size: 11px; color: var(--text-muted);">{{ expanded ? 'collapse' : 'expand' }}</span>
    </div>

    <!-- Expanded content -->
    <div v-if="expanded" style="margin-top: 16px;">

      <!-- Project selector row -->
      <div style="display: flex; gap: 12px; align-items: flex-end; margin-bottom: 20px;">
        <div style="flex: 1;">
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Project</label>
          <select v-model="selectedProjectId" @change="onProjectSelect" style="width: 100%;">
            <option :value="0">Select a project...</option>
            <option v-for="p in projectStore.projects" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.character_count }} characters)
            </option>
          </select>
        </div>
        <button class="btn" style="white-space: nowrap;" @click="showNewForm = true" v-if="!showNewForm">
          + New Project
        </button>
      </div>

      <!-- New Project Form -->
      <div v-if="showNewForm" class="card" style="margin-bottom: 20px; background: var(--bg-tertiary);">
        <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">Create New Project</h4>

        <!-- Concept seeder -->
        <div style="margin-bottom: 14px; padding: 10px; border: 1px dashed var(--accent-primary); border-radius: 4px;">
          <label class="field-label" style="color: var(--accent-primary);">Seed from Concept (optional)</label>
          <textarea v-model="conceptText" rows="2" placeholder="Describe your project idea, e.g. 'A cyberpunk detective story in Tokyo 2089 with neon streets and androids'" class="field-input" style="width: 100%; resize: vertical; margin-bottom: 8px;"></textarea>
          <EchoAssistButton
            context-type="concept"
            :context-payload="{ concept_description: conceptText }"
            label="Generate from Concept"
            :disabled="!conceptText.trim()"
            @accept="handleConceptAccept"
          />
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
          <div>
            <label class="field-label">Name *</label>
            <input v-model="newProject.name" type="text" placeholder="My New Project" class="field-input" />
          </div>
          <div>
            <label class="field-label">Checkpoint *</label>
            <select v-model="newProject.checkpoint_model" class="field-input" style="width: 100%;">
              <option value="">Select checkpoint...</option>
              <option v-for="c in projectStore.checkpoints" :key="c.filename" :value="c.filename">
                {{ c.filename }} ({{ c.size_mb }} MB)
              </option>
            </select>
          </div>
          <div>
            <label class="field-label">Genre</label>
            <input v-model="newProject.genre" type="text" placeholder="anime, sci-fi, etc." class="field-input" />
          </div>
          <div>
            <label class="field-label">Sampler</label>
            <select v-model="newProject.sampler" class="field-input" style="width: 100%;">
              <option v-for="s in samplerOptions" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div>
            <label class="field-label">Steps</label>
            <input v-model.number="newProject.steps" type="number" min="1" max="100" class="field-input" />
          </div>
          <div>
            <label class="field-label">CFG Scale</label>
            <input v-model.number="newProject.cfg_scale" type="number" min="1" max="30" step="0.5" class="field-input" />
          </div>
          <div>
            <label class="field-label">Width</label>
            <input v-model.number="newProject.width" type="number" min="256" max="2048" step="64" class="field-input" />
          </div>
          <div>
            <label class="field-label">Height</label>
            <input v-model.number="newProject.height" type="number" min="256" max="2048" step="64" class="field-input" />
          </div>
        </div>
        <div style="margin-bottom: 10px;">
          <label class="field-label">Description</label>
          <textarea v-model="newProject.description" rows="2" placeholder="Project description..." class="field-input" style="width: 100%; resize: vertical;"></textarea>
        </div>
        <div style="display: flex; gap: 8px;">
          <button
            class="btn btn-primary"
            @click="handleCreateProject"
            :disabled="!newProject.name || !newProject.checkpoint_model || projectStore.saving"
          >
            {{ projectStore.saving ? 'Creating...' : 'Create Project' }}
          </button>
          <button class="btn" @click="showNewForm = false">Cancel</button>
        </div>
      </div>

      <!-- Project Detail (only when a project is selected) -->
      <template v-if="projectStore.currentProject && !showNewForm">

        <!-- Section: Project Details -->
        <div style="margin-bottom: 20px;">
          <h4 style="font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px;">Project Details</h4>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div>
              <label class="field-label">Name</label>
              <input v-model="editProject.name" type="text" class="field-input" />
            </div>
            <div>
              <label class="field-label">Genre</label>
              <input v-model="editProject.genre" type="text" class="field-input" />
            </div>
          </div>
          <div style="margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <label class="field-label" style="margin-bottom: 0;">Description</label>
              <EchoAssistButton
                context-type="description"
                :context-payload="echoContext"
                :current-value="editProject.description"
                compact
                @accept="editProject.description = $event.suggestion"
              />
            </div>
            <textarea v-model="editProject.description" rows="2" class="field-input" style="width: 100%; resize: vertical;"></textarea>
          </div>
          <button
            :class="['btn', detailsSaved ? 'btn-saved' : 'btn-primary']"
            style="font-size: 12px; padding: 4px 12px; transition: all 200ms ease;"
            @click="handleUpdateProject"
            :disabled="projectStore.saving || !detailsDirty"
          >
            {{ detailsSaved ? 'Saved' : projectStore.saving ? 'Saving...' : 'Save Details' }}
          </button>
          <span v-if="!detailsDirty && !detailsSaved" style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">no changes</span>
        </div>

        <!-- Section: Storyline -->
        <div style="margin-bottom: 20px;">
          <h4 style="font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px;">Storyline</h4>
          <div v-if="!projectStore.currentProject.storyline && !editingStoryline" style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
            No storyline yet.
            <button class="btn" style="font-size: 11px; padding: 2px 8px; margin-left: 8px;" @click="editingStoryline = true">Add Storyline</button>
          </div>
          <template v-if="projectStore.currentProject.storyline || editingStoryline">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
              <div>
                <label class="field-label">Title</label>
                <input v-model="editStoryline.title" type="text" placeholder="Story title" class="field-input" />
              </div>
              <div>
                <label class="field-label">Genre</label>
                <input v-model="editStoryline.genre" type="text" placeholder="adventure, comedy..." class="field-input" />
              </div>
              <div>
                <label class="field-label">Theme</label>
                <input v-model="editStoryline.theme" type="text" placeholder="friendship, heroism..." class="field-input" />
              </div>
              <div>
                <label class="field-label">Target Audience</label>
                <input v-model="editStoryline.target_audience" type="text" placeholder="kids, teens, all ages..." class="field-input" />
              </div>
            </div>
            <div style="margin-bottom: 10px;">
              <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                <label class="field-label" style="margin-bottom: 0;">Summary</label>
                <EchoAssistButton
                  context-type="storyline"
                  :context-payload="echoContext"
                  :current-value="editStoryline.summary"
                  compact
                  @accept="editStoryline.summary = $event.suggestion"
                />
              </div>
              <textarea v-model="editStoryline.summary" rows="3" placeholder="Story summary..." class="field-input" style="width: 100%; resize: vertical;"></textarea>
            </div>
            <button
              :class="['btn', storylineSaved ? 'btn-saved' : 'btn-primary']"
              style="font-size: 12px; padding: 4px 12px; transition: all 200ms ease;"
              @click="handleUpsertStoryline"
              :disabled="projectStore.saving || !storylineDirty"
            >
              {{ storylineSaved ? 'Saved' : projectStore.saving ? 'Saving...' : 'Save Storyline' }}
            </button>
            <span v-if="!storylineDirty && !storylineSaved" style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">no changes</span>
          </template>
        </div>

        <!-- Section: Generation Style -->
        <div>
          <h4 style="font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">Generation Style (SSOT)</h4>
          <p style="font-size: 11px; color: var(--status-warning); margin-bottom: 10px;">Changes affect ALL characters in this project.</p>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div style="grid-column: 1 / -1;">
              <label class="field-label">Checkpoint Model</label>
              <select v-model="editStyle.checkpoint_model" class="field-input" style="width: 100%;">
                <option value="">Select checkpoint...</option>
                <option v-for="c in projectStore.checkpoints" :key="c.filename" :value="c.filename">
                  {{ c.filename }} ({{ c.size_mb }} MB)
                </option>
              </select>
              <span
                v-if="editStyle.checkpoint_model && !checkpointExists(editStyle.checkpoint_model)"
                style="font-size: 11px; color: var(--status-error);"
              >
                Model file not found on disk
              </span>
            </div>
            <div>
              <label class="field-label">CFG Scale</label>
              <input v-model.number="editStyle.cfg_scale" type="number" min="1" max="30" step="0.5" class="field-input" />
            </div>
            <div>
              <label class="field-label">Steps</label>
              <input v-model.number="editStyle.steps" type="number" min="1" max="100" class="field-input" />
            </div>
            <div>
              <label class="field-label">Sampler</label>
              <select v-model="editStyle.sampler" class="field-input" style="width: 100%;">
                <option v-for="s in samplerOptions" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div>
              <label class="field-label">Width</label>
              <input v-model.number="editStyle.width" type="number" min="256" max="2048" step="64" class="field-input" />
            </div>
            <div>
              <label class="field-label">Height</label>
              <input v-model.number="editStyle.height" type="number" min="256" max="2048" step="64" class="field-input" />
            </div>
          </div>
          <div style="margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <label class="field-label" style="margin-bottom: 0;">Positive Prompt Template</label>
              <EchoAssistButton
                context-type="positive_template"
                :context-payload="echoContext"
                :current-value="editStyle.positive_prompt_template"
                compact
                @accept="editStyle.positive_prompt_template = $event.suggestion"
              />
            </div>
            <textarea v-model="editStyle.positive_prompt_template" rows="2" class="field-input" style="width: 100%; resize: vertical;" placeholder="masterpiece, best quality..."></textarea>
          </div>
          <div style="margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <label class="field-label" style="margin-bottom: 0;">Negative Prompt Template</label>
              <EchoAssistButton
                context-type="negative_template"
                :context-payload="echoContext"
                :current-value="editStyle.negative_prompt_template"
                compact
                @accept="editStyle.negative_prompt_template = $event.suggestion"
              />
            </div>
            <textarea v-model="editStyle.negative_prompt_template" rows="2" class="field-input" style="width: 100%; resize: vertical;" placeholder="worst quality, low quality..."></textarea>
          </div>
          <button
            :class="['btn', styleSaved ? 'btn-saved' : 'btn-primary']"
            style="font-size: 12px; padding: 4px 12px; transition: all 200ms ease;"
            @click="handleUpdateStyle"
            :disabled="projectStore.saving || !styleDirty"
          >
            {{ styleSaved ? 'Saved' : projectStore.saving ? 'Saving...' : 'Save Generation Style' }}
          </button>
          <span v-if="!styleDirty && !styleSaved" style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">no changes</span>
        </div>

      </template>

      <!-- Loading state -->
      <div v-if="projectStore.loading && !projectStore.currentProject" style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 13px;">
        Loading project...
      </div>

      <!-- Error -->
      <div v-if="projectStore.error" style="margin-top: 12px; padding: 8px 12px; background: rgba(160,80,80,0.1); border: 1px solid var(--status-error); border-radius: 3px;">
        <p style="color: var(--status-error); font-size: 12px; margin: 0;">{{ projectStore.error }}</p>
        <button class="btn" style="font-size: 11px; padding: 2px 8px; margin-top: 4px;" @click="projectStore.clearError()">Dismiss</button>
      </div>

      <!-- Save success feedback -->
      <div v-if="saveMessage" style="margin-top: 12px; font-size: 12px; color: var(--status-success);">
        {{ saveMessage }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useProjectStore } from '@/stores/project'
import type { ProjectCreate, ProjectUpdate, StorylineUpsert, StyleUpdate } from '@/types'
import EchoAssistButton from './EchoAssistButton.vue'

const emit = defineEmits<{
  'project-selected': [projectId: number, projectName: string]
}>()

const projectStore = useProjectStore()

const expanded = ref(false)
const showNewForm = ref(false)
const editingStoryline = ref(false)
const selectedProjectId = ref(0)
const saveMessage = ref('')
const conceptText = ref('')

const samplerOptions = [
  'DPM++ 2M Karras',
  'DPM++ 2M SDE Karras',
  'DPM++ 2S a Karras',
  'DPM++ SDE Karras',
  'DPM++ 2M',
  'Euler a',
  'Euler',
  'DDIM',
]

// New project form
const newProject = reactive<ProjectCreate>({
  name: '',
  description: '',
  genre: '',
  checkpoint_model: '',
  cfg_scale: 7,
  steps: 25,
  sampler: 'DPM++ 2M Karras',
  width: 768,
  height: 768,
})

// Edit forms (populated from currentProject)
const editProject = reactive<ProjectUpdate>({
  name: '',
  description: '',
  genre: '',
})

const editStoryline = reactive<StorylineUpsert>({
  title: '',
  summary: '',
  theme: '',
  genre: '',
  target_audience: '',
})

const editStyle = reactive<StyleUpdate>({
  checkpoint_model: '',
  cfg_scale: 7,
  steps: 25,
  sampler: 'DPM++ 2M Karras',
  width: 768,
  height: 768,
  positive_prompt_template: '',
  negative_prompt_template: '',
})

// Populate edit forms when currentProject changes
watch(() => projectStore.currentProject, (proj) => {
  if (!proj) return
  editProject.name = proj.name
  editProject.description = proj.description || ''
  editProject.genre = proj.genre || ''

  if (proj.storyline) {
    editStoryline.title = proj.storyline.title || ''
    editStoryline.summary = proj.storyline.summary || ''
    editStoryline.theme = proj.storyline.theme || ''
    editStoryline.genre = proj.storyline.genre || ''
    editStoryline.target_audience = proj.storyline.target_audience || ''
    editingStoryline.value = true
  } else {
    editStoryline.title = ''
    editStoryline.summary = ''
    editStoryline.theme = ''
    editStoryline.genre = ''
    editStoryline.target_audience = ''
    editingStoryline.value = false
  }

  if (proj.style) {
    editStyle.checkpoint_model = proj.style.checkpoint_model || ''
    editStyle.cfg_scale = proj.style.cfg_scale || 7
    editStyle.steps = proj.style.steps || 25
    editStyle.sampler = proj.style.sampler || 'DPM++ 2M Karras'
    editStyle.width = proj.style.width || 768
    editStyle.height = proj.style.height || 768
    editStyle.positive_prompt_template = proj.style.positive_prompt_template || ''
    editStyle.negative_prompt_template = proj.style.negative_prompt_template || ''
  }

  // Snapshot for dirty tracking
  snapshotProject()
  snapshotStoryline()
  snapshotStyle()
}, { immediate: true })

const echoContext = computed(() => ({
  project_name: editProject.name || projectStore.currentProject?.name || undefined,
  project_genre: editProject.genre || projectStore.currentProject?.genre || undefined,
  project_description: editProject.description || projectStore.currentProject?.description || undefined,
  checkpoint_model: editStyle.checkpoint_model || projectStore.currentProject?.style?.checkpoint_model || undefined,
  storyline_title: editStoryline.title || undefined,
  storyline_summary: editStoryline.summary || undefined,
  storyline_theme: editStoryline.theme || undefined,
  positive_prompt_template: editStyle.positive_prompt_template || undefined,
  negative_prompt_template: editStyle.negative_prompt_template || undefined,
}))

// Dirty tracking — compare current edits to last-saved snapshot
const savedProjectSnapshot = ref({ name: '', description: '', genre: '' })
const savedStorylineSnapshot = ref({ title: '', summary: '', theme: '', genre: '', target_audience: '' })
const savedStyleSnapshot = ref({ checkpoint_model: '', cfg_scale: 7, steps: 25, sampler: '', width: 768, height: 768, positive_prompt_template: '', negative_prompt_template: '' })

const detailsDirty = computed(() => {
  const s = savedProjectSnapshot.value
  return editProject.name !== s.name || editProject.description !== s.description || editProject.genre !== s.genre
})
const storylineDirty = computed(() => {
  const s = savedStorylineSnapshot.value
  return editStoryline.title !== s.title || editStoryline.summary !== s.summary || editStoryline.theme !== s.theme || editStoryline.genre !== s.genre || editStoryline.target_audience !== s.target_audience
})
const styleDirty = computed(() => {
  const s = savedStyleSnapshot.value
  return editStyle.checkpoint_model !== s.checkpoint_model || editStyle.cfg_scale !== s.cfg_scale || editStyle.steps !== s.steps || editStyle.sampler !== s.sampler || editStyle.width !== s.width || editStyle.height !== s.height || editStyle.positive_prompt_template !== s.positive_prompt_template || editStyle.negative_prompt_template !== s.negative_prompt_template
})

// Save confirmation states
const detailsSaved = ref(false)
const storylineSaved = ref(false)
const styleSaved = ref(false)

function flashSaved(target: typeof detailsSaved) {
  target.value = true
  setTimeout(() => { target.value = false }, 2000)
}

function snapshotProject() {
  savedProjectSnapshot.value = { name: editProject.name || '', description: editProject.description || '', genre: editProject.genre || '' }
}
function snapshotStoryline() {
  savedStorylineSnapshot.value = { title: editStoryline.title || '', summary: editStoryline.summary || '', theme: editStoryline.theme || '', genre: editStoryline.genre || '', target_audience: editStoryline.target_audience || '' }
}
function snapshotStyle() {
  savedStyleSnapshot.value = { checkpoint_model: editStyle.checkpoint_model || '', cfg_scale: editStyle.cfg_scale || 7, steps: editStyle.steps || 25, sampler: editStyle.sampler || '', width: editStyle.width || 768, height: editStyle.height || 768, positive_prompt_template: editStyle.positive_prompt_template || '', negative_prompt_template: editStyle.negative_prompt_template || '' }
}

function handleConceptAccept({ suggestion }: { suggestion: string }) {
  // Try to parse JSON from the suggestion (strip markdown fences if present)
  let text = suggestion.trim()
  if (text.startsWith('```')) {
    text = text.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '')
  }
  try {
    const data = JSON.parse(text)
    if (data.name) newProject.name = data.name
    if (data.genre) newProject.genre = data.genre
    if (data.description) newProject.description = data.description
    if (data.recommended_steps) newProject.steps = Number(data.recommended_steps) || 25
    if (data.recommended_cfg) newProject.cfg_scale = Number(data.recommended_cfg) || 7
  } catch {
    // Fallback: put raw text in description
    newProject.description = suggestion
  }
}

function checkpointExists(filename: string): boolean {
  return projectStore.checkpoints.some(c => c.filename === filename)
}

function showSaved() {
  saveMessage.value = 'Saved successfully'
  setTimeout(() => { saveMessage.value = '' }, 3000)
}

async function onProjectSelect() {
  if (!selectedProjectId.value) {
    projectStore.currentProject = null
    return
  }
  await projectStore.fetchProjectDetail(selectedProjectId.value)
  const proj = projectStore.projects.find(p => p.id === selectedProjectId.value)
  if (proj) {
    emit('project-selected', proj.id, proj.name)
  }
}

async function handleCreateProject() {
  const projectId = await projectStore.createProject({ ...newProject })
  if (projectId) {
    selectedProjectId.value = projectId
    await projectStore.fetchProjectDetail(projectId)
    showNewForm.value = false
    // Reset form
    newProject.name = ''
    newProject.description = ''
    newProject.genre = ''
    newProject.checkpoint_model = ''
    const proj = projectStore.projects.find(p => p.id === projectId)
    if (proj) {
      emit('project-selected', proj.id, proj.name)
    }
    showSaved()
  }
}

async function handleUpdateProject() {
  if (!projectStore.currentProject) return
  await projectStore.updateProject(projectStore.currentProject.id, { ...editProject })
  snapshotProject()
  flashSaved(detailsSaved)
}

async function handleUpsertStoryline() {
  if (!projectStore.currentProject) return
  await projectStore.upsertStoryline(projectStore.currentProject.id, { ...editStoryline })
  snapshotStoryline()
  flashSaved(storylineSaved)
}

async function handleUpdateStyle() {
  if (!projectStore.currentProject) return
  await projectStore.updateStyle(projectStore.currentProject.id, { ...editStyle })
  snapshotStyle()
  flashSaved(styleSaved)
}

onMounted(async () => {
  await Promise.all([
    projectStore.fetchProjects(),
    projectStore.fetchCheckpoints(),
  ])
})
</script>

<style scoped>
.field-label {
  font-size: 11px;
  color: var(--text-muted);
  display: block;
  margin-bottom: 4px;
}
.field-input {
  padding: 5px 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: var(--font-primary);
  width: 100%;
}
.field-input:focus {
  border-color: var(--border-focus);
  outline: none;
}
.btn-saved {
  background: var(--status-success) !important;
  color: var(--bg-primary) !important;
  border-color: var(--status-success) !important;
}
</style>
