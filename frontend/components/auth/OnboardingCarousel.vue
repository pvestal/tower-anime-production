<template>
  <div class="onboarding-page">
    <div class="onboarding-card">
      <div class="carousel">
        <transition :name="slideDirection" mode="out-in">
          <div :key="currentSlide" class="slide">
            <!-- Slide 1 -->
            <template v-if="currentSlide === 0">
              <div class="slide-icon">&#127916;</div>
              <h2>Welcome to the Studio</h2>
              <p>Your personal anime production house. Create characters, write scenes, generate images and video — all from one place.</p>
            </template>
            <!-- Slide 2 -->
            <template v-if="currentSlide === 1">
              <div class="slide-icon">&#128218;</div>
              <h2>Your Projects</h2>
              <p>Each project is a movie production with its own visual style, characters, and story. Browse projects in the Story tab.</p>
            </template>
            <!-- Slide 3 -->
            <template v-if="currentSlide === 2">
              <div class="slide-icon">&#127917;</div>
              <h2>Your Cast</h2>
              <p>Characters are your actors. The system learns their faces from reference images and generates them consistently across scenes.</p>
            </template>
            <!-- Slide 4 -->
            <template v-if="currentSlide === 3">
              <div class="slide-icon">&#9881;&#65039;</div>
              <h2>The Pipeline</h2>
              <p>Write scenes, generate images, create video, review quality, then publish. Each step builds on the last.</p>
              <div class="pipeline-visual">
                <span>Story</span>
                <span class="arrow">→</span>
                <span>Cast</span>
                <span class="arrow">→</span>
                <span>Script</span>
                <span class="arrow">→</span>
                <span>Produce</span>
                <span class="arrow">→</span>
                <span>Review</span>
                <span class="arrow">→</span>
                <span>Publish</span>
              </div>
            </template>
            <!-- Slide 5 -->
            <template v-if="currentSlide === 4">
              <div class="slide-icon">&#128640;</div>
              <h2>Let's Go!</h2>
              <p>Choose how much detail you want to see:</p>
              <div class="mode-choice">
                <button
                  class="mode-btn"
                  :class="{ active: selectedMode === 'easy' }"
                  @click="selectedMode = 'easy'"
                >
                  <strong>Easy</strong>
                  <span>Clean interface, just the essentials</span>
                </button>
                <button
                  class="mode-btn"
                  :class="{ active: selectedMode === 'advanced' }"
                  @click="selectedMode = 'advanced'"
                >
                  <strong>Advanced</strong>
                  <span>Full controls: CFG, samplers, orchestrator</span>
                </button>
              </div>
            </template>
          </div>
        </transition>
      </div>

      <!-- Navigation -->
      <div class="nav-controls">
        <button v-if="currentSlide > 0" class="btn" @click="prev">Back</button>
        <span v-else></span>

        <div class="dots">
          <span
            v-for="i in totalSlides"
            :key="i"
            class="dot"
            :class="{ active: i - 1 === currentSlide }"
            @click="currentSlide = i - 1"
          ></span>
        </div>

        <button v-if="currentSlide < totalSlides - 1" class="btn btn-primary" @click="next">Next</button>
        <button v-else class="btn btn-primary" @click="finish">Start Exploring</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { createRequest } from '@/api/base'

const request = createRequest('/api')
const authStore = useAuthStore()
const router = useRouter()

const totalSlides = 5
const currentSlide = ref(0)
const slideDirection = ref('slide-left')
const selectedMode = ref<'easy' | 'advanced'>('easy')

function next() {
  slideDirection.value = 'slide-left'
  if (currentSlide.value < totalSlides - 1) currentSlide.value++
}

function prev() {
  slideDirection.value = 'slide-right'
  if (currentSlide.value > 0) currentSlide.value--
}

async function finish() {
  // Save mode preference and mark onboarded
  try {
    await request('/studio/auth/me/preferences', {
      method: 'PATCH',
      body: JSON.stringify({ ui_mode: selectedMode.value, onboarded: true }),
    })
    if (authStore.user) {
      authStore.user.ui_mode = selectedMode.value
      authStore.user.onboarded = true
    }
  } catch { /* proceed anyway */ }
  router.push('/story')
}
</script>

<style scoped>
.onboarding-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
}

.onboarding-card {
  width: 100%;
  max-width: 560px;
  padding: 48px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 16px;
}

.slide {
  text-align: center;
  min-height: 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.slide-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.slide h2 {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.slide p {
  font-size: 15px;
  color: var(--text-secondary);
  line-height: 1.6;
  max-width: 400px;
}

.pipeline-visual {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 20px;
  font-size: 13px;
  color: var(--accent-primary);
  flex-wrap: wrap;
  justify-content: center;
}

.pipeline-visual .arrow {
  color: var(--text-muted);
}

.mode-choice {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.mode-btn {
  flex: 1;
  padding: 16px;
  border: 2px solid var(--border-primary);
  border-radius: 10px;
  background: var(--bg-tertiary);
  cursor: pointer;
  text-align: left;
  transition: border-color 150ms;
}

.mode-btn:hover {
  border-color: var(--border-focus);
}

.mode-btn.active {
  border-color: var(--accent-primary);
  background: rgba(122, 162, 247, 0.1);
}

.mode-btn strong {
  display: block;
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.mode-btn span {
  font-size: 12px;
  color: var(--text-muted);
}

/* Navigation */
.nav-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 32px;
}

.dots {
  display: flex;
  gap: 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  cursor: pointer;
  transition: background 150ms;
}

.dot.active {
  background: var(--accent-primary);
}

/* Slide transitions */
.slide-left-enter-active,
.slide-left-leave-active,
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 250ms ease, opacity 250ms ease;
}

.slide-left-enter-from { transform: translateX(40px); opacity: 0; }
.slide-left-leave-to { transform: translateX(-40px); opacity: 0; }
.slide-right-enter-from { transform: translateX(-40px); opacity: 0; }
.slide-right-leave-to { transform: translateX(40px); opacity: 0; }
</style>
