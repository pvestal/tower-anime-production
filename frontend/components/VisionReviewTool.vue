<template>
  <div class="vision-tool">
    <h3 style="margin: 0 0 16px;">Vision QC Inspector</h3>

    <!-- Mode selector -->
    <div class="mode-tabs">
      <button :class="{ active: mode === 'character' }" @click="mode = 'character'">From Character</button>
      <button :class="{ active: mode === 'direct' }" @click="mode = 'direct'">Direct Path</button>
    </div>

    <!-- CHARACTER MODE: project → character → image grid -->
    <div v-if="mode === 'character'" class="section">
      <div class="filter-row">
        <select v-model="selectedProject" @change="onProjectChange">
          <option value="">Select project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.name">{{ p.name }} ({{ p.character_count }})</option>
        </select>
        <select v-model="selectedCharSlug" @change="onCharacterChange" :disabled="!selectedProject">
          <option value="">Select character...</option>
          <option v-for="c in filteredCharacters" :key="c.slug" :value="c.slug">{{ c.name }} ({{ c.image_count }})</option>
        </select>
      </div>

      <!-- Image grid -->
      <div v-if="datasetImages.length" class="image-grid">
        <div
          v-for="img in datasetImages"
          :key="img.id"
          class="grid-thumb"
          :class="{ selected: selectedImage === img.name }"
          @click="selectImage(img)"
        >
          <img :src="imageUrl(img.name)" :alt="img.name" loading="lazy" @error="($event.target as HTMLImageElement).style.display = 'none'" />
          <div class="thumb-label">{{ img.name }}</div>
          <span v-if="img.status" :class="['status-dot', img.status]" :title="img.status"></span>
        </div>
      </div>
      <p v-else-if="selectedCharSlug && !loadingImages" style="color: var(--text-muted);">No images found for this character.</p>
      <p v-if="loadingImages" style="color: var(--text-muted);">Loading images...</p>
    </div>

    <!-- DIRECT MODE: upload/drag-drop + context -->
    <div v-if="mode === 'direct'" class="section">
      <div
        class="drop-zone"
        :class="{ dragging: isDragging, 'has-file': !!uploadedFile }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDrop"
        @click="openFilePicker"
      >
        <input ref="fileInput" type="file" accept="image/*" style="display: none" @change="onFileSelect" />
        <div v-if="uploadPreviewUrl" class="drop-preview">
          <img :src="uploadPreviewUrl" alt="Upload preview" />
          <button class="drop-clear" @click.stop="clearUpload" title="Remove">&times;</button>
        </div>
        <div v-else class="drop-placeholder">
          <div class="drop-icon">&#8681;</div>
          <div>Drop image here or click to browse</div>
          <div class="drop-hint">PNG, JPG, WebP</div>
        </div>
      </div>
      <label>Character Name</label>
      <input v-model="directCharName" type="text" placeholder="e.g. Rosa" />
      <label>Design Prompt</label>
      <textarea v-model="directDesignPrompt" rows="3" placeholder="1woman, pink hair, blue eyes, casual outfit..."></textarea>
    </div>

    <!-- Review button -->
    <div class="action-row">
      <button
        class="review-btn"
        :disabled="!canReview || reviewing"
        @click="runReview"
      >
        {{ reviewing ? 'Analyzing...' : 'Run Vision QC' }}
      </button>
      <span v-if="reviewTime" class="review-time">{{ reviewTime }}s</span>
    </div>

    <!-- Selected image preview -->
    <div v-if="previewSrc" class="preview-panel">
      <img :src="previewSrc" alt="Preview" class="preview-img" />
    </div>

    <!-- Results -->
    <div v-if="result" class="results-panel">
      <h4>QC Results</h4>

      <!-- Quality score bar -->
      <div class="score-row">
        <span class="score-label">Quality Score</span>
        <div class="score-bar">
          <div class="score-fill" :style="{ width: `${result.quality_score * 100}%`, background: qualityColor(result.quality_score) }"></div>
        </div>
        <span class="score-value" :style="{ color: qualityColor(result.quality_score) }">
          {{ (result.quality_score * 100).toFixed(0) }}%
        </span>
      </div>

      <!-- Individual scores -->
      <div class="scores-grid">
        <div class="score-item">
          <span class="score-name">Character Match</span>
          <span class="score-num">{{ result.review.character_match }}/10</span>
        </div>
        <div class="score-item">
          <span class="score-name">Clarity</span>
          <span class="score-num">{{ result.review.clarity }}/10</span>
        </div>
        <div class="score-item">
          <span class="score-name">Training Value</span>
          <span class="score-num">{{ result.review.training_value }}/10</span>
        </div>
        <div class="score-item">
          <span class="score-name">Solo</span>
          <span :class="['bool-badge', result.review.solo ? 'pass' : 'fail']">
            {{ result.review.solo ? 'Yes' : 'No' }}
          </span>
        </div>
        <div class="score-item">
          <span class="score-name">Completeness</span>
          <span class="score-num">{{ result.review.completeness }}</span>
        </div>
        <div v-if="result.review.gender_match !== undefined" class="score-item">
          <span class="score-name">Gender Match</span>
          <span :class="['bool-badge', result.review.gender_match ? 'pass' : 'fail']">
            {{ result.review.gender_match ? 'Yes' : 'No' }}
          </span>
        </div>
        <div v-if="result.review.has_anatomical_defects !== undefined" class="score-item">
          <span class="score-name">Anatomy Defects</span>
          <span :class="['bool-badge', result.review.has_anatomical_defects ? 'fail' : 'pass']">
            {{ result.review.has_anatomical_defects ? 'Yes' : 'None' }}
          </span>
        </div>
      </div>

      <!-- Caption -->
      <div v-if="result.review.caption" class="caption-box">
        <strong>Caption:</strong> {{ result.review.caption }}
      </div>

      <!-- Issues -->
      <div v-if="result.review.issues?.length" class="issues-box">
        <strong>Issues:</strong>
        <ul>
          <li v-for="(issue, i) in result.review.issues" :key="i">{{ issue }}</li>
        </ul>
      </div>

      <!-- Categories -->
      <div v-if="result.categories?.length" class="categories-row">
        <span v-for="cat in result.categories" :key="cat" class="category-tag">{{ cat }}</span>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="error-box">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { DirectVisionReviewResponse } from '@/api/visual'
