<template>
  <div>
    <div v-if="!hasProject" style="color: var(--text-muted); font-size: 13px;">
      Select a project to view scenes.
    </div>

    <!-- Generate from story button -->
    <div v-if="hasProject && scenes.length === 0 && !loading" style="margin-bottom: 16px;">
      <button
        class="btn btn-primary"
        style="font-size: 12px; padding: 6px 14px;"
        :disabled="generatingFromStory"
        @click="$emit('generate-from-story')"
      >
        {{ generatingFromStory ? 'Generating...' : 'Generate Scenes from Story' }}
      </button>
      <span style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">
        Uses AI to break your storyline into production-ready scenes
      </span>
    </div>
    <div v-else-if="loading" style="color: var(--text-muted); font-size: 13px;">Loading scenes...</div>
    <div v-else-if="scenes.length === 0" style="color: var(--text-muted); font-size: 13px;">
      No scenes yet. Click "+ New Scene" to create one.
    </div>

    <!-- Grouped by episode -->
    <div v-else>
      <div v-for="group in episodeGroups" :key="group.key" class="episode-group">
        <div class="episode-group-header" @click="toggleGroup(group.key)">
          <span class="group-chevron" :class="{ open: openGroups[group.key] }">&#9656;</span>
          <span class="group-title">{{ group.label }}</span>
          <span class="group-meta">{{ group.scenes.length }} scene{{ group.scenes.length !== 1 ? 's' : '' }}</span>
          <div class="group-progress">
            <div class="progress-bar">
              <div class="progress-fill progress-done" :style="{ width: group.donePercent + '%' }"></div>
              <div class="progress-fill progress-generating" :style="{ width: group.genPercent + '%', left: group.donePercent + '%' }"></div>
            </div>
            <span class="progress-label">{{ group.doneCount }}/{{ group.scenes.length }}</span>
          </div>
        </div>

        <div v-if="openGroups[group.key]" class="episode-group-body">
          <div
            v-for="scene in group.scenes"
            :key="scene.id"
            class="scene-row"
            @click="$emit('edit', scene)"
          >
            <span class="scene-number">{{ scene.scene_number ?? '—' }}</span>
            <div class="scene-info">
              <span class="scene-title">{{ scene.title }}</span>
              <span v-if="scene.description" class="scene-desc">{{ scene.description }}</span>
            </div>
            <div class="scene-stats">
              <span v-if="scene.location" class="stat-pill">{{ scene.location }}</span>
              <span class="stat-pill">{{ scene.total_shots }} shot{{ scene.total_shots !== 1 ? 's' : '' }}</span>
              <span v-if="scene.actual_duration_seconds" class="stat-pill">{{ scene.actual_duration_seconds.toFixed(1) }}s</span>
            </div>
            <!-- Training readiness -->
            <div v-if="gapBySceneId?.[scene.id]" class="scene-chars">
              <span
                v-for="ch in gapBySceneId[scene.id].characters"
                :key="ch.slug"
                :class="ch.has_lora ? 'char-pill-ready' : 'char-pill-unready'"
                class="char-pill"
              >{{ ch.name }}</span>
            </div>
            <span :class="statusBadgeClass(scene.generation_status)" class="status-badge">
              {{ statusLabel(scene.generation_status) }}
            </span>
            <div class="scene-actions" @click.stop>
              <button
                v-if="scene.generation_status === 'generating'"
                class="action-icon" title="Monitor"
                @click="$emit('monitor', scene)"
              >&#9881;</button>
              <button
                v-if="scene.final_video_path"
                class="action-icon action-play" title="Play"
                @click="$emit('play', scene)"
              >&#9654;</button>
              <button
                class="action-icon action-delete" title="Delete"
                @click="$emit('delete', scene)"
              >&times;</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import type { BuilderScene, GapAnalysisScene } from '@/types'

const props = defineProps<{
  scenes: BuilderScene[]
  loading: boolean
  hasProject: boolean
  generatingFromStory?: boolean
  gapBySceneId?: Record<string, GapAnalysisScene>
}>()

defineEmits<{
  edit: [scene: BuilderScene]
  monitor: [scene: BuilderScene]
  play: [scene: BuilderScene]
  delete: [scene: BuilderScene]
  'generate-from-story': []
}>()

interface EpisodeGroup {
  key: string
  label: string
  scenes: BuilderScene[]
  doneCount: number
  donePercent: number
  genPercent: number
}

const openGroups = reactive<Record<string, boolean>>({})

function toggleGroup(key: string) {
  openGroups[key] = !openGroups[key]
}

