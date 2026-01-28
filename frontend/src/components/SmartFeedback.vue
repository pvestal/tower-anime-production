<template>
  <div class="smart-feedback">
    <Card>
      <template #header>
        <div class="flex justify-content-between align-items-center p-3">
          <div class="flex align-items-center gap-2">
            <i class="pi pi-check-circle" style="font-size: 1.5rem; color: #10b981;"></i>
            <h3 class="m-0">Smart Feedback System</h3>
            <Tag v-if="selectedProject" :value="selectedProject.name" severity="info" />
            <Tag v-if="selectedCharacter" :value="selectedCharacter" severity="warning" />
          </div>
          <div class="flex align-items-center gap-2">
            <Tag :value="trainingReadiness.message"
                 :severity="trainingReadiness.ready ? 'success' : 'warning'" />
            <Button
              label="Generate Images"
              icon="pi pi-images"
              @click="generateImages"
              :disabled="!selectedCharacter"
              severity="info"
              size="small"
            />
            <Button
              label="Start Training"
              icon="pi pi-play"
              @click="startTraining"
              :disabled="!trainingReadiness.ready"
              severity="success"
              size="small"
            />
          </div>
        </div>
      </template>

      <template #content>
        <div class="grid">
          <!-- Left: Image Grid for Approval -->
          <div class="col-12 lg:col-8">
            <div class="image-grid">
              <div v-if="imagesLoading" class="text-center p-5">
                <ProgressSpinner />
                <p class="mt-3">Loading images...</p>
              </div>

              <div v-else-if="images.length === 0" class="text-center p-5">
                <i class="pi pi-image" style="font-size: 3rem; color: #64748b;"></i>
                <p class="mt-3 text-500">No images generated yet</p>
                <Button label="Generate First Batch" icon="pi pi-plus" @click="generateImages" />
              </div>

              <div v-else class="image-container">
                <div v-for="image in images" :key="image.path"
                     class="image-item p-2">
                  <div class="image-wrapper">
                    <Image :src="`/api/anime/images${image.path}`"
                           :alt="image.character"
                           preview
                           class="w-full" />

                    <!-- Approval Status Overlay -->
                    <div class="approval-overlay">
                      <Tag v-if="image.approved === true"
                           value="Approved" severity="success"
                           icon="pi pi-check" />
                      <Tag v-else-if="image.approved === false"
                           value="Rejected" severity="danger"
                           icon="pi pi-times" />
                      <Tag v-else
                           value="Pending" severity="warning"
                           icon="pi pi-clock" />
                    </div>

                    <!-- Action Buttons -->
                    <div class="image-actions p-2">
                      <div class="flex gap-2 justify-content-center">
                        <Button
                          icon="pi pi-check"
                          @click="approveImage(image)"
                          severity="success"
                          size="small"
                          rounded
                          :disabled="image.approved === true"
                        />
                        <Button
                          icon="pi pi-times"
                          @click="rejectImage(image)"
                          severity="danger"
                          size="small"
                          rounded
                          :disabled="image.approved === false"
                        />
                        <Button
                          icon="pi pi-comment"
                          @click="showFeedbackDialog(image)"
                          severity="secondary"
                          size="small"
                          rounded
                        />
                      </div>
                    </div>
                  </div>
                  <div class="text-center mt-2">
                    <small class="text-500">{{ image.character }} #{{ image.index }}</small>
                  </div>
                </div>
              </div>
            </div>

            <!-- Pagination -->
            <div class="flex justify-content-center mt-3" v-if="images.length > 0">
              <Paginator :rows="12" :totalRecords="totalImages"
                        v-model:first="currentPage"
                        @page="onPageChange" />
            </div>
          </div>

          <!-- Right: Style Requirements & SSOT -->
          <div class="col-12 lg:col-4">
            <!-- Quality Gate Status -->
            <Card class="mb-3">
              <template #title>
                <div class="text-base">Quality Gate Status</div>
              </template>
              <template #content>
                <div v-if="qualityGate">
                  <div class="mb-3">
                    <label class="text-xs text-500">Project Style</label>
                    <div class="font-semibold">{{ qualityGate.style }}</div>
                  </div>

                  <div class="mb-3">
                    <label class="text-xs text-500">Approval Progress</label>
                    <ProgressBar :value="approvalProgress" showValue>
                      <span>{{ approvedCount }}/{{ qualityGate.minApprovedImages }}</span>
                    </ProgressBar>
                  </div>

                  <div class="mb-3">
                    <label class="text-xs text-500">Required Model</label>
                    <div class="text-sm font-mono">{{ qualityGate.model }}</div>
                  </div>

                  <Divider />

                  <div class="mb-2">
                    <label class="text-xs text-500 text-green-500">✓ Requirements</label>
                    <ul class="pl-3 m-0 mt-1">
                      <li v-for="req in qualityGate.requirements" :key="req"
                          class="text-sm text-green-400">
                        {{ req }}
                      </li>
                    </ul>
                  </div>

                  <div>
                    <label class="text-xs text-500 text-red-500">✗ Not Allowed</label>
                    <div class="flex flex-wrap gap-1 mt-2">
                      <Tag v-for="item in qualityGate.notAllowed" :key="item"
                           :value="item" severity="danger" class="text-xs" />
                    </div>
                  </div>
                </div>
                <div v-else class="text-center text-500">
                  Select a project to view requirements
                </div>
              </template>
            </Card>

            <!-- Character SSOT -->
            <Card v-if="characterSSoT">
              <template #title>
                <div class="text-base">Character Reference</div>
              </template>
              <template #content>
                <div class="mb-2">
                  <label class="text-xs text-500">Name</label>
                  <div class="font-semibold">{{ characterSSoT.name }}</div>
                </div>
                <div class="mb-2">
                  <label class="text-xs text-500">Design Prompt</label>
                  <div class="text-sm">{{ characterSSoT.design_prompt }}</div>
                </div>
                <div class="mb-2">
                  <label class="text-xs text-500">Personality</label>
                  <div class="text-sm">{{ characterSSoT.personality }}</div>
                </div>
                <div v-if="characterSSoT.appearance_data">
                  <label class="text-xs text-500">Appearance</label>
                  <div class="flex flex-wrap gap-1 mt-1">
                    <Tag v-for="(value, key) in JSON.parse(characterSSoT.appearance_data)"
                         :key="key"
                         :value="`${key}: ${value}`"
                         severity="info"
                         class="text-xs" />
                  </div>
                </div>
              </template>
            </Card>

            <!-- Recent Feedback -->
            <Card class="mt-3" v-if="recentFeedback.length > 0">
              <template #title>
                <div class="text-base">Recent Feedback</div>
              </template>
              <template #content>
                <div v-for="feedback in recentFeedback" :key="feedback.id"
                     class="mb-2 p-2 surface-ground border-round">
                  <div class="flex justify-content-between mb-1">
                    <small class="font-semibold">{{ feedback.character_name }}</small>
                    <Rating :modelValue="feedback.rating" :readonly="true" :cancel="false" />
                  </div>
                  <small class="text-500">{{ feedback.user_feedback }}</small>
                  <div v-if="feedback.ai_suggestions" class="mt-1">
                    <small class="text-primary">AI: {{ feedback.ai_suggestions }}</small>
                  </div>
                </div>
              </template>
            </Card>
          </div>
        </div>
      </template>
    </Card>

    <!-- Feedback Dialog -->
    <Dialog v-model:visible="showFeedback" header="Provide Feedback" :modal="true" :style="{width: '450px'}">
      <div class="p-fluid">
        <div class="field">
          <label>Rating</label>
          <Rating v-model="currentFeedback.rating" :cancel="false" />
        </div>
        <div class="field">
          <label>Feedback</label>
          <Textarea v-model="currentFeedback.feedback" rows="4"
                   placeholder="What needs improvement? Be specific about visual issues..." />
        </div>
      </div>
      <template #footer>
        <Button label="Cancel" @click="showFeedback = false" severity="secondary" />
        <Button label="Submit" @click="submitFeedback" icon="pi pi-send" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'

