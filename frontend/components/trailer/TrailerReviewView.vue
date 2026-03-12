<template>
  <div class="trailer-review">
    <!-- Project selector -->
    <div class="toolbar">
      <select v-model="selectedProjectId" class="field-input project-select">
        <option :value="null" disabled>Select project...</option>
        <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>

      <button v-if="selectedProjectId" class="btn btn-sm" @click="createNew" :disabled="creating">
        + New Trailer
      </button>
    </div>

    <!-- Trailer list for selected project -->
    <div v-if="trailerStore.trailers.length" class="trailer-list">
      <button
        v-for="t in trailerStore.trailers" :key="t.id"
        class="trailer-chip"
        :class="{ active: selectedTrailerId === t.id }"
        @click="selectTrailer(t.id)"
      >
        v{{ t.version }}
        <span class="chip-status" :class="t.status">{{ t.status }}</span>
        <span class="chip-shots">{{ t.completed_shots }}/{{ t.shot_count }}</span>
      </button>
    </div>

    <div v-if="!selectedTrailerId" class="empty-state">
      Select a project to review trailers
    </div>

    <!-- Scorecard -->
    <template v-if="scorecard">
      <!-- Verdict banner -->
      <div class="verdict-banner" :class="scorecard.overall_pass ? 'pass' : 'fail'">
        <span class="verdict-label">{{ scorecard.overall_pass ? 'PASS' : 'FAIL' }}</span>
        <span class="verdict-detail">
          {{ scorecard.pass_count }} passed, {{ scorecard.fail_count }} failed, {{ scorecard.skip_count }} pending
        </span>
      </div>

      <!-- Dimension cards -->
      <div class="dimensions">
        <div
          v-for="d in scorecard.dimensions" :key="d.key"
          class="dim-card"
          :class="{ pass: d.passed, fail: !d.passed && d.score !== null, pending: !d.passed && d.score === null }"
        >
          <div class="dim-header">
            <span class="dim-icon">{{ d.passed ? '✓' : d.score === null ? '—' : '✗' }}</span>
            <span class="dim-name">{{ d.name }}</span>
            <span v-if="d.score !== null" class="dim-score">{{ d.score }}/10</span>
          </div>
          <div class="dim-details">{{ d.details }}</div>
          <div v-if="d.recommendation" class="dim-rec">{{ d.recommendation }}</div>
        </div>
      </div>

      <!-- Recommendations -->
      <div v-if="scorecard.recommendations.length" class="rec-section">
        <h3>Fix These</h3>
        <div v-for="(rec, i) in scorecard.recommendations" :key="i" class="rec-item">
          {{ rec }}
        </div>
      </div>

      <!-- Shot grid -->
      <h3>Shots</h3>
      <div class="shot-grid">
        <div v-for="shot in scorecard.shot_scores" :key="shot.shot_id" class="shot-card">
          <!-- Video preview -->
          <div class="shot-preview">
            <video
              v-if="shotVideoUrl(shot)"
              :src="shotVideoUrl(shot) ?? undefined"
              muted loop preload="metadata"
              @mouseenter="($event.target as HTMLVideoElement)?.play()"
              @mouseleave="($event.target as HTMLVideoElement)?.pause()"
            />
            <div v-else class="no-video">
              {{ shot.has_keyframe ? 'No video' : 'No keyframe' }}
            </div>
            <span class="role-badge">{{ shot.role }}</span>
          </div>

          <!-- Scores -->
          <div class="shot-meta">
            <div class="shot-number">#{{ shot.shot_number }}</div>
            <div class="shot-status" :class="shot.status">{{ shot.status }}</div>
          </div>

          <div v-if="shot.quality_score != null" class="score-bars">
            <div v-if="shot.character_match != null" class="score-row">
              <span class="score-label">Char</span>
              <div class="score-bar">
                <div class="score-fill" :style="barStyle(shot.character_match)" />
              </div>
              <span class="score-val">{{ shot.character_match.toFixed(1) }}</span>
            </div>
            <div v-if="shot.motion_execution != null" class="score-row">
              <span class="score-label">Motion</span>
              <div class="score-bar">
                <div class="score-fill" :style="barStyle(shot.motion_execution)" />
              </div>
              <span class="score-val">{{ shot.motion_execution.toFixed(1) }}</span>
            </div>
            <div v-if="shot.composition != null" class="score-row">
              <span class="score-label">Comp</span>
              <div class="score-bar">
                <div class="score-fill" :style="barStyle(shot.composition)" />
              </div>
              <span class="score-val">{{ shot.composition.toFixed(1) }}</span>
            </div>
          </div>

          <!-- Issues -->
          <div v-if="shot.issues.length" class="shot-issues">
            <span v-for="issue in shot.issues.slice(0, 3)" :key="issue" class="issue-chip">
              {{ issue.replace(/_/g, ' ') }}
            </span>
          </div>

          <!-- LoRA info -->
          <div v-if="shot.lora_name || shot.image_lora" class="shot-lora">
            <span v-if="shot.image_lora" class="lora-chip img">{{ shortLora(shot.image_lora) }}</span>
            <span v-if="shot.lora_name" class="lora-chip vid">{{ shortLora(shot.lora_name) }}</span>
            <span v-if="shot.motion_tier" class="tier-chip">{{ shot.motion_tier }}</span>
          </div>

          <!-- Actions -->
          <div class="shot-actions">
            <button class="btn btn-xs" @click="doAction(shot.shot_id, 'regenerate')" title="Regenerate">
              Regen
            </button>
            <button class="btn btn-xs" @click="doAction(shot.shot_id, 'new_seed')" title="New seed">
              Seed
            </button>
            <button class="btn btn-xs" @click="doAction(shot.shot_id, 'bump_tier')" title="Bump motion tier">
              Tier+
            </button>
          </div>
        </div>
      </div>

      <!-- Footer actions -->
      <div class="footer-actions">
        <button class="btn" @click="refreshScore" :disabled="refreshing">
          {{ refreshing ? 'Scoring...' : 'Rescore' }}
        </button>
        <button
          class="btn btn-primary"
          @click="approve"
          :disabled="!scorecard.overall_pass"
          :title="scorecard.overall_pass ? 'Approve and unlock production' : 'Fix failed dimensions first'"
        >
          Approve Trailer
        </button>
      </div>
    </template>

    <!-- No scorecard yet but trailer selected -->
    <div v-else-if="selectedTrailerId && !scorecard && !trailerStore.loading" class="empty-state">
      <p>No scorecard yet.</p>
      <button class="btn btn-primary" @click="refreshScore">Score This Trailer</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useTrailerStore } from '@/stores/trailer'
