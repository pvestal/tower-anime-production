<template>
  <div class="rehearsal-overlay" @click.self="$emit('close')">
    <div class="rehearsal-container">
      <!-- Top bar -->
      <div class="rehearsal-header">
        <span class="rehearsal-title">Rehearsal: {{ sceneTitle }}</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="shot-indicator">Shot {{ currentShotIdx + 1 }} / {{ dialogueShots.length }}</span>
          <button class="rehearsal-close" @click="$emit('close')">&times;</button>
        </div>
      </div>

      <!-- Main area: image + dialogue -->
      <div class="rehearsal-stage">
        <!-- Scene image -->
        <div class="stage-image">
          <img
            v-if="currentImageUrl"
            :src="currentImageUrl"
            alt=""
            class="shot-image"
            :class="{ 'image-entering': imageTransition }"
          />
          <div v-else class="image-placeholder">
            <span>No keyframe</span>
          </div>
          <!-- Character name overlay -->
          <div v-if="currentShot" class="character-badge">
            {{ characterName(currentShot.dialogue_character_slug) }}
          </div>
        </div>

        <!-- Dialogue panel -->
        <div class="stage-dialogue">
          <!-- Shot list (scrollable) -->
          <div class="dialogue-timeline" ref="timelineRef">
            <div
              v-for="(shot, i) in dialogueShots"
              :key="shot.id || i"
              class="timeline-line"
              :class="{ active: i === currentShotIdx, played: i < currentShotIdx }"
              @click="jumpTo(i)"
            >
              <span class="tl-char" :class="{ speaking: i === currentShotIdx && isPlaying }">
                {{ characterName(shot.dialogue_character_slug) }}
              </span>
              <span class="tl-text">{{ shot.dialogue_text }}</span>
              <span v-if="i === currentShotIdx && isPlaying" class="tl-playing-dot" />
            </div>
          </div>

          <!-- Edit area for current line -->
          <div v-if="currentShot" class="dialogue-editor">
            <div class="editor-row">
              <select
                :value="editCharSlug"
                @change="editCharSlug = ($event.target as HTMLSelectElement).value"
                class="char-select"
              >
                <option v-for="c in characters" :key="c.slug" :value="c.slug">{{ c.name }}</option>
              </select>
              <textarea
                v-model="editText"
                rows="2"
                class="edit-textarea"
                placeholder="Enter dialogue..."
                @keydown.ctrl.enter="saveAndSynthesize"
              />
            </div>
            <div class="editor-actions">
              <button
                class="btn-rehearsal btn-save"
                :disabled="!isDirty"
                @click="saveEdit"
              >Save</button>
              <button
                class="btn-rehearsal btn-synth"
                :disabled="synthBusy"
                @click="synthesizeAndPlay"
              >{{ synthBusy ? 'Generating...' : 'Speak' }}</button>
              <audio v-if="audioUrl" ref="audioEl" :src="audioUrl" @ended="onAudioEnded" />
              <span v-if="lastEngine" class="engine-tag">{{ lastEngine }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Playback controls -->
      <div class="rehearsal-controls">
        <button class="ctrl-btn" :disabled="currentShotIdx <= 0" @click="prev">&laquo; Prev</button>
        <button class="ctrl-btn ctrl-play" @click="toggleAutoPlay">
          {{ autoPlaying ? 'Stop' : 'Play All' }}
        </button>
        <button class="ctrl-btn" :disabled="currentShotIdx >= dialogueShots.length - 1" @click="next">Next &raquo;</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { scenesApi } from '@/api/scenes'

const props = defineProps<{
  shots: Array<Record<string, any>>
  sceneTitle: string
  characters: { slug: string; name: string }[]
  sourceImageUrl: (path: string) => string
}>()

const emit = defineEmits<{
  close: []
  'update-shot': [shotId: string, field: string, value: string]
}>()

// Filter to only shots with dialogue
const dialogueShots = computed(() =>
  props.shots.filter(s => s.dialogue_text && s.dialogue_character_slug)
)

const currentShotIdx = ref(0)
const currentShot = computed(() => dialogueShots.value[currentShotIdx.value] || null)

const currentImageUrl = computed(() => {
  const shot = currentShot.value
  if (!shot) return null
  if (shot.source_image_path) return props.sourceImageUrl(shot.source_image_path)
  if (shot.first_frame_path) return props.sourceImageUrl(shot.first_frame_path)
  return null
})

const imageTransition = ref(false)

// Editor state
const editText = ref('')
const editCharSlug = ref('')
const isDirty = computed(() => {
  const s = currentShot.value
  if (!s) return false
  return editText.value !== s.dialogue_text || editCharSlug.value !== s.dialogue_character_slug
})

// Audio state
const synthBusy = ref(false)
const audioUrl = ref<string | null>(null)
const audioEl = ref<HTMLAudioElement | null>(null)
const isPlaying = ref(false)
const lastEngine = ref<string | null>(null)
const autoPlaying = ref(false)
const timelineRef = ref<HTMLElement | null>(null)

function characterName(slug: string | undefined): string {
  if (!slug) return '?'
  const c = props.characters.find(ch => ch.slug === slug)
  return c?.name || slug.replace(/_/g, ' ')
}

// Sync editor with current shot
watch(currentShot, (shot) => {
  if (shot) {
    editText.value = shot.dialogue_text || ''
    editCharSlug.value = shot.dialogue_character_slug || ''
    audioUrl.value = null
    lastEngine.value = null
    isPlaying.value = false
  }
}, { immediate: true })

// Image transition effect
watch(currentShotIdx, () => {
  imageTransition.value = true
  setTimeout(() => { imageTransition.value = false }, 300)
})

// Scroll timeline to active
watch(currentShotIdx, async () => {
  await nextTick()
  const el = timelineRef.value?.querySelector('.timeline-line.active')
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
})

function saveEdit() {
  const shot = currentShot.value
  if (!shot?.id) return
  if (editText.value !== shot.dialogue_text) {
    emit('update-shot', shot.id, 'dialogue_text', editText.value)
    shot.dialogue_text = editText.value
  }
  if (editCharSlug.value !== shot.dialogue_character_slug) {
    emit('update-shot', shot.id, 'dialogue_character_slug', editCharSlug.value)
    shot.dialogue_character_slug = editCharSlug.value
  }
}

async function synthesizeAndPlay() {
  const shot = currentShot.value
  if (!shot?.id) return
  // Save first if dirty
  if (isDirty.value) saveEdit()
  synthBusy.value = true
  try {
    const result = await scenesApi.synthesizeShotDialogue(shot.id)
    lastEngine.value = result.engine_used
    audioUrl.value = scenesApi.synthesisAudioUrl(result.job_id)
    await nextTick()
    isPlaying.value = true
    audioEl.value?.play()
  } catch (e: any) {
    alert(`Synthesis failed: ${e.message || e}`)
  } finally {
    synthBusy.value = false
  }
}

function saveAndSynthesize() {
  saveEdit()
  synthesizeAndPlay()
}

function onAudioEnded() {
  isPlaying.value = false
  if (autoPlaying.value) {
    if (currentShotIdx.value < dialogueShots.value.length - 1) {
      setTimeout(() => {
        next()
        // Auto-synthesize next line
        setTimeout(() => synthesizeAndPlay(), 200)
      }, 400)
    } else {
      autoPlaying.value = false
    }
  }
}

function jumpTo(idx: number) {
  autoPlaying.value = false
  audioEl.value?.pause()
  isPlaying.value = false
  currentShotIdx.value = idx
}

function prev() {
  if (currentShotIdx.value > 0) {
    audioEl.value?.pause()
    isPlaying.value = false
    currentShotIdx.value--
  }
}

function next() {
  if (currentShotIdx.value < dialogueShots.value.length - 1) {
    audioEl.value?.pause()
    isPlaying.value = false
    currentShotIdx.value++
  }
}

function toggleAutoPlay() {
  if (autoPlaying.value) {
    autoPlaying.value = false
    audioEl.value?.pause()
    isPlaying.value = false
  } else {
    autoPlaying.value = true
    synthesizeAndPlay()
  }
}

onUnmounted(() => {
  audioEl.value?.pause()
})
</script>

<style scoped>
.rehearsal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rehearsal-container {
  width: 95vw;
  max-width: 1200px;
  height: 85vh;
  background: #0f1117;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.rehearsal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.rehearsal-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--accent-primary, #7aa2f7);
}

.shot-indicator {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 3px 10px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 12px;
}

.rehearsal-close {
  width: 32px;
  height: 32px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  color: rgba(255, 255, 255, 0.6);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rehearsal-close:hover {
  background: rgba(220, 50, 50, 0.2);
  color: #f07070;
}

.rehearsal-stage {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.stage-image {
  flex: 0 0 50%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #080810;
  overflow: hidden;
}

.shot-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: opacity 0.3s ease;
}

.image-entering {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0.3; transform: scale(0.98); }
  to { opacity: 1; transform: scale(1); }
}

.image-placeholder {
  color: rgba(255, 255, 255, 0.2);
  font-size: 14px;
}

.character-badge {
  position: absolute;
  bottom: 16px;
  left: 16px;
  padding: 6px 14px;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(122, 162, 247, 0.3);
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-primary, #7aa2f7);
}

.stage-dialogue {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-left: 1px solid rgba(255, 255, 255, 0.06);
}

.dialogue-timeline {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.timeline-line {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
  border-left: 3px solid transparent;
}

.timeline-line:hover {
  background: rgba(255, 255, 255, 0.03);
}

.timeline-line.active {
  background: rgba(122, 162, 247, 0.08);
  border-left-color: var(--accent-primary, #7aa2f7);
}

.timeline-line.played {
  opacity: 0.5;
}

.tl-char {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-primary, #7aa2f7);
  min-width: 90px;
  padding-top: 1px;
}

.tl-char.speaking {
  animation: pulse 1s ease infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.tl-text {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.4;
}

.tl-playing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  flex-shrink: 0;
  margin-top: 4px;
  animation: pulse 1s ease infinite;
}

.dialogue-editor {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding: 12px 16px;
  flex-shrink: 0;
}

.editor-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.char-select {
  flex-shrink: 0;
  width: 140px;
  padding: 6px 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--text-primary, #e8e8e8);
  font-size: 12px;
  font-family: inherit;
}

.edit-textarea {
  flex: 1;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--text-primary, #e8e8e8);
  font-size: 13px;
  font-family: inherit;
  resize: none;
}

.edit-textarea:focus, .char-select:focus {
  border-color: var(--accent-primary, #7aa2f7);
  outline: none;
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-rehearsal {
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
}

.btn-save {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary, #e8e8e8);
}

.btn-save:disabled {
  opacity: 0.3;
  cursor: default;
}

.btn-synth {
  background: var(--accent-primary, #7aa2f7);
  color: #fff;
}

.btn-synth:disabled {
  opacity: 0.5;
  cursor: default;
}

.engine-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 8px;
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary, #7aa2f7);
}

.rehearsal-controls {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.ctrl-btn {
  padding: 8px 20px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.ctrl-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.ctrl-btn:disabled {
  opacity: 0.3;
  cursor: default;
}

.ctrl-play {
  background: rgba(34, 197, 94, 0.15);
  border-color: rgba(34, 197, 94, 0.3);
  color: #22c55e;
  min-width: 100px;
}

.ctrl-play:hover {
  background: rgba(34, 197, 94, 0.25) !important;
  color: #22c55e !important;
}
</style>
