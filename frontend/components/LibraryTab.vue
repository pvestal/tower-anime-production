<template>
  <div>
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h2 style="font-size: 18px; font-weight: 500;">Library</h2>
        <p style="font-size: 13px; color: var(--text-muted);">
          Browse approved training images. Generate similar variants from your best work.
        </p>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span v-if="totalApproved > 0" style="font-size: 12px; color: var(--text-muted);">
          {{ totalApproved }} approved
        </span>
        <button class="btn" @click="refresh" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Filter toggle + search -->
    <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap;">
      <input
        v-model="searchText"
        type="text"
        placeholder="Search by name..."
        style="flex: 1; min-width: 160px; padding: 7px 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 6px; font-size: 12px; font-family: var(--font-primary); outline: none;"
      />
      <button class="btn" style="font-size: 12px; padding: 7px 14px;" @click="libFiltersOpen = !libFiltersOpen">
        {{ libFiltersOpen ? 'Hide Filters' : 'Filters' }}
        <span v-if="libActiveFilterCount > 0" style="display: inline-block; background: var(--accent-primary); color: #fff; font-size: 10px; padding: 0 5px; border-radius: 8px; margin-left: 4px;">{{ libActiveFilterCount }}</span>
      </button>
    </div>

    <!-- Collapsible filters -->
    <Transition name="lib-collapse">
      <div v-if="libFiltersOpen" style="background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px;">
        <!-- Project -->
        <div v-if="projectList.length > 1" style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
          <span class="filter-label">Project</span>
          <button class="chip" :class="{ active: !selectedProject }" @click="selectedProject = ''">All</button>
          <button v-for="proj in projectList" :key="proj" class="chip" :class="{ active: selectedProject === proj }" @click="selectedProject = proj">{{ proj }}</button>
        </div>
        <!-- Model -->
        <div v-if="modelList.length > 1" style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
          <span class="filter-label">Model</span>
          <button v-for="model in modelList" :key="model" class="chip chip-small" :class="{ active: selectedModel === model }" @click="selectedModel = selectedModel === model ? '' : model">{{ modelShortName(model) }}</button>
        </div>
        <!-- Character -->
        <div v-if="filteredCharacterList.length > 1" style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
          <span class="filter-label">Character</span>
          <button class="chip" :class="{ active: !selectedSlug }" @click="selectedSlug = ''">All ({{ filteredApproved }})</button>
          <button v-for="ch in filteredCharacterList" :key="ch.slug" class="chip" :class="{ active: selectedSlug === ch.slug }" @click="selectedSlug = ch.slug">{{ ch.name }} ({{ ch.approved }})</button>
        </div>
        <!-- Media type -->
        <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
          <span class="filter-label">Type</span>
          <button class="chip" :class="{ active: !selectedMediaType }" @click="selectedMediaType = ''">All</button>
          <button class="chip" :class="{ active: selectedMediaType === 'keyframe' }" @click="selectedMediaType = selectedMediaType === 'keyframe' ? '' : 'keyframe'">Keyframes</button>
          <button class="chip" :class="{ active: selectedMediaType === 'video' }" @click="selectedMediaType = selectedMediaType === 'video' ? '' : 'video'">Videos</button>
          <button class="chip" :class="{ active: selectedMediaType === 'video_audio' }" @click="selectedMediaType = selectedMediaType === 'video_audio' ? '' : 'video_audio'">Videos w/ Audio</button>
        </div>
      </div>
    </Transition>

    <!-- Masonry image grid -->
    <div v-if="displayImages.length" class="lib-masonry" :style="{ columnCount: libColumns }">
      <div
        v-for="img in displayImages"
        :key="img.slug + '/' + img.name"
        class="masonry-card"
        @click="openDetail(img)"
      >
        <video
          v-if="isVideo(img.name)"
          :src="imageUrl(img.slug, img.name)"
          class="masonry-card-img"
          muted
          loop
          playsinline
          preload="metadata"
          @loadeddata="($event.target as HTMLVideoElement).parentElement?.classList.add('loaded')"
          @mouseenter="($event.target as HTMLVideoElement)?.play()"
          @mouseleave="(e: Event) => { const v = e.target as HTMLVideoElement; v.pause(); v.currentTime = 0 }"
        />
        <img
          v-else
          :src="imageUrl(img.slug, img.name)"
          :alt="img.name"
          class="masonry-card-img"
          loading="lazy"
          @load="($event.target as HTMLImageElement).parentElement?.classList.add('loaded')"
        />
        <!-- Character name (when showing all) -->
        <span v-if="!selectedSlug" class="char-badge">
          {{ img.characterName }}
        </span>
        <!-- Hover action overlay -->
        <div class="hover-actions" @click.stop>
          <button
            class="hover-btn hover-btn-primary"
            title="Generate 3 similar variants"
            @click="quickGenerate(img, 3)"
            :disabled="quickGenerating === img.slug + '/' + img.name"
          >
            {{ quickGenerating === img.slug + '/' + img.name ? '...' : '+3 Similar' }}
          </button>
          <button
            class="hover-btn"
            title="Set as IP-Adapter reference"
            @click="quickSetRef(img)"
          >
            Ref
          </button>
          <button
            class="hover-btn"
            title="Copy file path + metadata for terminal"
            @click="copyReference(img)"
          >
            Copy
          </button>
          <button
            class="hover-btn hover-btn-reject"
            title="Reject — move back to pending"
            @click="quickReject(img)"
          >
            Reject
          </button>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading" style="text-align: center; padding: 48px; color: var(--text-muted);">
      <template v-if="characterList.length === 0">
        No approved images yet. Approve images in the Approve tab to see them here.
      </template>
      <template v-else>
        No approved images for this character.
      </template>
    </div>

    <!-- Loading -->
    <div v-if="loading" style="text-align: center; padding: 32px; color: var(--text-muted);">
      Loading approved images...
    </div>

    <!-- Detail modal -->
    <Teleport to="body">
      <Transition name="panel">
        <div v-if="detailImage" class="panel-overlay" @click.self="detailImage = null">
          <div class="panel-content">
            <!-- Header -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
              <h3 style="font-size: 16px; font-weight: 500;">{{ detailImage.characterName }} - {{ detailImage.name }}</h3>
              <button class="btn" style="font-size: 14px; padding: 4px 10px;" @click="detailImage = null">Close</button>
            </div>

            <!-- Image or Video -->
            <div style="text-align: center; margin-bottom: 16px; background: var(--bg-primary); border-radius: 4px; padding: 8px;">
              <video
                v-if="isVideo(detailImage.name)"
                :src="imageUrl(detailImage.slug, detailImage.name)"
                controls
                autoplay
                loop
                playsinline
                style="max-width: 100%; max-height: 400px; border-radius: 3px;"
              />
              <img
                v-else
                :src="imageUrl(detailImage.slug, detailImage.name)"
                :alt="detailImage.name"
                style="max-width: 100%; max-height: 400px; border-radius: 3px;"
              />
            </div>

            <!-- Metadata -->
            <div v-if="detailMeta" style="margin-bottom: 16px;">
              <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 8px; color: var(--text-secondary);">Generation Metadata</h4>
              <div class="meta-grid">
                <div class="meta-row">
                  <span class="meta-label">Seed</span>
                  <span class="meta-value">
                    <template v-if="detailMeta.seed">
                      <code style="cursor: pointer; color: var(--accent-primary);" @click="copySeed" :title="'Click to copy'">{{ detailMeta.seed }}</code>
                      <span v-if="seedCopied" style="font-size: 10px; color: var(--status-success); margin-left: 4px;">copied</span>
                    </template>
                    <span v-else style="color: var(--text-muted);">unknown</span>
                  </span>
                </div>
                <div class="meta-row">
                  <span class="meta-label">Model</span>
                  <span class="meta-value">{{ detailMeta.checkpoint_model || 'unknown' }}</span>
                </div>
                <div v-if="detailMeta.cfg_scale" class="meta-row">
                  <span class="meta-label">CFG</span>
                  <span class="meta-value">{{ detailMeta.cfg_scale }}</span>
                </div>
                <div v-if="detailMeta.steps" class="meta-row">
                  <span class="meta-label">Steps</span>
                  <span class="meta-value">{{ detailMeta.steps }}</span>
                </div>
                <div v-if="detailMeta.sampler" class="meta-row">
                  <span class="meta-label">Sampler</span>
                  <span class="meta-value">{{ detailMeta.sampler }} / {{ detailMeta.scheduler || 'normal' }}</span>
                </div>
                <div v-if="detailMeta.width" class="meta-row">
                  <span class="meta-label">Size</span>
                  <span class="meta-value">{{ detailMeta.width }}x{{ detailMeta.height }}</span>
                </div>
                <div v-if="detailMeta.quality_score != null" class="meta-row">
                  <span class="meta-label">Quality</span>
                  <span class="meta-value">
                    <span :style="{ color: qualityColor(detailMeta.quality_score) }">{{ (detailMeta.quality_score * 100).toFixed(0) }}%</span>
                  </span>
                </div>
              </div>
            </div>

            <!-- Vision review -->
            <div v-if="detailMeta?.vision_review" style="margin-bottom: 16px;">
              <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 8px; color: var(--text-secondary);">Vision Assessment</h4>
              <div class="meta-grid">
                <div class="meta-row">
                  <span class="meta-label">Character</span>
                  <span class="meta-value">
                    <span :style="{ color: qualityColor(detailMeta.vision_review.character_match / 10) }">{{ detailMeta.vision_review.character_match }}/10</span>
                  </span>
                </div>
                <div class="meta-row">
                  <span class="meta-label">Solo</span>
                  <span class="meta-value" :style="{ color: detailMeta.vision_review.solo ? 'var(--status-success)' : 'var(--status-error)' }">
                    {{ detailMeta.vision_review.solo ? 'Yes' : 'No' }}
                  </span>
                </div>
                <div class="meta-row">
                  <span class="meta-label">Clarity</span>
                  <span class="meta-value">
                    <span :style="{ color: qualityColor(detailMeta.vision_review.clarity / 10) }">{{ detailMeta.vision_review.clarity }}/10</span>
                  </span>
                </div>
                <div class="meta-row">
                  <span class="meta-label">Training Value</span>
                  <span class="meta-value">
                    <span :style="{ color: qualityColor(detailMeta.vision_review.training_value / 10) }">{{ detailMeta.vision_review.training_value }}/10</span>
                  </span>
                </div>
              </div>
              <div v-if="detailMeta.vision_review.caption" style="margin-top: 8px; font-size: 11px; padding: 6px 8px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; line-height: 1.4; color: var(--text-secondary);">
                {{ detailMeta.vision_review.caption }}
              </div>
            </div>

            <!-- Full prompt -->
            <div v-if="detailMeta?.full_prompt" style="margin-bottom: 16px;">
              <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary);">Full Prompt</h4>
              <div style="font-size: 11px; padding: 8px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; line-height: 1.5; max-height: 120px; overflow-y: auto; color: var(--text-secondary);">
                {{ detailMeta.full_prompt }}
              </div>
            </div>

            <!-- Negative prompt -->
            <div v-if="detailMeta?.negative_prompt" style="margin-bottom: 16px;">
              <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary);">Negative Prompt</h4>
              <div style="font-size: 11px; padding: 8px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; line-height: 1.5; max-height: 80px; overflow-y: auto; color: var(--text-muted);">
                {{ detailMeta.negative_prompt }}
              </div>
            </div>

            <!-- Action buttons -->
            <div style="margin-bottom: 16px;">
              <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 8px; color: var(--text-secondary);">Actions</h4>
              <div style="display: flex; flex-direction: column; gap: 8px;">
                <!-- Generate Similar -->
                <div style="display: flex; gap: 6px; align-items: center;">
                  <button
                    class="btn btn-active"
                    style="flex: 1; font-size: 12px;"
                    @click="generateSimilar(3)"
                    :disabled="refining"
                  >
                    {{ refining ? 'Queued...' : 'Generate Similar (3)' }}
                  </button>
                  <button
                    class="btn"
                    style="font-size: 12px; padding: 6px 10px;"
                    @click="generateSimilar(1)"
                    :disabled="refining"
                  >
                    (1)
                  </button>
                </div>

                <!-- Weight / Denoise controls -->
                <div style="display: flex; gap: 8px; align-items: center;">
                  <label style="font-size: 11px; color: var(--text-muted);">Weight:</label>
                  <input
                    v-model.number="refineWeight"
                    type="number"
                    min="0.1"
                    max="1.5"
                    step="0.1"
                    style="width: 60px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
                  />
                  <label style="font-size: 11px; color: var(--text-muted);">Denoise:</label>
                  <input
                    v-model.number="refineDenoise"
                    type="number"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    style="width: 60px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
                  />
                </div>

                <!-- Set as Reference -->
                <button
                  class="btn"
                  style="font-size: 12px;"
                  @click="setAsReference"
                  :disabled="settingRef"
                >
                  {{ settingRef ? 'Done!' : 'Set as IP-Adapter Reference' }}
                </button>

                <!-- Reject / Unapprove -->
                <button
                  class="btn btn-reject"
                  style="font-size: 12px;"
                  @click="rejectFromLibrary"
                  :disabled="rejecting"
                >
                  {{ rejecting ? 'Rejected!' : 'Reject (Remove from Library)' }}
                </button>
              </div>
            </div>

            <!-- Toast -->
            <div v-if="toast" style="padding: 8px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 12px;"
              :style="{ background: toast.type === 'success' ? 'rgba(80,160,80,0.15)' : 'rgba(160,80,80,0.15)', color: toast.type === 'success' ? 'var(--status-success)' : 'var(--status-error)', border: '1px solid ' + (toast.type === 'success' ? 'var(--status-success)' : 'var(--status-error)') }"
            >
              {{ toast.message }}
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/api/client'
import type { ImageMetadata } from '@/types'

