<template>
  <div>
    <!-- Shot Spec (AI Enrichment) -->
    <div class="spec-section">
      <div class="section-header">Shot Spec</div>

      <!-- Pose Type -->
      <div class="field-row">
        <div class="field-group">
          <label class="field-label">Pose</label>
          <div v-if="shot.pose_type" class="pose-badge">{{ shot.pose_type }}</div>
          <div v-else class="empty-hint">Not enriched yet</div>
        </div>
        <div class="field-group">
          <label class="field-label">Emotion</label>
          <div v-if="shot.emotional_beat" class="emotion-badge">{{ shot.emotional_beat }}</div>
          <div v-else class="empty-hint">--</div>
        </div>
      </div>

      <!-- Viewer Should Feel -->
      <div v-if="shot.viewer_should_feel" class="field-group">
        <label class="field-label">Viewer Should Feel</label>
        <div class="feeling-text">{{ shot.viewer_should_feel }}</div>
      </div>

      <!-- Pose Vocabulary -->
      <div v-if="shot.pose_vocabulary && shot.pose_vocabulary.length" class="field-group">
        <label class="field-label">Available Poses</label>
        <div class="pose-chips">
          <span
            v-for="pose in shot.pose_vocabulary"
            :key="pose"
            class="pose-chip"
            :class="{ 'pose-chip--active': pose === shot.pose_type }"
          >{{ pose }}</span>
        </div>
      </div>

      <!-- Must Differ From -->
      <div v-if="shot.must_differ_from && shot.must_differ_from.length" class="field-group">
        <label class="field-label">Must Differ From ({{ shot.must_differ_from.length }} shots)</label>
        <div class="differ-list">
          <span v-for="sid in shot.must_differ_from" :key="sid" class="differ-id">
            {{ sid.slice(0, 8) }}...
          </span>
        </div>
      </div>
    </div>

    <!-- Variety Score -->
    <div v-if="shot.review_feedback && isVarietyWarning" class="variety-section">
      <div class="section-header">
        <span>Variety Check</span>
        <span class="warning-badge">Warning</span>
      </div>
      <div class="variety-warning">
        {{ shot.review_feedback }}
      </div>
      <div class="variety-actions">
        <button class="btn btn-small" @click="$emit('update-field', 'pose_type', null)">
          Reset Pose
        </button>
        <button class="btn btn-small" @click="$emit('regenerate')">
          Regenerate
        </button>
      </div>
    </div>

    <!-- Quality Scores -->
    <div class="scores-section">
      <div class="section-header">Quality</div>

      <div v-if="shot.quality_score != null" class="score-grid">
        <div class="score-row">
          <span class="score-label">Overall (MHP)</span>
          <div class="score-bar-container">
            <div class="score-bar" :style="barStyle(shot.quality_score)" />
          </div>
          <span class="score-value" :class="scoreClass(shot.quality_score)">
            {{ (shot.quality_score * 100).toFixed(0) }}
          </span>
        </div>
      </div>

      <div v-else class="empty-state">
        <div class="empty-icon">--</div>
        <div class="empty-desc">Scores populate after generation + QC review.</div>
      </div>
    </div>

    <!-- Generation Info -->
    <div v-if="shot.status === 'completed'" class="gen-info-section">
      <div class="section-header">Generation</div>
      <div class="gen-grid">
        <div v-if="shot.video_engine" class="gen-item">
          <span class="gen-label">Engine</span>
          <span class="source-badge" :class="engineBadgeClass">{{ shot.video_engine }}</span>
        </div>
        <div v-if="shot.generation_time_seconds" class="gen-item">
          <span class="gen-label">Time</span>
          <span class="gen-value">{{ formatTime(shot.generation_time_seconds) }}</span>
        </div>
        <div v-if="shot.guidance_scale" class="gen-item">
          <span class="gen-label">CFG</span>
          <span class="gen-value">{{ shot.guidance_scale }}</span>
        </div>
        <div v-if="shot.steps" class="gen-item">
          <span class="gen-label">Steps</span>
          <span class="gen-value">{{ shot.steps }}</span>
        </div>
        <div v-if="shot.lora_name" class="gen-item">
          <span class="gen-label">LoRA</span>
          <span class="gen-value">{{ shot.lora_name }} @ {{ shot.lora_strength || 0.8 }}</span>
        </div>
        <div v-if="shot.seed" class="gen-item">
          <span class="gen-label">Seed</span>
          <span class="gen-value seed-value">{{ shot.seed }}</span>
        </div>
      </div>
    </div>

    <!-- Storyboard Notes -->
    <div v-if="shot.storyboard_notes" class="notes-section">
      <div class="section-header">Storyboard Notes</div>
      <div class="notes-text">{{ shot.storyboard_notes }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BuilderShot } from '@/types'

const props = defineProps<{
  shot: Partial<BuilderShot>
}>()

defineEmits<{
  'update-field': [field: string, value: unknown]
  'regenerate': []
}>()

