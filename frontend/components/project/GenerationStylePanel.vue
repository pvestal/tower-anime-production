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
            {{ c.style_label || c.filename }} — {{ c.architecture || '?' }} / {{ c.prompt_format || '?' }} ({{ c.size_mb }} MB)
          </option>
        </select>
        <div v-if="selectedProfile" class="checkpoint-info">
          <span class="chip">{{ selectedProfile.architecture }}</span>
          <span class="chip">{{ selectedProfile.prompt_format }}</span>
          <span v-if="selectedProfile.default_cfg" class="chip-muted">CFG {{ selectedProfile.default_cfg }}</span>
          <span v-if="selectedProfile.default_steps" class="chip-muted">{{ selectedProfile.default_steps }} steps</span>
          <span v-if="selectedProfile.default_sampler" class="chip-muted">{{ selectedProfile.default_sampler }}</span>
        </div>
        <span
          v-if="editStyle.checkpoint_model && !checkpointExists(editStyle.checkpoint_model)"
          style="font-size: 11px; color: var(--status-error);"
        >
          Model file not found on disk
        </span>
        <div v-if="preambleMismatch" class="preamble-warning">
          <span>Style preamble may not match this model's expected format.</span>
          <button class="btn-apply-defaults" @click="applyProfileDefaults">Apply model defaults</button>
        </div>
      </div>
      <div>
        <label class="field-label">CFG Scale <span class="field-hint">Higher = stricter prompt adherence</span></label>
        <input v-model.number="editStyle.cfg_scale" type="range" min="1" max="20" step="0.5" class="field-range" />
        <span class="range-value">{{ editStyle.cfg_scale }}</span>
      </div>
      <div>
        <label class="field-label">Steps <span class="field-hint">More = finer detail, slower</span></label>
        <input v-model.number="editStyle.steps" type="range" min="10" max="60" step="5" class="field-range" />
        <span class="range-value">{{ editStyle.steps }}</span>
      </div>
      <div>
        <label class="field-label">Sampler</label>
        <select v-model="editStyle.sampler" class="field-input" style="width: 100%;">
          <option v-for="s in samplerOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </div>
      <div>
        <label class="field-label">Scheduler</label>
        <select v-model="editStyle.scheduler" class="field-input" style="width: 100%;">
          <option value="normal">Normal — standard noise schedule</option>
          <option value="karras">Karras — sharper details</option>
          <option value="exponential">Exponential — smooth falloff</option>
          <option value="simple">Simple — linear</option>
          <option value="sgm_uniform">SGM Uniform — even spacing</option>
        </select>
      </div>
      <div>
        <label class="field-label">Resolution</label>
        <div style="display: flex; gap: 6px; align-items: center;">
          <input v-model.number="editStyle.width" type="number" min="256" max="2048" step="64" class="field-input" style="width: 80px;" />
          <span style="color: var(--text-muted); font-size: 12px;">×</span>
          <input v-model.number="editStyle.height" type="number" min="256" max="2048" step="64" class="field-input" style="width: 80px;" />
          <span class="field-hint" style="font-size: 10px;">{{ (editStyle.width || 512) * (editStyle.height || 768) > 589824 ? 'SDXL' : 'SD1.5' }} range</span>
        </div>
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
    <div style="margin-bottom: 10px;">
      <label class="field-label">Switch Reason (optional)</label>
      <input v-model="reason" type="text" class="field-input" placeholder="e.g. Testing pony model for NSFW project" />
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

    <!-- Style History -->
    <div v-if="projectId" style="margin-top: 16px; border-top: 1px solid var(--border-primary); padding-top: 12px;">
      <button class="history-toggle" @click="toggleHistory">
        <span style="font-size: 12px; font-weight: 500; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px;">
          Style History
        </span>
        <span v-if="styleHistory.length > 0" style="font-size: 11px; color: var(--text-muted); margin-left: 4px;">({{ styleHistory.length }})</span>
        <span class="history-arrow" :class="{ open: historyOpen }">&#9654;</span>
      </button>
      <div v-if="historyOpen && styleHistory.length > 0" style="margin-top: 8px;">
        <div
          v-for="entry in styleHistory"
          :key="entry.id"
          class="history-entry"
        >
          <div class="history-header">
            <span class="history-checkpoint">{{ entry.checkpoint_model || 'Unknown' }}</span>
            <span class="history-date">{{ formatDate(entry.switched_at) }}</span>
          </div>
          <div class="history-stats">
            <span>{{ entry.generation_count }} gens</span>
            <span v-if="entry.avg_quality_at_switch != null">{{ (entry.avg_quality_at_switch * 100).toFixed(0) }}% quality at switch</span>
            <span v-if="entry.live_total > 0">{{ entry.live_approved }}/{{ entry.live_total }} approved</span>
            <span v-if="entry.live_avg_quality != null">{{ (entry.live_avg_quality * 100).toFixed(0) }}% lifetime avg</span>
          </div>
          <div v-if="entry.reason" class="history-reason">{{ entry.reason }}</div>
          <button
            class="btn history-use-btn"
            @click="prefillFromHistory(entry)"
          >
            Use This Checkpoint
          </button>
        </div>
      </div>
      <div v-if="historyOpen && styleHistory.length === 0" style="font-size: 12px; color: var(--text-muted); margin-top: 6px;">
        No previous style changes recorded.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, ref, watch } from 'vue'