interface LibraryImage {
  slug: string
  characterName: string
  name: string
  seed: number | null
  qualityScore: number | null
  project_name: string
  checkpoint_model: string
}

interface CharacterEntry {
  slug: string
  name: string
  approved: number
  project_name: string
  checkpoint_model: string
}

const loading = ref(false)
const selectedSlug = ref('')
const selectedProject = ref('')
const selectedModel = ref('')
const allImages = ref<LibraryImage[]>([])
const characterList = ref<CharacterEntry[]>([])
const allProjects = ref<string[]>([])
const allModels = ref<string[]>([])
const detailImage = ref<LibraryImage | null>(null)
const detailMeta = ref<ImageMetadata | null>(null)
const seedCopied = ref(false)
const refining = ref(false)
const settingRef = ref(false)
const refineWeight = ref(0.7)
const refineDenoise = ref(0.65)
const toast = ref<{ message: string; type: 'success' | 'error' } | null>(null)
const quickGenerating = ref('')
const rejecting = ref(false)
const searchText = ref('')
const libFiltersOpen = ref(false)
const selectedMediaType = ref('')

const libColumns = computed(() => {
  if (typeof window === 'undefined') return 4
  const w = window.innerWidth
  if (w < 640) return 2
  if (w < 1024) return 3
  if (w < 1440) return 4
  if (w < 1920) return 5
  if (w < 2560) return 6
  return 7
})
const libActiveFilterCount = computed(() => {
  let c = 0
  if (selectedProject.value) c++
  if (selectedModel.value) c++
  if (selectedSlug.value) c++
  if (selectedMediaType.value) c++
  return c
})