const isVarietyWarning = computed(() => {
  const fb = props.shot?.review_feedback || ''
  return fb.toLowerCase().includes('variety') || fb.toLowerCase().includes('similarity')
})

const engineBadgeClass = computed(() => {
  const eng = props.shot?.video_engine || ''
  if (eng.startsWith('framepack')) return 'source-badge--good'
  if (eng.startsWith('wan22')) return 'source-badge--auto'
  if (eng === 'wan') return 'source-badge--ok'
  return 'source-badge--manual'
})

function barStyle(score: number | null | undefined) {
  const s = score ?? 0
  const pct = Math.min(100, Math.max(0, s * 100))
  const color = s >= 0.75 ? '#50c878' : s >= 0.5 ? '#f0b43c' : '#c85050'
  return { width: `${pct}%`, background: color }
}

function scoreClass(score: number | null | undefined) {
  const s = score ?? 0
  if (s >= 0.75) return 'score--good'
  if (s >= 0.5) return 'score--ok'
  return 'score--poor'
}

function formatTime(seconds: number | null | undefined) {
  if (!seconds) return '--'
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}
</script>

<style scoped>
.section-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.spec-section, .scores-section, .gen-info-section, .notes-section {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-primary);
}

.variety-section {
  margin-bottom: 14px;
  padding: 10px;
  background: rgba(240, 180, 60, 0.08);
  border: 1px solid rgba(240, 180, 60, 0.25);
  border-radius: 4px;
}

.variety-warning {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  line-height: 1.4;
}

.variety-actions {
  display: flex;
  gap: 6px;
}

.warning-badge {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
  background: rgba(240, 180, 60, 0.2);
  color: #f0b43c;
  border: 1px solid rgba(240, 180, 60, 0.4);
}

/* Pose */
.pose-badge {
  font-size: 12px;
  padding: 2px 8px;
  background: rgba(122, 162, 247, 0.12);
  color: var(--accent-primary);
  border: 1px solid rgba(122, 162, 247, 0.25);
  border-radius: 4px;
  display: inline-block;
}

.emotion-badge {
  font-size: 12px;
  padding: 2px 8px;
  background: rgba(200, 160, 255, 0.12);
  color: #c8a0ff;
  border: 1px solid rgba(200, 160, 255, 0.25);
  border-radius: 4px;
  display: inline-block;
}

.feeling-text {
  font-size: 11px;
  color: var(--text-secondary);
  font-style: italic;
  line-height: 1.4;
}

.pose-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.pose-chip {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
}

.pose-chip--active {
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary);
  border-color: rgba(122, 162, 247, 0.4);
  font-weight: 500;
}

.differ-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.differ-id {
  font-size: 10px;
  padding: 1px 6px;
  background: rgba(200, 80, 80, 0.08);
  color: var(--text-muted);
  border: 1px solid rgba(200, 80, 80, 0.2);
  border-radius: 4px;
  font-family: monospace;
}

/* Scores */
.score-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-label {
  font-size: 11px;
  color: var(--text-secondary);
  min-width: 80px;
}

.score-bar-container {
  flex: 1;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.score-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 300ms ease;
}

.score-value {
  font-size: 12px;
  font-weight: 600;
  min-width: 28px;
  text-align: right;
}

.score--good { color: #50c878; }
.score--ok { color: #f0b43c; }
.score--poor { color: #c85050; }

/* Generation info */
.gen-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 12px;
}

.gen-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}

.gen-label {
  color: var(--text-secondary);
  font-weight: 500;
  min-width: 40px;
}

.gen-value {
  color: var(--text-primary);
}

.seed-value {
  font-family: monospace;
  font-size: 10px;
}

/* Notes */
.notes-text {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Shared */
.field-group { margin-bottom: 8px; }
.field-label { font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 3px; }
.field-row { display: flex; gap: 8px; }
.field-row .field-group { flex: 1; }
.empty-hint { font-size: 11px; color: var(--text-muted); }
.empty-state { text-align: center; padding: 16px 8px; }
.empty-icon { font-size: 18px; color: var(--text-muted); margin-bottom: 4px; }
.empty-desc { font-size: 11px; color: var(--text-muted); }
.btn-small { font-size: 10px; padding: 3px 8px; }
.source-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 500; }
.source-badge--auto { background: rgba(122, 162, 247, 0.15); color: var(--accent-primary); border: 1px solid rgba(122, 162, 247, 0.3); }
.source-badge--manual { background: rgba(160, 160, 160, 0.1); color: var(--text-secondary); border: 1px solid var(--border-primary); }
.source-badge--good { background: rgba(80, 200, 120, 0.15); color: #50c878; border: 1px solid rgba(80, 200, 120, 0.3); }
.source-badge--ok { background: rgba(240, 180, 60, 0.15); color: #f0b43c; border: 1px solid rgba(240, 180, 60, 0.3); }
</style>
