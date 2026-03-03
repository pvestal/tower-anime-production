<template>
  <div>
    <!-- Source Image -->
    <div class="field-group">
      <label class="field-label">Source Image</label>
      <div style="display: flex; gap: 8px; align-items: center;">
        <input
          :value="shot.source_image_path"
          @input="updateField('source_image_path', ($event.target as HTMLInputElement).value)"
          type="text"
          placeholder="character_slug/images/filename.png"
          class="field-input"
          style="flex: 1;"
        />
        <button class="btn" style="font-size: 11px; padding: 4px 8px;" @click="$emit('browse-image')">Browse</button>
      </div>
      <div v-if="shot.source_image_path" style="display: flex; align-items: center; gap: 6px; margin-top: 6px;">
        <span v-if="shot.source_image_auto_assigned" class="source-badge source-badge--auto" title="Auto-assigned">auto</span>
        <span v-else-if="shot.source_image_path" class="source-badge source-badge--manual" title="Manually selected">manual</span>
        <span
          v-if="shot.quality_score != null"
          class="source-badge"
          :class="shot.quality_score >= 0.65 ? 'source-badge--good' : shot.quality_score >= 0.4 ? 'source-badge--ok' : 'source-badge--poor'"
          :title="`Quality: ${(shot.quality_score * 100).toFixed(0)}%`"
        >{{ (shot.quality_score * 100).toFixed(0) }}%</span>
      </div>
      <div v-if="shot.source_image_path" style="margin-top: 8px;">
        <img
          :src="sourceImageUrl(shot.source_image_path || '')"
          style="max-width: 200px; max-height: 150px; border-radius: 4px; border: 1px solid var(--border-primary);"
          @error="($event.target as HTMLImageElement).style.display = 'none'"
        />
      </div>
    </div>

    <!-- Shot Type + Camera Angle -->
    <div class="field-row">
      <div class="field-group">
        <label class="field-label">Shot Type</label>
        <select :value="shot.shot_type" @change="updateField('shot_type', ($event.target as HTMLSelectElement).value)" class="field-input">
          <option v-for="t in shotTypes" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label">Camera</label>
        <select :value="shot.camera_angle" @change="updateField('camera_angle', ($event.target as HTMLSelectElement).value)" class="field-input">
          <option v-for="a in cameraAngles" :key="a" :value="a">{{ a }}</option>
        </select>
      </div>
    </div>

    <!-- Duration -->
    <div class="field-group">
      <label class="field-label">Duration: {{ shot.duration_seconds }}s</label>
      <input
        :value="shot.duration_seconds"
        @input="updateField('duration_seconds', Number(($event.target as HTMLInputElement).value))"
        type="range" min="2" max="10" step="1"
        style="width: 100%;"
      />
    </div>

    <!-- Motion Prompt -->
    <div class="field-group">
      <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
        <label class="field-label" style="margin-bottom: 0;">Motion Prompt</label>
        <EchoAssistButton
          context-type="motion_prompt"
          :context-payload="{
            project_name: projectStore.currentProject?.name,
            shot_type: shot.shot_type,
            scene_description: shot.motion_prompt ?? undefined,
          }"
          :current-value="shot.motion_prompt || ''"
          compact
          @accept="updateField('motion_prompt', $event.suggestion)"
        />
      </div>
      <div v-if="motionPresets.length > 0 && authStore.isAdvanced" style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px;">
        <button
          v-for="preset in motionPresets"
          :key="preset"
          class="preset-chip"
          @click="updateField('motion_prompt', preset)"
        >{{ preset }}</button>
      </div>
      <textarea
        :value="shot.motion_prompt"
        @input="updateField('motion_prompt', ($event.target as HTMLTextAreaElement).value)"
        rows="4"
        :placeholder="motionPlaceholder"
        class="field-input field-textarea"
      ></textarea>
    </div>

    <!-- Dialogue -->
    <div class="dialogue-section">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
        <label class="field-label" style="margin-bottom: 0; font-weight: 500; color: var(--accent-primary);">Dialogue</label>
        <button
          v-if="characters.length > 0"
          class="btn"
          style="font-size: 10px; padding: 2px 8px; color: var(--accent-primary);"
          :disabled="autoDialogueBusy"
          @click="$emit('auto-dialogue')"
        >{{ autoDialogueBusy ? 'Writing...' : 'Auto-Write' }}</button>
      </div>
      <select
        :value="shot.dialogue_character_slug || ''"
        @change="updateField('dialogue_character_slug', ($event.target as HTMLSelectElement).value || null)"
        class="field-input"
        style="margin-bottom: 6px;"
      >
        <option value="">No dialogue</option>
        <option v-for="c in characters" :key="c.slug" :value="c.slug">{{ c.name }}</option>
      </select>
      <textarea
        v-if="shot.dialogue_character_slug"
        :value="shot.dialogue_text"
        @input="updateField('dialogue_text', ($event.target as HTMLTextAreaElement).value)"
        rows="3"
        placeholder="What does this character say?"
        class="field-input field-textarea"
      ></textarea>
      <div v-if="shot.dialogue_character_slug && shot.dialogue_text" style="display: flex; align-items: center; gap: 8px; margin-top: 6px;">
        <button
          class="btn"
          style="font-size: 11px; padding: 3px 10px;"
          :disabled="synthBusy"
          @click="synthesizeAndPlay"
        >
          {{ synthBusy ? 'Generating...' : dialogueAudioUrl ? 'Re-generate' : 'Play Voice' }}
        </button>
        <span v-if="synthEngine" class="source-badge source-badge--auto" style="font-size: 10px;">{{ synthEngine }}</span>
        <span v-if="synthDuration" style="font-size: 10px; color: var(--text-secondary);">{{ synthDuration }}s</span>
        <audio v-if="dialogueAudioUrl" ref="audioPlayer" :src="dialogueAudioUrl" controls style="height: 28px; flex: 1;" />
      </div>
    </div>

    <!-- Scene Prompt -->
    <div class="field-group">
      <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
        <label class="field-label" style="margin-bottom: 0;">Scene Prompt</label>
        <span class="source-badge source-badge--auto" style="font-size: 9px;">drives keyframe + video</span>
      </div>
      <textarea
        :value="shot.generation_prompt"
        @input="updateField('generation_prompt', ($event.target as HTMLTextAreaElement).value)"
        rows="5"
        placeholder="Describe what happens in this shot..."
        class="field-input field-textarea"
      ></textarea>
    </div>

    <!-- Built Prompt Preview -->
    <div class="built-prompt-section">
      <div class="built-prompt-header" @click="toggleBuiltPrompt">
        <span class="field-label" style="margin-bottom: 0; font-weight: 500; cursor: pointer;">
          Final Prompt {{ builtPromptExpanded ? '\u25BE' : '\u25B8' }}
        </span>
        <span class="source-badge source-badge--auto" style="font-size: 9px;">sent to ComfyUI</span>
        <button
          v-if="!builtPromptExpanded"
          class="btn"
          style="font-size: 10px; padding: 2px 8px; margin-left: auto;"
          :disabled="builtPromptLoading"
          @click.stop="loadBuiltPrompt"
        >{{ builtPromptLoading ? 'Loading...' : 'Preview' }}</button>
      </div>
      <div v-if="builtPromptExpanded && builtPromptData" class="built-prompt-body">
        <div class="built-prompt-meta">
          <span class="source-badge" :class="engineBadgeClass">{{ builtPromptData.engine }}</span>
          <span style="font-size: 10px; color: var(--text-muted);">{{ builtPromptData.prompt_length }} chars</span>
        </div>
        <div v-if="builtPromptData.character_appearances.length" style="margin-bottom: 6px;">
          <div v-for="char in builtPromptData.character_appearances" :key="char.name" style="font-size: 10px; margin-bottom: 2px;">
            <span style="color: var(--accent-primary); font-weight: 500;">{{ char.name }}:</span>
            <span style="color: var(--text-secondary);"> {{ char.condensed.slice(0, 120) }}{{ char.condensed.length > 120 ? '...' : '' }}</span>
          </div>
        </div>
        <textarea
          :value="builtPromptData.final_prompt"
          readonly
          rows="6"
          class="field-input field-textarea built-prompt-text"
        ></textarea>
      </div>
      <div v-if="builtPromptExpanded && builtPromptError" style="font-size: 11px; color: var(--status-error); margin-top: 4px;">
        {{ builtPromptError }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { BuilderShot } from '@/types'
import { scenesApi } from '@/api/scenes'
import { useProjectStore } from '@/stores/project'
import { useAuthStore } from '@/stores/auth'
import EchoAssistButton from '../../EchoAssistButton.vue'

const projectStore = useProjectStore()
const authStore = useAuthStore()

const props = defineProps<{
  shot: Partial<BuilderShot>
  sourceImageUrl: (path: string) => string
  characters: { slug: string; name: string }[]
  shotVideoSrc: string
  autoDialogueBusy?: boolean
}>()

const emit = defineEmits<{
  'update-field': [field: string, value: unknown]
  'browse-image': []
  'auto-dialogue': []
}>()

const shotTypes = ['establishing', 'wide', 'medium', 'close-up', 'extreme_close-up', 'action']
const cameraAngles = ['eye-level', 'high', 'low', 'dutch', 'pov']

// Motion presets
const motionPresets = ref<string[]>([])
const motionPlaceholder = computed(() => {
  const type = props.shot?.shot_type || 'medium'
  const hints: Record<string, string> = {
    'close-up': 'subtle breathing, eyes shifting...',
    'extreme_close-up': 'pupil dilation, tear rolling...',
    'establishing': 'slow pan across cityscape...',
    'wide': 'characters walking through scene...',
    'medium': 'character gesturing, looking around...',
    'action': 'running forward, sword swing...',
  }
  return hints[type] || 'Describe the motion/action...'
})

async function loadPresets(shotType: string) {
  try {
    const data = await scenesApi.getMotionPresets(shotType)
    motionPresets.value = Array.isArray(data.presets) ? data.presets : []
  } catch {
    motionPresets.value = []
  }
}

watch(() => props.shot?.shot_type, (newType) => {
  if (newType) loadPresets(newType)
  else motionPresets.value = []
}, { immediate: true })

// Built prompt preview
const builtPromptExpanded = ref(false)
const builtPromptLoading = ref(false)
const builtPromptError = ref<string | null>(null)
const builtPromptData = ref<{
  final_prompt: string; final_negative: string; engine: string;
  prompt_length: number; style_anchor: string | null;
  scene_context: { location: string | null; time_of_day: string | null; mood: string | null; description: string | null };
  character_appearances: Array<{ name: string; condensed: string }>;
  motion_prompt: string | null; generation_prompt: string | null;
} | null>(null)

const engineBadgeClass = computed(() => {
  const eng = builtPromptData.value?.engine || ''
  if (eng.startsWith('framepack')) return 'source-badge--good'
  if (eng.startsWith('wan22')) return 'source-badge--auto'
  return 'source-badge--manual'
})

async function loadBuiltPrompt() {
  const shotAny = props.shot as any
  if (!shotAny?.id || !shotAny?.scene_id) return
  builtPromptLoading.value = true
  builtPromptError.value = null
  try {
    builtPromptData.value = await scenesApi.getBuiltPrompt(shotAny.scene_id, shotAny.id)
    builtPromptExpanded.value = true
  } catch (e: any) {
    builtPromptError.value = e.message || 'Failed to load prompt preview'
    builtPromptExpanded.value = true
  } finally {
    builtPromptLoading.value = false
  }
}

function toggleBuiltPrompt() {
  if (!builtPromptExpanded.value && !builtPromptData.value) {
    loadBuiltPrompt()
  } else {
    builtPromptExpanded.value = !builtPromptExpanded.value
  }
}

// Voice synthesis
const synthBusy = ref(false)
const dialogueAudioUrl = ref<string | null>(null)
const synthEngine = ref<string | null>(null)
const synthDuration = ref<number | null>(null)
const audioPlayer = ref<HTMLAudioElement | null>(null)

async function synthesizeAndPlay() {
  const shotId = (props.shot as any)?.id
  if (!shotId || !props.shot?.dialogue_text || !props.shot?.dialogue_character_slug) return
  synthBusy.value = true
  try {
    const result = await scenesApi.synthesizeShotDialogue(shotId)
    synthEngine.value = result.engine_used
    synthDuration.value = result.duration_seconds
    dialogueAudioUrl.value = scenesApi.synthesisAudioUrl(result.job_id)
    await new Promise(r => setTimeout(r, 100))
    audioPlayer.value?.play()
  } catch (e: any) {
    console.error('Voice synthesis failed:', e)
    alert(`Voice synthesis failed: ${e.message || e}`)
  } finally {
    synthBusy.value = false
  }
}

// Reset on shot change
watch(() => (props.shot as any)?.id, () => {
  builtPromptExpanded.value = false
  builtPromptData.value = null
  builtPromptError.value = null
  dialogueAudioUrl.value = null
  synthEngine.value = null
  synthDuration.value = null
})

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
.preset-chip { padding: 2px 8px; font-size: 11px; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-primary); border-radius: 12px; cursor: pointer; font-family: var(--font-primary); }
.preset-chip:hover { background: rgba(122, 162, 247, 0.15); border-color: var(--accent-primary); color: var(--accent-primary); }
.source-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 500; }
.source-badge--auto { background: rgba(122, 162, 247, 0.15); color: var(--accent-primary); border: 1px solid rgba(122, 162, 247, 0.3); }
.source-badge--manual { background: rgba(160, 160, 160, 0.1); color: var(--text-secondary); border: 1px solid var(--border-primary); }
.source-badge--good { background: rgba(80, 200, 120, 0.15); color: #50c878; border: 1px solid rgba(80, 200, 120, 0.3); }
.source-badge--ok { background: rgba(240, 180, 60, 0.15); color: #f0b43c; border: 1px solid rgba(240, 180, 60, 0.3); }
.source-badge--poor { background: rgba(200, 80, 80, 0.15); color: #c85050; border: 1px solid rgba(200, 80, 80, 0.3); }
.dialogue-section { border-top: 2px solid var(--accent-primary); padding-top: 10px; margin-top: 8px; background: rgba(122, 162, 247, 0.04); margin-left: -12px; margin-right: -12px; padding-left: 12px; padding-right: 12px; padding-bottom: 8px; }
.built-prompt-section { border-top: 1px solid var(--border-primary); padding-top: 8px; margin-top: 8px; }
.built-prompt-header { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.built-prompt-body { margin-top: 6px; }
.built-prompt-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.built-prompt-text { font-size: 11px !important; background: rgba(122, 162, 247, 0.04) !important; color: var(--text-secondary) !important; cursor: default; }
</style>
