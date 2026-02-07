<template>
  <div class="media-upload-panel">
    <div class="upload-header">
      <h3><i class="pi pi-cloud-upload"></i> Media Ingestion Point</h3>
      <div class="status-indicators">
        <Tag v-if="uploadStatus === 'ready'" value="Ready" severity="success" icon="pi pi-check" />
        <Tag v-else-if="uploadStatus === 'processing'" value="Processing" severity="warning" icon="pi pi-spin pi-spinner" />
        <Tag v-else-if="uploadStatus === 'error'" value="Error" severity="danger" icon="pi pi-times" />
      </div>
    </div>

    <!-- Upload Area -->
    <div class="upload-area"
         :class="{ 'drag-over': isDragOver, 'uploading': isUploading }"
         @dragover.prevent="isDragOver = true"
         @dragleave="isDragOver = false"
         @drop.prevent="handleDrop">

      <div class="upload-content">
        <div class="upload-icon">
          <i class="pi pi-cloud-upload" style="font-size: 3rem; color: #ff8c00;"></i>
        </div>
        <div class="upload-text">
          <h4>Drop Videos/Images Here</h4>
          <p>Or click to select files</p>
          <p class="upload-formats">Supports: MP4, AVI, MOV, JPG, PNG, WebP</p>
        </div>
        <FileUpload
          ref="fileUpload"
          mode="advanced"
          :multiple="true"
          accept="video/*,image/*"
          :max-file-size="1000000000"
          @uploader="customUploader"
          @select="onFileSelect"
          :custom-upload="true"
          :auto="false"
          class="hidden-uploader">
          <template #empty>
            <Button label="Choose Files" icon="pi pi-upload" @click="$refs.fileUpload.choose()" />
          </template>
        </FileUpload>
      </div>
    </div>

    <!-- Processing Queue -->
    <div v-if="processingQueue.length > 0" class="processing-queue">
      <h4><i class="pi pi-clock"></i> Processing Queue</h4>
      <div v-for="item in processingQueue" :key="item.id" class="queue-item">
        <div class="queue-info">
          <span class="filename">{{ item.name }}</span>
          <span class="filesize">{{ formatFileSize(item.size) }}</span>
        </div>
        <div class="queue-progress">
          <ProgressBar :value="item.progress" :show-value="false" />
          <span class="progress-text">{{ item.status }}</span>
        </div>
      </div>
    </div>

    <!-- Recent Uploads -->
    <div v-if="recentUploads.length > 0" class="recent-uploads">
      <h4><i class="pi pi-history"></i> Recent Uploads</h4>
      <div class="upload-grid">
        <div v-for="upload in recentUploads" :key="upload.id"
             class="upload-card" @click="viewUpload(upload)">

          <!-- Video Thumbnail -->
          <div v-if="upload.type === 'video'" class="upload-thumbnail video-thumb">
            <i class="pi pi-play-circle"></i>
            <div class="duration">{{ formatDuration(upload.metadata.duration) }}</div>
          </div>

          <!-- Image Thumbnail -->
          <div v-else class="upload-thumbnail image-thumb">
            <img :src="getImageThumbnail(upload)" alt="thumbnail" />
          </div>

          <div class="upload-details">
            <div class="upload-name">{{ upload.name }}</div>
            <div class="upload-meta">
              <span class="resolution">{{ upload.metadata.resolution }}</span>
              <span class="characters" v-if="upload.characters">
                {{ upload.characters.join(', ') }}
              </span>
            </div>
            <div class="upload-actions">
              <Tag v-if="upload.auto_generated" value="Auto-Generated" severity="info" class="text-xs" />
              <Tag v-if="upload.loras_trained" value="LoRAs Ready" severity="success" class="text-xs" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Auto-Generation Settings -->
    <div class="auto-generation-settings">
      <h4><i class="pi pi-cog"></i> Auto-Generation Settings</h4>

      <div class="setting-row">
        <label class="setting-label">
          <Checkbox v-model="autoSettings.enabled" binary />
          Enable Auto-Generation
        </label>
      </div>

      <div v-if="autoSettings.enabled" class="setting-group">
        <div class="setting-row">
          <label>Generation Style:</label>
          <Dropdown v-model="autoSettings.style"
                   :options="styleOptions"
                   option-label="label"
                   option-value="value" />
        </div>

        <div class="setting-row">
          <label>Character Detection:</label>
          <Dropdown v-model="autoSettings.detection"
                   :options="detectionOptions"
                   option-label="label"
                   option-value="value" />
        </div>

        <div class="setting-row">
          <label class="setting-label">
            <Checkbox v-model="autoSettings.train_loras" binary />
            Auto-Train LoRAs
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useToast } from 'primevue/usetoast'