import { useProjectStore } from '@/stores/project'
import { trailersApi } from '@/api/trailers'

const trailerStore = useTrailerStore()
const projectStore = useProjectStore()

const selectedProjectId = ref<number | null>(null)
const selectedTrailerId = ref<string | null>(null)
const creating = ref(false)
const refreshing = ref(false)
const projects = ref<any[]>([])

const scorecard = ref<any | null>(null)

onMounted(async () => {
  await projectStore.fetchProjects()
  projects.value = projectStore.projects
})

watch(selectedProjectId, async (pid) => {
  if (!pid) return
  selectedTrailerId.value = null
  scorecard.value = null
  await trailerStore.fetchTrailers(pid)
  // Auto-select latest
  if (trailerStore.trailers.length) {
    selectTrailer(trailerStore.trailers[0].id)
  }
})

async function selectTrailer(id: string) {
  selectedTrailerId.value = id
  scorecard.value = null
  // Fetch detail (for video paths) and scorecard in parallel
  await trailerStore.fetchTrailer(id)
  try {
    scorecard.value = await trailersApi.getScorecard(id)
  } catch {
    // No scorecard yet — that's fine
  }
}

async function createNew() {
  if (!selectedProjectId.value) return
  creating.value = true
  try {
    const result = await trailersApi.createTrailer(selectedProjectId.value)
    await trailerStore.fetchTrailers(selectedProjectId.value)
    selectTrailer(result.trailer_id)
  } finally {
    creating.value = false
  }
}

async function refreshScore() {
  if (!selectedTrailerId.value) return
  refreshing.value = true
  try {
    scorecard.value = await trailersApi.refreshScorecard(selectedTrailerId.value)
  } finally {
    refreshing.value = false
  }
}

async function doAction(shotId: string, action: string, value?: string) {
  if (!selectedTrailerId.value) return
  await trailerStore.shotAction(selectedTrailerId.value, shotId, action, value)
  scorecard.value = trailerStore.scorecard
}

async function approve() {
  if (!selectedTrailerId.value) return
  await trailerStore.approveTrailer(selectedTrailerId.value)
}

function shotVideoUrl(shot: any): string | null {
  if (!shot.has_video) return null
  // Find the actual path from the trailer detail
  const detail = trailerStore.currentTrailer
  if (detail?.shots) {
    const s = detail.shots.find((s: any) => s.id === shot.shot_id)
    if (s?.output_video_path) return `/comfyui-output/${s.output_video_path.split('/').pop()}`
  }
  return null
}

function shortLora(name: string): string {
  return name.replace(/\.safetensors$/, '').replace(/^wan22_[a-z]+\/wan22_/, '').slice(0, 20)
}

function barStyle(val: number) {
  const pct = (val / 10) * 100
  const color = val >= 7 ? '#4caf50' : val >= 5 ? '#ff9800' : '#f44336'
  return { width: pct + '%', background: color }
}
</script>

<style scoped>
.trailer-review { max-width: 1200px; }

.toolbar {
  display: flex; gap: 12px; align-items: center; margin-bottom: 16px;
}
.project-select {
  max-width: 300px;
}

