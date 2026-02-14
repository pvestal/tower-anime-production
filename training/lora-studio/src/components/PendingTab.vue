<template>
  <div>
    <!-- Toast notifications -->
    <div style="position: fixed; top: 16px; right: 16px; z-index: 1000; display: flex; flex-direction: column; gap: 8px;">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :style="{
            padding: '10px 16px',
            borderRadius: '4px',
            fontSize: '13px',
            fontFamily: 'var(--font-primary)',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            border: '1px solid',
            minWidth: '280px',
            background: toast.type === 'approve' ? 'rgba(80,160,80,0.15)' : toast.type === 'regen' ? 'rgba(80,120,200,0.15)' : 'rgba(160,80,80,0.15)',
            borderColor: toast.type === 'approve' ? 'var(--status-success)' : toast.type === 'regen' ? 'var(--accent-primary)' : 'var(--status-error)',
            color: toast.type === 'approve' ? 'var(--status-success)' : toast.type === 'regen' ? 'var(--accent-primary)' : 'var(--status-error)',
          }"
        >
          {{ toast.message }}
        </div>
      </TransitionGroup>
    </div>

    <!-- Batch progress overlay -->
    <div v-if="batchProgress" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 999; display: flex; align-items: center; justify-content: center;">
      <div class="card" style="text-align: center; min-width: 300px;">
        <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 12px;"></div>
        <p style="color: var(--text-primary); margin-bottom: 4px;">{{ batchProgress.action }}</p>
        <p style="color: var(--text-muted); font-size: 13px;">{{ batchProgress.done }}/{{ batchProgress.total }}</p>
        <div class="progress-track" style="margin-top: 12px;">
          <div class="progress-bar" :style="{ width: `${(batchProgress.done / batchProgress.total) * 100}%` }"></div>
        </div>
      </div>
    </div>

    <!-- Inline prompt editor overlay -->
    <div v-if="editingImage" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 998; display: flex; align-items: center; justify-content: center;" @click.self="editingImage = null">
      <div class="card" style="min-width: 480px; max-width: 600px;">
        <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 8px;">
          {{ editingAction === 'approve' ? 'Approve' : 'Reject' }} — {{ editingImage.character_name }}
        </h4>
        <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">
          Edit the caption for this image. This will update the training caption file.
        </p>
        <textarea
          ref="editPromptEl"
          v-model="editPromptText"
          @keydown.ctrl.enter="submitEditedApproval"
          @keydown.meta.enter="submitEditedApproval"
          style="width: 100%; min-height: 80px; font-size: 12px; padding: 8px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary); line-height: 1.5;"
        ></textarea>
        <div style="display: flex; justify-content: space-between; margin-top: 2px;">
          <span style="font-size: 10px; color: var(--text-muted);">{{ editPromptText.length }} chars</span>
          <span style="font-size: 10px; color: var(--text-muted);">Ctrl+Enter to submit</span>
        </div>

        <!-- Structured rejection reasons (only show on reject) -->
        <div v-if="editingAction === 'reject'" style="margin-top: 10px;">
          <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 6px;">
            What's wrong? (select all that apply — feeds into regeneration)
          </label>
          <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            <button
              v-for="reason in rejectionReasons"
              :key="reason.id"
              :class="['rejection-chip', { active: selectedReasons.has(reason.id) }]"
              @click="toggleReason(reason.id)"
            >
              {{ reason.label }}
            </button>
          </div>
        </div>

        <div style="margin-top: 8px;">
          <label style="font-size: 11px; color: var(--text-muted);">Additional notes (optional):</label>
          <input
            v-model="editFeedbackText"
            type="text"
            :placeholder="editingAction === 'reject' ? 'e.g., wrong hair color, needs more detail' : 'e.g., good pose, accurate colors'"
            style="width: 100%; padding: 6px 8px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-top: 4px;"
          />
        </div>
        <div style="display: flex; gap: 8px; margin-top: 12px;">
          <button
            :class="editingAction === 'approve' ? 'btn btn-success' : 'btn btn-danger'"
            style="flex: 1;"
            @click="submitEditedApproval"
          >
            {{ editingAction === 'approve' ? 'Approve' : 'Reject' }} with Edits
          </button>
          <button
            :class="editingAction === 'approve' ? 'btn btn-success' : 'btn btn-danger'"
            style="flex: 1; opacity: 0.7;"
            @click="submitQuickApproval"
          >
            {{ editingAction === 'approve' ? 'Approve' : 'Reject' }} (no changes)
          </button>
          <button class="btn" @click="editingImage = null">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Reassign character modal -->
    <div v-if="reassigningImage" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 998; display: flex; align-items: center; justify-content: center;" @click.self="reassigningImage = null">
      <div class="card" style="min-width: 400px; max-width: 500px;">
        <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 8px;">
          Reassign Image
        </h4>
        <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">
          Move <strong>{{ reassigningImage.name }}</strong> from <strong>{{ reassigningImage.character_name }}</strong> to:
        </p>
        <select
          v-model="reassignTarget"
          style="width: 100%; padding: 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; font-family: var(--font-primary);"
        >
          <option value="" disabled>Select character...</option>
          <option
            v-for="char in availableReassignTargets"
            :key="char.slug"
            :value="char.slug"
          >{{ char.name }} ({{ char.project_name }})</option>
        </select>
        <div style="display: flex; gap: 8px; margin-top: 12px;">
          <button
            class="btn"
            style="flex: 1; background: var(--accent-primary); color: var(--bg-primary);"
            :disabled="!reassignTarget || reassigning"
            @click="submitReassign"
          >
            {{ reassigning ? 'Moving...' : 'Reassign' }}
          </button>
          <button class="btn" @click="reassigningImage = null">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Header with filters and batch actions -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <h2 style="font-size: 18px; font-weight: 500;">Pending Approval</h2>
        <span style="font-size: 13px; color: var(--text-muted);">
          {{ modelFilteredImages.length }} images
        </span>
      </div>
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <select v-model="approvalStore.filterProject" @change="onProjectFilterChange" style="min-width: 200px;">
          <option value="">All Projects</option>
          <option v-for="name in approvalStore.projectNames" :key="name" :value="name">
            {{ name }} ({{ projectImageCount(name) }})
          </option>
        </select>
        <select v-model="approvalStore.filterCharacter" style="min-width: 180px;">
          <option value="">All Characters</option>
          <option v-for="name in approvalStore.characterNames" :key="name" :value="name">
            {{ name }} ({{ approvalStore.groupedImages[name]?.length || 0 }})
          </option>
        </select>
        <button class="btn" @click="approvalStore.fetchPendingImages()" :disabled="approvalStore.loading">
          Refresh
        </button>
        <button
          v-if="selectedImages.size > 0"
          class="btn btn-success"
          @click="batchApprove(true)"
          :disabled="approvalStore.loading"
        >
          Approve {{ selectedImages.size }}
        </button>
        <button
          v-if="selectedImages.size > 0"
          class="btn btn-danger"
          @click="batchApprove(false)"
          :disabled="approvalStore.loading"
        >
          Reject {{ selectedImages.size }}
        </button>
      </div>
    </div>

    <!-- Model filter chips -->
    <div v-if="modelNames.length > 1" style="display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center;">
      <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-right: 4px;">Model:</span>
      <button
        class="model-chip"
        :class="{ active: !filterModel }"
        @click="filterModel = ''"
      >
        All ({{ approvalStore.filteredImages.length }})
      </button>
      <button
        v-for="m in modelNames"
        :key="m.name"
        class="model-chip"
        :class="{ active: filterModel === m.name }"
        @click="filterModel = filterModel === m.name ? '' : m.name"
      >
        {{ m.short }} ({{ m.count }})
      </button>
    </div>

    <!-- Loading -->
    <div v-if="approvalStore.loading && !batchProgress" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading pending images...</p>
    </div>

    <!-- Error -->
    <div v-else-if="approvalStore.error" class="card" style="background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error);">{{ approvalStore.error }}</p>
      <button class="btn" @click="approvalStore.clearError()" style="margin-top: 8px;">Dismiss</button>
    </div>

    <!-- Empty -->
    <div v-else-if="modelFilteredImages.length === 0 && !batchProgress" style="text-align: center; padding: 48px;">
      <p style="color: var(--text-muted); font-size: 16px;">No pending approvals</p>
      <p style="color: var(--text-muted); font-size: 13px;">All images have been reviewed.</p>
    </div>

    <!-- Hierarchical display: Project → Character → Images -->
    <div v-else>
      <div v-for="(projectGroup, projectName) in projectCharacterGroups" :key="projectName" style="margin-bottom: 36px;">
        <!-- Project header -->
        <div style="margin-bottom: 16px; padding-bottom: 10px; border-bottom: 2px solid var(--accent-primary);">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 12px;">
              <h3 style="font-size: 17px; font-weight: 600;">{{ projectName }}</h3>
              <span class="badge badge-pending">{{ projectGroup.total }} pending</span>
              <!-- Show model from first image in group -->
              <span v-if="projectGroup.checkpoint" class="context-tag model-tag">
                {{ projectGroup.checkpoint.replace('.safetensors', '') }}
              </span>
              <span v-if="projectGroup.style" class="context-tag style-tag">
                {{ projectGroup.style }}
              </span>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="btn" style="font-size: 12px; padding: 4px 10px;" @click="selectAllProject(projectGroup)">
                Select All
              </button>
              <button
                class="btn llava-btn"
                :class="{ 'llava-active': llavaReviewing === `project:${projectName}` }"
                style="font-size: 12px; padding: 4px 10px;"
                @click.stop="runLlavaReviewProject(projectName, projectGroup)"
                :disabled="!!llavaReviewing"
              >
                <span v-if="llavaReviewing === `project:${projectName}`" class="spinner" style="width: 10px; height: 10px; display: inline-block; vertical-align: middle; margin-right: 4px; border-width: 2px;"></span>
                {{ llavaReviewing === `project:${projectName}` ? 'Analyzing...' : 'LLaVA Review All' }}
              </button>
              <button class="btn btn-success" style="font-size: 12px; padding: 4px 10px;" @click="approveAllProject(projectName, projectGroup)">
                Approve All
              </button>
            </div>
          </div>
        </div>

        <!-- Character subgroups within this project -->
        <div v-for="(charImages, charName) in projectGroup.characters" :key="charName" style="margin-bottom: 24px; margin-left: 12px;">
          <!-- Character header with context -->
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border-primary);">
            <div style="display: flex; align-items: center; gap: 10px;">
              <h4 style="font-size: 15px; font-weight: 500;">{{ charName }}</h4>
              <span class="badge badge-pending" style="font-size: 11px;">{{ charImages.length }} pending</span>
            </div>
            <div style="display: flex; gap: 6px;">
              <button class="btn" style="font-size: 11px; padding: 3px 8px;" @click="selectAll(charImages)">
                Select
              </button>
              <button
                class="btn llava-btn"
                :class="{ 'llava-active': llavaReviewing === charName }"
                style="font-size: 11px; padding: 3px 8px;"
                @click.stop="runLlavaReview(charName, charImages)"
                :disabled="!!llavaReviewing"
              >
                <span v-if="llavaReviewing === charName" class="spinner" style="width: 10px; height: 10px; display: inline-block; vertical-align: middle; margin-right: 4px; border-width: 2px;"></span>
                {{ llavaReviewing === charName ? 'Analyzing...' : 'LLaVA Review' }}
              </button>
              <button class="btn btn-success" style="font-size: 11px; padding: 3px 8px;" @click="approveGroup(charName, charImages)">
                Approve All
              </button>
            </div>
          </div>

          <!-- Image grid -->
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px;">
            <TransitionGroup name="card">
              <div
                v-for="image in charImages"
                :key="image.id"
                class="image-card"
                :class="{
                  selected: selectedImages.has(image.id),
                  expanded: expandedImage === image.id,
                  'flash-approve': flashState[image.id] === 'approve',
                  'flash-reject': flashState[image.id] === 'reject',
                  'llava-reviewed': !!image.metadata?.llava_review,
                }"
                @click="toggleExpand(image)"
              >
                <!-- Selection checkbox -->
                <div class="select-check" @click.stop="toggleSelection(image)">
                  <input type="checkbox" :checked="selectedImages.has(image.id)" />
                </div>

                <img
                  :src="imageUrl(image)"
                  :alt="image.name"
                  loading="lazy"
                  @error="onImageError($event)"
                />

                <div class="meta">
                  <!-- Context badges: always visible -->
                  <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px;">
                    <span class="context-tag char-tag">{{ image.character_name }}</span>
                    <span v-if="image.checkpoint_model" class="context-tag model-tag">
                      {{ image.checkpoint_model.replace('.safetensors', '') }}
                    </span>
                    <span v-if="image.metadata?.seed" class="seed-badge" @click.stop="copySeed(image.metadata.seed)" title="Copy seed">
                      {{ image.metadata.seed }}
                    </span>
                    <span v-if="image.metadata?.quality_score != null" class="context-tag" :style="{ color: qualityColor(image.metadata.quality_score), borderColor: qualityColor(image.metadata.quality_score) }">
                      Q:{{ (image.metadata.quality_score * 100).toFixed(0) }}%
                    </span>
                  </div>

                  <!-- LLaVA review inline indicators -->
                  <div v-if="image.metadata?.llava_review" style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 4px;">
                    <span class="context-tag" :style="{ color: image.metadata.llava_review.solo ? 'var(--status-success)' : 'var(--status-error)', borderColor: image.metadata.llava_review.solo ? 'var(--status-success)' : 'var(--status-error)' }">
                      {{ image.metadata.llava_review.solo ? 'Solo' : 'Multi' }}
                    </span>
                    <span class="context-tag" style="color: var(--text-muted); border-color: var(--border-primary);">
                      {{ image.metadata.llava_review.completeness }}
                    </span>
                    <span v-for="issue in (image.metadata.llava_review.issues || []).slice(0, 2)" :key="issue" class="context-tag" style="color: var(--status-warning); border-color: var(--status-warning);">
                      {{ issue.length > 30 ? issue.slice(0, 27) + '...' : issue }}
                    </span>
                  </div>

                  <!-- Expanded details -->
                  <div v-if="expandedImage === image.id" style="margin-bottom: 8px;">
                    <div v-if="image.metadata?.pose" style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">
                      Pose: {{ image.metadata.pose }}
                    </div>
                    <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4; padding: 4px 6px; background: var(--bg-primary); border-radius: 2px; max-height: 60px; overflow-y: auto;">
                      {{ image.design_prompt || image.prompt || 'No prompt' }}
                    </div>
                  </div>

                  <!-- Action buttons -->
                  <div style="display: flex; gap: 4px;">
                    <button
                      class="btn btn-success"
                      style="flex: 1; font-size: 12px; padding: 4px 8px;"
                      @click.stop="openApprovalEditor(image, 'approve')"
                      :disabled="approvalStore.loading"
                    >
                      Approve
                    </button>
                    <button
                      class="btn btn-danger"
                      style="flex: 1; font-size: 12px; padding: 4px 8px;"
                      @click.stop="openApprovalEditor(image, 'reject')"
                      :disabled="approvalStore.loading"
                    >
                      Reject
                    </button>
                    <button
                      class="btn"
                      style="font-size: 11px; padding: 4px 6px; white-space: nowrap;"
                      title="Reassign to different character"
                      @click.stop="openReassign(image)"
                      :disabled="approvalStore.loading"
                    >
                      &#8644;
                    </button>
                    <button
                      class="btn"
                      style="font-size: 11px; padding: 4px 6px; white-space: nowrap;"
                      @click.stop="detailImage = image"
                      title="Full details + regeneration controls"
                    >
                      More
                    </button>
                  </div>
                </div>
              </div>
            </TransitionGroup>
          </div>
        </div>
      </div>
    </div>

    <!-- Image detail slide-over panel -->
    <ImageDetailPanel
      :image="detailImage"
      :action-disabled="approvalStore.loading"
      @close="detailImage = null"
      @approve="onDetailApprove"
      @reassign="(img) => { detailImage = null; openReassign(img) }"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useApprovalStore } from '@/stores/approval'
