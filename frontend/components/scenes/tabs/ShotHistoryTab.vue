<template>
  <div>
    <!-- Video Player -->
    <div v-if="shot.output_video_path" class="field-group">
      <label class="field-label">Latest Render</label>
      <video
        :src="shotVideoSrc"
        controls
        style="max-width: 100%; border-radius: 4px; border: 1px solid var(--border-primary);"
      ></video>
      <div style="display: flex; align-items: center; gap: 6px; margin-top: 6px;">
        <span v-if="shot.video_engine" class="source-badge" :class="engineBadgeClass">
          {{ shot.video_engine }}
        </span>
        <span v-if="shot.duration_seconds" style="font-size: 10px; color: var(--text-muted);">
          {{ shot.duration_seconds }}s
        </span>
        <span
          v-if="shot.quality_score != null"
          class="source-badge"
          :class="shot.quality_score >= 0.65 ? 'source-badge--good' : shot.quality_score >= 0.4 ? 'source-badge--ok' : 'source-badge--poor'"
        >{{ (shot.quality_score * 100).toFixed(0) }}% quality</span>
      </div>
    </div>

    <!-- No video yet -->
    <div v-else class="empty-state">
      <div class="empty-icon">&#9654;</div>
      <div class="empty-title">No render yet</div>
      <div class="empty-desc">Generate this shot to see the video here.</div>
    </div>

    <!-- Render History placeholder -->
    <div class="history-section">
      <div class="field-label" style="font-weight: 500;">Render History</div>
      <div class="empty-desc">
        Previous renders will appear here in a future update.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BuilderShot } from '@/types'

const props = defineProps<{
  shot: Partial<BuilderShot>
  shotVideoSrc: string
}>()

const engineBadgeClass = computed(() => {
  const eng = props.shot.video_engine || ''
  if (eng.startsWith('framepack')) return 'source-badge--good'
  if (eng.startsWith('wan22')) return 'source-badge--auto'
  if (eng === 'wan') return 'source-badge--ok'
  return 'source-badge--manual'
})
</script>

<style scoped>
.field-group { margin-bottom: 10px; }
.field-label { font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px; }
.source-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 500; }
.source-badge--auto { background: rgba(122, 162, 247, 0.15); color: var(--accent-primary); border: 1px solid rgba(122, 162, 247, 0.3); }
.source-badge--manual { background: rgba(160, 160, 160, 0.1); color: var(--text-secondary); border: 1px solid var(--border-primary); }
.source-badge--good { background: rgba(80, 200, 120, 0.15); color: #50c878; border: 1px solid rgba(80, 200, 120, 0.3); }
.source-badge--ok { background: rgba(240, 180, 60, 0.15); color: #f0b43c; border: 1px solid rgba(240, 180, 60, 0.3); }
.source-badge--poor { background: rgba(200, 80, 80, 0.15); color: #c85050; border: 1px solid rgba(200, 80, 80, 0.3); }
.empty-state { text-align: center; padding: 32px 16px; }
.empty-icon { font-size: 32px; color: var(--text-muted); margin-bottom: 8px; }
.empty-title { font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 4px; }
.empty-desc { font-size: 11px; color: var(--text-muted); }
.history-section { border-top: 1px solid var(--border-primary); padding-top: 10px; margin-top: 12px; }
</style>