const totalApproved = computed(() => characterList.value.reduce((s, c) => s + c.approved, 0))

// Context-aware filter lists — model pills only show models relevant to selected project and vice versa
const projectList = computed(() => {
  if (!selectedModel.value) return allProjects.value
  const relevant = new Set(characterList.value.filter(c => c.checkpoint_model === selectedModel.value).map(c => c.project_name))
  return allProjects.value.filter(p => relevant.has(p))
})

const modelList = computed(() => {
  if (!selectedProject.value) return allModels.value
  const relevant = new Set(characterList.value.filter(c => c.project_name === selectedProject.value).map(c => c.checkpoint_model))
  return allModels.value.filter(m => relevant.has(m))
})

const filteredCharacterList = computed(() => {
  let list = characterList.value
  if (selectedProject.value) {
    list = list.filter(c => c.project_name === selectedProject.value)
  }
  if (selectedModel.value) {
    list = list.filter(c => c.checkpoint_model === selectedModel.value)
  }
  return list
})

const filteredApproved = computed(() => filteredCharacterList.value.reduce((s, c) => s + c.approved, 0))

const displayImages = computed(() => {
  let imgs = allImages.value
  if (selectedProject.value) {
    imgs = imgs.filter(img => img.project_name === selectedProject.value)
  }
  if (selectedModel.value) {
    imgs = imgs.filter(img => img.checkpoint_model === selectedModel.value)
  }
  if (selectedSlug.value) {
    imgs = imgs.filter(img => img.slug === selectedSlug.value)
  }
  if (selectedMediaType.value) {
    if (selectedMediaType.value === 'video' || selectedMediaType.value === 'video_audio') {
      imgs = imgs.filter(img => isVideo(img.name))
    } else if (selectedMediaType.value === 'keyframe') {
      imgs = imgs.filter(img => !isVideo(img.name))
    }
  }
  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    imgs = imgs.filter(img => img.name.toLowerCase().includes(q) || img.characterName.toLowerCase().includes(q))
  }
  return imgs
})

