<template>
  <div>
    <!-- Video Engine -->
    <div v-if="authStore.isAdvanced" class="field-group">
      <label class="field-label">Video Engine</label>
      <select
        :value="shot.video_engine || 'framepack'"
        @change="updateField('video_engine', ($event.target as HTMLSelectElement).value)"
        class="field-input"
      >
        <option value="framepack">FramePack (I2V, solo + LoRA, highest quality)</option>
        <option value="framepack_f1">FramePack F1 (I2V, faster)</option>
        <option value="wan">Wan 2.1 T2V (text-only, multi-char, environments)</option>
        <option value="wan22">Wan 2.2 5B (T2V/I2V, fast, good quality)</option>
        <option value="wan22_14b">Wan 2.2 14B (I2V, best quality, needs source image)</option>
        <option value="ltx">LTX-Video (I2V/T2V, LoRA support)</option>
      </select>
      <div v-if="engineHint" style="font-size: 10px; color: var(--text-muted); margin-top: 3px;">
        {{ engineHint }}
      </div>
    </div>

    <!-- Seed + Steps -->
    <div v-if="authStore.isAdvanced" class="field-row">
      <div class="field-group">
        <label class="field-label">Seed</label>
        <input
          :value="shot.seed"
          @input="updateField('seed', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null)"
          type="number" placeholder="Random"
          class="field-input"
        />
      </div>
      <div class="field-group">
        <label class="field-label">Steps</label>
        <select
          :value="shot.steps"
          @change="updateField('steps', ($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : null)"
          class="field-input"
        >
          <option :value="null">Default ({{ stepsDefault }})</option>
          <option :value="4">4 (lightx2v)</option>
          <option :value="15">15</option>
          <option :value="20">20</option>
          <option :value="25">25</option>
          <option :value="30">30</option>
        </select>
      </div>
    </div>

    <!-- Transition -->
    <div class="field-row">
      <div class="field-group">
        <label class="field-label">Transition</label>
        <select
          :value="shot.transition_type || 'dissolve'"
          @change="updateField('transition_type', ($event.target as HTMLSelectElement).value)"
          class="field-input"
        >
          <option value="dissolve">Dissolve</option>
          <option value="fade">Fade</option>
          <option value="fadeblack">Fade Black</option>
          <option value="wipeleft">Wipe Left</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label">Transition (s)</label>
        <input
          :value="shot.transition_duration ?? 0.3"
          @input="updateField('transition_duration', Number(($event.target as HTMLInputElement).value))"
          type="number" min="0.1" max="2" step="0.1"
          class="field-input"
        />
      </div>
    </div>

    <!-- Negative Prompt -->
    <div v-if="authStore.isAdvanced" class="field-group">
      <label class="field-label">Negative Prompt</label>
      <textarea
        :value="shot.generation_negative"
        @input="updateField('generation_negative', ($event.target as HTMLTextAreaElement).value)"
        rows="2"
        placeholder="worst quality, low quality, blurry, deformed"
        class="field-input field-textarea"
        style="font-size: 11px;"
      ></textarea>
    </div>

    <!-- Character State (NSM) -->
    <div v-if="characterStates.length > 0 && authStore.isAdvanced" class="state-section">
      <div class="state-header" @click="stateExpanded = !stateExpanded">
        <span class="field-label" style="margin-bottom: 0; font-weight: 500; cursor: pointer;">
          Character State {{ stateExpanded ? '\u25BE' : '\u25B8' }}
        </span>
        <span
          v-for="cs in characterStates"
          :key="cs.character_slug"
          class="source-badge"
          :class="cs.state_source === 'manual' ? 'source-badge--manual' : 'source-badge--auto'"
          style="font-size: 9px;"
        >{{ cs.state_source }}</span>
      </div>
      <div v-if="stateExpanded">
        <div v-for="cs in characterStates" :key="cs.character_slug" class="state-card">
          <div style="font-size: 11px; font-weight: 500; color: var(--accent-primary); margin-bottom: 4px;">{{ cs.character_slug }}</div>
          <div class="state-grid">
            <div v-if="cs.clothing" class="state-item">
              <span class="state-label">Clothing</span>
              <span class="state-value">{{ cs.clothing }}</span>
            </div>
            <div v-if="cs.emotional_state && cs.emotional_state !== 'calm'" class="state-item">
              <span class="state-label">Emotion</span>
              <span class="state-value">{{ cs.emotional_state }}</span>
            </div>
            <div v-if="cs.hair_state" class="state-item">
              <span class="state-label">Hair</span>
              <span class="state-value">{{ cs.hair_state }}</span>
            </div>
            <div v-if="cs.body_state && cs.body_state !== 'clean'" class="state-item">
              <span class="state-label">Body</span>
              <span class="state-value">{{ cs.body_state }}</span>
            </div>
            <div v-if="cs.energy_level && cs.energy_level !== 'normal'" class="state-item">
              <span class="state-label">Energy</span>
              <span class="state-value">{{ cs.energy_level }}</span>
            </div>
            <div v-if="cs.location_in_scene" class="state-item">
              <span class="state-label">Position</span>
              <span class="state-value">{{ cs.location_in_scene }}</span>
            </div>
            <div v-if="cs.accessories && cs.accessories.length" class="state-item">
              <span class="state-label">Accessories</span>
              <span class="state-value">{{ cs.accessories.join(', ') }}</span>
            </div>
            <div v-if="cs.carrying && cs.carrying.length" class="state-item">
              <span class="state-label">Carrying</span>
              <span class="state-value">{{ cs.carrying.join(', ') }}</span>
            </div>
          </div>
          <div v-if="cs.injuries && cs.injuries.length" style="margin-top: 4px;">
            <span class="state-label">Injuries</span>
            <span
              v-for="(inj, i) in cs.injuries"
              :key="i"
              class="source-badge source-badge--poor"
              style="font-size: 9px; margin-left: 4px;"
            >{{ inj.severity }} {{ inj.type }} ({{ inj.location }})</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="shot.error_message" style="margin-top: 8px; padding: 8px; background: rgba(160,80,80,0.15); border-radius: 4px; font-size: 12px; color: var(--status-error);">
      Error: {{ shot.error_message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { BuilderShot, CharacterSceneState } from '@/types'
import { scenesApi } from '@/api/scenes'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const props = defineProps<{
  shot: Partial<BuilderShot>
}>()

const emit = defineEmits<{
  'update-field': [field: string, value: unknown]
}>()

const stateExpanded = ref(false)
const characterStates = ref<CharacterSceneState[]>([])

const engineHint = computed(() => {
  const engine = props.shot?.video_engine || 'framepack'
  const hints: Record<string, string> = {
    framepack: 'I2V — needs source image. Best for solo characters with LoRA.',
    framepack_f1: 'Faster FramePack variant. Slightly lower quality.',
    wan: 'Text-to-video — no source image needed. Best for multi-character and establishing shots.',
    wan22: 'Wan 2.2 5B — faster than 2.1, good for T2V and I2V.',
    wan22_14b: 'Wan 2.2 14B — highest quality I2V, needs source image. Uses lightx2v (4 steps).',
    ltx: 'LTX-Video — supports LoRA. Experimental.',
  }
  return hints[engine] || ''
})

const stepsDefault = computed(() => {
  const engine = props.shot?.video_engine || 'framepack'
  if (engine === 'wan' || engine === 'wan22') return 20
  if (engine === 'wan22_14b') return 4
  return 25
})

// Fetch character states when shot changes
watch(() => (props.shot as any)?.id, async () => {
  characterStates.value = []
  stateExpanded.value = false

  const shotAny = props.shot as any
  if (shotAny?.scene_id) {
    try {
      const baseUrl = (scenesApi as any).baseUrl || '/anime-studio/api'
      const resp = await fetch(`${baseUrl}/narrative/state/${shotAny.scene_id}`)
      if (resp.ok) {
        const data = await resp.json()
        const chars = shotAny.characters_present || []
        characterStates.value = (data.states || []).filter(
          (s: CharacterSceneState) => chars.length === 0 || chars.includes(s.character_slug)
        )
      }
    } catch {
      // NSM not available — silently skip
    }
  }
}, { immediate: true })

function updateField(field: string, value: unknown) {
  emit('update-field', field, value)
}
</script>

<style scoped>
.field-group { margin-bottom: 10px; }
.field-label { font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px; }
.field-input { width: 100%; padding: 6px 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; font-family: var(--font-primary); }
.field-input:focus { border-color: var(--border-focus); outline: none; }
.field-textarea { resize: vertical; min-height: 60px; }
.field-row { display: flex; gap: 8px; }
.field-row .field-group { flex: 1; }
.source-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 500; }
.source-badge--auto { background: rgba(122, 162, 247, 0.15); color: var(--accent-primary); border: 1px solid rgba(122, 162, 247, 0.3); }
.source-badge--manual { background: rgba(160, 160, 160, 0.1); color: var(--text-secondary); border: 1px solid var(--border-primary); }
.source-badge--poor { background: rgba(200, 80, 80, 0.15); color: #c85050; border: 1px solid rgba(200, 80, 80, 0.3); }
.state-section { border-top: 1px solid var(--border-primary); padding-top: 8px; margin-top: 8px; }
.state-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; cursor: pointer; }
.state-card { background: rgba(122, 162, 247, 0.04); border: 1px solid var(--border-primary); border-radius: 4px; padding: 8px; margin-bottom: 6px; }
.state-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 12px; }
.state-item { display: flex; gap: 4px; font-size: 11px; }
.state-label { color: var(--text-secondary); font-weight: 500; min-width: 60px; }
.state-value { color: var(--text-primary); word-break: break-word; }
</style>
