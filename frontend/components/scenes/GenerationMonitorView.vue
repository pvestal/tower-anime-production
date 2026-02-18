<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <span style="font-size: 16px; font-weight: 500;">Generating: {{ sceneTitle }}</span>
        <span style="margin-left: 12px; font-size: 13px; color: var(--text-muted);">
          {{ monitorStatus?.completed_shots || 0 }}/{{ monitorStatus?.total_shots || 0 }} shots
        </span>
      </div>
      <button class="btn" @click="$emit('back')">Back</button>
    </div>

    <!-- Overall progress bar -->
    <div v-if="monitorStatus" style="margin-bottom: 24px;">
      <div style="height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden;">
        <div
          :style="{
            width: overallProgress + '%',
            height: '100%',
            background: monitorStatus.generation_status === 'failed' ? 'var(--status-error)' : 'var(--accent-primary)',
            transition: 'width 0.5s ease',
          }"
        ></div>
      </div>
      <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 12px; color: var(--text-muted);">
        <span>{{ Math.round(overallProgress) }}%</span>
        <span>{{ monitorStatus.generation_status }}</span>
      </div>
    </div>

    <!-- Shot list with statuses -->
    <div style="display: flex; flex-direction: column; gap: 12px;">
      <div
        v-for="shot in monitorStatus?.shots || []"
        :key="shot.id"
        class="card"
        :style="{
          borderLeft: shot.status === 'completed' ? '3px solid var(--status-success)'
            : shot.status === 'generating' ? '3px solid var(--accent-primary)'
            : shot.status === 'failed' ? '3px solid var(--status-error)'
            : '3px solid var(--border-primary)',
        }"
      >
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <span style="font-weight: 500;">Shot {{ shot.shot_number }}</span>
            <span :class="statusBadgeClass(shot.status)" style="margin-left: 8px; font-size: 11px; padding: 2px 8px; border-radius: 3px;">
              {{ shot.status === 'generating' ? 'generating...' : shot.status }}
            </span>
            <span v-if="shot.generation_time_seconds" style="margin-left: 8px; font-size: 11px; color: var(--text-muted);">
              {{ Math.round(shot.generation_time_seconds / 60) }}min
            </span>
            <span v-if="shot.quality_score" style="margin-left: 8px; font-size: 11px; color: var(--text-muted);">
              Q:{{ shot.quality_score.toFixed(2) }}
            </span>
          </div>
          <div>
            <button
              v-if="shot.status === 'failed'"
              class="btn" style="font-size: 11px; padding: 2px 8px;"
              @click="$emit('retry-shot', shot)"
            >Retry</button>
            <button
              v-if="shot.output_video_path"
              class="btn" style="font-size: 11px; padding: 2px 8px; margin-left: 4px;"
              @click="$emit('play-shot', shot)"
            >Play</button>
          </div>
        </div>
        <div v-if="shot.motion_prompt" style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
          {{ shot.motion_prompt }}
        </div>
        <div v-if="shot.error_message" style="font-size: 12px; color: var(--status-error); margin-top: 4px;">
          {{ shot.error_message }}
        </div>
      </div>
    </div>

    <!-- Video preview -->
    <div v-if="monitorStatus?.final_video_path" class="card" style="margin-top: 24px;">
      <div style="font-size: 13px; font-weight: 500; margin-bottom: 8px;">Scene Preview</div>
      <video
        :src="sceneVideoSrc"
        controls autoplay
        style="max-width: 100%; border-radius: 4px;"
      ></video>
      <div v-if="monitorStatus.actual_duration_seconds" style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
        Duration: {{ monitorStatus.actual_duration_seconds.toFixed(1) }}s
      </div>
    </div>

    <!-- Assemble button when partial -->
    <div v-if="monitorStatus?.generation_status === 'partial' || monitorStatus?.generation_status === 'completed'" style="margin-top: 16px;">
      <button class="btn btn-primary" @click="$emit('reassemble')">Re-assemble Video</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SceneGenerationStatus } from '@/types'

const props = defineProps<{
  sceneTitle: string
  monitorStatus: SceneGenerationStatus | null
  sceneVideoSrc: string
}>()

defineEmits<{
  back: []
  'retry-shot': [shot: { id: string }]
  'play-shot': [shot: { id: string }]
  reassemble: []
}>()

const overallProgress = computed(() => {
  if (!props.monitorStatus) return 0
  const total = props.monitorStatus.total_shots || 1
  const completed = props.monitorStatus.completed_shots || 0
  return (completed / total) * 100
})

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    draft: 'badge-draft',
    pending: 'badge-draft',
    generating: 'badge-generating',
    completed: 'badge-completed',
    partial: 'badge-partial',
    failed: 'badge-failed',
  }
  return map[status] || 'badge-draft'
}
</script>

<style scoped>
.badge-draft {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.badge-generating {
  background: rgba(122, 162, 247, 0.2);
  color: var(--accent-primary);
}
.badge-completed {
  background: rgba(80, 160, 80, 0.2);
  color: var(--status-success);
}
.badge-partial {
  background: rgba(160, 128, 80, 0.2);
  color: var(--status-warning);
}
.badge-failed {
  background: rgba(160, 80, 80, 0.2);
  color: var(--status-error);
}
</style>