import { useCharactersStore } from '@/stores/characters'
import { api } from '@/api/client'
import type { PendingImage } from '@/types'
import ImageDetailPanel from '@/components/ImageDetailPanel.vue'

const MIN_TRAINING = 10
const approvalStore = useApprovalStore()
const charactersStore = useCharactersStore()
const filterModel = ref('')
const selectedImages = ref<Set<string>>(new Set())
const expandedImage = ref<string | null>(null)
const flashState = reactive<Record<string, 'approve' | 'reject' | null>>({})
const toasts = ref<{ id: number; message: string; type: 'approve' | 'reject' | 'regen' }[]>([])
const batchProgress = ref<{ action: string; done: number; total: number } | null>(null)
const detailImage = ref<PendingImage | null>(null)

// LLaVA review state
const llavaReviewing = ref<string | null>(null)

// Inline editor state
const editingImage = ref<PendingImage | null>(null)
const editingAction = ref<'approve' | 'reject'>('approve')
const editPromptText = ref('')
const editFeedbackText = ref('')
const selectedReasons = ref<Set<string>>(new Set())

// Reassign state
const reassigningImage = ref<PendingImage | null>(null)
const reassignTarget = ref('')
const reassigning = ref(false)

const availableReassignTargets = computed(() => {
  if (!reassigningImage.value) return []
  const currentSlug = reassigningImage.value.character_slug
  return charactersStore.characters
    .filter(c => c.slug !== currentSlug)
    .sort((a, b) => a.name.localeCompare(b.name))
})

