<template>
  <div class="scene-builder-root" :class="{ 'has-sidebar': currentView !== 'library' }">
    <SceneSidebar v-if="currentView !== 'library'" />
    <div class="scene-builder-content">
    <div v-if="currentView === 'library' && selectedProjectId" style="display: flex; gap: 8px; margin-bottom: 16px; align-items: center;">
      <button class="btn btn-primary" @click="store.openNewScene">+ New Scene</button>
      <button
        v-if="scenes.length > 0 && authStore.isAdvanced"
        class="btn"
        :disabled="generatingTraining"
        @click="store.generateTrainingFromScenes"
        title="Generate LoRA training images with poses matching your scene descriptions"
      >{{ generatingTraining ? 'Generating...' : 'Train for Scenes' }}</button>
    </div>

    <!-- Sub-view toggle (Scenes / Episodes) — hidden when episodes extracted to Publish tab -->
    <div v-if="currentView === 'library' && selectedProjectId && !hideEpisodes" style="display: flex; gap: 4px; margin-bottom: 16px;">
      <button
        :class="['btn', librarySubView === 'scenes' ? 'btn-primary' : '']"
        style="font-size: 12px; padding: 4px 14px;"
        @click="librarySubView = 'scenes'"
      >Scenes</button>
      <button
        :class="['btn', librarySubView === 'episodes' ? 'btn-primary' : '']"
        style="font-size: 12px; padding: 4px 14px;"
        @click="librarySubView = 'episodes'"
      >Episodes</button>
    </div>

    <!-- VIEW 1a: Scene Library -->
    <SceneLibraryView
      v-if="currentView === 'library' && librarySubView === 'scenes'"
      :scenes="scenes"
      :loading="loading"
      :has-project="!!selectedProjectId"
      :generating-from-story="generatingFromStory"
      :gap-by-scene-id="gapBySceneId"
      @edit="store.openEditor"
      @monitor="store.openMonitor"
      @play="store.playSceneVideo"
      @delete="store.deleteScene"
      @generate-from-story="store.generateFromStory"
    />

    <!-- VIEW 1b: Episodes -->
    <EpisodeView
      v-if="currentView === 'library' && librarySubView === 'episodes'"
      :project-id="selectedProjectId"
      :scenes="scenes"
      @play-episode="store.playEpisodeVideo"
    />

    <!-- VIEW 2: Scene Editor -->
    <SceneEditorView
      v-if="currentView === 'editor'"
      :scene="editScene"
      :scene-id="editSceneId"
      :shots="editShots"
      :selected-shot-idx="selectedShotIdx"
      :saving="saving"
      :generating="generating"
      :shot-video-src="currentShotVideoSrc"
      :source-image-url="store.sourceImageUrl"
      :characters="projectCharacters"
      :gap-characters="gapByCharSlug"
      @save="store.saveScene"
      @confirm-generate="store.confirmGenerate"
      @back="store.backToLibrary"
      @select-shot="store.selectShot"
      @add-shot="store.addShot"
      @remove-shot="store.removeShot"
      @browse-image="store.openImagePickerAction"
      @auto-assign="store.autoAssignAll"
      @update-shot-field="store.updateShotField"
      @update-scene="store.onUpdateScene"
      @audio-changed="store.onAudioChanged"
      @go-to-training="goToTraining"
    />

    <!-- VIEW 3: Generation Monitor -->
    <GenerationMonitorView
      v-if="currentView === 'monitor'"
      :scene-title="editScene.title || ''"
      :monitor-status="monitorStatus"
      :scene-video-src="sceneVideoSrc"
      @back="store.backToLibrary"
      @retry-shot="store.retryShot"
      @play-shot="store.playShotVideo"
      @reassemble="store.reassemble"
    />

    <!-- Image Picker Modal -->
    <ImagePickerModal
      :visible="showImagePicker"
      :loading="loadingImages"
      :approved-images="approvedImages"
      :image-url="store.imageUrl"
      :characters-present="currentShotCharacters"
      :recommendations="currentShotRecommendations"
      :current-shot-type="currentShotType"
      @close="showImagePicker = false"
      @select="store.selectImage"
    />

    <!-- Video Player Modal -->
    <div v-if="showVideoPlayer" style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center;" @click.self="showVideoPlayer = false" @keydown.escape.window="showVideoPlayer = false">
      <div style="max-width: 90vw; max-height: 90vh;">
        <video :src="videoPlayerSrc" controls autoplay style="max-width: 100%; max-height: 85vh; border-radius: 4px;"></video>
        <div style="text-align: center; margin-top: 8px;">
          <button class="btn" @click="showVideoPlayer = false">Close</button>
        </div>
      </div>
    </div>

    <!-- Generate Confirmation -->
    <div v-if="showGenerateConfirm" style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center;" @click.self="showGenerateConfirm = false" @keydown.escape.window="showGenerateConfirm = false">
      <div class="card" style="width: 400px;">
        <div style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">Start Scene Generation?</div>
        <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 16px;">
          This will generate {{ editShots.length }} shot{{ editShots.length !== 1 ? 's' : '' }} sequentially with
          FramePack. Each shot's last frame becomes the next shot's first frame for continuity.
        </div>
        <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
          Estimated time: ~{{ store.estimateMinutes(editShots) }} minutes
        </div>
        <div v-if="generationUnreadyChars.length > 0" style="border-left: 3px solid var(--status-warning); background: rgba(160, 128, 80, 0.1); padding: 10px 12px; margin-bottom: 16px; border-radius: 0 4px 4px 0;">
          <div style="font-size: 12px; font-weight: 500; color: var(--status-warning); margin-bottom: 6px;">Characters without LoRA</div>
          <div v-for="c in generationUnreadyChars" :key="c.slug" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 2px;">
            {{ c.name }} — {{ c.reason }}
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">
            FramePack doesn't use LoRAs directly, but source image quality depends on training data.
          </div>
        </div>
        <div style="display: flex; gap: 8px; justify-content: flex-end;">
          <button class="btn" @click="showGenerateConfirm = false">Cancel</button>
          <button class="btn btn-success" @click="store.startGeneration">Generate</button>
        </div>
      </div>
    </div>
    </div><!-- .scene-builder-content -->
  </div>
