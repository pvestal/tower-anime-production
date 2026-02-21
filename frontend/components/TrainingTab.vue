<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h2 style="font-size: 18px; font-weight: 500;">Training</h2>
        <p style="font-size: 12px; color: var(--text-muted);">LoRA training produces ComfyUI-compatible .safetensors files</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="btn" @click="reconcile" :disabled="trainingStore.loading" style="font-size: 12px;">
          Reconcile
        </button>
        <button class="btn" @click="confirmClearFinished" :disabled="trainingStore.loading" style="font-size: 12px;">
          Clear Finished
        </button>
        <button class="btn" @click="refresh" :disabled="trainingStore.loading">
          Refresh
        </button>
      </div>
    </div>

    <!-- Trained LoRAs chips (always visible at top) -->
    <div v-if="trainingStore.loras.length > 0" style="margin-bottom: 20px;">
      <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Trained LoRAs</div>
      <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        <div
          v-for="lora in trainingStore.loras"
          :key="lora.filename"
          class="lora-chip"
        >
          <span style="font-weight: 500;">{{ lora.slug }}</span>
          <span style="color: var(--text-muted); font-size: 11px;">{{ lora.size_mb }}MB</span>
          <button class="chip-delete" @click="confirmDeleteLora(lora)" :disabled="actionLoading === lora.slug">&times;</button>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="trainingStore.loading" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading...</p>
    </div>

    <!-- Error -->
    <div v-else-if="trainingStore.error" class="card" style="background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error);">{{ trainingStore.error }}</p>
      <button class="btn" @click="trainingStore.clearError()" style="margin-top: 8px;">Dismiss</button>
    </div>

    <!-- Two-column layout -->
    <div v-else class="training-layout">

      <!-- LEFT: Character Training Status -->
      <div class="training-characters">
        <div style="font-size: 13px; font-weight: 500; margin-bottom: 12px; color: var(--accent-primary);">Character Training Status</div>
        <div v-if="charactersStore.characters.length === 0" style="text-align: center; padding: 24px; color: var(--text-muted); font-size: 13px;">
          No characters loaded. <RouterLink to="/characters" style="color: var(--accent-primary);">Go to Characters</RouterLink>
        </div>
        <div v-else style="display: flex; flex-direction: column; gap: 10px;">
          <div
            v-for="char in sortedCharacters"
            :key="char.slug"
            class="card char-training-card"
            :style="charCardStyle(char)"
          >
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="font-size: 14px; font-weight: 500;">{{ char.name }}</div>
              <span v-if="charLora(char.slug)" class="badge badge-approved" style="font-size: 10px;">LoRA Ready</span>
              <span v-else-if="charStats(char.slug).canTrain" class="badge badge-pending" style="font-size: 10px;">Ready to Train</span>
              <span v-else style="font-size: 11px; color: var(--text-muted);">{{ charStats(char.slug).approved }}/10</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">{{ char.project_name }}</div>

            <!-- Progress bar -->
            <div class="progress-track" style="height: 5px; margin-bottom: 8px;">
              <div
                class="progress-bar"
                :class="{ ready: charStats(char.slug).canTrain }"
                :style="{ width: `${Math.min(100, (charStats(char.slug).approved / 10) * 100)}%` }"
              ></div>
            </div>

            <!-- LoRA info if exists -->
            <div v-if="charLora(char.slug)" style="font-size: 11px; color: var(--text-secondary);">
              {{ charLora(char.slug)!.filename }} &middot; {{ charLora(char.slug)!.size_mb }}MB &middot; {{ formatTime(charLora(char.slug)!.created_at) }}
            </div>

            <!-- Train button if ready but no LoRA -->
            <button
              v-else-if="charStats(char.slug).canTrain"
              class="btn btn-success"
              style="font-size: 11px; padding: 4px 12px; margin-top: 4px;"
              @click="startTrainingForChar(char)"
              :disabled="trainingStore.loading"
            >
              Start Training
            </button>
          </div>
        </div>
      </div>

      <!-- RIGHT: Job Monitor -->
      <div class="training-jobs">
        <div style="font-size: 13px; font-weight: 500; margin-bottom: 12px; color: var(--accent-primary);">Job Monitor</div>

        <!-- Stats mini-bar -->
        <div v-if="trainingStore.jobs.length > 0" style="display: flex; gap: 12px; margin-bottom: 16px; font-size: 12px;">
          <span style="color: var(--status-success);">{{ completedCount }} completed</span>
          <span style="color: var(--status-warning);">{{ runningCount }} running</span>
          <span v-if="failedCount" style="color: var(--status-error);">{{ failedCount }} failed</span>
        </div>

        <!-- Empty -->
        <div v-if="trainingStore.jobs.length === 0" style="text-align: center; padding: 32px; color: var(--text-muted); font-size: 13px;">
          No training jobs yet. Start training on a character with 10+ approved images.
        </div>

        <!-- Jobs list (newest first) -->
        <div v-else style="display: flex; flex-direction: column; gap: 10px;">
      <div
        v-for="job in sortedJobs"
        :key="job.job_id"
        class="card"
        :style="jobBorderStyle(job)"
      >
        <!-- Header: character name + status badge -->
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <h3 style="font-size: 16px; font-weight: 500;">{{ job.character_name }}</h3>
            <span class="badge" :class="statusClass(job.status)">{{ job.status }}</span>
          </div>
          <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
            <button v-if="job.status === 'running' || job.status === 'queued'" class="btn btn-danger" style="font-size: 11px; padding: 3px 8px;" @click="confirmCancel(job)" :disabled="actionLoading === job.job_id">Cancel</button>
            <button v-if="job.status === 'failed' || job.status === 'invalidated'" class="btn" style="font-size: 11px; padding: 3px 8px; color: var(--status-warning);" @click="retryJob(job)" :disabled="actionLoading === job.job_id">Retry</button>
            <button v-if="job.status === 'completed'" class="btn" style="font-size: 11px; padding: 3px 8px; color: var(--text-muted);" @click="confirmInvalidate(job)" :disabled="actionLoading === job.job_id">Invalidate</button>
            <button v-if="job.status === 'completed' || job.status === 'failed' || job.status === 'invalidated'" class="btn btn-danger" style="font-size: 11px; padding: 3px 8px;" @click="confirmDelete(job)" :disabled="actionLoading === job.job_id">Delete</button>
            <button v-if="job.status === 'running' || job.status === 'completed' || job.status === 'failed'" class="btn" style="font-size: 11px; padding: 3px 8px;" @click="toggleLog(job.job_id)">{{ expandedLog === job.job_id ? 'Hide Log' : 'View Log' }}</button>
          </div>
        </div>

        <!-- Running: epoch progress bar -->
        <div v-if="job.status === 'running' && job.epoch && job.total_epochs" style="margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
            <span style="color: var(--text-secondary);">Epoch {{ job.epoch }}/{{ job.total_epochs }}</span>
            <span v-if="job.loss != null" style="color: var(--text-muted);">Loss: {{ job.loss.toFixed(6) }}</span>
          </div>
          <div class="progress-track" style="height: 6px;">
            <div class="progress-bar" style="background: var(--status-warning);" :style="{ width: `${(job.epoch / job.total_epochs) * 100}%` }"></div>
          </div>
        </div>

        <!-- Config grid -->
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px 16px; font-size: 13px; margin-bottom: 8px;">
          <div><div style="color: var(--text-muted); font-size: 11px;">Images</div><div style="color: var(--text-primary); font-weight: 500;">{{ job.approved_images }}</div></div>
          <div><div style="color: var(--text-muted); font-size: 11px;">Epochs</div><div style="color: var(--text-primary); font-weight: 500;">{{ job.epochs }}</div></div>
          <div><div style="color: var(--text-muted); font-size: 11px;">Learning Rate</div><div style="color: var(--text-primary); font-weight: 500;">{{ job.learning_rate }}</div></div>
          <div><div style="color: var(--text-muted); font-size: 11px;">Resolution</div><div style="color: var(--text-primary); font-weight: 500;">{{ job.resolution }}</div></div>
          <div v-if="job.checkpoint"><div style="color: var(--text-muted); font-size: 11px;">Checkpoint</div><div style="color: var(--text-primary); font-weight: 500; font-size: 11px;">{{ job.checkpoint.replace('.safetensors', '') }}</div></div>
        </div>

        <!-- Completed: results -->
        <div v-if="job.status === 'completed'" style="background: rgba(80,160,80,0.08); border: 1px solid rgba(80,160,80,0.2); border-radius: 4px; padding: 10px 12px; margin-top: 8px;">
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px 16px; font-size: 12px;">
            <div v-if="job.best_loss != null"><span style="color: var(--text-muted);">Best Loss:</span><span style="color: var(--status-success); font-weight: 500; margin-left: 4px;">{{ job.best_loss.toFixed(6) }}</span></div>
            <div v-if="job.final_loss != null"><span style="color: var(--text-muted);">Final Loss:</span><span style="color: var(--text-secondary); margin-left: 4px;">{{ job.final_loss.toFixed(6) }}</span></div>
            <div v-if="job.total_steps"><span style="color: var(--text-muted);">Steps:</span><span style="color: var(--text-secondary); margin-left: 4px;">{{ job.total_steps }}</span></div>
            <div v-if="job.file_size_mb"><span style="color: var(--text-muted);">File Size:</span><span style="color: var(--text-secondary); margin-left: 4px;">{{ job.file_size_mb }} MB</span></div>
          </div>
          <div v-if="job.output_path" style="margin-top: 8px; font-size: 11px; color: var(--text-muted); font-family: monospace; word-break: break-all;">{{ job.output_path }}</div>
        </div>

        <!-- Failed/Invalidated: error message -->
        <div v-if="job.status === 'failed' || job.status === 'invalidated'" :style="{ background: job.status === 'invalidated' ? 'rgba(120,120,120,0.08)' : 'rgba(160,80,80,0.08)', border: `1px solid ${job.status === 'invalidated' ? 'rgba(120,120,120,0.2)' : 'rgba(160,80,80,0.2)'}`, borderRadius: '4px', padding: '10px 12px', marginTop: '8px' }">
          <div v-if="job.error" style="font-size: 12px; font-family: monospace; word-break: break-all;" :style="{ color: job.status === 'invalidated' ? 'var(--text-muted)' : 'var(--status-error)' }">{{ job.error }}</div>
          <div v-else style="font-size: 12px; color: var(--status-error);">Training failed — check the log for details.</div>
        </div>

        <!-- Timestamps -->
        <div style="display: flex; gap: 16px; margin-top: 10px; font-size: 11px; color: var(--text-muted);">
          <span>Created: {{ formatTime(job.created_at) }}</span>
          <span v-if="job.started_at">Started: {{ formatTime(job.started_at) }}</span>
          <span v-if="job.completed_at">Completed: {{ formatTime(job.completed_at) }}</span>
          <span v-if="job.failed_at">Failed: {{ formatTime(job.failed_at) }}</span>
          <span v-if="job.status === 'running' && job.started_at" style="color: var(--status-warning);">Running for {{ elapsed(job.started_at) }}</span>
        </div>

        <!-- Log viewer -->
        <div v-if="expandedLog === job.job_id" style="margin-top: 12px;">
          <div v-if="logLoading" style="text-align: center; padding: 16px;"><div class="spinner" style="width: 20px; height: 20px; margin: 0 auto;"></div></div>
          <pre v-else-if="logLines.length > 0" style="background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 4px; padding: 10px 12px; font-size: 11px; line-height: 1.5; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: var(--text-secondary);">{{ logLines.join('\n') }}</pre>
          <p v-else style="font-size: 12px; color: var(--text-muted); padding: 8px;">No log output yet.</p>
        </div>
      </div><!-- end job card -->
        </div><!-- end jobs list -->
      </div><!-- end training-jobs -->

    </div><!-- end training-layout -->

    <!-- Confirm dialog -->
    <ConfirmDialog
      :dialog="confirmDialogData"
      @confirm="handleConfirmAction"
      @cancel="confirmDialogData = null; pendingAction = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useTrainingStore } from '@/stores/training'