.trailer-list {
  display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap;
}
.trailer-chip {
  padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-primary);
  background: var(--bg-secondary); cursor: pointer; font-size: 13px;
  display: flex; align-items: center; gap: 6px;
}
.trailer-chip.active { border-color: var(--accent-primary); background: var(--bg-tertiary); }
.chip-status { font-size: 11px; opacity: 0.7; }
.chip-status.approved { color: #4caf50; }
.chip-status.draft { color: #999; }
.chip-shots { font-size: 11px; color: var(--text-tertiary); }

/* Verdict banner */
.verdict-banner {
  padding: 16px 20px; border-radius: 8px; margin-bottom: 20px;
  display: flex; align-items: center; gap: 16px;
}
.verdict-banner.pass { background: #1b3a1b; border: 1px solid #4caf50; }
.verdict-banner.fail { background: #3a1b1b; border: 1px solid #f44336; }
.verdict-label { font-size: 24px; font-weight: 700; letter-spacing: 2px; }
.verdict-banner.pass .verdict-label { color: #4caf50; }
.verdict-banner.fail .verdict-label { color: #f44336; }
.verdict-detail { color: var(--text-secondary); font-size: 14px; }

/* Dimensions */
.dimensions {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px; margin-bottom: 24px;
}
.dim-card {
  padding: 12px; border-radius: 8px; border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
}
.dim-card.pass { border-left: 3px solid #4caf50; }
.dim-card.fail { border-left: 3px solid #f44336; }
.dim-card.pending { border-left: 3px solid #666; opacity: 0.7; }
.dim-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.dim-icon { font-size: 16px; font-weight: 700; }
.dim-card.pass .dim-icon { color: #4caf50; }
.dim-card.fail .dim-icon { color: #f44336; }
.dim-card.pending .dim-icon { color: #666; }
.dim-name { font-size: 13px; font-weight: 600; flex: 1; }
.dim-score { font-size: 13px; font-weight: 700; color: var(--text-secondary); }
.dim-details { font-size: 12px; color: var(--text-tertiary); line-height: 1.4; }
.dim-rec { font-size: 12px; color: #ff9800; margin-top: 6px; font-style: italic; }

/* Recommendations */
.rec-section { margin-bottom: 24px; }
.rec-section h3 { font-size: 14px; margin-bottom: 8px; color: #f44336; }
.rec-item {
  padding: 8px 12px; margin-bottom: 4px; border-radius: 4px;
  background: #2a1a1a; border-left: 3px solid #f44336;
  font-size: 13px; color: var(--text-secondary);
}

/* Shot grid */
.shot-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px; margin-bottom: 24px;
}
.shot-card {
  border-radius: 8px; border: 1px solid var(--border-primary);
  background: var(--bg-secondary); overflow: hidden;
}
.shot-preview { position: relative; aspect-ratio: 2/3; background: #111; }
.shot-preview video { width: 100%; height: 100%; object-fit: cover; }
.no-video {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-tertiary); font-size: 13px;
}
.role-badge {
  position: absolute; top: 6px; left: 6px;
  padding: 2px 8px; border-radius: 4px;
  background: rgba(0,0,0,0.7); color: #fff; font-size: 11px;
}

.shot-meta {
  display: flex; justify-content: space-between; padding: 8px 10px 4px;
  font-size: 12px;
}
.shot-number { font-weight: 600; }
.shot-status { opacity: 0.7; }
.shot-status.completed { color: #4caf50; }
.shot-status.pending { color: #ff9800; }
.shot-status.generating { color: #2196f3; }

/* Score bars */
.score-bars { padding: 0 10px 4px; }
.score-row { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; }
.score-label { font-size: 10px; width: 38px; color: var(--text-tertiary); }
.score-bar { flex: 1; height: 4px; background: var(--bg-tertiary); border-radius: 2px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 2px; transition: width 200ms; }
.score-val { font-size: 10px; width: 24px; text-align: right; color: var(--text-secondary); }

/* Issues */
.shot-issues { padding: 2px 10px 4px; display: flex; gap: 4px; flex-wrap: wrap; }
.issue-chip {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: #3a2020; color: #f44336;
}

/* LoRA */
.shot-lora { padding: 2px 10px 6px; display: flex; gap: 4px; flex-wrap: wrap; }
.lora-chip {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.lora-chip.img { background: #1a2a3a; color: #64b5f6; }
.lora-chip.vid { background: #2a1a3a; color: #ce93d8; }
.tier-chip { font-size: 10px; padding: 1px 6px; border-radius: 3px; background: #2a2a1a; color: #ffd54f; }

/* Actions */
.shot-actions {
  padding: 6px 10px 8px; display: flex; gap: 4px;
  border-top: 1px solid var(--border-primary);
}
.btn-xs { font-size: 11px; padding: 3px 8px; }

/* Footer */
.footer-actions {
  display: flex; gap: 12px; justify-content: flex-end; padding: 16px 0;
  border-top: 1px solid var(--border-primary);
}

.empty-state {
  text-align: center; padding: 60px 20px; color: var(--text-tertiary);
}

h3 { font-size: 14px; margin-bottom: 12px; color: var(--text-secondary); }
</style>