function modelShortName(model: string): string {
  return model.replace('.safetensors', '').replace(/_/g, ' ')
}

// Reset downstream filters when upstream filter changes
watch(selectedProject, () => {
  // Clear model if it's no longer relevant to the selected project
  if (selectedModel.value && !modelList.value.includes(selectedModel.value)) {
    selectedModel.value = ''
  }
  selectedSlug.value = ''
})
watch(selectedModel, () => {
  // Clear project if it's no longer relevant to the selected model
  if (selectedProject.value && !projectList.value.includes(selectedProject.value)) {
    selectedProject.value = ''
  }
  selectedSlug.value = ''
})

onMounted(() => {
  refresh()
})

async function refresh() {
  loading.value = true
  try {
    const data = await api.getLibrary()
    characterList.value = data.characters
    allProjects.value = data.projects || []
    allModels.value = data.models || []
    allImages.value = data.images.map(img => ({
      slug: img.slug,
      characterName: img.characterName,
      name: img.name,
      seed: null,
      qualityScore: null,
      project_name: img.project_name || '',
      checkpoint_model: img.checkpoint_model || '',
    }))
  } catch (err) {
    console.error('Failed to load library:', err)
  } finally {
    loading.value = false
  }
}

function isVideo(name: string): boolean {
  return /\.(mp4|webm|mov)$/i.test(name)
}

