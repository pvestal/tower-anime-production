<template>
  <div class="audio-tab">
    <!-- Voice Dialogue -->
    <div class="section">
      <label class="section-label">Voice Dialogue</label>
      <div v-if="shot.dialogue_text" class="status-row">
        <span class="status-badge" :class="hasVoice ? 'badge-ok' : 'badge-warn'">
          {{ hasVoice ? 'Synthesized' : 'Pending' }}
        </span>
        <span class="char-name">{{ shot.dialogue_character_slug || 'unassigned' }}</span>
      </div>
      <div v-else class="empty-state">No dialogue on this shot</div>

      <div v-if="shot.dialogue_text" class="dialogue-preview">{{ shot.dialogue_text }}</div>

      <div v-if="shot.dialogue_text" class="synth-controls">
        <button class="btn btn-primary" :disabled="synthBusy" @click="synthesizeVoice">
          {{ synthBusy ? 'Synthesizing...' : hasVoice ? 'Re-synthesize' : 'Synthesize Voice' }}
        </button>
        <audio v-if="voiceUrl" :src="voiceUrl" controls class="audio-player" />
      </div>
    </div>

    <!-- Foley SFX -->
    <div class="section">
      <label class="section-label">Foley SFX</label>
      <div class="status-row">
        <span class="status-badge" :class="hasSfx ? 'badge-ok' : 'badge-warn'">
          {{ hasSfx ? 'Mixed' : hasVideo ? 'Ready to generate' : 'No video yet' }}
        </span>
        <span v-if="shot.lora_name" class="char-name">LoRA: {{ shot.lora_name }}</span>
      </div>
      <div v-if="hasSfx" class="sfx-info">
        <audio :src="sfxAudioUrl" controls class="audio-player" />
      </div>
      <div v-if="hasVideo && !hasSfx" class="synth-controls">
        <button class="btn btn-accent" :disabled="sfxBusy" @click="generateAudio">
          {{ sfxBusy ? 'Generating...' : 'Generate Voice + SFX' }}
        </button>
      </div>
      <div v-if="hasSfx" class="synth-controls">
        <button class="btn btn-secondary" :disabled="sfxBusy" @click="generateAudio">
          {{ sfxBusy ? 'Regenerating...' : 'Regenerate Audio' }}
        </button>
      </div>
    </div>

    <!-- Audio Pipeline Progress -->
    <div class="section summary">
      <label class="section-label">Audio Pipeline</label>
      <div class="pipeline-steps">
        <div class="step" :class="{ done: !!shot.dialogue_text }">1. Dialogue written</div>
        <div class="step" :class="{ done: hasVoice }">2. Voice synthesized</div>
        <div class="step" :class="{ done: hasSfx }">3. Foley mixed</div>
      </div>
    </div>

    <!-- Error display -->
    <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { BuilderShot } from '@/types'
import { scenesApi } from '@/api/scenes'

const props = defineProps<{
  shot: Partial<BuilderShot>
  sceneId?: string
}>()

const emit = defineEmits<{
  (e: 'updated', shot: Partial<BuilderShot>): void
}>()

const synthBusy = ref(false)
const sfxBusy = ref(false)
const voiceUrl = ref<string | null>(null)
const errorMsg = ref<string | null>(null)

const hasVideo = computed(() => !!props.shot.output_video_path)
const hasVoice = computed(() => !!props.shot.voice_audio_path || !!voiceUrl.value)
const hasSfx = computed(() => !!props.shot.sfx_audio_path)

const sfxAudioUrl = computed(() => {
  if (!props.sceneId || !props.shot.id) return ''
  return scenesApi.shotAudioUrl(props.sceneId, props.shot.id)
})

async function synthesizeVoice() {
  if (!props.shot.id) return
  synthBusy.value = true
  errorMsg.value = null
  try {
    const result = await scenesApi.synthesizeShotDialogue(props.shot.id)
    if (result?.job_id) {
      voiceUrl.value = scenesApi.synthesisAudioUrl(result.job_id)
    }
  } catch (e: any) {
    errorMsg.value = `Voice synthesis failed: ${e.message || e}`
  } finally {
    synthBusy.value = false
  }
}

async function generateAudio() {
  if (!props.shot.id || !props.sceneId) return
  sfxBusy.value = true
  errorMsg.value = null
  try {
    const result = await scenesApi.generateShotAudio(props.sceneId, props.shot.id)
    if (result.sfx_audio_path) {
      // Signal parent to refresh shot data
      emit('updated', {
        ...props.shot,
        sfx_audio_path: result.sfx_audio_path,
        voice_audio_path: result.voice_audio_path,
        dialogue_text: result.dialogue_text || props.shot.dialogue_text,
        dialogue_character_slug: result.dialogue_character_slug || props.shot.dialogue_character_slug,
      })
    } else {
      errorMsg.value = 'No audio generated — check LoRA mapping or dialogue'
    }
  } catch (e: any) {
    errorMsg.value = `Audio generation failed: ${e.message || e}`
  } finally {
    sfxBusy.value = false
  }
}
</script>

<style scoped>
.audio-tab {
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section {
  border-bottom: 1px solid var(--border-primary);
  padding-bottom: 10px;
}
.section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
  display: block;
}
.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.status-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 500;
}
.badge-ok {
  background: rgba(80, 180, 120, 0.15);
  color: var(--status-success, #67c23a);
}
.badge-warn {
  background: rgba(230, 162, 60, 0.15);
  color: var(--status-warning, #e6a23c);
}
.char-name {
  font-size: 11px;
  color: var(--text-secondary);
}
.dialogue-preview {
  font-size: 11px;
  color: var(--text-primary);
  font-style: italic;
  margin: 4px 0;
  padding: 4px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  max-height: 60px;
  overflow-y: auto;
}
.synth-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.btn {
  border: none;
  font-size: 11px;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--accent-primary);
  color: #fff;
}
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-accent {
  background: #1f6feb;
  color: #fff;
}
.btn-accent:hover:not(:disabled) { opacity: 0.85; }
.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
}
.btn-secondary:hover:not(:disabled) { background: var(--bg-secondary); }
.audio-player {
  height: 28px;
  flex: 1;
  min-width: 0;
}
.sfx-info {
  margin-top: 6px;
}
.empty-state {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}
.pipeline-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.step {
  font-size: 11px;
  color: var(--text-muted);
  padding-left: 16px;
  position: relative;
}
.step::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 5px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1px solid var(--text-muted);
}
.step.done::before {
  background: var(--status-success, #67c23a);
  border-color: var(--status-success, #67c23a);
}
.summary {
  border-bottom: none;
}
.error-msg {
  font-size: 11px;
  color: #f85149;
  background: rgba(248, 81, 73, 0.1);
  padding: 6px 10px;
  border-radius: 4px;
}
</style>