// Structured rejection reason categories (IDs match backend REJECTION_NEGATIVE_MAP)
const rejectionReasons = [
  { id: 'wrong_appearance', label: 'Wrong Appearance' },
  { id: 'wrong_style', label: 'Wrong Style' },
  { id: 'bad_quality', label: 'Bad Quality' },
  { id: 'not_solo', label: 'Not Solo' },
  { id: 'wrong_pose', label: 'Wrong Pose' },
  { id: 'wrong_expression', label: 'Wrong Expression' },
]

function toggleReason(id: string) {
  if (selectedReasons.value.has(id)) {
    selectedReasons.value.delete(id)
  } else {
    selectedReasons.value.add(id)
  }
  selectedReasons.value = new Set(selectedReasons.value)
}

let toastId = 0

interface CharacterGroup {
  [characterName: string]: PendingImage[]
}

interface ProjectGroup {
  characters: CharacterGroup
  total: number
  checkpoint: string
  style: string
}

// Unique checkpoint models with counts
const modelNames = computed(() => {
  const counts: Record<string, number> = {}
  for (const img of approvalStore.filteredImages) {
    const model = img.checkpoint_model || 'unknown'
    counts[model] = (counts[model] || 0) + 1
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count, short: name.replace('.safetensors', '') }))
})

