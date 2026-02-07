<template>
  <Card class="training-status-panel">
    <template #title>
      <div class="header">
        <span>LoRA Training Status</span>
        <div class="header-actions">
          <Button
            icon="pi pi-sync"
            class="p-button-text p-button-sm"
            @click="autoDeployAll"
            :loading="autoDeploying"
            v-tooltip="'Auto-deploy all completed LoRAs'"
          />
          <Button
            icon="pi pi-refresh"
            class="p-button-text p-button-sm"
            @click="refresh"
            :loading="loading"
            v-tooltip="'Refresh status'"
          />
        </div>
      </div>
    </template>

    <template #content>
      <div v-if="loading && !trainingJobs.length" class="loading-state">
        <ProgressBar mode="indeterminate" class="mb-3" />
        <p class="text-center text-color-secondary">Loading training status...</p>
      </div>

      <div v-else-if="trainingJobs.length === 0" class="empty-state">
        <div class="text-center p-4">
          <i class="pi pi-info-circle text-4xl text-color-secondary mb-3"></i>
          <p class="text-color-secondary mb-3">No training jobs found.</p>
          <p class="text-sm text-color-secondary">Start training from the References tab to see LoRA status here.</p>
        </div>
      </div>

      <div v-else class="training-jobs">
        <div v-for="job in trainingJobs" :key="job.character_name" class="training-job mb-4">
          <div class="job-header">
            <div class="character-info">
              <h4 class="character-name m-0">{{ job.character_name }}</h4>
              <small class="text-color-secondary">
                {{ job.training_dirs.length }} training {{ job.training_dirs.length === 1 ? 'session' : 'sessions' }}
              </small>
            </div>
            <Tag
              :value="getStatusLabel(job)"
              :severity="getStatusSeverity(job)"
              :icon="getStatusIcon(job)"
            />
          </div>

          <div v-if="job.is_training" class="progress-section mt-2 mb-3">
            <div class="progress-info mb-2">
              <span class="text-sm text-color-secondary">Training in progress...</span>
              <span v-if="job.progress" class="text-sm font-medium">
                Epoch {{ job.progress.current_epoch }}{{ job.progress.total_epochs ? `/${job.progress.total_epochs}` : '' }}
              </span>
            </div>
            <ProgressBar
              :value="job.progress?.progress_percent || 15"
              :showValue="false"
              class="training-progress"
            />
          </div>

          <div v-if="job.completed_loras.length > 0" class="completed-section mt-3">
            <h6 class="section-title">Completed LoRAs</h6>
            <div class="lora-list">
              <div v-for="lora in job.completed_loras.slice(0, 3)" :key="lora.path" class="lora-item">
                <div class="lora-info">
                  <i class="pi pi-check-circle text-green-500 mr-2"></i>
                  <div class="lora-details">
                    <span class="lora-name">{{ lora.path.split('/').pop() }}</span>
                    <span class="lora-meta">{{ lora.size_mb.toFixed(1) }} MB • {{ formatDate(lora.created) }}</span>
                  </div>
                </div>

                <div class="lora-actions">
                  <Button
                    v-if="!job.deployed_to_comfyui && job.latest_lora?.path === lora.path"
                    label="Deploy"
                    icon="pi pi-upload"
                    class="p-button-sm p-button-outlined"
                    @click="deployLora(job.character_name)"
                    :loading="deployingLoras[job.character_name]"
                  />
                  <Button
                    v-else-if="job.deployed_to_comfyui && job.latest_lora?.path === lora.path"
                    label="Test"
                    icon="pi pi-play"
                    class="p-button-sm p-button-success p-button-outlined"
                    @click="testLora(job.character_name)"
                    :loading="testingLoras[job.character_name]"
                  />
                  <Button
                    v-if="job.latest_lora?.path === lora.path"
                    icon="pi pi-search"
                    class="p-button-sm p-button-text"
                    @click="showQualityReport(job.character_name)"
                    v-tooltip="'View quality report'"
                  />
                </div>
              </div>

              <Button
                v-if="job.completed_loras.length > 3"
                label="+{{ job.completed_loras.length - 3 }} more"
                class="p-button-text p-button-sm mt-2"
                @click="showAllLoras(job.character_name)"
              />
            </div>
          </div>

          <div v-if="job.deployed_to_comfyui" class="deployed-badge mt-3">
            <div class="deployment-info">
              <i class="pi pi-check text-green-500 mr-2"></i>
              <span class="text-sm font-medium text-green-600">Deployed to ComfyUI</span>
              <Badge
                value="Ready for Generation"
                severity="success"
                class="ml-2"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Summary Stats -->
      <div v-if="trainingJobs.length > 0" class="summary-stats mt-4 pt-3 border-top-1 border-color">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-value">{{ trainingJobs.length }}</span>
            <span class="stat-label">Characters</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ activeTrainingCount }}</span>
            <span class="stat-label">Training</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ deployedCount }}</span>
            <span class="stat-label">Deployed</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ totalLoras }}</span>
            <span class="stat-label">Total LoRAs</span>
          </div>
        </div>
      </div>
    </template>
  </Card>

  <!-- Test Results Dialog -->
  <Dialog v-model:visible="showTestDialog" header="LoRA Test Results" :style="{ width: '50rem' }" modal>
    <div v-if="testResults" class="test-results">
      <div class="result-header mb-3">
        <h5>{{ testResults.character_name }} Test Generation</h5>
        <Tag :value="testResults.status" :severity="testResults.status === 'success' ? 'success' : 'danger'" />
      </div>

      <div v-if="testResults.status === 'success'" class="success-results">
        <div class="generated-image mb-3" v-if="testResults.generated_images?.length">
          <label class="form-label">Generated Image:</label>
          <Image
            :src="getImageUrl(testResults.generated_images[0])"
            :alt="'Generated ' + testResults.character_name"
            width="300"
            preview
            class="generated-preview"
          />
        </div>

        <div class="generation-info">
          <div class="info-item">
            <strong>Prompt:</strong>
            <p class="mt-1">{{ testResults.prompt }}</p>
          </div>
          <div class="info-item">
            <strong>Generation Time:</strong> {{ testResults.generation_time?.toFixed(1) }}s
          </div>
        </div>
      </div>

      <div v-else class="error-results">
        <Message severity="error" :closable="false">
          <strong>Generation Failed:</strong> {{ testResults.error }}
        </Message>
      </div>
    </div>

    <template #footer>
      <Button label="Close" @click="showTestDialog = false" class="p-button-secondary" />
      <Button
        v-if="testResults?.status === 'success'"
        label="Run Quality Check"
        @click="runQualityCheck"
        :loading="runningQualityCheck"
      />
    </template>
  </Dialog>

  <!-- Quality Report Dialog -->
  <Dialog v-model:visible="showQualityDialog" header="Quality Report" :style="{ width: '60rem' }" modal>
    <div v-if="qualityReport" class="quality-report">
      <div class="quality-overview mb-4">
        <div class="quality-score">
          <span class="score-label">Overall Quality:</span>
          <Tag
            :value="qualityReport.overall_assessment?.quality"
            :severity="getQualitySeverity(qualityReport.overall_assessment?.quality)"
            class="text-lg"
          />
        </div>
      </div>

      <div class="quality-details">
        <div v-if="qualityReport.clip_verification?.status === 'success'" class="clip-results mb-4">
          <h6>CLIP Similarity Analysis</h6>
          <div class="similarity-stats">
            <div class="stat">
              <span class="label">Average Similarity:</span>
              <span class="value">{{ (qualityReport.clip_verification.average_similarity * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat">
              <span class="label">Best Match:</span>
              <span class="value">{{ (qualityReport.clip_verification.max_similarity * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat">
              <span class="label">References Used:</span>
              <span class="value">{{ qualityReport.clip_verification.reference_count }}</span>
            </div>
          </div>

          <ProgressBar
            :value="qualityReport.clip_verification.average_similarity * 100"
            class="similarity-bar mt-2"
          />
        </div>

        <div v-if="qualityReport.text_alignment?.status === 'success'" class="text-results">
          <h6>Text-Image Alignment</h6>
          <div class="prompt-results">
            <div v-for="result in qualityReport.text_alignment.text_prompt_results.slice(0, 4)"
                 :key="result.prompt"
                 class="prompt-result">
              <span class="prompt">{{ result.prompt }}</span>
              <ProgressBar :value="result.similarity_score * 100" :showValue="false" class="prompt-bar" />
              <span class="score">{{ (result.similarity_score * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <Button label="Close" @click="showQualityDialog = false" />
    </template>
  </Dialog>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useToast } from 'primevue/usetoast'

const toast = useToast()

// Reactive state
const trainingJobs = ref([])
const loading = ref(false)
const autoDeploying = ref(false)
const deployingLoras = ref({})
const testingLoras = ref({})
const runningQualityCheck = ref(false)

// Dialog state
const showTestDialog = ref(false)
const showQualityDialog = ref(false)
const testResults = ref(null)
const qualityReport = ref(null)

// Auto-refresh
let refreshInterval = null

// Computed properties
const activeTrainingCount = computed(() =>
  trainingJobs.value.filter(job => job.is_training).length
)

const deployedCount = computed(() =>
  trainingJobs.value.filter(job => job.deployed_to_comfyui).length
)

const totalLoras = computed(() =>
  trainingJobs.value.reduce((sum, job) => sum + job.completed_loras.length, 0)
)

// Methods
async function refresh() {
  loading.value = true
  try {
    const response = await fetch('/api/training/status')
    if (response.ok) {
      const data = await response.json()
      trainingJobs.value = data.training_jobs || []
    } else {
      throw new Error(`HTTP ${response.status}`)
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: `Failed to load training status: ${error.message}`,
      life: 3000
    })
  } finally {
    loading.value = false
  }
}

async function deployLora(characterName) {
  deployingLoras.value[characterName] = true
  try {
    const response = await fetch(`/api/training/deploy/${characterName}`, {
      method: 'POST'
    })

    if (response.ok) {
      toast.add({
        severity: 'success',
        summary: 'Deployed',
        detail: `${characterName} LoRA deployed to ComfyUI`,
        life: 3000
      })
      await refresh()
    } else {
      const error = await response.json()
      throw new Error(error.detail || 'Deployment failed')
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Deployment Failed',
      detail: error.message,
      life: 3000
    })
  } finally {
    deployingLoras.value[characterName] = false
  }
}

async function testLora(characterName) {
  testingLoras.value[characterName] = true
  try {
    const response = await fetch(`/api/training/test/${characterName}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: `${characterName}, high quality, detailed, masterpiece`
      })
    })

    if (response.ok) {
      const result = await response.json()
      testResults.value = result
      showTestDialog.value = true
    } else {
      throw new Error('Test generation failed')
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Test Failed',
      detail: error.message,
      life: 3000
    })
  } finally {
    testingLoras.value[characterName] = false
  }
}

async function autoDeployAll() {
  autoDeploying.value = true
  try {
    const response = await fetch('/api/training/auto-deploy', { method: 'POST' })
    if (response.ok) {
      const result = await response.json()
      toast.add({
        severity: 'success',
        summary: 'Auto-Deploy Complete',
        detail: `Deployed ${result.deployed_count} LoRAs`,
        life: 3000
      })
      await refresh()
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Auto-Deploy Failed',
      detail: error.message,
      life: 3000
    })
  } finally {
    autoDeploying.value = false
  }
}

async function runQualityCheck() {
  if (!testResults.value?.generated_images?.length) return

  runningQualityCheck.value = true
  // This would call the quality verification API endpoint when implemented
  // For now, show a placeholder
  toast.add({
    severity: 'info',
    summary: 'Quality Check',
    detail: 'Quality verification integration pending',
    life: 3000
  })
  runningQualityCheck.value = false
}

function showQualityReport(characterName) {
  // Placeholder for quality report
  toast.add({
    severity: 'info',
    summary: 'Quality Report',
    detail: 'Quality reporting integration pending',
    life: 3000
  })
}

function showAllLoras(characterName) {
  // Placeholder for expanded lora view
  console.log('Show all LoRAs for', characterName)
}

function getStatusLabel(job) {
  if (job.is_training) return 'Training'
  if (job.deployed_to_comfyui) return 'Ready'
  if (job.completed_loras.length > 0) return 'Complete'
  return 'Pending'
}

function getStatusSeverity(job) {
  if (job.is_training) return 'info'
  if (job.deployed_to_comfyui) return 'success'
  if (job.completed_loras.length > 0) return 'warning'
  return 'secondary'
}

function getStatusIcon(job) {
  if (job.is_training) return 'pi pi-spin pi-spinner'
  if (job.deployed_to_comfyui) return 'pi pi-check'
  if (job.completed_loras.length > 0) return 'pi pi-clock'
  return 'pi pi-minus'
}

function getQualitySeverity(quality) {
  switch (quality?.toUpperCase()) {
    case 'EXCELLENT': return 'success'
    case 'GOOD': return 'success'
    case 'ACCEPTABLE': return 'warning'
    case 'POOR': return 'danger'
    default: return 'secondary'
  }
}

function formatDate(dateString) {
  return new Date(dateString).toLocaleString()
}

function getImageUrl(imagePath) {
  // Convert file path to URL
  if (imagePath.startsWith('/mnt/1TB-storage/ComfyUI/output/')) {
    return `/api/video/download/${imagePath.split('/').pop()}`
  }
  return imagePath
}

// Lifecycle
onMounted(() => {
  refresh()
  // Auto-refresh every 10 seconds
  refreshInterval = setInterval(refresh, 10000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.training-status-panel .header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.training-job {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1rem;
  background: var(--surface-ground);
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
}

.character-info h4 {
  text-transform: capitalize;
  margin-bottom: 0.25rem;
}

.training-progress {
  height: 4px;
}

.section-title {
  margin: 0 0 0.75rem 0;
  color: var(--text-color-secondary);
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.lora-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  margin-bottom: 0.5rem;
  background: var(--surface-card);
}

.lora-info {
  display: flex;
  align-items: center;
  flex: 1;
}

.lora-details {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.lora-name {
  font-weight: 500;
  font-size: 0.9rem;
}

.lora-meta {
  font-size: 0.75rem;
  color: var(--text-color-secondary);
}

.lora-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.deployment-info {
  display: flex;
  align-items: center;
  padding: 0.5rem;
  background: var(--green-50);
  border-radius: 4px;
}

.summary-stats {
  background: var(--surface-card);
  border-radius: 8px;
  padding: 1rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  text-align: center;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary-color);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-color-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 2rem;
}

.test-results .result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.generated-preview {
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.info-item {
  margin-bottom: 1rem;
}

.quality-overview {
  text-align: center;
  padding: 1rem;
  background: var(--surface-card);
  border-radius: 8px;
}

.quality-score {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  font-size: 1.1rem;
}

.similarity-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 1rem;
}

.similarity-stats .stat {
  text-align: center;
}

.similarity-stats .label {
  display: block;
  font-size: 0.875rem;
  color: var(--text-color-secondary);
  margin-bottom: 0.25rem;
}

.similarity-stats .value {
  display: block;
  font-weight: 600;
  font-size: 1.1rem;
}

.prompt-result {
  display: grid;
  grid-template-columns: 2fr 3fr auto;
  gap: 1rem;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-color);
}

.prompt-result:last-child {
  border-bottom: none;
}

.prompt {
  font-size: 0.875rem;
}

.prompt-bar {
  height: 6px;
}

.score {
  font-weight: 600;
  font-size: 0.875rem;
}
</style>