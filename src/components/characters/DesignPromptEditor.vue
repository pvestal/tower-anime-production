<template>
  <div style="margin-bottom: 8px;">
    <div v-if="!editing" style="font-size: 12px; line-height: 1.5; color: var(--text-secondary); cursor: pointer; padding: 4px 6px; border-radius: 3px; background: var(--bg-primary); min-height: 24px;" @click="$emit('start-edit', character)">
      {{ character.design_prompt || 'Click to add design prompt...' }}
    </div>
    <div v-else>
      <textarea
        ref="textareaRef"
        :value="editText"
        @input="$emit('update:editText', ($event.target as HTMLTextAreaElement).value)"
        style="width: 100%; min-height: 60px; font-size: 12px; padding: 6px 8px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--accent-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary); line-height: 1.4;"
        placeholder="Describe the character's appearance..."
      ></textarea>
      <div style="display: flex; gap: 4px; margin-top: 4px;">
        <button class="btn btn-success" style="font-size: 11px; padding: 3px 8px;" @click="$emit('save', editText)" :disabled="saving">
          {{ saving ? 'Saving...' : 'Save' }}
        </button>
        <button class="btn" style="font-size: 11px; padding: 3px 8px; color: var(--accent-primary);" @click="$emit('save-regenerate', editText)" :disabled="saving">
          Save & Regenerate
        </button>
        <button class="btn" style="font-size: 11px; padding: 3px 8px;" @click="$emit('cancel')">
          Cancel
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Character } from '@/types'

const props = defineProps<{
  character: Character
  editing: boolean
  editText: string
  saving: boolean
}>()

defineEmits<{
  (e: 'start-edit', character: Character): void
  (e: 'cancel'): void
  (e: 'save', text: string): void
  (e: 'save-regenerate', text: string): void
  (e: 'update:editText', text: string): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)

watch(() => props.editing, (val) => {
  if (val) {
    setTimeout(() => textareaRef.value?.focus(), 50)
  }
})
</script>