import type { StyleUpdate, CheckpointFile, GenerationStyle, StyleHistoryEntry } from '@/types'
import { storyApi } from '@/api/story'
import EchoAssistButton from '../EchoAssistButton.vue'

const props = defineProps<{
  styleProp: GenerationStyle | null
  checkpoints: CheckpointFile[]
  saving: boolean
  echoContext: Record<string, string | undefined>
  projectId?: number
}>()

const emit = defineEmits<{
  save: [data: StyleUpdate]
}>()

// ComfyUI-native sampler names with friendly display labels
const samplerOptions = [
  { value: 'euler', label: 'Euler — fast, clean lines' },
  { value: 'euler_ancestral', label: 'Euler Ancestral — creative, varied' },
  { value: 'dpmpp_2m', label: 'DPM++ 2M — balanced quality/speed' },
  { value: 'dpmpp_2m_sde', label: 'DPM++ 2M SDE — detailed, slower' },
  { value: 'dpmpp_2s_ancestral', label: 'DPM++ 2S Ancestral — artistic' },
  { value: 'dpmpp_sde', label: 'DPM++ SDE — smooth gradients' },
  { value: 'ddim', label: 'DDIM — deterministic, fast' },
  { value: 'uni_pc', label: 'UniPC — fast, 10-15 steps' },
  { value: 'lcm', label: 'LCM — ultra-fast, 4-8 steps' },
]

const editStyle = reactive<StyleUpdate>({
  checkpoint_model: '',
  cfg_scale: 7,
  steps: 25,
  sampler: 'dpmpp_2m',
  scheduler: 'karras',
  width: 768,
  height: 768,
  positive_prompt_template: '',
  negative_prompt_template: '',
})

const savedSnapshot = ref({
  checkpoint_model: '', cfg_scale: 7, steps: 25, sampler: '', scheduler: 'karras',
  width: 768, height: 768, positive_prompt_template: '', negative_prompt_template: '',
})

const saved = ref(false)

function snapshot() {
  savedSnapshot.value = {
    checkpoint_model: editStyle.checkpoint_model || '',
    cfg_scale: editStyle.cfg_scale || 7,
    steps: editStyle.steps || 25,
    sampler: editStyle.sampler || '',
    scheduler: editStyle.scheduler || 'karras',
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
    || editStyle.scheduler !== s.scheduler
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
  editStyle.sampler = s.sampler || 'dpmpp_2m'
  editStyle.scheduler = (s as any).scheduler || 'karras'
  editStyle.width = s.width || 768
  editStyle.height = s.height || 768
  editStyle.positive_prompt_template = s.positive_prompt_template || ''
  editStyle.negative_prompt_template = s.negative_prompt_template || ''
  snapshot()
}, { immediate: true })

function checkpointExists(filename: string): boolean {
  return props.checkpoints.some(c => c.filename === filename)
}

const selectedProfile = computed(() => {
  if (!editStyle.checkpoint_model) return null
  return props.checkpoints.find(c => c.filename === editStyle.checkpoint_model) || null
})

const reason = ref('')
const preambleMismatch = ref(false)