// Images filtered by model (on top of store's project/character filter)
const modelFilteredImages = computed(() => {
  const base = approvalStore.filteredImages
  if (!filterModel.value) return base
  return base.filter(img => (img.checkpoint_model || 'unknown') === filterModel.value)
})

// Hierarchical grouping: Project → Character → Images
const projectCharacterGroups = computed(() => {
  const groups: Record<string, ProjectGroup> = {}
  for (const img of modelFilteredImages.value) {
    const proj = img.project_name || 'Unknown'
    if (!groups[proj]) {
      groups[proj] = {
        characters: {},
        total: 0,
        checkpoint: img.checkpoint_model || '',
        style: img.default_style || '',
      }
    }
    if (!groups[proj].characters[img.character_name]) {
      groups[proj].characters[img.character_name] = []
    }
    groups[proj].characters[img.character_name].push(img)
    groups[proj].total++
  }
  return groups
})

function projectImageCount(projectName: string): number {
  return approvalStore.pendingImages.filter(img => img.project_name === projectName).length
}

function onProjectFilterChange() {
  approvalStore.filterCharacter = ''
}

function imageUrl(image: PendingImage): string {
  return api.imageUrl(image.character_slug, image.name)
}

function onImageError(event: Event) {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}

function showToast(message: string, type: 'approve' | 'reject' | 'regen', durationMs = 3000) {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, durationMs)
}