const episodeGroups = computed<EpisodeGroup[]>(() => {
  const groups: Record<string, { label: string; epNum: number | null; scenes: BuilderScene[] }> = {}

  for (const scene of props.scenes) {
    const key = scene.episode_id || '__unlinked__'
    if (!groups[key]) {
      const label = scene.episode_number != null && scene.episode_title
        ? `Episode ${scene.episode_number} — ${scene.episode_title}`
        : scene.episode_title
          ? scene.episode_title
          : 'Unlinked Scenes'
      groups[key] = { label, epNum: scene.episode_number ?? null, scenes: [] }
      // Auto-open all groups on first render
      if (openGroups[key] === undefined) openGroups[key] = true
    }
    groups[key].scenes.push(scene)
  }

  return Object.entries(groups)
    .sort(([, a], [, b]) => (a.epNum ?? 999) - (b.epNum ?? 999))
    .map(([key, g]) => {
      const done = g.scenes.filter(s => s.generation_status === 'completed').length
      const gen = g.scenes.filter(s => s.generation_status === 'generating').length
      const total = g.scenes.length || 1
      return {
        key,
        label: g.label,
        scenes: g.scenes,
        doneCount: done,
        donePercent: (done / total) * 100,
        genPercent: (gen / total) * 100,
      }
    })
})

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    draft: 'badge-draft',
    pending: 'badge-pending',
    generating: 'badge-generating',
    completed: 'badge-completed',
    awaiting_review: 'badge-review',
    needs_regen: 'badge-warning',
    partial: 'badge-warning',
    failed: 'badge-failed',
  }
  return map[status] || 'badge-draft'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    draft: 'Draft',
    pending: 'Queued',
    generating: 'Generating',
    completed: 'Done',
    awaiting_review: 'Review',
    needs_regen: 'Needs Regen',
    partial: 'Partial',
    failed: 'Failed',
  }
  return map[status] || status
}
</script>

<style scoped>
.episode-group {
  margin-bottom: 4px;
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  overflow: hidden;
}

.episode-group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  cursor: pointer;
  user-select: none;
  transition: background 150ms;
}

.episode-group-header:hover {
  background: var(--bg-tertiary);
}

.group-chevron {
  font-size: 12px;
  color: var(--text-muted);
  transition: transform 200ms;
  display: inline-block;
}

.group-chevron.open {
  transform: rotate(90deg);
}

.group-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.group-meta {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.group-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 120px;
}

.progress-bar {
  position: relative;
  flex: 1;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 3px;
  transition: width 300ms ease;
}

.progress-done {
  background: var(--status-success);
  left: 0;
}

.progress-generating {
  background: var(--accent-primary);
  opacity: 0.7;
}

.progress-label {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  min-width: 28px;
  text-align: right;
}

.episode-group-body {
  border-top: 1px solid var(--border-primary);
}

.scene-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 100ms;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.scene-row:last-child {
  border-bottom: none;
}

.scene-row:hover {
  background: var(--bg-hover, rgba(255, 255, 255, 0.03));
}

.scene-number {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  min-width: 24px;
  text-align: center;
}

.scene-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.scene-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.scene-desc {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.scene-stats {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.stat-pill {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

.scene-chars {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.char-pill {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
}

.char-pill-ready {
  background: rgba(80, 160, 80, 0.15);
  color: var(--status-success);
}

.char-pill-unready {
  background: transparent;
  outline: 1px solid var(--status-error);
  color: var(--status-error);
}

.status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-draft { background: var(--bg-tertiary); color: var(--text-secondary); }
.badge-pending { background: rgba(160, 160, 80, 0.15); color: #b0b060; }
.badge-generating { background: rgba(122, 162, 247, 0.2); color: var(--accent-primary); }
.badge-completed { background: rgba(80, 160, 80, 0.2); color: var(--status-success); }
.badge-review { background: rgba(180, 140, 60, 0.2); color: #d0a830; }
.badge-warning { background: rgba(160, 128, 80, 0.2); color: var(--status-warning); }
.badge-failed { background: rgba(160, 80, 80, 0.2); color: var(--status-error); }

.scene-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.action-icon {
  background: none;
  border: 1px solid var(--border-primary);
  color: var(--text-muted);
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 150ms;
}

.action-icon:hover { border-color: var(--text-secondary); color: var(--text-primary); }
.action-play:hover { border-color: var(--status-success); color: var(--status-success); }
.action-delete:hover { border-color: var(--status-error); color: var(--status-error); }
</style>