function imageUrl(slug: string, name: string): string {
  return api.imageUrl(slug, name)
}

async function openDetail(img: LibraryImage) {
  detailImage.value = img
  detailMeta.value = null
  toast.value = null
  try {
    detailMeta.value = await api.getImageMetadata(img.slug, img.name)
  } catch {
    // no metadata
  }
}

function copySeed() {
  if (detailMeta.value?.seed) {
    navigator.clipboard.writeText(String(detailMeta.value.seed))
    seedCopied.value = true
    setTimeout(() => { seedCopied.value = false }, 1500)
  }
}

function qualityColor(score: number): string {
  if (score >= 0.7) return 'var(--status-success)'
  if (score >= 0.4) return 'var(--status-warning)'
  return 'var(--status-error)'
}

async function generateSimilar(count: number) {
  if (!detailImage.value) return
  refining.value = true
  toast.value = null
  try {
    const result = await api.refineImage({
      character_slug: detailImage.value.slug,
      reference_image: detailImage.value.name,
      count,
      weight: refineWeight.value,
      denoise: refineDenoise.value,
    })
    const queued = result.results.filter(r => r.prompt_id).length
    toast.value = {
      message: `${queued} variant${queued !== 1 ? 's' : ''} queued for ${detailImage.value.characterName} — review in Approve tab`,
      type: 'success',
    }
  } catch (err) {
    toast.value = {
      message: `Failed to queue refinement: ${err instanceof Error ? err.message : 'unknown error'}`,
      type: 'error',
    }
  } finally {
    setTimeout(() => { refining.value = false }, 2000)
  }
}

