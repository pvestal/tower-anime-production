<template>
  <div class="card">
    <h4 class="section-heading">Generation Style (SSOT)</h4>
    <p style="font-size: 11px; color: var(--status-warning); margin-bottom: 10px;">Changes affect ALL characters in this project.</p>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
      <div style="grid-column: 1 / -1;">
        <label class="field-label">Checkpoint Model</label>
        <select v-model="editStyle.checkpoint_model" class="field-input" style="width: 100%;">
          <option value="">Select checkpoint...</option>
          <option v-for="c in checkpoints" :key="c.filename" :value="c.filename">
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
        <label class="field-label" style="margin-bottom: 0;">Style Preamble</label>
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
        <label class="field-label" style="margin-bottom: 0;">Negative Template</label>
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
      :class="['btn', saved ? 'btn-saved' : 'btn-primary']"
      style="font-size: 12px; padding: 4px 12px; transition: all 200ms ease;"
      @click="handleSave"
      :disabled="saving || !dirty"
    >
      {{ saved ? 'Saved' : saving ? 'Saving...' : 'Save Generation Style' }}
    </button>
    <span v-if="!dirty && !saved" style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">no changes</span>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, ref, watch } from 'vue'
import type { StyleUpdate, CheckpointFile, GenerationStyle } from '@/types'
import EchoAssistButton from '../EchoAssistButton.vue'

const props = defineProps<{
  styleProp: GenerationStyle | null
  checkpoints: CheckpointFile[]
  saving: boolean
  echoContext: Record<string, string | undefined>
}>()

const emit = defineEmits<{
  save: [data: StyleUpdate]
}>()

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

const savedSnapshot = ref({
  checkpoint_model: '', cfg_scale: 7, steps: 25, sampler: '',
  width: 768, height: 768, positive_prompt_template: '', negative_prompt_template: '',
})

const saved = ref(false)

function snapshot() {
  savedSnapshot.value = {
    checkpoint_model: editStyle.checkpoint_model || '',
    cfg_scale: editStyle.cfg_scale || 7,
    steps: editStyle.steps || 25,
    sampler: editStyle.sampler || '',
    width: editStyle.width || 768,
    height: editStyle.height || 768,
    positive_prompt_template: editStyle.positive_prompt_template || '',
    negative_prompt_template: editStyle.negative_prompt_template || '',
  }
}

const dirty = computed(() => {
  const s = savedSnapshot.value
  return editStyle.checkpoint_model !== s.checkpoint_model
    || editStyle.cfg_scale !== s.cfg_scale
    || editStyle.steps !== s.steps
    || editStyle.sampler !== s.sampler
    || editStyle.width !== s.width
    || editStyle.height !== s.height
    || editStyle.positive_prompt_template !== s.positive_prompt_template
    || editStyle.negative_prompt_template !== s.negative_prompt_template
})

watch(() => props.styleProp, (s) => {
  if (!s) return
  editStyle.checkpoint_model = s.checkpoint_model || ''
  editStyle.cfg_scale = s.cfg_scale || 7
  editStyle.steps = s.steps || 25
  editStyle.sampler = s.sampler || 'DPM++ 2M Karras'
  editStyle.width = s.width || 768
  editStyle.height = s.height || 768
  editStyle.positive_prompt_template = s.positive_prompt_template || ''
  editStyle.negative_prompt_template = s.negative_prompt_template || ''
  snapshot()
}, { immediate: true })

function checkpointExists(filename: string): boolean {
  return props.checkpoints.some(c => c.filename === filename)
}

function handleSave() {
  emit('save', { ...editStyle })
  snapshot()
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}
</script>

<style scoped>
.section-heading {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
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