function toggleExpand(image: PendingImage) {
  expandedImage.value = expandedImage.value === image.id ? null : image.id
}

function toggleSelection(image: PendingImage) {
  if (selectedImages.value.has(image.id)) {
    selectedImages.value.delete(image.id)
  } else {
    selectedImages.value.add(image.id)
  }
  selectedImages.value = new Set(selectedImages.value)
}

function selectAll(images: PendingImage[]) {
  for (const img of images) {
    selectedImages.value.add(img.id)
  }
  selectedImages.value = new Set(selectedImages.value)
}

function selectAllProject(projectGroup: ProjectGroup) {
  for (const images of Object.values(projectGroup.characters)) {
    for (const img of images) {
      selectedImages.value.add(img.id)
    }
  }
  selectedImages.value = new Set(selectedImages.value)
}

function openReassign(image: PendingImage) {
  reassigningImage.value = image
  reassignTarget.value = ''
  // Ensure characters are loaded for dropdown
  if (charactersStore.characters.length === 0) {
    charactersStore.fetchCharacters()
  }
}

async function submitReassign() {
  if (!reassigningImage.value || !reassignTarget.value) return
  reassigning.value = true
  const image = reassigningImage.value
  const target = reassignTarget.value

  try {
    await api.reassignImage({
      character_slug: image.character_slug,
      image_name: image.name,
      target_character_slug: target,
    })
    const targetChar = charactersStore.characters.find(c => c.slug === target)
    showToast(`Moved ${image.name} → ${targetChar?.name || target}`, 'regen')
    reassigningImage.value = null
    await approvalStore.fetchPendingImages()
  } catch (e: any) {
    showToast(`Reassign failed: ${e.message}`, 'reject')
  } finally {
    reassigning.value = false
  }
}

