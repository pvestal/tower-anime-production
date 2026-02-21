<template>
  <div class="card">
    <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Voice Extraction</h3>
    <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
      Extract speech segments from a video for voice cloning. Uses ffmpeg silence detection to isolate dialogue.
    </p>
    <input
      v-model="voiceUrl"
      type="url"
      placeholder="https://youtube.com/watch?v=... (trailer, interview, etc)"
      style="width: 100%; padding: 6px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-bottom: 8px;"
    />
    <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap;">
      <label style="font-size: 12px; color: var(--text-muted);">Min sec:</label>
      <input v-model.number="voiceMinDuration" type="number" min="0.3" max="5" step="0.1"
        style="width: 60px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
      <label style="font-size: 12px; color: var(--text-muted);">Max sec:</label>
      <input v-model.number="voiceMaxDuration" type="number" min="1" max="120" step="1"
        style="width: 60px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
    </div>
    <button
      class="btn"
      style="width: 100%; color: var(--accent-primary);"
      @click="extractVoice"
      :disabled="!voiceUrl || voiceLoading || !selectedProject"
    >
      {{ voiceLoading ? 'Extracting audio segments...' : 'Extract Voice Clips' }}
    </button>
    <div v-if="voiceResult" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">
      {{ voiceResult.segments_extracted }} speech segments extracted
    </div>
    <div v-if="voiceResult?.segments?.length" style="margin-top: 8px;">
      <button
        class="btn"
        style="width: 100%; margin-bottom: 8px; color: var(--accent-secondary, var(--accent-primary));"
        @click="transcribeVoice"
        :disabled="transcribeLoading || !selectedProject"
      >
        {{ transcribeLoading ? 'Transcribing with Whisper...' : `Transcribe ${voiceResult.segments.length} Segments` }}
      </button>
      <div v-if="transcribeResult" style="margin-bottom: 8px; font-size: 12px; color: var(--status-success);">
        {{ transcribeResult.transcribed }} transcribed, {{ transcribeResult.characters_matched }} matched to characters
      </div>
      <div style="max-height: 200px; overflow-y: auto;">
        <div v-for="seg in displaySegments" :key="seg.filename"
          style="display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); padding: 3px 0; border-bottom: 1px solid var(--border-primary);">
          <span style="min-width: 32px;">{{ seg.duration?.toFixed(1) || '?' }}s</span>
          <audio :src="api.voiceSegmentUrl(selectedProject, seg.filename)" controls preload="none"
            style="height: 24px; width: 140px; flex-shrink: 0;" />
          <span v-if="seg.text" style="flex: 1; font-size: 10px;">{{ seg.text }}</span>
          <span v-if="seg.matched_character"
            style="font-size: 9px; padding: 1px 6px; background: rgba(80,160,80,0.2); border-radius: 8px; white-space: nowrap;">
            {{ seg.matched_character }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{
  selectedProject: string
}>()

const emit = defineEmits<{
  error: [message: string]
}>()

type VoiceSegment = {
  filename: string
  start: number
  end: number
  duration: number
  text?: string
  matched_character?: string | null
}

const voiceUrl = ref('')
const voiceMinDuration = ref(0.5)
const voiceMaxDuration = ref(30)
const voiceLoading = ref(false)
const voiceResult = ref<{ segments_extracted: number; segments: VoiceSegment[] } | null>(null)
const transcribeLoading = ref(false)
const transcribeResult = ref<{ transcribed: number; characters_matched: number } | null>(null)

const displaySegments = computed(() => {
  if (!voiceResult.value?.segments) return []
  return voiceResult.value.segments
})

async function extractVoice() {
  voiceLoading.value = true
  voiceResult.value = null
  try {
    voiceResult.value = await api.ingestVoice(
      voiceUrl.value, props.selectedProject, voiceMinDuration.value, voiceMaxDuration.value,
    )
    voiceUrl.value = ''
  } catch (e: any) {
    emit('error', e.message || 'Voice extraction failed')
  } finally {
    voiceLoading.value = false
  }
}

async function transcribeVoice() {
  if (!props.selectedProject) return
  transcribeLoading.value = true
  transcribeResult.value = null
  try {
    const result = await api.transcribeVoice(props.selectedProject, 'base')
    transcribeResult.value = { transcribed: result.transcribed, characters_matched: result.characters_matched }
    if (voiceResult.value?.segments) {
      for (const t of result.transcriptions) {
        const seg = voiceResult.value.segments.find(s => s.filename === t.filename)
        if (seg) {
          seg.text = t.text
          seg.matched_character = t.matched_character
        }
      }
    }
  } catch (e: any) {
    emit('error', e.message || 'Transcription failed')
  } finally {
    transcribeLoading.value = false
  }
}
</script>