const toast = useToast()

// Upload state
const uploadStatus = ref('ready')
const isDragOver = ref(false)
const isUploading = ref(false)
const processingQueue = ref([])
const recentUploads = ref([])

// Auto-generation settings
const autoSettings = ref({
  enabled: true,
  style: 'movie_realistic',
  detection: 'high_confidence',
  train_loras: true
})

const styleOptions = [
  { label: 'Movie Realistic', value: 'movie_realistic' },
  { label: 'Anime Style', value: 'anime' },
  { label: 'Game Style', value: 'game_style' },
  { label: 'Mixed Style', value: 'mixed' }
]

const detectionOptions = [
  { label: 'High Confidence', value: 'high_confidence' },
  { label: 'Medium Confidence', value: 'medium_confidence' },
  { label: 'Low Confidence', value: 'low_confidence' },
  { label: 'All Detected', value: 'all_detected' }
]

// File handling
const handleDrop = async (event) => {
  isDragOver.value = false
  const files = Array.from(event.dataTransfer.files)
  await processFiles(files)
}

const onFileSelect = (event) => {
  processFiles(event.files)
}

const customUploader = async (event) => {
  await processFiles(event.files)
}

const processFiles = async (files) => {
  isUploading.value = true
  uploadStatus.value = 'processing'

  for (const file of files) {
    const uploadItem = {
      id: Date.now() + Math.random(),
      name: file.name,
      size: file.size,
      progress: 0,
      status: 'Uploading...'
    }

    processingQueue.value.push(uploadItem)

    try {
      // Upload to ingestion point
      await uploadToIngestionPoint(file, uploadItem)

      // Trigger processing
      if (autoSettings.value.enabled) {
        await triggerAutoProcessing(file, uploadItem)
      }

      uploadItem.status = 'Complete'
      uploadItem.progress = 100

      toast.add({
        severity: 'success',
        summary: 'Upload Complete',
        detail: `${file.name} processed successfully`,
        life: 3000
      })

    } catch (error) {
      uploadItem.status = `Error: ${error.message}`
      uploadItem.progress = 0

      toast.add({
        severity: 'error',
        summary: 'Upload Failed',
        detail: `Failed to process ${file.name}`,
        life: 5000
      })
    }
  }

  isUploading.value = false
  uploadStatus.value = 'ready'

  // Clear completed items after 3 seconds
  setTimeout(() => {
    processingQueue.value = processingQueue.value.filter(item => item.status.includes('Error'))
  }, 3000)

  // Refresh recent uploads
  await loadRecentUploads()
}