function openApprovalEditor(image: PendingImage, action: 'approve' | 'reject') {
  editingImage.value = image
  editingAction.value = action
  editPromptText.value = image.design_prompt || image.prompt || ''
  editFeedbackText.value = ''
  selectedReasons.value = new Set()
}

function buildFeedbackString(): string {
  // Combine structured reasons with free text: "wrong_appearance|bad_quality|Free text note"
  const parts: string[] = [...selectedReasons.value]
  if (editFeedbackText.value.trim()) {
    parts.push(editFeedbackText.value.trim())
  }
  return parts.length > 0 ? parts.join('|') : ''
}

async function submitEditedApproval() {
  if (!editingImage.value) return
  const image = editingImage.value
  const approved = editingAction.value === 'approve'
  editingImage.value = null

  await doApprove(image, approved, buildFeedbackString(), editPromptText.value)
}

async function submitQuickApproval() {
  if (!editingImage.value) return
  const image = editingImage.value
  const approved = editingAction.value === 'approve'
  editingImage.value = null

  await doApprove(image, approved, buildFeedbackString(), '')
}

async function doApprove(image: PendingImage, approved: boolean, feedback: string = '', editedPrompt: string = '') {
  const type = approved ? 'approve' : 'reject'
  flashState[image.id] = type

  await new Promise(r => setTimeout(r, 250))

  try {
    await approvalStore.approveImage(image, approved, feedback, editedPrompt)
    await charactersStore.fetchCharacterDataset(image.character_slug || image.character_name)
    const charStats = charactersStore.getCharacterStats(image.character_slug || image.character_name)
    const approvedNow = charStats.approved

    if (approved && approvedNow >= MIN_TRAINING) {
      showToast(
        `${image.character_name} READY TO TRAIN! (${approvedNow}/${MIN_TRAINING})`,
        'approve'
      )
    } else if (approved) {
      showToast(
        `Approved ${image.character_name} (${approvedNow}/${MIN_TRAINING})`,
        type
      )
    } else {
      showToast(`Rejected ${image.character_name} — regenerating`, type)
    }
  } catch {
    showToast(`Failed to ${type} image`, 'reject')
  }

  selectedImages.value.delete(image.id)
  selectedImages.value = new Set(selectedImages.value)
  if (expandedImage.value === image.id) expandedImage.value = null
  delete flashState[image.id]
}

