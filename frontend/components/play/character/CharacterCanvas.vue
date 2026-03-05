<template>
  <div class="character-canvas">
    <!-- Portrait display -->
    <div class="portrait-container" :class="{ 'has-image': portraitUrl }">
      <transition name="portrait-fade" mode="out-in">
        <img
          v-if="portraitUrl"
          :key="portraitUrl"
          :src="portraitUrl"
          class="portrait-image"
          alt="Character portrait"
          @load="imageLoaded = true"
        />
        <div v-else class="portrait-placeholder">
          <span class="placeholder-icon">&#x2606;</span>
          <span class="placeholder-text">No portrait</span>
        </div>
      </transition>

      <!-- Generating overlay -->
      <transition name="fade">
        <div v-if="generating" class="gen-overlay">
          <div class="gen-spinner" />
          <span class="gen-text">Generating...</span>
        </div>
      </transition>

      <!-- Clickable hotspot regions -->
      <div class="hotspots">
        <button
          v-for="zone in hotspotZones"
          :key="zone.part"
          class="hotspot"
          :class="{ active: activePart === zone.part }"
          :style="zone.style"
          :title="zone.label"
          @click="$emit('select-part', zone.part)"
        >
          <span class="hotspot-dot" />
        </button>
      </div>
    </div>

    <!-- Character name -->
    <div v-if="name" class="character-name">{{ name }}</div>

    <!-- Generate button -->
    <button
      class="generate-btn"
      :disabled="generating || !slug"
      @click="$emit('generate')"
    >
      <span class="btn-icon">&#x2728;</span>
      {{ generating ? 'Generating...' : 'Generate Portrait' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { BodyPart } from '@/stores/characterViewer'

defineProps<{
  portraitUrl: string | null
  name: string
  slug: string
  activePart: BodyPart
  generating: boolean
}>()

defineEmits<{
  'select-part': [part: BodyPart]
  generate: []
}>()

const imageLoaded = ref(false)

const hotspotZones: { part: BodyPart; label: string; style: Record<string, string> }[] = [
  { part: 'hair', label: 'Hair', style: { top: '5%', left: '50%', width: '40%', height: '15%' } },
  { part: 'face', label: 'Face', style: { top: '18%', left: '50%', width: '30%', height: '12%' } },
  { part: 'eyes', label: 'Eyes', style: { top: '22%', left: '50%', width: '26%', height: '6%' } },
  { part: 'skin', label: 'Skin', style: { top: '30%', left: '50%', width: '24%', height: '8%' } },
  { part: 'body', label: 'Body', style: { top: '40%', left: '50%', width: '36%', height: '20%' } },
  { part: 'outfit', label: 'Outfit', style: { top: '55%', left: '50%', width: '40%', height: '25%' } },
  { part: 'accessories', label: 'Accessories', style: { top: '80%', left: '50%', width: '34%', height: '12%' } },
]
</script>

<style scoped>
.character-canvas {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 20px;
}

.portrait-container {
  position: relative;
  width: 100%;
  max-width: 360px;
  aspect-ratio: 3/4;
  border-radius: 16px;
  overflow: hidden;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  transition: border-color 0.3s ease;
}

.portrait-container.has-image {
  border-color: rgba(99,102,241,0.2);
}

.portrait-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.portrait-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-muted, #666);
}

.placeholder-icon {
  font-size: 48px;
  opacity: 0.3;
}

.placeholder-text {
  font-size: 13px;
  opacity: 0.5;
}

/* Hotspot overlay */
.hotspots {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.hotspot {
  position: absolute;
  transform: translateX(-50%);
  background: transparent;
  border: none;
  cursor: pointer;
  pointer-events: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.hotspot:hover .hotspot-dot,
.hotspot.active .hotspot-dot {
  opacity: 1;
  transform: scale(1);
}

.hotspot-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(99,102,241,0.7);
  border: 2px solid rgba(255,255,255,0.8);
  opacity: 0;
  transform: scale(0.5);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 0 8px rgba(99,102,241,0.4);
}

.hotspot.active .hotspot-dot {
  background: rgba(99,102,241,1);
  box-shadow: 0 0 12px rgba(99,102,241,0.6);
}

/* Generate overlay */
.gen-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(4px);
}

.gen-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(99,102,241,0.3);
  border-top-color: rgba(99,102,241,1);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.gen-text {
  color: rgba(255,255,255,0.8);
  font-size: 13px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Character name */
.character-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #e8e8e8);
  letter-spacing: 0.02em;
}

/* Generate button */
.generate-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  background: rgba(99,102,241,0.15);
  border: 1px solid rgba(99,102,241,0.3);
  border-radius: 10px;
  color: var(--accent-primary, #6366f1);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.25s ease;
}

.generate-btn:hover:not(:disabled) {
  background: rgba(99,102,241,0.25);
  border-color: rgba(99,102,241,0.5);
}

.generate-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-icon {
  font-size: 14px;
}

/* Transitions */
.portrait-fade-enter-active,
.portrait-fade-leave-active {
  transition: opacity 0.4s ease;
}
.portrait-fade-enter-from,
.portrait-fade-leave-to {
  opacity: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
