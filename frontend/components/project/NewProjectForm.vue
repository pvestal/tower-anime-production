<template>
  <div class="card" style="margin-bottom: 20px; background: var(--bg-tertiary);">
    <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">Create New Project</h4>

    <!-- Concept seeder -->
    <div style="margin-bottom: 14px; padding: 10px; border: 1px dashed var(--accent-primary); border-radius: 4px;">
      <label class="field-label" style="color: var(--accent-primary);">Seed from Concept (optional)</label>
      <textarea
        v-model="conceptText"
        rows="2"
        placeholder="Describe your project idea, e.g. 'A cyberpunk detective story in Tokyo 2089 with neon streets and androids'"
        class="field-input"
        style="width: 100%; resize: vertical; margin-bottom: 8px;"
      ></textarea>
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
        <input v-model="form.name" type="text" placeholder="My New Project" class="field-input" />
      </div>
      <div>
        <label class="field-label">Checkpoint *</label>
        <select v-model="form.checkpoint_model" class="field-input" style="width: 100%;">
          <option value="">Select checkpoint...</option>
          <option v-for="c in checkpoints" :key="c.filename" :value="c.filename">
            {{ c.filename }} ({{ c.size_mb }} MB)
          </option>
        </select>
      </div>
      <div>
        <label class="field-label">Genre</label>
        <input v-model="form.genre" type="text" placeholder="anime, sci-fi, etc." class="field-input" />
      </div>
      <div>
        <label class="field-label">Sampler</label>
        <select v-model="form.sampler" class="field-input" style="width: 100%;">
          <option v-for="s in samplerOptions" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>
      <div>
        <label class="field-label">Steps</label>
        <input v-model.number="form.steps" type="number" min="1" max="100" class="field-input" />
      </div>
      <div>
        <label class="field-label">CFG Scale</label>
        <input v-model.number="form.cfg_scale" type="number" min="1" max="30" step="0.5" class="field-input" />
      </div>
      <div>
        <label class="field-label">Width</label>
        <input v-model.number="form.width" type="number" min="256" max="2048" step="64" class="field-input" />
      </div>
      <div>
        <label class="field-label">Height</label>
        <input v-model.number="form.height" type="number" min="256" max="2048" step="64" class="field-input" />
      </div>
    </div>
    <div style="margin-bottom: 10px;">
      <label class="field-label">Description</label>
      <textarea v-model="form.description" rows="2" placeholder="Project description..." class="field-input" style="width: 100%; resize: vertical;"></textarea>
    </div>
    <div style="display: flex; gap: 8px;">
      <button
        class="btn btn-primary"
        @click="$emit('create', { ...form })"
        :disabled="!form.name || !form.checkpoint_model || saving"
      >
        {{ saving ? 'Creating...' : 'Create Project' }}
      </button>
      <button class="btn" @click="$emit('cancel')">Cancel</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import type { ProjectCreate, CheckpointFile } from '@/types'
import EchoAssistButton from '../EchoAssistButton.vue'

const props = defineProps<{
  checkpoints: CheckpointFile[]
  saving: boolean
}>()

defineEmits<{
  create: [data: ProjectCreate]
  cancel: []
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

const conceptText = ref('')

const form = reactive<ProjectCreate>({
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

function handleConceptAccept({ suggestion }: { suggestion: string }) {
  let text = suggestion.trim()
  if (text.startsWith('```')) {
    text = text.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '')
  }
  try {
    const data = JSON.parse(text)
    if (data.name) form.name = data.name
    if (data.genre) form.genre = data.genre
    if (data.description) form.description = data.description
    if (data.recommended_steps) form.steps = Number(data.recommended_steps) || 25
    if (data.recommended_cfg) form.cfg_scale = Number(data.recommended_cfg) || 7
  } catch {
    form.description = suggestion
  }
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.genre = ''
  form.checkpoint_model = ''
  form.cfg_scale = 7
  form.steps = 25
  form.sampler = 'DPM++ 2M Karras'
  form.width = 768
  form.height = 768
}

defineExpose({ resetForm })
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
</style>