async function approveGroup(groupName: string, images: PendingImage[]) {
  batchProgress.value = { action: `Approving ${images.length} for ${groupName}...`, done: 0, total: images.length }
  for (const image of images) {
    try { await approvalStore.approveImage(image, true) } catch { /* continue */ }
    batchProgress.value!.done++
  }
  batchProgress.value = null
  showToast(`Approved ${images.length} for ${groupName}`, 'approve')
}

async function approveAllProject(projectName: string, projectGroup: ProjectGroup) {
  const allImages = Object.values(projectGroup.characters).flat()
  batchProgress.value = { action: `Approving ${allImages.length} for ${projectName}...`, done: 0, total: allImages.length }
  for (const image of allImages) {
    try { await approvalStore.approveImage(image, true) } catch { /* continue */ }
    batchProgress.value!.done++
  }
  batchProgress.value = null
  showToast(`Approved ${allImages.length} for ${projectName}`, 'approve')
}

function copySeed(seed: number) {
  navigator.clipboard.writeText(String(seed))
  showToast(`Seed ${seed} copied`, 'approve')
}

function qualityColor(score: number): string {
  if (score >= 0.7) return 'var(--status-success)'
  if (score >= 0.4) return 'var(--status-warning)'
  return 'var(--status-error)'
}

async function onDetailApprove(image: PendingImage, approved: boolean) {
  await doApprove(image, approved)
  detailImage.value = null
}

async function runLlavaReviewProject(projectName: string, projectGroup: ProjectGroup) {
  if (llavaReviewing.value) return
  llavaReviewing.value = `project:${projectName}`
  const totalImages = projectGroup.total

  const est = totalImages * 8
  showToast(`LLaVA reviewing ${totalImages} images across ${Object.keys(projectGroup.characters).length} characters (~${est}s)...`, 'regen', est * 1000)

  try {
    const result = await api.llavaReview({ project_name: projectName, max_images: totalImages })

    const parts = [`${result.reviewed} reviewed`]
    if (result.auto_approved) parts.push(`${result.auto_approved} auto-approved`)
    if (result.auto_rejected) parts.push(`${result.auto_rejected} auto-rejected`)
    if (result.regen_queued) parts.push(`${result.regen_queued} regen queued`)
    const still = result.results.filter(r => r.action === 'pending').length
    if (still) parts.push(`${still} need manual review`)

    showToast(`${projectName}: ${parts.join(', ')}`, 'regen', 8000)

    await approvalStore.fetchPendingImages()
  } catch (err) {
    showToast(`LLaVA review failed for ${projectName}`, 'reject')
    console.error('LLaVA project review failed:', err)
  } finally {
    llavaReviewing.value = null
  }
}

async function runLlavaReview(charName: string, images: PendingImage[]) {
  if (llavaReviewing.value) return
  llavaReviewing.value = charName
  const slug = images[0]?.character_slug
  if (!slug) { llavaReviewing.value = null; return }

  const est = images.length * 8
  showToast(`LLaVA reviewing ${images.length} ${charName} images (~${est}s)...`, 'regen', est * 1000)

  try {
    const result = await api.llavaReview({ character_slug: slug, max_images: images.length })

    const parts = [`${result.reviewed} reviewed`]
    if (result.auto_approved) parts.push(`${result.auto_approved} auto-approved`)
    if (result.auto_rejected) parts.push(`${result.auto_rejected} auto-rejected`)
    if (result.regen_queued) parts.push(`${result.regen_queued} regen queued`)
    const still = result.results.filter(r => r.action === 'pending').length
    if (still) parts.push(`${still} need manual review`)

    showToast(`${charName}: ${parts.join(', ')}`, 'regen', 8000)

    await approvalStore.fetchPendingImages()
  } catch (err) {
    showToast(`LLaVA review failed for ${charName}`, 'reject')
    console.error('LLaVA review failed:', err)
  } finally {
    llavaReviewing.value = null
  }
}