import { useCharactersStore } from '@/stores/characters'
import type { TrainingJob, LoraFile, Character } from '@/types'
import ConfirmDialog from './training/ConfirmDialog.vue'
import type { ConfirmDialogData } from './training/ConfirmDialog.vue'

const trainingStore = useTrainingStore()
const charactersStore = useCharactersStore()
const expandedLog = ref<string | null>(null)
const logLines = ref<string[]>([])
const logLoading = ref(false)
const actionLoading = ref<string | null>(null)
const confirmDialogData = ref<ConfirmDialogData | null>(null)
const pendingAction = ref<((deleteLora: boolean) => Promise<void>) | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  trainingStore.fetchLoras()
  pollTimer = setInterval(() => {
    const hasActive = trainingStore.jobs.some(j => j.status === 'running' || j.status === 'queued')
    if (hasActive) {
      trainingStore.fetchTrainingJobs()
      if (expandedLog.value) fetchLog(expandedLog.value)
    }
  }, 5000)
})

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

// Character training helpers
function charStats(slug: string) {
  const s = charactersStore.getCharacterStats(slug)
  return { ...s, canTrain: s.approved >= 10 }
}

function charLora(slug: string): LoraFile | undefined {
  return trainingStore.loras.find(l => l.slug === slug)
}