async function quickGenerate(img: LibraryImage, count: number) {
  const key = img.slug + '/' + img.name
  quickGenerating.value = key
  try {
    await api.refineImage({
      character_slug: img.slug,
      reference_image: img.name,
      count,
      weight: 0.7,
      denoise: 0.65,
    })
  } catch { /* swallow — toast shows in detail panel */ }
  finally {
    setTimeout(() => { quickGenerating.value = '' }, 1500)
  }
}

async function quickSetRef(img: LibraryImage) {
  try {
    await api.addReferenceImage(img.slug, img.name)
  } catch { /* swallow */ }
}

async function quickReject(img: LibraryImage) {
  try {
    await api.approveImage({
      character_name: img.characterName,
      character_slug: img.slug,
      image_name: img.name,
      approved: false,
      feedback: 'Rejected from library',
    })
    allImages.value = allImages.value.filter(i => !(i.slug === img.slug && i.name === img.name))
    const ch = characterList.value.find(c => c.slug === img.slug)
    if (ch) ch.approved = Math.max(0, ch.approved - 1)
  } catch { /* swallow */ }
}

async function copyReference(img: LibraryImage) {
  const filePath = `/opt/anime-studio/datasets/${img.slug}/approved/${img.name}`
  const meta = [
    `File: ${filePath}`,
    `Character: ${img.characterName} (${img.slug})`,
    `Project: ${img.project_name}`,
    `Checkpoint: ${img.checkpoint_model}`,
    img.seed ? `Seed: ${img.seed}` : '',
    img.qualityScore ? `Quality: ${img.qualityScore}` : '',
  ].filter(Boolean).join('\n')
  try {
    await navigator.clipboard.writeText(meta)
    toast.value = { type: 'success', text: 'Copied to clipboard' }
  } catch {
    prompt('Copy this reference:', meta)
  }
}

async function rejectFromLibrary() {
  if (!detailImage.value) return
  rejecting.value = true
  toast.value = null
  try {
    await api.approveImage({
      character_name: detailImage.value.characterName,
      character_slug: detailImage.value.slug,
      image_name: detailImage.value.name,
      approved: false,
      feedback: 'Rejected from library',
    })
    allImages.value = allImages.value.filter(i => !(i.slug === detailImage.value!.slug && i.name === detailImage.value!.name))
    const ch = characterList.value.find(c => c.slug === detailImage.value!.slug)
    if (ch) ch.approved = Math.max(0, ch.approved - 1)
    toast.value = { message: `Rejected ${detailImage.value.name} — moved back to pending`, type: 'success' }
    setTimeout(() => { detailImage.value = null }, 800)
  } catch (err) {
    toast.value = { message: `Failed: ${err instanceof Error ? err.message : 'unknown error'}`, type: 'error' }
  } finally {
    setTimeout(() => { rejecting.value = false }, 2000)
  }
}

