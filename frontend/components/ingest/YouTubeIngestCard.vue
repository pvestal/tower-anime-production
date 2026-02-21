<template>
  <div class="card">
    <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">YouTube Video</h3>
    <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
      {{ targetMode === 'project'
        ? 'Extract frames and distribute to ALL characters in the project for individual approval.'
        : 'Paste a YouTube URL to extract frames from the video.' }}
    </p>
    <input
      v-model="youtubeUrl"
      type="url"
      placeholder="https://youtube.com/watch?v=..."
      style="width: 100%; padding: 6px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-bottom: 8px;"
    />
    <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap;">
      <label style="font-size: 12px; color: var(--text-muted);">Max frames:</label>
      <input
        v-model.number="maxFrames"
        type="number"
        min="1"
        max="300"
        style="width: 70px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
      />
      <label style="font-size: 12px; color: var(--text-muted);">FPS:</label>
      <input
        v-model.number="fps"
        type="number"
        min="0.5"
        max="10"
        step="0.5"
        style="width: 60px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
      />
      <span style="font-size: 11px; color: var(--text-muted);">(higher = more frames)</span>
    </div>
    <button
      class="btn"
      style="width: 100%; color: var(--accent-primary);"
      @click="ingest"
      :disabled="!youtubeUrl || loading || !canSubmit"
    >
      {{ loading ? 'Downloading & extracting...' : targetMode === 'project' ? 'Extract to All Characters' : 'Extract Frames' }}
    </button>
    <div v-if="result" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">
      <template v-if="result.characters_seeded">
        Extracted {{ result.frames_extracted }} frames to {{ result.characters_seeded }} characters. Check the Pending tab.
      </template>
      <template v-else>
        Extracted {{ result.frames_extracted }} frames. Check the Pending tab.
      </template>
    </div>
    <div v-if="result?.per_character" style="margin-top: 4px; font-size: 11px; color: var(--text-secondary);">
      <div v-for="(count, slug) in result.per_character" :key="slug">
        {{ slug }}: {{ count }} frames
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{
  targetMode: 'character' | 'project'
  selectedCharacter: string
  selectedProject: string
}>()

const emit = defineEmits<{
  error: [message: string]
}>()

const youtubeUrl = ref('')
const maxFrames = ref(60)
const fps = ref(4)
const loading = ref(false)
const result = ref<{ frames_extracted: number; characters_seeded?: number; per_character?: Record<string, number> } | null>(null)

const canSubmit = computed(() => {
  if (props.targetMode === 'character') return !!props.selectedCharacter
  return !!props.selectedProject
})

async function ingest() {
  loading.value = true
  result.value = null
  try {
    if (props.targetMode === 'project') {
      result.value = await api.ingestYoutubeProject(
        youtubeUrl.value, props.selectedProject, maxFrames.value, fps.value,
      )
    } else {
      result.value = await api.ingestYoutube(
        youtubeUrl.value, props.selectedCharacter, maxFrames.value, fps.value,
      )
    }
    youtubeUrl.value = ''
  } catch (e: any) {
    emit('error', e.message || 'YouTube ingestion failed')
  } finally {
    loading.value = false
  }
}

defineExpose({ fps })
</script>
