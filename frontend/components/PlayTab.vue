<template>
  <div class="play-tab">
    <!-- Error banners -->
    <div v-if="classicStore.error && !directorActive" class="error-banner">
      {{ classicStore.error }}
      <button @click="classicStore.error = null" class="error-dismiss">&times;</button>
    </div>
    <div v-if="directorStore.error && directorActive" class="error-banner">
      {{ directorStore.error }}
      <button @click="directorStore.error = null" class="error-dismiss">&times;</button>
    </div>

    <!-- Character viewer -->
    <PlayCharacterView
      v-if="showCharacterViewer"
      @back="showCharacterViewer = false"
    />

    <!-- Director mode active -->
    <PlayDirector
      v-else-if="directorActive"
      @quit="directorStore.endSession()"
    />

    <!-- Director ending -->
    <PlayEndingScreen
      v-else-if="directorStore.isEnded && directorStore.currentScene"
      :last-scene="directorStore.currentScene"
      :scene-count="directorStore.sceneCount"
      :relationships="directorStore.relationships"
      :scenes="directorStore.sceneHistory"
      @close="directorStore.resetState()"
      @new-game="directorStore.resetState()"
    />

    <!-- Classic VN mode active -->
    <PlayScene
      v-else-if="classicStore.currentScene && !classicStore.isEnded"
      :scene="classicStore.currentScene"
      :image="classicStore.imageStatus"
      :choosing="classicStore.choosing"
      @choose="classicStore.submitChoice($event)"
      @quit="confirmQuit"
    />

    <!-- Classic ending -->
    <PlayEndingScreen
      v-else-if="classicStore.isEnded && classicStore.currentScene"
      :last-scene="classicStore.currentScene"
      :scene-count="classicStore.sceneCount"
      :relationships="classicStore.relationships"
      :scenes="classicStore.sceneHistory"
      @close="classicStore.endSession()"
      @new-game="classicStore.resetState()"
    />

    <!-- Launcher: no active game -->
    <PlayLauncher
      v-else
      :starting="classicStore.loading || directorStore.loading"
      :active-sessions="classicStore.activeSessions"
      @start="handleStart"
      @start-director="handleStartDirector"
      @resume="handleResume"
      @open-characters="showCharacterViewer = true"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useInteractiveStore } from '@/stores/interactive'
import { useDirectorStore } from '@/stores/director'
import PlayLauncher from './play/PlayLauncher.vue'
import PlayScene from './play/PlayScene.vue'
import PlayDirector from './play/PlayDirector.vue'
import PlayEndingScreen from './play/PlayEndingScreen.vue'
import PlayCharacterView from './play/PlayCharacterView.vue'

const classicStore = useInteractiveStore()
const directorStore = useDirectorStore()
const showCharacterViewer = ref(false)

const directorActive = computed(() =>
  directorStore.sessionId !== null && !directorStore.isEnded
)

onMounted(() => {
  classicStore.fetchActiveSessions()
})

async function handleStart(projectId: number) {
  await classicStore.startSession(projectId)
}

async function handleStartDirector(projectId: number) {
  await directorStore.startSession(projectId)
}

async function handleResume(sessionId: string) {
  await classicStore.resumeSession(sessionId)
}

function confirmQuit() {
  if (window.confirm('End this session? Your progress will be lost.')) {
    classicStore.endSession()
  }
}
</script>

<style scoped>
.play-tab {
  position: relative;
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(220, 50, 50, 0.15);
  border: 1px solid rgba(220, 50, 50, 0.3);
  border-radius: 8px;
  color: #f07070;
  font-size: 14px;
  margin-bottom: 16px;
}

.error-dismiss {
  background: none;
  border: none;
  color: #f07070;
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
}
</style>
