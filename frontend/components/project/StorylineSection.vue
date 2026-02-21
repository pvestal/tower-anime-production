<template>
  <div style="margin-bottom: 20px;">
    <h4 style="font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px;">Storyline</h4>
    <div v-if="!hasStoryline && !editing" style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
      No storyline yet.
      <button class="btn" style="font-size: 11px; padding: 2px 8px; margin-left: 8px;" @click="editing = true">Add Storyline</button>
    </div>
    <template v-if="hasStoryline || editing">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
        <div>
          <label class="field-label">Title</label>
          <input v-model="editStoryline.title" type="text" placeholder="Story title" class="field-input" />
        </div>
        <div>
          <label class="field-label">Genre</label>
          <input v-model="editStoryline.genre" type="text" placeholder="adventure, comedy..." class="field-input" />
        </div>
        <div>
          <label class="field-label">Theme</label>
          <input v-model="editStoryline.theme" type="text" placeholder="friendship, heroism..." class="field-input" />
        </div>
        <div>
          <label class="field-label">Target Audience</label>
          <input v-model="editStoryline.target_audience" type="text" placeholder="kids, teens, all ages..." class="field-input" />
        </div>
      </div>
      <div style="margin-bottom: 10px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
          <label class="field-label" style="margin-bottom: 0;">Summary</label>
          <EchoAssistButton
            context-type="storyline"
            :context-payload="echoContext"
            :current-value="editStoryline.summary"
            compact
            @accept="editStoryline.summary = $event.suggestion"
          />
        </div>
        <textarea v-model="editStoryline.summary" rows="3" placeholder="Story summary..." class="field-input" style="width: 100%; resize: vertical;"></textarea>
      </div>
      <button
        :class="['btn', saved ? 'btn-saved' : 'btn-primary']"
        style="font-size: 12px; padding: 4px 12px; transition: all 200ms ease;"
        @click="handleSave"
        :disabled="saving || !dirty"
      >
        {{ saved ? 'Saved' : saving ? 'Saving...' : 'Save Storyline' }}
      </button>
      <span v-if="!dirty && !saved" style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">no changes</span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, ref, watch } from 'vue'
import type { StorylineUpsert, Storyline } from '@/types'
import EchoAssistButton from '../EchoAssistButton.vue'

const props = defineProps<{
  storyline: Storyline | null
  saving: boolean
  echoContext: Record<string, string | undefined>
}>()

const emit = defineEmits<{
  save: [data: StorylineUpsert]
}>()

const editing = ref(false)
const saved = ref(false)

const hasStoryline = computed(() => !!props.storyline)

const editStoryline = reactive<StorylineUpsert>({
  title: '',
  summary: '',
  theme: '',
  genre: '',
  target_audience: '',
})

const savedSnapshot = ref({ title: '', summary: '', theme: '', genre: '', target_audience: '' })

function snapshot() {
  savedSnapshot.value = {
    title: editStoryline.title || '',
    summary: editStoryline.summary || '',
    theme: editStoryline.theme || '',
    genre: editStoryline.genre || '',
    target_audience: editStoryline.target_audience || '',
  }
}

const dirty = computed(() => {
  const s = savedSnapshot.value
  return editStoryline.title !== s.title
    || editStoryline.summary !== s.summary
    || editStoryline.theme !== s.theme
    || editStoryline.genre !== s.genre
    || editStoryline.target_audience !== s.target_audience
})

watch(() => props.storyline, (sl) => {
  if (sl) {
    editStoryline.title = sl.title || ''
    editStoryline.summary = sl.summary || ''
    editStoryline.theme = sl.theme || ''
    editStoryline.genre = sl.genre || ''
    editStoryline.target_audience = sl.target_audience || ''
    editing.value = true
  } else {
    editStoryline.title = ''
    editStoryline.summary = ''
    editStoryline.theme = ''
    editStoryline.genre = ''
    editStoryline.target_audience = ''
    editing.value = false
  }
  snapshot()
}, { immediate: true })

function handleSave() {
  emit('save', { ...editStoryline })
  snapshot()
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}
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
.btn-saved {
  background: var(--status-success) !important;
  color: var(--bg-primary) !important;
  border-color: var(--status-success) !important;
}
</style>
