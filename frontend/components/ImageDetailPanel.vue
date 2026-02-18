<template>
  <Teleport to="body">
    <Transition name="panel">
      <div v-if="image" class="panel-overlay" @click.self="$emit('close')">
        <div class="panel-content">
          <!-- Header -->
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h3 style="font-size: 16px; font-weight: 500;">{{ image.character_name }} - {{ image.name }}</h3>
            <button class="btn" style="font-size: 14px; padding: 4px 10px;" @click="$emit('close')">Close</button>
          </div>

          <!-- Image preview -->
          <div style="text-align: center; margin-bottom: 16px; background: var(--bg-primary); border-radius: 4px; padding: 8px;">
            <img
              :src="imageUrl"
              :alt="image.name"
              style="max-width: 100%; max-height: 400px; border-radius: 3px;"
            />
          </div>

          <!-- Identify character -->
          <div style="margin-bottom: 12px; display: flex; align-items: flex-start; gap: 8px;">
            <button
              class="btn"
              style="font-size: 11px; padding: 4px 10px; white-space: nowrap;"
              :disabled="identifying"
              @click="identifyCharacterInImage"
            >
              {{ identifying ? 'Identifying...' : 'Who is this?' }}
            </button>
            <div v-if="identifying" class="spinner" style="width: 16px; height: 16px; flex-shrink: 0; margin-top: 2px;"></div>
            <div v-if="identifyResult" style="font-size: 11px; line-height: 1.4; color: var(--text-secondary); padding: 4px 8px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; flex: 1;">
              <div v-if="identifyResult.suggested_name" style="font-weight: 500; color: var(--accent-primary); margin-bottom: 2px;">
                {{ identifyResult.suggested_name }}
              </div>
              {{ identifyResult.description }}
              <button
                class="btn"
                style="font-size: 10px; padding: 2px 8px; margin-top: 4px; color: var(--accent-primary);"
                @click="useIdentifyAsPrompt"
              >
                Use as design prompt
              </button>
            </div>
          </div>

          <!-- Metadata section -->
          <div v-if="meta" style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 8px; color: var(--text-secondary);">Generation Metadata</h4>
            <div class="meta-grid">
              <div class="meta-row">
                <span class="meta-label">Seed</span>
                <span class="meta-value" style="display: flex; align-items: center; gap: 6px;">
                  <template v-if="meta.seed">
                    <code style="cursor: pointer; color: var(--accent-primary);" @click="copySeed" :title="'Click to copy'">{{ meta.seed }}</code>
                    <span v-if="seedCopied" style="font-size: 10px; color: var(--status-success);">copied</span>
                  </template>
                  <span v-else style="color: var(--text-muted);">unknown</span>
                </span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Model</span>
                <span class="meta-value">{{ meta.checkpoint_model || 'unknown' }}</span>
              </div>
              <div v-if="meta.cfg_scale" class="meta-row">
                <span class="meta-label">CFG</span>
                <span class="meta-value">{{ meta.cfg_scale }}</span>
              </div>
              <div v-if="meta.steps" class="meta-row">
                <span class="meta-label">Steps</span>
                <span class="meta-value">{{ meta.steps }}</span>
              </div>
              <div v-if="meta.sampler" class="meta-row">
                <span class="meta-label">Sampler</span>
                <span class="meta-value">{{ meta.sampler }} / {{ meta.scheduler || 'normal' }}</span>
              </div>
              <div v-if="meta.width" class="meta-row">
                <span class="meta-label">Size</span>
                <span class="meta-value">{{ meta.width }}x{{ meta.height }}</span>
              </div>
              <div v-if="meta.pose" class="meta-row">
                <span class="meta-label">Pose</span>
                <span class="meta-value">{{ meta.pose }}</span>
              </div>
              <div v-if="meta.source" class="meta-row">
                <span class="meta-label">Source</span>
                <span class="meta-value">{{ meta.source }}</span>
              </div>
              <div v-if="meta.quality_score != null" class="meta-row">
                <span class="meta-label">Quality</span>
                <span class="meta-value">
                  <span :style="{ color: qualityColor(meta.quality_score) }">{{ (meta.quality_score * 100).toFixed(0) }}%</span>
                </span>
              </div>
            </div>
          </div>

          <!-- Vision Assessment (gemma3:12b) -->
          <div v-if="meta?.vision_review" style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 8px; color: var(--text-secondary);">Vision Assessment</h4>
            <div class="meta-grid">
              <div class="meta-row">
                <span class="meta-label">Character</span>
                <span class="meta-value">
                  <span :style="{ color: qualityColor(meta.vision_review.character_match / 10) }">{{ meta.vision_review.character_match }}/10</span>
                </span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Solo</span>
                <span class="meta-value" :style="{ color: meta.vision_review.solo ? 'var(--status-success)' : 'var(--status-error)' }">
                  {{ meta.vision_review.solo ? 'Yes' : 'No — multi-character' }}
                </span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Clarity</span>
                <span class="meta-value">
                  <span :style="{ color: qualityColor(meta.vision_review.clarity / 10) }">{{ meta.vision_review.clarity }}/10</span>
                </span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Completeness</span>
                <span class="meta-value">{{ meta.vision_review.completeness }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Training Value</span>
                <span class="meta-value">
                  <span :style="{ color: qualityColor(meta.vision_review.training_value / 10) }">{{ meta.vision_review.training_value }}/10</span>
                </span>
              </div>
            </div>
            <div v-if="meta.vision_review.issues?.length" style="margin-top: 6px; display: flex; gap: 4px; flex-wrap: wrap;">
              <span
                v-for="issue in meta.vision_review.issues"
                :key="issue"
                style="font-size: 10px; padding: 2px 6px; border-radius: 2px; background: rgba(160,120,80,0.15); color: var(--status-warning); border: 1px solid var(--status-warning);"
              >
                {{ issue }}
              </span>
            </div>
            <div v-if="meta.vision_review.caption" style="margin-top: 8px; font-size: 11px; padding: 6px 8px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; line-height: 1.4; color: var(--text-secondary);">
              {{ meta.vision_review.caption }}
            </div>
          </div>

          <!-- Full prompt (expandable) -->
          <div style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary);">Full Prompt</h4>
            <div style="font-size: 11px; padding: 8px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; line-height: 1.5; max-height: 120px; overflow-y: auto; color: var(--text-secondary);">
              {{ meta?.full_prompt || image.prompt || 'No prompt data' }}
            </div>
          </div>

          <!-- Generate Variant (IP-Adapter + original params) -->
          <div style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary);">Generate Variant</h4>
            <textarea
              v-model="editablePrompt"
              style="width: 100%; min-height: 50px; font-size: 11px; padding: 6px 8px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary); line-height: 1.4;"
              placeholder="Prompt (pre-filled from original metadata)..."
            ></textarea>
            <div style="display: flex; gap: 6px; margin-top: 6px; align-items: center; flex-wrap: wrap;">
              <label style="font-size: 11px; color: var(--text-muted);">Seed:</label>
              <input
                v-model="editableSeed"
                type="number"
                style="width: 120px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
                placeholder="auto"
              />
              <label style="font-size: 11px; color: var(--text-muted);">Count:</label>
              <input
                v-model.number="regenCount"
                type="number"
                min="1"
                max="10"
                style="width: 50px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
              />
              <label style="font-size: 11px; color: var(--text-muted);">Weight:</label>
              <input
                v-model.number="ipaWeight"
                type="number"
                min="0.1"
                max="1.5"
                step="0.1"
                style="width: 50px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
              />
              <label style="font-size: 11px; color: var(--text-muted);">Denoise:</label>
              <input
                v-model.number="ipaDenoise"
                type="number"
                min="0.1"
                max="1.0"
                step="0.05"
                style="width: 50px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
              />
            </div>
            <div style="display: flex; gap: 6px; margin-top: 6px; align-items: center;">
              <button
                class="btn"
                style="font-size: 11px; padding: 4px 12px; color: var(--accent-primary);"
                @click="generateVariant"
                :disabled="generatingVariant"
              >
                {{ generatingVariant ? 'Queued...' : 'Generate Variant' }}
              </button>
              <span v-if="variantResult" style="font-size: 11px; color: var(--status-success);">{{ variantResult }}</span>
            </div>
          </div>

          <!-- Action buttons -->
          <div style="display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border-primary);">
            <button class="btn btn-success" style="flex: 1;" @click="$emit('approve', image, true)" :disabled="actionDisabled">
              Approve
            </button>
            <button class="btn btn-danger" style="flex: 1;" @click="$emit('approve', image, false)" :disabled="actionDisabled">
              Reject
            </button>
            <button class="btn" style="flex: 0; padding: 6px 12px; white-space: nowrap;" @click="$emit('reassign', image)" :disabled="actionDisabled" title="Move to different character">
              &#8644; Reassign
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/api/client'
import type { PendingImage, ImageMetadata, IdentifyResult } from '@/types'