const toast = useToast()

// Props
const props = defineProps({
  selectedProject: Object,
  selectedCharacter: String
})

// State
const images = ref([])
const imagesLoading = ref(false)
const totalImages = ref(0)
const currentPage = ref(0)

const qualityGate = ref(null)
const characterSSoT = ref(null)
const approvedCount = ref(0)
const recentFeedback = ref([])

const showFeedback = ref(false)
const currentImage = ref(null)
const currentFeedback = ref({
  rating: 5,
  feedback: ''
})

// Quality Gates Configuration (matching Python backend)
const qualityGates = {
  'Super Mario Galaxy Anime Adventure': {
    model: 'realisticVision_v51.safetensors',
    style: 'Illumination Studios 3D movie style (2026 release)',
    minApprovedImages: 15,
    requirements: [
      'Realistic 3D character rendering',
      'Photorealistic textures and lighting',
      'Cinematic movie quality'
    ],
    notAllowed: ['Anime', 'cartoon', 'stylized', '2D', 'flat colors']
  },
  'Tokyo Debt Desire': {
    model: 'custom_anime_model.safetensors',
    style: 'Modern anime with realistic proportions',
    minApprovedImages: 12,
    requirements: [
      'Adult human proportions',
      'Detailed facial features',
      'Tokyo urban setting'
    ],
    notAllowed: ['Childish', 'cartoon', 'oversized eyes']
  },
  'Cyberpunk Goblin Slayer': {
    model: 'arcane_style_model.safetensors',
    style: 'Arcane (League of Legends) animation style',
    minApprovedImages: 10,
    requirements: [
      'Arcane painterly aesthetic',
      'Hand-painted textures',
      'Dramatic lighting'
    ],
    notAllowed: ['Photorealistic', 'anime', 'flat shading']
  }
}