import type { Character, DatasetImage } from '@/types'

const mode = ref<'character' | 'direct'>('character')

// Character mode state
const projects = ref<Array<{ id: number; name: string; character_count: number }>>([])
const characters = ref<Character[]>([])
const selectedProject = ref('')
const selectedCharSlug = ref('')
const datasetImages = ref<DatasetImage[]>([])
const selectedImage = ref('')
const loadingImages = ref(false)

// Direct mode state
const directCharName = ref('')
const directDesignPrompt = ref('')
const uploadedFile = ref<File | null>(null)
const uploadPreviewUrl = ref<string | null>(null)
const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

// Review state
const reviewing = ref(false)
const result = ref<DirectVisionReviewResponse | null>(null)
const error = ref('')
const reviewTime = ref<number | null>(null)

const filteredCharacters = computed(() =>
  characters.value.filter(c => c.project_name === selectedProject.value)
)

const canReview = computed(() => {
  if (mode.value === 'character') return !!selectedCharSlug.value && !!selectedImage.value
  return !!uploadedFile.value
})

const previewSrc = computed(() => {
  if (mode.value === 'character' && selectedCharSlug.value && selectedImage.value) {
    return api.imageUrl(selectedCharSlug.value, selectedImage.value)
  }
  if (mode.value === 'direct' && uploadPreviewUrl.value) {
    return uploadPreviewUrl.value
  }
  return null
})

function imageUrl(imageName: string): string {
  return api.imageUrl(selectedCharSlug.value, imageName)
}

function qualityColor(score: number): string {
  if (score >= 0.8) return 'var(--status-success, #4caf50)'
  if (score >= 0.5) return 'var(--status-warning, #ff9800)'
  return 'var(--status-error, #f44336)'
}

async function onProjectChange() {
  selectedCharSlug.value = ''
  datasetImages.value = []
  selectedImage.value = ''
  result.value = null
}

async function onCharacterChange() {
  selectedImage.value = ''
  result.value = null
  if (!selectedCharSlug.value) {
    datasetImages.value = []
    return
  }
  loadingImages.value = true
  try {
    const char = filteredCharacters.value.find(c => c.slug === selectedCharSlug.value)
    const resp = await api.getCharacterDataset(selectedCharSlug.value)
    datasetImages.value = resp.images
    // Pre-fill direct fields from character data for convenience
    if (char) {
      directCharName.value = char.name
      directDesignPrompt.value = char.design_prompt || ''
    }
  } catch (e) {
    datasetImages.value = []
  } finally {
    loadingImages.value = false
  }
}

function selectImage(img: DatasetImage) {
  selectedImage.value = img.name
  result.value = null
  error.value = ''
}

function setUploadFile(file: File) {
  uploadedFile.value = file
  if (uploadPreviewUrl.value) URL.revokeObjectURL(uploadPreviewUrl.value)
  uploadPreviewUrl.value = URL.createObjectURL(file)
  result.value = null
  error.value = ''
}

function clearUpload() {
  uploadedFile.value = null
  if (uploadPreviewUrl.value) URL.revokeObjectURL(uploadPreviewUrl.value)
  uploadPreviewUrl.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function openFilePicker() {
  fileInput.value?.click()
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.[0]) setUploadFile(input.files[0])
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) setUploadFile(file)
}

