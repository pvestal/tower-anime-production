<template>
  <div class="storyboard-grid-wrapper">
    <!-- Top bar -->
    <div class="storyboard-topbar">
      <span class="topbar-title">Storyboard</span>
      <span class="topbar-count">{{ shots.length }} shots</span>
      <div style="flex: 1;"></div>
      <button
        v-if="selectedIndices.size > 0"
        class="btn btn-sm"
        @click="emit('batch-regen', [...selectedIndices])"
      >Regen selected ({{ selectedIndices.size }})</button>
      <button
        class="btn btn-sm btn-keyframe"
        :disabled="keyframeBlitzBusy"
        @click="emit('keyframe-blitz')"
      >{{ keyframeBlitzBusy ? 'Keyframing...' : 'Keyframe All' }}</button>
      <button class="btn btn-sm" @click="emit('add-shot')">+ Shot</button>
    </div>

    <!-- Grid -->
    <div class="storyboard-grid">
      <div
        v-for="(shot, idx) in shots"
        :key="shot.id || idx"
        class="grid-tile"
        :class="{ selected: selectedShotIdx === idx }"
        @click="emit('select-shot', idx)"
      >
        <!-- Batch checkbox -->
        <input
          type="checkbox"
          class="tile-checkbox"
          :checked="selectedIndices.has(idx)"
          @click.stop="toggleBatchSelect(idx)"
        />

        <!-- Thumbnail -->
        <div class="tile-thumb">
          <img
            v-if="shot.source_image_path"
            :src="sourceImageUrl(shot.source_image_path)"
            @error="($event.target as HTMLImageElement).style.display = 'none'"
          />
          <div v-else class="tile-placeholder">
            <span>{{ shot.shot_number }}</span>
          </div>
        </div>

        <!-- Info bar -->
        <div class="tile-info">
          <span class="tile-shot-num">#{{ shot.shot_number }}</span>
          <span class="tile-duration">{{ shot.duration_seconds || 3 }}s</span>
          <span class="tile-engine" :class="engineClass(shot.video_engine)">
            {{ engineLabel(shot.video_engine) }}
          </span>
        </div>

        <!-- Status chip -->
        <div class="tile-status">
          <span class="status-badge" :class="statusClass(shot.status || 'pending')">
            {{ shot.status || 'pending' }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { BuilderShot } from '@/types'

const props = defineProps<{
  shots: Partial<BuilderShot>[]
  selectedShotIdx: number
  sourceImageUrl: (path: string) => string
  keyframeBlitzBusy?: boolean
}>()

const emit = defineEmits<{
  'select-shot': [idx: number]
  'add-shot': []
  'batch-regen': [indices: number[]]
  'keyframe-blitz': []
}>()

const selectedIndices = ref(new Set<number>())

function toggleBatchSelect(idx: number) {
  const next = new Set(selectedIndices.value)
  if (next.has(idx)) {
    next.delete(idx)
  } else {
    next.add(idx)
  }
  selectedIndices.value = next
}

function engineLabel(engine?: string | null): string {
  const map: Record<string, string> = {
    framepack: 'FP',
    framepack_f1: 'F1',
    wan: 'Wan',
    wan22: 'W22',
    wan22_14b: '14B',
    ltx: 'LTX',
    reference_v2v: 'V2V',
  }
  return map[engine || ''] || engine || 'FP'
}

function engineClass(engine?: string | null): string {
  if (!engine || engine.startsWith('framepack')) return 'engine-fp'
  if (engine.startsWith('wan22')) return 'engine-wan22'
  if (engine === 'wan') return 'engine-wan'
  return 'engine-other'
}

function statusClass(status: string): string {
  if (status === 'completed') return 'status-completed'
  if (status === 'generating') return 'status-generating'
  if (status === 'failed') return 'status-failed'
  return 'status-pending'
}
</script>

<style scoped>
.storyboard-grid-wrapper {
  flex: 1;
  min-width: 400px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.storyboard-topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.topbar-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-primary);
}

.topbar-count {
  font-size: 11px;
  color: var(--text-muted);
}

.btn-sm {
  font-size: 11px;
  padding: 4px 10px;
}

.btn-keyframe {
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary, #7aa2f7);
  border: 1px solid rgba(122, 162, 247, 0.3);
}

.btn-keyframe:disabled {
  opacity: 0.5;
  cursor: wait;
}

.storyboard-grid {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  align-content: start;
}

.grid-tile {
  position: relative;
  border: 2px solid var(--border-primary);
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 100ms, box-shadow 100ms;
  background: var(--bg-secondary);
}

.grid-tile:hover {
  border-color: var(--text-muted);
}

.grid-tile.selected {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 1px var(--accent-primary);
}

.tile-checkbox {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 2;
  accent-color: var(--accent-primary);
}

.tile-thumb {
  width: 100%;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: var(--bg-tertiary);
}

.tile-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tile-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 20px;
  font-weight: 600;
}

.tile-info {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  font-size: 11px;
}

.tile-shot-num {
  font-weight: 600;
  color: var(--text-primary);
}

.tile-duration {
  color: var(--text-muted);
}

.tile-engine {
  margin-left: auto;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.engine-fp {
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary, #7aa2f7);
}

.engine-wan22 {
  background: rgba(187, 154, 247, 0.15);
  color: #bb9af7;
}

.engine-wan {
  background: rgba(224, 175, 104, 0.15);
  color: #e0af68;
}

.engine-other {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.tile-status {
  padding: 0 8px 6px;
}

.status-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.status-pending {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.status-completed {
  background: rgba(80, 160, 80, 0.2);
  color: var(--status-success, #4caf50);
}

.status-generating {
  background: rgba(122, 162, 247, 0.2);
  color: var(--accent-primary, #7aa2f7);
}

.status-failed {
  background: rgba(160, 80, 80, 0.2);
  color: var(--status-error, #f44336);
}
</style>
