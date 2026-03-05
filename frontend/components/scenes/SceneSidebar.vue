<template>
  <div class="scene-sidebar">
    <!-- Project selector -->
    <div class="sidebar-section">
      <select
        class="sidebar-select"
        :value="store.selectedProjectId"
        @change="onProjectChange"
      >
        <option :value="0" disabled>Select project...</option>
        <option v-for="p in store.projects" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
    </div>

    <!-- Generation Mode Toggle -->
    <div v-if="store.selectedProjectId" class="sidebar-section mode-toggle-section">
      <div class="mode-toggle">
        <button
          class="mode-btn"
          :class="{ active: generationMode === 'autopilot' }"
          @click="setMode('autopilot')"
          title="AI enriches shots, enforces variety, consults advisor"
        >Autopilot</button>
        <button
          class="mode-btn"
          :class="{ active: generationMode === 'direct' }"
          @click="setMode('direct')"
          title="You steer, AI suggests on HUD only"
        >Direct</button>
      </div>
    </div>

    <!-- Actions -->
    <div v-if="store.selectedProjectId" class="sidebar-section" style="padding: 8px 12px;">
      <button class="btn btn-primary btn-sm" style="width: 100%;" @click="store.openNewScene">
        + New Scene
      </button>
    </div>

    <!-- Scene list -->
    <div class="scene-list">
      <div v-if="store.loading" style="padding: 16px 12px; color: var(--text-muted); font-size: 12px;">
        Loading scenes...
      </div>
      <div v-else-if="store.scenes.length === 0 && store.selectedProjectId" style="padding: 16px 12px; color: var(--text-muted); font-size: 12px;">
        No scenes yet
      </div>
      <div
        v-for="(scene, idx) in store.scenes"
        :key="scene.id"
        class="scene-item"
        :class="{ active: store.editSceneId === scene.id }"
        @click="store.openEditor(scene)"
      >
        <div class="scene-item-header">
          <span class="scene-number">{{ idx + 1 }}</span>
          <span class="scene-title">{{ scene.title }}</span>
          <span class="scene-shot-count" :title="`${scene.total_shots} shots`">
            {{ scene.total_shots }}
          </span>
        </div>
        <div v-if="scene.generation_status && scene.generation_status !== 'draft'" class="scene-status">
          <span
            class="status-chip"
            :class="statusClass(scene.generation_status)"
          >{{ scene.generation_status }}</span>
        </div>
        <!-- Shot sub-list (collapsed unless this scene is active) -->
        <div v-if="store.editSceneId === scene.id && store.editShots.length > 0" class="shot-sublist">
          <div
            v-for="(shot, shotIdx) in store.editShots"
            :key="shot.id || shotIdx"
            class="shot-subitem"
            :class="{ active: store.selectedShotIdx === shotIdx }"
            @click.stop="store.selectShot(shotIdx)"
          >
            <span class="shot-num">{{ shot.shot_number }}</span>
            <span class="shot-type">{{ shot.shot_type || 'medium' }}</span>
            <span v-if="shot.status === 'completed'" class="shot-done">done</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useSceneEditorStore } from '@/stores/sceneEditor'

const store = useSceneEditorStore()
const generationMode = ref<'autopilot' | 'direct'>('autopilot')

function onProjectChange(e: Event) {
  const val = Number((e.target as HTMLSelectElement).value)
  store.selectedProjectId = val
}

async function setMode(mode: 'autopilot' | 'direct') {
  generationMode.value = mode
  // Persist to backend
  if (store.selectedProjectId) {
    try {
      await fetch(`/anime-studio/api/projects/${store.selectedProjectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ generation_mode: mode }),
      })
    } catch {
      // Non-critical
    }
  }
}

// Load mode from scene data when project changes
watch(() => store.editScene, (scene) => {
  if (scene?.generation_mode) {
    generationMode.value = scene.generation_mode as 'autopilot' | 'direct'
  }
}, { immediate: true })

function statusClass(status: string) {
  if (status === 'completed') return 'status-success'
  if (status === 'generating') return 'status-active'
  if (status === 'failed') return 'status-error'
  return ''
}
</script>

<style scoped>
.scene-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-primary);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.sidebar-section {
  border-bottom: 1px solid var(--border-primary);
}

.sidebar-select {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: none;
  border-bottom: 1px solid var(--border-primary);
  font-size: 13px;
  font-family: var(--font-primary);
  outline: none;
  cursor: pointer;
}

.sidebar-select:focus {
  background: var(--bg-hover);
}

.mode-toggle-section {
  padding: 6px 12px;
}

.mode-toggle {
  display: flex;
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  overflow: hidden;
}

.mode-btn {
  flex: 1;
  padding: 5px 0;
  font-size: 11px;
  font-family: var(--font-primary);
  border: none;
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 150ms, color 150ms;
}

.mode-btn:first-child {
  border-right: 1px solid var(--border-primary);
}

.mode-btn:hover {
  background: var(--bg-hover);
}

.mode-btn.active {
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary);
  font-weight: 500;
}

.btn-sm {
  font-size: 12px;
  padding: 6px 12px;
}

.scene-list {
  flex: 1;
  overflow-y: auto;
}

.scene-item {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-primary);
  cursor: pointer;
  transition: background 100ms;
}

.scene-item:hover {
  background: var(--bg-hover);
}

.scene-item.active {
  background: var(--bg-tertiary);
  border-left: 3px solid var(--accent-primary);
  padding-left: 9px;
}

.scene-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.scene-number {
  font-size: 11px;
  color: var(--text-muted);
  min-width: 16px;
}

.scene-title {
  flex: 1;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.scene-shot-count {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 8px;
}

.scene-status {
  margin-top: 4px;
}

.status-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.status-success {
  background: rgba(76, 175, 80, 0.15);
  color: var(--status-success, #4caf50);
}

.status-active {
  background: rgba(33, 150, 243, 0.15);
  color: var(--accent-primary, #2196f3);
}

.status-error {
  background: rgba(244, 67, 54, 0.15);
  color: var(--status-error, #f44336);
}

.shot-sublist {
  margin-top: 6px;
  padding-left: 8px;
  border-left: 1px solid var(--border-primary);
  margin-left: 8px;
}

.shot-subitem {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
}

.shot-subitem:hover {
  background: var(--bg-hover);
}

.shot-subitem.active {
  background: rgba(var(--accent-primary-rgb, 33, 150, 243), 0.15);
  color: var(--accent-primary);
}

.shot-num {
  font-size: 10px;
  color: var(--text-muted);
  min-width: 14px;
}

.shot-type {
  flex: 1;
}

.shot-done {
  font-size: 10px;
  color: var(--status-success, #4caf50);
}
</style>