function charCardStyle(char: Character) {
  const lora = charLora(char.slug)
  if (lora) return { borderLeftColor: 'var(--status-success)', borderLeftWidth: '3px' }
  if (charStats(char.slug).canTrain) return { borderLeftColor: 'var(--accent-primary)', borderLeftWidth: '3px' }
  return {}
}

const sortedCharacters = computed(() => {
  return [...charactersStore.characters].sort((a, b) => {
    const aLora = charLora(a.slug) ? 2 : charStats(a.slug).canTrain ? 1 : 0
    const bLora = charLora(b.slug) ? 2 : charStats(b.slug).canTrain ? 1 : 0
    if (aLora !== bLora) return bLora - aLora
    return charStats(b.slug).approved - charStats(a.slug).approved
  })
})

async function startTrainingForChar(char: Character) {
  try {
    await trainingStore.startTraining({ character_name: char.name })
    trainingStore.fetchTrainingJobs()
  } catch (error) {
    console.error('Failed to start training:', error)
  }
}

const sortedJobs = computed(() => [...trainingStore.jobs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
const completedCount = computed(() => trainingStore.jobs.filter(j => j.status === 'completed').length)
const runningCount = computed(() => trainingStore.jobs.filter(j => j.status === 'running' || j.status === 'queued').length)
const failedCount = computed(() => trainingStore.jobs.filter(j => j.status === 'failed').length)

function statusClass(status: string): string {
  switch (status) {
    case 'completed': return 'badge-approved'
    case 'running': case 'queued': return 'badge-pending'
    case 'failed': case 'invalidated': return 'badge-rejected'
    default: return ''
  }
}

function jobBorderStyle(job: TrainingJob) {
  if (job.status === 'completed') return { borderLeftColor: 'var(--status-success)', borderLeftWidth: '3px' }
  if (job.status === 'running') return { borderLeftColor: 'var(--status-warning)', borderLeftWidth: '3px' }
  if (job.status === 'failed') return { borderLeftColor: 'var(--status-error)', borderLeftWidth: '3px' }
  if (job.status === 'invalidated') return { borderLeftColor: 'var(--text-muted)', borderLeftWidth: '3px' }
  return {}
}

function formatTime(iso: string): string { return new Date(iso).toLocaleString() }

function elapsed(iso: string): string {
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${sec % 60}s`
  return `${Math.floor(min / 60)}h ${min % 60}m`
}

async function fetchLog(jobId: string) {
  logLoading.value = true
  try {
    const resp = await fetch(`/api/training/jobs/${encodeURIComponent(jobId)}/log?tail=100`)
    if (resp.ok) { const data = await resp.json(); logLines.value = data.lines || [] }
    else logLines.value = ['(Log not available)']
  } catch { logLines.value = ['(Failed to fetch log)'] }
  finally { logLoading.value = false }
}

async function toggleLog(jobId: string) {
  if (expandedLog.value === jobId) { expandedLog.value = null; logLines.value = [] }
  else { expandedLog.value = jobId; await fetchLog(jobId) }
}

function refresh() { trainingStore.fetchTrainingJobs(); trainingStore.fetchLoras(); if (expandedLog.value) fetchLog(expandedLog.value) }

function handleConfirmAction(deleteLora: boolean) {
  if (pendingAction.value) pendingAction.value(deleteLora)
  confirmDialogData.value = null
  pendingAction.value = null
}

function confirmCancel(job: TrainingJob) {
  confirmDialogData.value = { title: 'Cancel Training', message: `Cancel training for "${job.character_name}"? The process will be killed and the job marked as failed.`, confirmLabel: 'Cancel Job' }
  pendingAction.value = async () => { actionLoading.value = job.job_id; try { await trainingStore.cancelJob(job.job_id) } finally { actionLoading.value = null } }
}

async function retryJob(job: TrainingJob) { actionLoading.value = job.job_id; try { await trainingStore.retryJob(job.job_id) } finally { actionLoading.value = null } }

function confirmInvalidate(job: TrainingJob) {
  confirmDialogData.value = { title: 'Invalidate Training', message: `Mark training for "${job.character_name}" as invalidated? This indicates the LoRA was trained on bad data.`, confirmLabel: 'Invalidate', showDeleteLora: true }
  pendingAction.value = async (deleteLora) => { actionLoading.value = job.job_id; try { await trainingStore.invalidateJob(job.job_id, deleteLora) } finally { actionLoading.value = null } }
}

function confirmDelete(job: TrainingJob) {
  confirmDialogData.value = { title: 'Delete Job Record', message: `Remove the job record for "${job.character_name}" from the list? This does not delete the LoRA file.`, confirmLabel: 'Delete' }
  pendingAction.value = async () => { actionLoading.value = job.job_id; try { await trainingStore.deleteJob(job.job_id) } finally { actionLoading.value = null } }
}

function confirmDeleteLora(lora: LoraFile) {
  confirmDialogData.value = { title: 'Delete LoRA File', message: `Permanently delete ${lora.filename} (${lora.size_mb} MB) from disk?`, confirmLabel: 'Delete File' }
  pendingAction.value = async () => { actionLoading.value = lora.slug; try { await trainingStore.deleteLora(lora.slug) } finally { actionLoading.value = null } }
}

async function reconcile() { actionLoading.value = 'reconcile'; try { await trainingStore.reconcileJobs() } finally { actionLoading.value = null } }

function confirmClearFinished() {
  confirmDialogData.value = { title: 'Clear Finished Jobs', message: 'Remove all completed, failed, and invalidated jobs older than 7 days from the list?', confirmLabel: 'Clear' }
  pendingAction.value = async () => { actionLoading.value = 'clear'; try { await trainingStore.clearFinished(7) } finally { actionLoading.value = null } }
}
</script>

<style scoped>
.btn-danger {
  color: var(--status-error);
  border-color: var(--status-error);
}
.btn-danger:hover {
  background: rgba(160,80,80,0.1);
}
.btn-success {
  color: var(--status-success);
  border-color: var(--status-success);
}
.btn-success:hover {
  background: rgba(80,160,80,0.1);
}
.training-layout {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 20px;
  align-items: flex-start;
}
@media (max-width: 1000px) {
  .training-layout {
    grid-template-columns: 1fr;
  }
}
.training-characters,
.training-jobs {
  min-width: 0;
}
.char-training-card {
  padding: 12px 14px;
}
.lora-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(80,160,80,0.1);
  border: 1px solid rgba(80,160,80,0.3);
  border-radius: 20px;
  font-size: 12px;
  color: var(--text-primary);
}
.chip-delete {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
  line-height: 1;
}
.chip-delete:hover {
  color: var(--status-error);
}
</style>