const props = defineProps<{
  image: PendingImage | null
  actionDisabled?: boolean
}>()

defineEmits<{
  close: []
  approve: [image: PendingImage, approved: boolean]
  reassign: [image: PendingImage]
}>()

const meta = ref<ImageMetadata | null>(null)
const loading = ref(false)
const seedCopied = ref(false)
const editablePrompt = ref('')
const editableSeed = ref<string>('')
const regenCount = ref(3)
const ipaWeight = ref(0.7)
const ipaDenoise = ref(0.65)
const generatingVariant = ref(false)
const variantResult = ref('')
const identifying = ref(false)
const identifyResult = ref<IdentifyResult | null>(null)

const imageUrl = computed(() => {
  if (!props.image) return ''
  return api.imageUrl(props.image.character_slug, props.image.name)
})

watch(() => props.image, async (img) => {
  if (!img) {
    meta.value = null
    identifyResult.value = null
    return
  }
  identifyResult.value = null
  // Use inline metadata if available, otherwise fetch
  if (img.metadata) {
    meta.value = img.metadata
  } else {
    loading.value = true
    try {
      meta.value = await api.getImageMetadata(img.character_slug, img.name)
    } catch {
      meta.value = null
    } finally {
      loading.value = false
    }
  }
  // Pre-fill editable fields — prefer full_prompt (what actually generated the image)
  editablePrompt.value = meta.value?.full_prompt || meta.value?.design_prompt || img.design_prompt || ''
  editableSeed.value = meta.value?.seed ? String(meta.value.seed) : ''
  variantResult.value = ''
}, { immediate: true })