// Computed
const approvalProgress = computed(() => {
  if (!qualityGate.value) return 0
  return Math.min((approvedCount.value / qualityGate.value.minApprovedImages) * 100, 100)
})

const trainingReadiness = computed(() => {
  if (!qualityGate.value) return { ready: false, message: 'No project selected' }

  const required = qualityGate.value.minApprovedImages
  if (approvedCount.value >= required) {
    return { ready: true, message: `✅ Ready (${approvedCount.value}/${required})` }
  }
  return {
    ready: false,
    message: `⚠️ Need ${required - approvedCount.value} more (${approvedCount.value}/${required})`
  }
})

// Watchers
watch(() => props.selectedProject, (newProject) => {
  if (newProject) {
    qualityGate.value = qualityGates[newProject.name] || null
    loadImages()
  }
})

watch(() => props.selectedCharacter, (newCharacter) => {
  if (newCharacter) {
    loadCharacterSSoT(newCharacter)
    loadImages()
  }
})

// Methods
async function loadImages() {
  if (!props.selectedProject || !props.selectedCharacter) return

  imagesLoading.value = true
  try {
    // Call Smart Feedback API backend
    const response = await fetch(`http://localhost:8405/api/recent-images?character=${props.selectedCharacter}`)
    if (response.ok) {
      const data = await response.json()
      images.value = data.images || []
      totalImages.value = data.total || 0
      approvedCount.value = data.approved_count || 0
    }
  } catch (error) {
    console.error('Failed to load images:', error)
  } finally {
    imagesLoading.value = false
  }
}

async function loadCharacterSSoT(characterName) {
  try {
    // Get character data from Smart Feedback backend
    const response = await fetch(`http://localhost:8405/api/character/${characterName}`)
    if (response.ok) {
      characterSSoT.value = await response.json()
    }
  } catch (error) {
    console.error('Failed to load character SSoT:', error)
  }
}

async function approveImage(image) {
  try {
    const response = await fetch('http://localhost:8405/api/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_path: image.path,
        character_name: props.selectedCharacter,
        approved: true,
        project_id: props.selectedProject.id
      })
    })

    if (response.ok) {
      image.approved = true
      approvedCount.value++
      toast.add({ severity: 'success', summary: 'Approved', life: 2000 })
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Failed to approve', life: 3000 })
  }
}