</template>

<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '@/stores/project'
import { useAuthStore } from '@/stores/auth'
import { useSceneEditorStore } from '@/stores/sceneEditor'
import SceneSidebar from './scenes/SceneSidebar.vue'
import SceneLibraryView from './scenes/SceneLibraryView.vue'
import SceneEditorView from './scenes/SceneEditorView.vue'
import GenerationMonitorView from './scenes/GenerationMonitorView.vue'
import ImagePickerModal from './scenes/ImagePickerModal.vue'
import EpisodeView from './scenes/EpisodeView.vue'

const props = withDefaults(defineProps<{
  hideEpisodes?: boolean
  projectId?: number
}>(), {
  hideEpisodes: false,
  projectId: 0,
})

const router = useRouter()
const route = useRoute()
const projectStore = useProjectStore()
const authStore = useAuthStore()
const store = useSceneEditorStore()

const {
  selectedProjectId,
  scenes,
  currentView,
  librarySubView,
  editScene,
  editShots,
  selectedShotIdx,
  editSceneId,
  loading,
  saving,
  generating,
  generatingFromStory,
  generatingTraining,
  monitorStatus,
  showImagePicker,
  loadingImages,
  approvedImages,
  showVideoPlayer,
  videoPlayerSrc,
  showGenerateConfirm,
  gapBySceneId,
  gapByCharSlug,
  generationUnreadyChars,
  currentShotCharacters,
  currentShotRecommendations,
  currentShotType,
  projectCharacters,
  sceneVideoSrc,
  currentShotVideoSrc,
} = storeToRefs(store)

// Init project from prop
if (props.projectId) {
  selectedProjectId.value = props.projectId
}

// Sync with parent-provided projectId prop
watch(() => props.projectId, (pid) => {
  if (pid && pid !== selectedProjectId.value) {
    selectedProjectId.value = pid
  }
})

// Load projects on mount
store.loadProjects()

watch(selectedProjectId, async (pid) => {
  if (!pid) {
    scenes.value = []
    store.gapAnalysis = null
    return
  }
  await store.loadScenes()
  store.loadGapAnalysis()
  projectStore.fetchProjectDetail(pid)
})

// Deep-link: open scene/shot from query params (e.g. from Review > Edit Shot)
onMounted(async () => {
  const qScene = route.query.scene_id as string | undefined
  const qShot = route.query.shot_id as string | undefined
  if (qScene) {
    const waitForScenes = () => new Promise<void>(resolve => {
      if (scenes.value.length > 0 || !selectedProjectId.value) return resolve()
      const stop = watch(scenes, () => { stop(); resolve() })
    })
    await waitForScenes()
    const target = scenes.value.find(s => s.id === qScene)
    if (target) {
      await store.openEditor(target)
      if (qShot) {
        const shotIdx = editShots.value.findIndex(s => (s as any).id === qShot)
        if (shotIdx >= 0) selectedShotIdx.value = shotIdx
      }
    }
    router.replace({ query: {} })
  }
})

function goToTraining() {
  router.push('/train')
}

onUnmounted(() => {
  store.cleanup()
})
</script>

<style scoped>
.scene-builder-root {
  height: 100%;
}

.scene-builder-root.has-sidebar {
  display: flex;
  height: calc(100vh - 96px);
  overflow: hidden;
}

.scene-builder-content {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

.scene-builder-root:not(.has-sidebar) .scene-builder-content {
  padding: 0;
}

.scene-builder-root.has-sidebar .scene-builder-content {
  padding: 0;
}
</style>
