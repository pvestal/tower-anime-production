<template>
  <div>
    <!-- Action Presets -->
    <div class="field-group">
      <label class="field-label">Action Presets</label>
      <div v-if="loading" class="loading-text">Loading catalog...</div>
      <div v-else-if="Object.keys(presets).length" class="preset-grid">
        <button
          v-for="(preset, key) in presets"
          :key="key"
          class="preset-btn"
          :class="{ active: isPresetActive(key as string) }"
          :title="`${preset.label} (${preset.tier})`"
          @click="applyPreset(key as string, preset)"
        >{{ preset.label }}</button>
      </div>
      <div v-else class="empty-text">No presets for this rating</div>
    </div>

    <!-- Video LoRA -->
    <div class="field-group">
      <label class="field-label">Video LoRA (Motion)</label>
      <select
        :value="shot.lora_name || ''"
        @change="updateField('lora_name', ($event.target as HTMLSelectElement).value || null)"
        class="field-input"
      >
        <option value="">None</option>
        <option
          v-for="(pair, key) in loraPairs"
          :key="key"
          :value="pair.high"
        >{{ pair.label || key }} ({{ pair.tier }})</option>
      </select>
      <div v-if="shot.lora_name" class="strength-row">
        <label class="field-label-sm">Strength</label>
        <input
          :value="shot.lora_strength ?? 0.85"
          @input="updateField('lora_strength', Number(($event.target as HTMLInputElement).value))"
          type="range" min="0.1" max="1.5" step="0.05"
          class="strength-slider"
        />
        <span class="strength-value">{{ (shot.lora_strength ?? 0.85).toFixed(2) }}</span>
      </div>
    </div>

    <!-- Image LoRA -->
    <div class="field-group">
      <label class="field-label">Image LoRA (Keyframe)</label>
      <input
        :value="shot.image_lora || ''"
        @input="updateField('image_lora', ($event.target as HTMLInputElement).value || null)"
        type="text"
        placeholder="e.g. ass_ride_illustrious.safetensors"
        class="field-input"
      />
      <div v-if="shot.image_lora" class="strength-row">
        <label class="field-label-sm">Strength</label>
        <input
          :value="shot.image_lora_strength ?? 0.7"
          @input="updateField('image_lora_strength', Number(($event.target as HTMLInputElement).value))"
          type="range" min="0.1" max="1.5" step="0.05"
          class="strength-slider"
        />
        <span class="strength-value">{{ (shot.image_lora_strength ?? 0.7).toFixed(2) }}</span>
      </div>
    </div>

    <!-- Characters Present -->
    <div class="field-group">
      <label class="field-label">Characters Present</label>
      <div v-if="characters.length" class="char-grid">
        <label
          v-for="char in characters"
          :key="char.slug"
          class="char-checkbox"
        >
          <input
            type="checkbox"
            :checked="(shot.characters_present || []).includes(char.slug)"
            @change="toggleCharacter(char.slug)"
          />
          <span>{{ char.name }}</span>
        </label>
      </div>
      <div v-else class="empty-text">No characters in project</div>
    </div>

    <!-- Video Engine (quick switch) -->
    <div class="field-group">
      <label class="field-label">Video Engine</label>
      <select
        :value="shot.video_engine || 'framepack'"
        @change="updateField('video_engine', ($event.target as HTMLSelectElement).value)"
        class="field-input"
      >
        <option value="framepack">FramePack I2V</option>
        <option value="framepack_f1">FramePack F1</option>
        <option value="wan22_14b">WAN 2.2 14B (best)</option>
        <option value="wan22">WAN 2.2 5B</option>
        <option value="wan">WAN 2.1 T2V</option>
        <option value="ltx">LTX-Video</option>
      </select>
    </div>

    <!-- Guidance Scale -->
    <div class="field-group">
      <label class="field-label">Guidance Scale</label>
      <div class="strength-row">
        <input
          :value="shot.guidance_scale ?? 6.0"
          @input="updateField('guidance_scale', Number(($event.target as HTMLInputElement).value))"
          type="range" min="1" max="15" step="0.5"
          class="strength-slider"
        />
        <span class="strength-value">{{ (shot.guidance_scale ?? 6.0).toFixed(1) }}</span>
      </div>
    </div>

    <!-- Current Config Summary -->
    <div v-if="shot.lora_name || shot.image_lora" class="config-summary">
      <div class="field-label" style="margin-bottom: 6px;">Active Config</div>
      <div v-if="shot.lora_name" class="config-item">
        <span class="config-key">Video:</span>
        <span class="config-val">{{ shortName(shot.lora_name) }} @ {{ shot.lora_strength ?? 0.85 }}</span>
      </div>
      <div v-if="shot.image_lora" class="config-item">
        <span class="config-key">Image:</span>
        <span class="config-val">{{ shortName(shot.image_lora) }} @ {{ shot.image_lora_strength ?? 0.7 }}</span>
      </div>
      <div class="config-item">
        <span class="config-key">Engine:</span>
        <span class="config-val">{{ shot.video_engine || 'framepack' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { BuilderShot } from '@/types'

interface LoraPreset {
  label: string
  tier: string
  image_lora: string | null
  image_lora_strength: number
  video_lora: string
  video_lora_strength: number
  video_engine: string
}

interface LoraPair {
  label: string
  tier: string
  high: string
  low: string
  tags?: string[]
}

const props = defineProps<{
  shot: Partial<BuilderShot>
  characters: { slug: string; name: string }[]
  contentRating?: string
}>()

const emit = defineEmits<{
  'update-field': [field: string, value: unknown]
}>()

const loading = ref(false)
const presets = ref<Record<string, LoraPreset>>({})
const loraPairs = ref<Record<string, LoraPair>>({})

async function loadCatalog() {
  loading.value = true
  try {
    const rating = props.contentRating || 'XXX'
    const resp = await fetch(`/anime-studio/api/scenes/lora-catalog?content_rating=${rating}`)
    if (resp.ok) {
      const data = await resp.json()
      presets.value = data.action_presets || {}
      loraPairs.value = data.video_lora_pairs || {}
    }
  } catch (e) {
    console.error('Failed to load LoRA catalog:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadCatalog)
watch(() => props.contentRating, loadCatalog)

function updateField(field: string, value: unknown) {
  emit('update-field', field, value)
}

function isPresetActive(key: string): boolean {
  const preset = presets.value[key]
  if (!preset) return false
  // Check if video_lora key matches current lora_name (by looking up the pair)
  const pair = loraPairs.value[preset.video_lora]
  return !!(pair && props.shot.lora_name === pair.high)
}

function applyPreset(key: string, preset: LoraPreset) {
  // If already active, clear it
  if (isPresetActive(key)) {
    updateField('lora_name', null)
    updateField('lora_strength', 0.85)
    updateField('image_lora', null)
    updateField('image_lora_strength', 0.7)
    return
  }

  // Look up the video LoRA pair
  const pair = loraPairs.value[preset.video_lora]
  if (pair) {
    updateField('lora_name', pair.high)
    updateField('lora_strength', preset.video_lora_strength)
  }
  if (preset.image_lora) {
    updateField('image_lora', preset.image_lora)
    updateField('image_lora_strength', preset.image_lora_strength)
  } else {
    updateField('image_lora', null)
    updateField('image_lora_strength', 0.7)
  }
  updateField('video_engine', preset.video_engine || 'wan22_14b')
}

function toggleCharacter(slug: string) {
  const current = [...(props.shot.characters_present || [])]
  const idx = current.indexOf(slug)
  if (idx >= 0) {
    current.splice(idx, 1)
  } else {
    current.push(slug)
  }
  updateField('characters_present', current)
}

function shortName(path: string | null): string {
  if (!path) return ''
  return path.split('/').pop()?.replace('.safetensors', '') || path
}
</script>

<style scoped>
.field-group { margin-bottom: 12px; }
.field-label { font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px; }
.field-label-sm { font-size: 11px; color: var(--text-muted); min-width: 55px; }
.field-input { width: 100%; padding: 6px 8px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; font-family: var(--font-primary); }
.field-input:focus { border-color: var(--border-focus); outline: none; }

.preset-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}

.preset-btn {
  padding: 6px 4px;
  font-size: 11px;
  font-family: var(--font-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  cursor: pointer;
  transition: all 150ms;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preset-btn:hover {
  border-color: var(--accent-primary);
  color: var(--text-primary);
}

.preset-btn.active {
  background: rgba(122, 162, 247, 0.15);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}

.strength-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.strength-slider {
  flex: 1;
  accent-color: var(--accent-primary);
  height: 4px;
}

.strength-value {
  font-size: 11px;
  color: var(--accent-primary);
  font-family: var(--font-mono, monospace);
  min-width: 32px;
  text-align: right;
}

.char-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.char-checkbox {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-primary);
  padding: 3px 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  cursor: pointer;
}

.char-checkbox input { accent-color: var(--accent-primary); }

.config-summary {
  margin-top: 8px;
  padding: 8px;
  background: rgba(122, 162, 247, 0.06);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
}

.config-item {
  display: flex;
  gap: 6px;
  font-size: 11px;
  margin-bottom: 2px;
}

.config-key {
  color: var(--text-muted);
  min-width: 45px;
}

.config-val {
  color: var(--text-primary);
  word-break: break-all;
}

.loading-text, .empty-text {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
  padding: 8px 0;
}
</style>
