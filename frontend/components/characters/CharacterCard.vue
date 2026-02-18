<template>
  <div
    class="card character-card"
    :style="characterStats.canTrain ? { borderColor: 'var(--status-success)' } : {}"
    @click="$emit('open-detail', character)"
  >
    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
      <h3 style="font-size: 15px; font-weight: 500;">{{ character.name }}</h3>
      <span
        v-if="characterStats.canTrain"
        class="badge badge-approved"
        style="font-size: 11px;"
      >
        Ready
      </span>
    </div>

    <!-- Thumbnail strip -->
    <div v-if="thumbnails.length > 0" class="thumbnail-strip">
      <img
        v-for="img in thumbnails"
        :key="img"
        :src="img"
        class="thumbnail"
        loading="lazy"
        @click.stop
      />
      <span v-if="characterStats.approved > thumbnails.length" class="thumbnail-more">
        +{{ characterStats.approved - thumbnails.length }}
      </span>
    </div>

    <!-- SSOT design prompt (click to edit) -->
    <div @click.stop>
      <DesignPromptEditor
        :character="character"
        :editing="editingSlug === character.slug"
        :edit-text="editPromptText"
        :saving="savingPrompt"
        @start-edit="$emit('start-edit', character)"
        @cancel="$emit('cancel-edit')"
        @save="$emit('save-prompt', { character, text: $event })"
        @save-regenerate="$emit('save-regenerate', { character, text: $event })"
      />
    </div>

    <!-- Approved progress toward threshold -->
    <div style="margin-bottom: 12px;">
      <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
        <span :style="{ color: characterStats.canTrain ? 'var(--status-success)' : 'var(--text-secondary)' }">
          {{ characterStats.approved }}/{{ minTrainingImages }} approved
        </span>
        <span v-if="characterStats.pending > 0" style="color: var(--text-muted);">
          {{ characterStats.pending }} pending
        </span>
        <span v-else-if="!characterStats.canTrain" style="color: var(--status-error); font-size: 11px;">
          Need {{ minTrainingImages - characterStats.approved }} more
        </span>
      </div>
      <div class="progress-track" style="height: 6px;">
        <div
          class="progress-bar"
          :class="{ ready: characterStats.canTrain }"
          :style="{ width: `${Math.min(100, (characterStats.approved / minTrainingImages) * 100)}%` }"
        ></div>
      </div>
    </div>

    <!-- Action area -->
    <div style="display: flex; gap: 6px;" @click.stop>
      <button
        v-if="!characterStats.canTrain"
        class="btn"
        style="flex: 1; font-size: 12px;"
        @click="$emit('generate-more', character)"
        :disabled="generatingSlug === character.slug"
      >
        {{ generatingSlug === character.slug ? 'Queued...' : `Generate ${minTrainingImages - characterStats.approved} More` }}
      </button>
      <span v-if="!characterStats.canTrain && characterStats.pending > 0" style="font-size: 11px; color: var(--text-muted); align-self: center;">
        {{ characterStats.pending }} pending
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Character, DatasetImage } from '@/types'
import DesignPromptEditor from './DesignPromptEditor.vue'
import { api } from '@/api/client'

interface CharacterStats {
  total: number
  approved: number
  pending: number
  canTrain: boolean
}

const props = defineProps<{
  character: Character
  characterStats: CharacterStats
  minTrainingImages: number
  editingSlug: string | null
  editPromptText: string
  savingPrompt: boolean
  generatingSlug: string | null
  trainingLoading: boolean
  datasetImages?: DatasetImage[]
}>()

defineEmits<{
  (e: 'start-edit', character: Character): void
  (e: 'cancel-edit'): void
  (e: 'save-prompt', payload: { character: Character; text: string }): void
  (e: 'save-regenerate', payload: { character: Character; text: string }): void
  (e: 'generate-more', character: Character): void
  (e: 'open-detail', character: Character): void
}>()

const thumbnails = computed(() => {
  const images = props.datasetImages || []
  const approved = images.filter(img => img.status === 'approved')
  return approved.slice(0, 4).map(img => api.imageUrl(props.character.slug, img.name))
})
</script>

<style scoped>
.character-card {
  cursor: pointer;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.character-card:hover {
  box-shadow: 0 0 0 1px var(--accent-primary);
}
.thumbnail-strip {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
  align-items: center;
}
.thumbnail {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--border-primary);
}
.thumbnail-more {
  font-size: 11px;
  color: var(--text-muted);
  padding: 0 6px;
  white-space: nowrap;
}
.meta-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
}
</style>
