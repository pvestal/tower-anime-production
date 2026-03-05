<template>
  <div class="character-editor">
    <!-- Character selector -->
    <div class="selector-row">
      <select
        class="char-select"
        :value="selectedSlug"
        @change="$emit('select', ($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>Select character...</option>
        <option
          v-for="c in characters"
          :key="c.slug"
          :value="c.slug"
        >
          {{ c.name }} ({{ c.project_name }})
        </option>
      </select>
    </div>

    <template v-if="character">
      <!-- Body part nav -->
      <BodyPartNav v-model="activePart" />

      <!-- Editor fields -->
      <div class="editor-body">
        <EditorSection
          :part="activePart"
          :appearance="appearance"
          :character="character"
          @update:appearance="handleAppearanceUpdate"
          @update:identity="handleIdentityUpdate"
        />
      </div>

      <!-- Design prompt preview -->
      <div class="prompt-section">
        <button class="prompt-toggle" @click="showPrompt = !showPrompt">
          <span class="toggle-icon" :class="{ open: showPrompt }">&#x25B6;</span>
          Design Prompt
        </button>
        <transition name="collapse">
          <div v-if="showPrompt" class="prompt-content">
            {{ character.design_prompt || 'No design prompt set' }}
          </div>
        </transition>
      </div>

      <!-- Save bar -->
      <transition name="slide-up">
        <div v-if="dirty" class="save-bar">
          <span class="save-label">Unsaved changes</span>
          <button class="save-btn" :disabled="saving" @click="$emit('save')">
            {{ saving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </transition>
    </template>

    <div v-else class="empty-state">
      Select a character to begin editing
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Character, AppearanceData } from '@/types'
import type { BodyPart } from '@/stores/characterViewer'
import BodyPartNav from './BodyPartNav.vue'
import EditorSection from './EditorSection.vue'

defineProps<{
  characters: { name: string; slug: string; project_name: string }[]
  selectedSlug: string
  character: Character | null
  appearance: AppearanceData
  dirty: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  select: [slug: string]
  save: []
  'update:appearance': [path: string, value: any]
  'update:identity': [field: string, value: any]
}>()

const activePart = defineModel<BodyPart>('activePart', { required: true })
const showPrompt = ref(false)

function handleAppearanceUpdate(path: string, value: any) {
  emit('update:appearance', path, value)
}

function handleIdentityUpdate(field: string, value: any) {
  emit('update:identity', field, value)
}
</script>

<style scoped>
.character-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.selector-row {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.char-select {
  width: 100%;
  padding: 10px 12px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px;
  color: var(--text-primary, #e8e8e8);
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23888' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
}

.char-select:focus {
  outline: none;
  border-color: rgba(99,102,241,0.5);
}

.char-select option {
  background: #1a1a2e;
  color: #e8e8e8;
}

.editor-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.1) transparent;
}

/* Prompt section */
.prompt-section {
  padding: 0 16px 12px;
}

.prompt-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  color: var(--text-muted, #888);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  cursor: pointer;
  padding: 6px 0;
  font-family: inherit;
}

.toggle-icon {
  font-size: 9px;
  transition: transform 0.2s ease;
}

.toggle-icon.open {
  transform: rotate(90deg);
}

.prompt-content {
  padding: 10px 12px;
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
  color: var(--text-muted, #aaa);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  max-height: 120px;
  overflow-y: auto;
}

/* Save bar */
.save-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: rgba(99,102,241,0.08);
  border-top: 1px solid rgba(99,102,241,0.2);
}

.save-label {
  font-size: 12px;
  color: var(--accent-primary, #6366f1);
}

.save-btn {
  padding: 6px 20px;
  background: var(--accent-primary, #6366f1);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: opacity 0.2s ease;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.save-btn:hover:not(:disabled) {
  opacity: 0.9;
}

/* Empty state */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #666);
  font-size: 14px;
}

/* Transitions */
.collapse-enter-active,
.collapse-leave-active {
  transition: opacity 0.2s ease, max-height 0.25s ease;
  overflow: hidden;
}
.collapse-enter-from,
.collapse-leave-to {
  opacity: 0;
  max-height: 0 !important;
}
.collapse-enter-to {
  max-height: 120px;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
