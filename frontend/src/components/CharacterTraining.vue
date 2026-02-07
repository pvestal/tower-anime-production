<template>
  <div class="character-training">
    <Card>
      <template #title>
        <div class="flex justify-content-between align-items-center">
          <span>Character LoRA Training</span>
          <Button
            label="Refresh Status"
            icon="pi pi-refresh"
            class="p-button-text"
            @click="loadTrainableCharacters"
            :loading="loading"
          />
        </div>
      </template>

      <template #content>
        <div v-if="loading" class="text-center p-4">
          <ProgressSpinner />
          <p class="mt-3">Loading character data...</p>
        </div>

        <div v-else-if="trainableCharacters.length === 0" class="text-center p-4">
          <i class="pi pi-exclamation-triangle text-4xl text-orange-500"></i>
          <p class="mt-3 text-lg">No characters have enough images for training</p>
          <p class="text-gray-600">Characters need at least 5 verified images</p>
        </div>

        <div v-else class="character-grid">
          <div v-for="character in trainableCharacters" :key="character.name"
               class="character-card p-3 border-1 border-gray-300 border-round">

            <div class="flex justify-content-between align-items-start mb-3">
              <h3 class="m-0">{{ character.display_name }}</h3>
              <Tag v-if="character.has_trained_lora"
                   value="LoRA Trained"
                   severity="success" />
            </div>

            <div class="character-info mb-3">
              <div class="flex justify-content-between mb-2">
                <span class="text-gray-600">Available Images:</span>
                <span class="font-bold">{{ character.image_count }}</span>
              </div>

              <div v-if="character.name === 'bowser_jr'" class="p-2 bg-yellow-100 border-round mb-2">
                <i class="pi pi-exclamation-triangle text-orange-500 mr-2"></i>
                <span class="text-sm">Images have BLACK eyes - need RED BLOODSHOT eyes for 2026 movie</span>
              </div>

              <ProgressBar
                :value="Math.min(100, character.image_count * 10)"
                :showValue="false"
                class="mb-2"
              />
            </div>

            <div class="training-actions">
              <Button
                :label="trainingStatus[character.name]?.status === 'training' ? 'Training...' : 'Start LoRA Training'"
                icon="pi pi-play"
                class="w-full"
                :disabled="trainingStatus[character.name]?.status === 'training'"
                :loading="trainingStatus[character.name]?.status === 'training'"
                @click="startTraining(character.name)"
                :severity="character.image_count >= 10 ? 'primary' : 'warning'"
              />

              <div v-if="trainingStatus[character.name]?.message"
                   class="mt-2 p-2 border-round"
                   :class="trainingStatus[character.name].success ? 'bg-green-100' : 'bg-red-100'">
                <small>{{ trainingStatus[character.name].message }}</small>
              </div>

              <div v-if="trainingStatus[character.name]?.dataset_path" class="mt-2">
                <small class="text-gray-600">
                  Dataset: {{ trainingStatus[character.name].dataset_path.split('/').pop() }}
                </small>
              </div>
            </div>
          </div>
        </div>

        <Divider />

        <div class="training-logs mt-3">
          <h4>Recent Training Activity</h4>
          <div v-if="recentActivity.length === 0" class="text-gray-600">
            No training activity yet
          </div>
          <Timeline v-else :value="recentActivity">
            <template #content="slotProps">
              <Card>
                <template #content>
                  <div class="flex justify-content-between">
                    <span>{{ slotProps.item.character }}</span>
                    <Tag :value="slotProps.item.status" :severity="getStatusSeverity(slotProps.item.status)" />
                  </div>
                  <small class="text-gray-600">{{ slotProps.item.timestamp }}</small>
                  <p class="mt-2 mb-0">{{ slotProps.item.message }}</p>
                </template>
              </Card>
            </template>
          </Timeline>
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import Card from 'primevue/card'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'
import ProgressSpinner from 'primevue/progressspinner'
import Divider from 'primevue/divider'
import Timeline from 'primevue/timeline'

interface TrainableCharacter {
  name: string
  display_name: string
  image_count: number
  has_trained_lora: boolean
}

interface TrainingStatus {
  status: string
  success?: boolean
  message?: string
  dataset_path?: string
  job_id?: string
}

interface ActivityItem {
  character: string
  status: string
  timestamp: string
  message: string
}

const trainableCharacters = ref<TrainableCharacter[]>([])
const trainingStatus = ref<Record<string, TrainingStatus>>({})
const recentActivity = ref<ActivityItem[]>([])
const loading = ref(false)

const loadTrainableCharacters = async () => {
  loading.value = true
  try {
    // First try the training dataset builder API
    const response = await fetch('/api/training/characters')
    if (response.ok) {
      trainableCharacters.value = await response.json()
    } else {
      // Fallback: manually check known characters
      const knownCharacters = ['mario', 'luigi', 'bowser_jr']
      const available = []

      for (const char of knownCharacters) {
        const statusResponse = await fetch(`/api/training/status/${char}`)
        if (statusResponse.ok) {
          const status = await statusResponse.json()
          if (status.ready_for_training) {
            available.push({
              name: char,
              display_name: char.replace('_', ' ').split(' ').map(w =>
                w.charAt(0).toUpperCase() + w.slice(1)
              ).join(' '),
              image_count: status.available_images,
              has_trained_lora: status.loras_trained > 0
            })
          }
        }
      }
      trainableCharacters.value = available
    }
  } catch (error) {
    console.error('Failed to load characters:', error)
    // Use hardcoded data as fallback
    trainableCharacters.value = [
      { name: 'bowser_jr', display_name: 'Bowser Jr', image_count: 5, has_trained_lora: false },
      { name: 'mario', display_name: 'Mario', image_count: 5, has_trained_lora: false },
      { name: 'luigi', display_name: 'Luigi', image_count: 5, has_trained_lora: false }
    ]
  } finally {
    loading.value = false
  }
}

const startTraining = async (characterName: string) => {
  trainingStatus.value[characterName] = { status: 'training' }

  try {
    const response = await fetch(`/api/training/start/${characterName}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: 41 })
    })

    const result = await response.json()

    trainingStatus.value[characterName] = {
      status: 'completed',
      success: result.success,
      message: result.message || 'Training started successfully',
      dataset_path: result.dataset_info?.dataset_path,
      job_id: result.job_id
    }

    // Add to activity log
    recentActivity.value.unshift({
      character: characterName.replace('_', ' ').toUpperCase(),
      status: result.success ? 'Started' : 'Failed',
      timestamp: new Date().toLocaleString(),
      message: result.message || 'Training job initiated'
    })

    // Reload character status after 2 seconds
    setTimeout(() => loadTrainableCharacters(), 2000)
  } catch (error) {
    trainingStatus.value[characterName] = {
      status: 'error',
      success: false,
      message: `Failed to start training: ${error}`
    }
  }
}

const getStatusSeverity = (status: string) => {
  switch(status.toLowerCase()) {
    case 'started': return 'success'
    case 'training': return 'info'
    case 'failed': return 'danger'
    default: return 'warning'
  }
}

onMounted(() => {
  loadTrainableCharacters()
})
</script>

<style scoped>
.character-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.character-card {
  transition: all 0.3s ease;
}

.character-card:hover {
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.training-logs {
  max-height: 400px;
  overflow-y: auto;
}
</style>