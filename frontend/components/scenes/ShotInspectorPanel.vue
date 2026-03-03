<template>
  <div v-if="shot" class="inspector-panel">
    <!-- Header -->
    <div class="inspector-header">
      <div style="font-size: 13px; font-weight: 500; color: var(--accent-primary);">
        Shot {{ shot.shot_number }}
      </div>
      <button class="btn btn-danger" style="font-size: 11px; padding: 2px 8px;" @click="$emit('remove')">Delete</button>
    </div>

    <!-- Tab buttons -->
    <div class="inspector-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="tab-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >{{ tab.label }}</button>
    </div>

    <!-- Tab content -->
    <div class="inspector-body">
      <ShotCreativeTab
        v-if="activeTab === 'creative'"
        :shot="shot"
        :source-image-url="sourceImageUrl"
        :characters="characters"
        :shot-video-src="shotVideoSrc"
        :auto-dialogue-busy="autoDialogueBusy"
        @update-field="(field: string, value: unknown) => $emit('update-field', field, value)"
        @browse-image="$emit('browse-image')"
        @auto-dialogue="$emit('auto-dialogue')"
      />
      <ShotTechnicalTab
        v-if="activeTab === 'technical'"
        :shot="shot"
        @update-field="(field: string, value: unknown) => $emit('update-field', field, value)"
      />
      <ShotHistoryTab
        v-if="activeTab === 'history'"
        :shot="shot"
        :shot-video-src="shotVideoSrc"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { BuilderShot } from '@/types'
import ShotCreativeTab from './tabs/ShotCreativeTab.vue'
import ShotTechnicalTab from './tabs/ShotTechnicalTab.vue'
import ShotHistoryTab from './tabs/ShotHistoryTab.vue'

defineProps<{
  shot: Partial<BuilderShot> | null
  shotVideoSrc: string
  sourceImageUrl: (path: string) => string
  characters: { slug: string; name: string }[]
  autoDialogueBusy?: boolean
}>()

defineEmits<{
  remove: []
  'browse-image': []
  'update-field': [field: string, value: unknown]
  'auto-dialogue': []
}>()

const tabs = [
  { id: 'creative', label: 'Creative' },
  { id: 'technical', label: 'Technical' },
  { id: 'history', label: 'History' },
]

const activeTab = ref('creative')
</script>

<style scoped>
.inspector-panel {
  width: 360px;
  flex-shrink: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border-primary);
  background: var(--bg-secondary);
}

.inspector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.inspector-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.tab-btn {
  flex: 1;
  padding: 8px 0;
  font-size: 12px;
  font-family: var(--font-primary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 150ms, border-color 150ms;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-primary);
}

.inspector-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
</style>
