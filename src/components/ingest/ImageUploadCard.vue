<template>
  <div class="card">
    <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Upload Image</h3>
    <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
      Upload a single image directly to a character's dataset.
    </p>
    <div
      class="drop-zone"
      @drop.prevent="onImageDrop"
      @dragover.prevent
      @click="imageFileInput?.click()"
    >
      <template v-if="imageFile">
        {{ imageFile.name }}
      </template>
      <template v-else>
        Drop an image here or click to browse
      </template>
    </div>
    <input ref="imageFileInput" type="file" accept="image/*" style="display: none;" @change="onImageSelect" />
    <button
      class="btn"
      style="width: 100%; margin-top: 8px; color: var(--accent-primary);"
      @click="ingestImage"
      :disabled="!imageFile || !selectedCharacter || loading"
    >
      {{ loading ? 'Uploading...' : 'Upload' }}
    </button>
    <div v-if="result" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">
      Uploaded {{ result.image }}. Check the Pending tab.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{
  selectedCharacter: string
}>()

const emit = defineEmits<{
  error: [message: string]
}>()

const imageFile = ref<File | null>(null)
const imageFileInput = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const result = ref<{ image: string } | null>(null)

function onImageDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (file && file.type.startsWith('image/')) imageFile.value = file
}

function onImageSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) imageFile.value = file
}

async function ingestImage() {
  if (!imageFile.value) return
  loading.value = true
  result.value = null
  try {
    result.value = await api.ingestImage(imageFile.value, props.selectedCharacter)
    imageFile.value = null
  } catch (e: any) {
    emit('error', e.message || 'Image upload failed')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.drop-zone {
  border: 2px dashed var(--border-primary);
  border-radius: 4px;
  padding: 20px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  transition: border-color 150ms ease;
}
.drop-zone:hover {
  border-color: var(--accent-primary);
}
</style>