async function rejectImage(image) {
  try {
    const response = await fetch('http://localhost:8405/api/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_path: image.path,
        character_name: props.selectedCharacter,
        approved: false,
        project_id: props.selectedProject.id
      })
    })

    if (response.ok) {
      image.approved = false
      if (approvedCount.value > 0) approvedCount.value--
      toast.add({ severity: 'info', summary: 'Rejected', life: 2000 })
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Failed to reject', life: 3000 })
  }
}

function showFeedbackDialog(image) {
  currentImage.value = image
  currentFeedback.value = { rating: 5, feedback: '' }
  showFeedback.value = true
}

async function submitFeedback() {
  if (!currentImage.value) return

  try {
    // Send to Smart Feedback backend for AI learning
    const response = await fetch('http://localhost:8405/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_path: currentImage.value.path,
        character_name: props.selectedCharacter,
        rating: currentFeedback.value.rating,
        feedback: currentFeedback.value.feedback
      })
    })

    if (response.ok) {
      const result = await response.json()
      toast.add({
        severity: 'success',
        summary: 'Feedback Submitted',
        detail: 'AI will learn from your feedback',
        life: 3000
      })

      // Update image status based on rating
      if (currentFeedback.value.rating >= 7) {
        await approveImage(currentImage.value)
      } else if (currentFeedback.value.rating <= 4) {
        await rejectImage(currentImage.value)
      }

      showFeedback.value = false
      loadRecentFeedback()
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Failed to submit feedback', life: 3000 })
  }
}

async function generateImages() {
  if (!props.selectedCharacter || !props.selectedProject) return

  toast.add({
    severity: 'info',
    summary: 'Generating Images',
    detail: `Creating 20 images for ${props.selectedCharacter}`,
    life: 5000
  })

  try {
    const response = await fetch('/api/anime/generate/character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: props.selectedProject.id,
        character_name: props.selectedCharacter,
        count: 20,
        style: qualityGate.value?.style,
        model: qualityGate.value?.model
      })
    })

    if (response.ok) {
      setTimeout(() => loadImages(), 3000) // Reload after a delay
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Generation failed', life: 3000 })
  }
}

async function startTraining() {
  if (!trainingReadiness.value.ready) return

  toast.add({
    severity: 'success',
    summary: 'Training Started',
    detail: `LoRA training for ${props.selectedCharacter} initiated`,
    life: 5000
  })

  try {
    const response = await fetch('/api/anime/lora/train', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: props.selectedProject.id,
        character_name: props.selectedCharacter,
        base_model: qualityGate.value.model
      })
    })

    if (response.ok) {
      const result = await response.json()
      toast.add({
        severity: 'info',
        summary: 'Training ID',
        detail: result.training_id,
        life: 8000
      })
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Failed to start training', life: 3000 })
  }
}

async function loadRecentFeedback() {
  try {
    const response = await fetch(`http://localhost:8405/api/feedback/recent?character=${props.selectedCharacter}`)
    if (response.ok) {
      recentFeedback.value = await response.json()
    }
  } catch (error) {
    console.error('Failed to load feedback:', error)
  }
}

function onPageChange(event) {
  currentPage.value = event.first
  loadImages()
}

onMounted(() => {
  if (props.selectedProject) {
    qualityGate.value = qualityGates[props.selectedProject.name] || null
  }
  if (props.selectedCharacter) {
    loadCharacterSSoT(props.selectedCharacter)
    loadImages()
    loadRecentFeedback()
  }
})
</script>

<style scoped>
.image-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}

.image-item {
  position: relative;
}

.image-wrapper {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: #1a1a1a;
  border: 1px solid #333;
}

.image-wrapper:hover .image-actions {
  opacity: 1;
}

.approval-overlay {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
}

.image-actions {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.8);
  opacity: 0;
  transition: opacity 0.2s;
}
</style>