async function identifyCharacterInImage() {
  if (!props.image || identifying.value) return
  identifying.value = true
  try {
    identifyResult.value = await api.identifyCharacter(
      props.image.character_slug, props.image.name)
  } catch (e) {
    console.error('Failed to identify character:', e)
    identifyResult.value = { description: 'Vision model unavailable', suggested_name: '' }
  } finally {
    identifying.value = false
  }
}

function useIdentifyAsPrompt() {
  if (!identifyResult.value?.description) return
  editablePrompt.value = identifyResult.value.description
}

function copySeed() {
  if (meta.value?.seed) {
    navigator.clipboard.writeText(String(meta.value.seed))
    seedCopied.value = true
    setTimeout(() => { seedCopied.value = false }, 1500)
  }
}

function qualityColor(score: number): string {
  if (score >= 0.7) return 'var(--status-success)'
  if (score >= 0.4) return 'var(--status-warning)'
  return 'var(--status-error)'
}

async function generateVariant() {
  if (!props.image) return
  generatingVariant.value = true
  variantResult.value = ''
  try {
    const result = await api.generateVariant(
      props.image.character_slug,
      props.image.name,
      {
        count: regenCount.value,
        weight: ipaWeight.value,
        denoise: ipaDenoise.value,
        prompt_override: editablePrompt.value.trim() || undefined,
        seed_offset: editableSeed.value ? parseInt(editableSeed.value) : 1,
      },
    )
    const queued = result.variants?.filter(v => v.prompt_id).length ?? 0
    variantResult.value = `Queued ${queued} variant${queued !== 1 ? 's' : ''}`
  } catch (error) {
    console.error('Failed to generate variant:', error)
    variantResult.value = 'Failed'
  } finally {
    setTimeout(() => { generatingVariant.value = false }, 2000)
  }
}
</script>

<style scoped>
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