async function runReview() {
  reviewing.value = true
  error.value = ''
  result.value = null
  reviewTime.value = null
  const start = Date.now()

  try {
    if (mode.value === 'character') {
      result.value = await api.visionReviewDirect({
        character_slug: selectedCharSlug.value,
        image_name: selectedImage.value,
      })
    } else if (uploadedFile.value) {
      result.value = await api.visionReviewUpload(
        uploadedFile.value,
        directCharName.value || undefined,
        directDesignPrompt.value || undefined,
      )
    }
    reviewTime.value = Math.round((Date.now() - start) / 1000)
  } catch (e: any) {
    error.value = e?.message || 'Vision review failed'
  } finally {
    reviewing.value = false
  }
}

onMounted(async () => {
  try {
    const [projResp, charResp] = await Promise.all([
      api.getProjects(),
      api.getCharacters(),
    ])
    projects.value = projResp.projects
    characters.value = charResp.characters
  } catch (e) {
    console.error('Failed to load projects/characters:', e)
  }
})
</script>

<style scoped>
.vision-tool {
  max-width: 900px;
}

.mode-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-primary);
}

.mode-tabs button {
  padding: 8px 20px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-family: var(--font-primary);
}

.mode-tabs button.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
}

.section {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.filter-row select {
  flex: 1;
  padding: 8px;
  background: var(--bg-secondary, #1a1a2e);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  font-size: 13px;
}

label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 8px;
}

input[type="text"], textarea {
  width: 100%;
  padding: 8px;
  background: var(--bg-secondary, #1a1a2e);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  font-size: 13px;
  font-family: var(--font-primary);
  box-sizing: border-box;
}

textarea {
  resize: vertical;
}

.drop-zone {
  border: 2px dashed var(--border-primary);
  border-radius: 8px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 150ms, background 150ms;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drop-zone:hover, .drop-zone.dragging {
  border-color: var(--accent-primary);
  background: rgba(var(--accent-primary-rgb, 99, 102, 241), 0.05);
}

.drop-zone.has-file {
  border-style: solid;
  padding: 8px;
}

.drop-placeholder {
  color: var(--text-muted);
  font-size: 13px;
}

.drop-icon {
  font-size: 32px;
  margin-bottom: 8px;
  opacity: 0.5;
}

.drop-hint {
  font-size: 11px;
  margin-top: 4px;
  opacity: 0.6;
}

.drop-preview {
  position: relative;
  display: inline-block;
}

.drop-preview img {
  max-width: 300px;
  max-height: 200px;
  border-radius: 6px;
  display: block;
}

.drop-clear {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(0,0,0,0.7);
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.drop-clear:hover {
  background: var(--status-error, #f44336);
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
  padding: 4px;
}

.grid-thumb {
  position: relative;
  border: 2px solid transparent;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 150ms;
}

.grid-thumb.selected {
  border-color: var(--accent-primary);
}

.grid-thumb img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}

.thumb-label {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 2px 4px;
  background: rgba(0,0,0,0.7);
  color: #ccc;
  font-size: 9px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.approved { background: var(--status-success, #4caf50); }
.status-dot.rejected { background: var(--status-error, #f44336); }
.status-dot.pending { background: var(--status-warning, #ff9800); }

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}

.review-btn {
  padding: 10px 24px;
  background: var(--accent-primary);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  font-family: var(--font-primary);
}

.review-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.review-time {
  color: var(--text-muted);
  font-size: 12px;
}

.preview-panel {
  margin-bottom: 16px;
}

.preview-img {
  max-width: 400px;
  max-height: 400px;
  border-radius: 8px;
  border: 1px solid var(--border-primary);
}

.results-panel {
  background: var(--bg-secondary, #1a1a2e);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 16px;
}

.results-panel h4 {
  margin: 0 0 12px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.score-label {
  font-size: 13px;
  min-width: 100px;
}

.score-bar {
  flex: 1;
  height: 12px;
  background: var(--bg-tertiary, #252540);
  border-radius: 6px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 300ms ease;
}

.score-value {
  font-size: 16px;
  font-weight: 600;
  min-width: 48px;
  text-align: right;
}

.scores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.score-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: var(--bg-tertiary, #252540);
  border-radius: 6px;
  font-size: 12px;
}

.score-name {
  color: var(--text-secondary);
}

.score-num {
  font-weight: 600;
}

.bool-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.bool-badge.pass {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.bool-badge.fail {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.caption-box {
  margin: 12px 0;
  padding: 10px;
  background: var(--bg-tertiary, #252540);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
}

.issues-box {
  margin: 12px 0;
  font-size: 13px;
}

.issues-box ul {
  margin: 4px 0 0;
  padding-left: 20px;
}

.issues-box li {
  color: var(--status-error, #f44336);
  margin-bottom: 2px;
}

.categories-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.category-tag {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  background: rgba(244, 67, 54, 0.15);
  color: var(--status-error, #f44336);
  border: 1px solid rgba(244, 67, 54, 0.3);
}

.error-box {
  margin-top: 12px;
  padding: 10px;
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid rgba(244, 67, 54, 0.3);
  border-radius: 6px;
  color: var(--status-error, #f44336);
  font-size: 13px;
}
</style>