// When checkpoint changes, check if preamble matches the new model's expected format
watch(() => editStyle.checkpoint_model, (newModel, oldModel) => {
  if (!newModel || !oldModel) return  // skip initial load
  const profile = props.checkpoints.find(c => c.filename === newModel)
  if (!profile?.quality_prefix) return
  // Flag mismatch if current preamble doesn't start with the new model's prefix
  const currentPreamble = (editStyle.positive_prompt_template || '').trim()
  const expectedPrefix = (profile.quality_prefix || '').trim()
  preambleMismatch.value = currentPreamble !== '' && !currentPreamble.startsWith(expectedPrefix.slice(0, 20))
})

function applyProfileDefaults() {
  const profile = props.checkpoints.find(c => c.filename === editStyle.checkpoint_model)
  if (!profile) return
  if (profile.quality_prefix) editStyle.positive_prompt_template = profile.quality_prefix
  if (profile.quality_negative) editStyle.negative_prompt_template = profile.quality_negative
  if (profile.default_cfg) editStyle.cfg_scale = profile.default_cfg
  if (profile.default_steps) editStyle.steps = profile.default_steps
  if (profile.default_sampler) editStyle.sampler = profile.default_sampler
  preambleMismatch.value = false
}

function handleSave() {
  const data: StyleUpdate = { ...editStyle }
  if (reason.value.trim()) {
    data.reason = reason.value.trim()
  }
  emit('save', data)
  snapshot()
  saved.value = true
  reason.value = ''
  setTimeout(() => { saved.value = false }, 2000)
  // Refresh history after save
  if (props.projectId) {
    setTimeout(() => loadHistory(), 500)
  }
}

// --- Style History ---
const historyOpen = ref(false)
const styleHistory = ref<StyleHistoryEntry[]>([])

async function loadHistory() {
  if (!props.projectId) return
  try {
    const resp = await storyApi.getStyleHistory(props.projectId)
    styleHistory.value = resp.history
  } catch {
    styleHistory.value = []
  }
}

function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value && styleHistory.value.length === 0) {
    loadHistory()
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function prefillFromHistory(entry: StyleHistoryEntry) {
  if (entry.checkpoint_model) editStyle.checkpoint_model = entry.checkpoint_model
  if (entry.cfg_scale != null) editStyle.cfg_scale = entry.cfg_scale
  if (entry.steps != null) editStyle.steps = entry.steps
  if (entry.sampler) editStyle.sampler = entry.sampler
  if (entry.width != null) editStyle.width = entry.width
  if (entry.height != null) editStyle.height = entry.height
}

watch(() => props.projectId, (id) => {
  if (id && historyOpen.value) loadHistory()
})
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
.field-hint {
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 400;
}
.field-range {
  width: calc(100% - 40px);
  vertical-align: middle;
  accent-color: var(--accent-primary);
}
.range-value {
  display: inline-block;
  width: 35px;
  text-align: right;
  font-size: 12px;
  color: var(--accent-primary);
  font-weight: 500;
}
.btn-saved {
  background: var(--status-success) !important;
  color: var(--bg-primary) !important;
  border-color: var(--status-success) !important;
}
.history-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  color: var(--text-primary);
  font-family: var(--font-primary);
}
.history-toggle:hover { opacity: 0.8; }
.history-arrow {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: auto;
  transition: transform 150ms ease;
}
.history-arrow.open { transform: rotate(90deg); }
.history-entry {
  padding: 8px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  margin-bottom: 6px;
}
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.history-checkpoint {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-all;
}
.history-date {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  margin-left: 8px;
}
.history-stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-muted);
}
.history-reason {
  font-size: 11px;
  color: var(--text-secondary);
  font-style: italic;
  margin-top: 4px;
}
.history-use-btn {
  font-size: 11px;
  padding: 2px 8px;
  margin-top: 6px;
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.history-use-btn:hover {
  background: var(--accent-primary);
  color: #fff;
}
.checkpoint-info {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--accent-primary);
  color: #fff;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.preamble-warning {
  margin-top: 6px;
  padding: 6px 10px;
  background: rgba(255, 170, 0, 0.1);
  border: 1px solid var(--status-warning);
  border-radius: 4px;
  font-size: 11px;
  color: var(--status-warning);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.btn-apply-defaults {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--status-warning);
  color: #000;
  border: none;
  border-radius: 3px;
  cursor: pointer;
  font-family: var(--font-primary);
  white-space: nowrap;
}
.btn-apply-defaults:hover {
  opacity: 0.85;
}
.chip-muted {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-primary);
  color: var(--text-muted);
  border: 1px solid var(--border-primary);
}
</style>