const uploadToIngestionPoint = async (file, uploadItem) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('auto_process', autoSettings.value.enabled)
  formData.append('settings', JSON.stringify(autoSettings.value))

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        uploadItem.progress = (e.loaded / e.total) * 50 // 50% for upload
        uploadItem.status = `Uploading... ${Math.round(uploadItem.progress)}%`
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status === 200) {
        uploadItem.progress = 50
        uploadItem.status = 'Processing...'
        resolve(JSON.parse(xhr.responseText))
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`))
      }
    })

    xhr.addEventListener('error', () => {
      reject(new Error('Network error'))
    })

    xhr.open('POST', '/api/upload/media')
    xhr.send(formData)
  })
}

const triggerAutoProcessing = async (file, uploadItem) => {
  try {
    const response = await fetch('/api/process/auto-generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        filename: file.name,
        settings: autoSettings.value
      })
    })

    if (!response.ok) {
      throw new Error(`Auto-processing failed: ${response.status}`)
    }

    const result = await response.json()

    uploadItem.progress = 100
    uploadItem.status = `Generated ${result.images_created || 0} images`

    return result

  } catch (error) {
    uploadItem.status = `Processing error: ${error.message}`
    throw error
  }
}

const loadRecentUploads = async () => {
  try {
    const response = await fetch('/api/uploads/recent?limit=12')
    const data = await response.json()
    recentUploads.value = data.uploads || []
  } catch (error) {
    console.error('Failed to load recent uploads:', error)
  }
}

const viewUpload = (upload) => {
  // Emit event to parent or navigate to detailed view
  toast.add({
    severity: 'info',
    summary: 'Upload Details',
    detail: `Viewing ${upload.name}`,
    life: 2000
  })
}

const getImageThumbnail = (upload) => {
  return `/api/uploads/thumbnail/${upload.id}`
}

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDuration = (seconds) => {
  if (!seconds) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onMounted(() => {
  loadRecentUploads()

  // Load settings from localStorage
  const savedSettings = localStorage.getItem('auto-generation-settings')
  if (savedSettings) {
    autoSettings.value = { ...autoSettings.value, ...JSON.parse(savedSettings) }
  }
})

// Watch for settings changes and save to localStorage
watch(autoSettings, (newSettings) => {
  localStorage.setItem('auto-generation-settings', JSON.stringify(newSettings))
}, { deep: true })
</script>

<style scoped>
.media-upload-panel {
  padding: 1.5rem;
  background: #111;
  height: 100%;
  overflow-y: auto;
}

.upload-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #333;
}

.upload-header h3 {
  margin: 0;
  color: #ff8c00;
}

.upload-area {
  border: 2px dashed #444;
  border-radius: 12px;
  padding: 3rem 2rem;
  text-align: center;
  margin-bottom: 2rem;
  transition: all 0.3s ease;
  background: #0a0a0a;
  position: relative;
  overflow: hidden;
}

.upload-area.drag-over {
  border-color: #ff8c00;
  background: rgba(255, 140, 0, 0.1);
}

.upload-area.uploading {
  border-color: #00ff00;
  background: rgba(0, 255, 0, 0.05);
}

.upload-content {
  position: relative;
  z-index: 2;
}

.upload-icon {
  margin-bottom: 1rem;
}

.upload-text h4 {
  margin: 0 0 0.5rem 0;
  color: #e0e0e0;
  font-size: 1.25rem;
}

.upload-text p {
  margin: 0.25rem 0;
  color: #999;
}

.upload-formats {
  font-size: 0.9rem;
  color: #666;
}

.hidden-uploader {
  display: none;
}

.processing-queue {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.processing-queue h4 {
  margin: 0 0 1rem 0;
  color: #ff8c00;
}

.queue-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid #333;
}

.queue-item:last-child {
  border-bottom: none;
}

.queue-info {
  flex: 1;
}

.filename {
  font-weight: 600;
  color: #e0e0e0;
  display: block;
}

.filesize {
  font-size: 0.9rem;
  color: #999;
}

.queue-progress {
  flex: 1;
  margin-left: 2rem;
  text-align: right;
}

.progress-text {
  margin-top: 0.25rem;
  font-size: 0.8rem;
  color: #999;
  display: block;
}

.recent-uploads {
  margin-bottom: 2rem;
}

.recent-uploads h4 {
  margin: 0 0 1rem 0;
  color: #ff8c00;
}

.upload-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}

.upload-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
}

.upload-card:hover {
  border-color: #ff8c00;
  transform: translateY(-2px);
}

.upload-thumbnail {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0a0a;
  position: relative;
}

.video-thumb {
  font-size: 2rem;
  color: #ff8c00;
}

.video-thumb .duration {
  position: absolute;
  bottom: 0.5rem;
  right: 0.5rem;
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
}

.image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.upload-details {
  padding: 1rem;
}

.upload-name {
  font-weight: 600;
  color: #e0e0e0;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.upload-meta {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.resolution {
  font-size: 0.8rem;
  color: #999;
}

.characters {
  font-size: 0.8rem;
  color: #ff8c00;
}

.upload-actions {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.auto-generation-settings {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 1.5rem;
}

.auto-generation-settings h4 {
  margin: 0 0 1rem 0;
  color: #ff8c00;
}

.setting-group {
  margin-left: 1.5rem;
  padding-left: 1rem;
  border-left: 2px solid #333;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  gap: 1rem;
}

.setting-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #e0e0e0;
  cursor: pointer;
}

.setting-row label:not(.setting-label) {
  color: #ccc;
  min-width: 140px;
}
</style>