async function batchApprove(approved: boolean) {
  const selected = approvalStore.pendingImages.filter(img => selectedImages.value.has(img.id))
  const action = approved ? 'Approving' : 'Rejecting'
  batchProgress.value = { action: `${action} ${selected.length} images...`, done: 0, total: selected.length }
  for (const image of selected) {
    try { await approvalStore.approveImage(image, approved) } catch { /* continue */ }
    batchProgress.value!.done++
  }
  batchProgress.value = null
  selectedImages.value = new Set()
  showToast(`${approved ? 'Approved' : 'Rejected'} ${selected.length} images`, approved ? 'approve' : 'reject')
}
</script>

<style scoped>
.card-enter-active { transition: all 300ms ease; }
.card-leave-active { transition: all 400ms ease; }
.card-enter-from { opacity: 0; transform: scale(0.9); }
.card-leave-to { opacity: 0; transform: scale(0.85); }

.toast-enter-active { transition: all 250ms ease; }
.toast-leave-active { transition: all 300ms ease; }
.toast-enter-from { opacity: 0; transform: translateX(40px); }
.toast-leave-to { opacity: 0; transform: translateX(40px); }

.image-card {
  position: relative;
  cursor: pointer;
  transition: all 200ms ease;
}

.image-card.expanded {
  border-color: var(--accent-primary) !important;
  box-shadow: 0 0 8px rgba(80, 120, 200, 0.25);
}

.image-card.flash-approve {
  border-color: var(--status-success) !important;
  box-shadow: 0 0 12px rgba(80, 160, 80, 0.4);
  transform: scale(0.97);
}
.image-card.flash-reject {
  border-color: var(--status-error) !important;
  box-shadow: 0 0 12px rgba(160, 80, 80, 0.4);
  transform: scale(0.97);
}

.select-check {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 2;
  cursor: pointer;
}
.select-check input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent-primary);
}

/* Context tags for project/character/model association */
.context-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 2px;
  border: 1px solid var(--border-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}
.char-tag {
  background: rgba(80, 120, 200, 0.12);
  color: var(--accent-primary);
  border-color: var(--accent-primary);
  font-weight: 500;
}
.model-tag {
  background: rgba(160, 120, 80, 0.12);
  color: var(--status-warning);
  border-color: var(--status-warning);
}
.style-tag {
  background: rgba(120, 80, 160, 0.12);
  color: #b080d0;
  border-color: #b080d0;
}

.seed-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  background: rgba(80, 120, 200, 0.15);
  color: var(--accent-primary);
  border: 1px solid var(--accent-primary);
  cursor: pointer;
  font-family: monospace;
  white-space: nowrap;
}
.seed-badge:hover {
  background: rgba(80, 120, 200, 0.3);
}

.model-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-primary);
  transition: all 150ms ease;
  white-space: nowrap;
}
.model-chip:hover {
  border-color: var(--status-warning);
  color: var(--status-warning);
}
.model-chip.active {
  background: rgba(160, 120, 80, 0.15);
  border-color: var(--status-warning);
  color: var(--status-warning);
  font-weight: 500;
}

.llava-btn {
  color: var(--accent-primary);
  transition: all 200ms ease;
}
.llava-btn:hover:not(:disabled) {
  background: rgba(80, 120, 200, 0.15);
  border-color: var(--accent-primary);
}
.llava-active {
  background: rgba(80, 120, 200, 0.12) !important;
  border-color: var(--accent-primary) !important;
  animation: llava-pulse 1.5s ease-in-out infinite;
}
@keyframes llava-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.image-card.llava-reviewed {
  border-left: 3px solid var(--accent-primary);
}

.rejection-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-primary);
  transition: all 150ms ease;
}
.rejection-chip:hover {
  border-color: var(--status-error);
  color: var(--status-error);
}
.rejection-chip.active {
  background: rgba(160, 80, 80, 0.2);
  border-color: var(--status-error);
  color: var(--status-error);
  font-weight: 500;
}
</style>