async function setAsReference() {
  if (!detailImage.value) return
  settingRef.value = true
  toast.value = null
  try {
    await api.addReferenceImage(detailImage.value.slug, detailImage.value.name)
    toast.value = {
      message: `Set as IP-Adapter reference for ${detailImage.value.characterName}`,
      type: 'success',
    }
  } catch (err) {
    toast.value = {
      message: `Failed: ${err instanceof Error ? err.message : 'unknown error'}`,
      type: 'error',
    }
  } finally {
    setTimeout(() => { settingRef.value = false }, 2000)
  }
}
</script>

<style scoped>
/* Masonry grid */
.lib-masonry {
  column-gap: 10px;
  column-fill: balance;
}
.masonry-card {
  break-inside: avoid;
  margin-bottom: 10px;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  cursor: pointer;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.masonry-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}
.masonry-card:not(.loaded) { min-height: 180px; }
.masonry-card-img {
  width: 100%;
  display: block;
  opacity: 0;
  transition: opacity 300ms ease;
}
.masonry-card.loaded .masonry-card-img { opacity: 1; }

/* Collapse transition */
.lib-collapse-enter-active, .lib-collapse-leave-active {
  transition: all 200ms ease;
  overflow: hidden;
}
.lib-collapse-enter-from, .lib-collapse-leave-to {
  opacity: 0;
  max-height: 0;
  padding: 0 12px;
  margin-bottom: 0;
}
.lib-collapse-enter-to, .lib-collapse-leave-from {
  max-height: 300px;
}

.image-card {
  padding: 0;
  overflow: hidden;
  cursor: pointer;
  position: relative;
}

.char-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  background: rgba(0, 0, 0, 0.7);
  color: var(--text-secondary);
}

.hover-actions {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  gap: 4px;
  padding: 6px;
  background: linear-gradient(to bottom, rgba(0,0,0,0.75) 0%, transparent 100%);
  opacity: 0;
  transition: opacity 150ms ease;
}

.image-card:hover .hover-actions {
  opacity: 1;
}

.hover-btn {
  padding: 3px 8px;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 3px;
  background: rgba(0,0,0,0.5);
  color: #fff;
  font-size: 10px;
  cursor: pointer;
  font-family: var(--font-primary);
  transition: background 100ms ease;
}

.hover-btn:hover {
  background: rgba(0,0,0,0.8);
}

.hover-btn:disabled {
  opacity: 0.5;
}

.hover-btn-primary {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
}

.hover-btn-primary:hover {
  background: var(--accent-primary);
  filter: brightness(1.2);
}

.hover-btn-reject {
  background: rgba(180, 60, 60, 0.7);
  border-color: var(--status-error);
}

.hover-btn-reject:hover {
  background: rgba(180, 60, 60, 0.9);
}

.btn-reject {
  color: var(--status-error);
  border-color: var(--status-error);
}

.btn-reject:hover {
  background: rgba(180, 60, 60, 0.15);
}

.chip {
  padding: 4px 12px;
  border-radius: 16px;
  border: 1px solid var(--border-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-family: var(--font-primary);
  transition: all 150ms ease;
}

.chip:hover {
  border-color: var(--accent-primary);
  color: var(--text-primary);
}

.chip.active {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: #fff;
}
.chip-small {
  padding: 2px 8px;
  font-size: 11px;
}
.filter-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 60px;
}

.panel-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.panel-content {
  width: 480px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-primary);
  padding: 20px;
  overflow-y: auto;
}

.panel-enter-active,
.panel-leave-active {
  transition: all 200ms ease;
}
.panel-enter-from .panel-content,
.panel-leave-to .panel-content {
  transform: translateX(100%);
}
.panel-enter-from,
.panel-leave-to {
  opacity: 0;
}

.meta-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 8px;
  font-size: 12px;
  background: var(--bg-primary);
  border-radius: 2px;
}

.meta-label {
  color: var(--text-muted);
  min-width: 80px;
}

.meta-value {
  color: var(--text-secondary);
  text-align: right;
}
</style>
