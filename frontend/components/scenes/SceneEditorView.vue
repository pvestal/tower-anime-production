<template>
  <div style="display: flex; gap: 0; height: 100%; overflow: hidden;">
    <!-- Left: Scene Details (collapsible sections) -->
    <div class="card" style="width: 280px; flex-shrink: 0; overflow-y: auto; height: 100%; border-radius: 0; border-right: 1px solid var(--border-primary);">
      <!-- Scene Info (always open) -->
      <div class="sidebar-group">
        <div style="font-size: 13px; font-weight: 500; margin-bottom: 12px; color: var(--accent-primary);">Scene Details</div>
        <div class="field-group">
          <label class="field-label">Title</label>
          <input v-model="localScene.title" type="text" placeholder="Scene title" class="field-input" />
        </div>
        <div class="field-group">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
            <label class="field-label" style="margin-bottom: 0;">Description</label>
            <EchoAssistButton
              context-type="concept"
              :context-payload="echoScenePayload"
              :current-value="localScene.description || ''"
              compact
              @accept="localScene.description = $event.suggestion"
            />
          </div>
          <textarea v-model="localScene.description" rows="3" class="field-input field-textarea"></textarea>
        </div>
        <div class="field-group">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
            <label class="field-label" style="margin-bottom: 0;">Location</label>
            <EchoAssistButton
              context-type="scene_location"
              :context-payload="{
                project_name: projectStore.currentProject?.name,
                project_genre: projectStore.currentProject?.genre ?? undefined,
                storyline_summary: storyline?.summary ?? undefined,
                scene_description: localScene.description ?? undefined,
              }"
              :current-value="localScene.location || ''"
              compact
              @accept="localScene.location = $event.suggestion"
            />
          </div>
          <input v-model="localScene.location" type="text" placeholder="dark alley, rooftop..." class="field-input" />
        </div>
      </div>

      <!-- Environment (collapsible) -->
      <div class="sidebar-group">
        <button class="section-toggle" @click="sectionOpen.environment = !sectionOpen.environment">
          <span class="toggle-chevron">{{ sectionOpen.environment ? '\u25BE' : '\u25B8' }}</span>
          Environment
        </button>
        <div v-if="sectionOpen.environment" class="section-body">
          <div class="field-group">
            <label class="field-label">Time</label>
            <SegmentedControl
              :model-value="localScene.time_of_day || ''"
              :options="timeSegmentOptions"
              size="sm"
              @update:model-value="localScene.time_of_day = $event as string"
            />
          </div>
          <div class="field-group">
            <label class="field-label">Weather</label>
            <SegmentedControl
              :model-value="localScene.weather || ''"
              :options="weatherSegmentOptions"
              size="sm"
              @update:model-value="localScene.weather = $event as string"
            />
          </div>
          <div class="field-group">
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
              <label class="field-label" style="margin-bottom: 0;">Mood</label>
              <EchoAssistButton
                context-type="scene_mood"
                :context-payload="{
                  project_name: projectStore.currentProject?.name,
                  project_genre: projectStore.currentProject?.genre ?? undefined,
                  storyline_theme: storyline?.tone ?? undefined,
                  scene_description: localScene.description ?? undefined,
                }"
                :current-value="localScene.mood || ''"
                compact
                @accept="localScene.mood = $event.suggestion"
              />
            </div>
            <input v-model="localScene.mood" type="text" placeholder="tense, peaceful..." class="field-input" />
          </div>
        </div>
      </div>

      <!-- Technical (collapsed by default) -->
      <div class="sidebar-group">
        <button class="section-toggle" @click="sectionOpen.technical = !sectionOpen.technical">
          <span class="toggle-chevron">{{ sectionOpen.technical ? '\u25BE' : '\u25B8' }}</span>
          Technical
        </button>
        <div v-if="sectionOpen.technical" class="section-body">
          <div class="field-group">
            <label class="field-label">Target Duration (s)</label>
            <input v-model.number="localScene.target_duration_seconds" type="number" min="5" max="300" class="field-input" />
          </div>
          <div class="field-group">
            <label class="field-label">Interpolation</label>
            <SegmentedControl
              :model-value="localPostInterpolate"
              :options="[{ value: null, label: 'Off' }, { value: 60, label: '60fps' }]"
              size="sm"
              @update:model-value="localPostInterpolate = $event as number | null"
            />
          </div>
          <div class="field-group">
            <label class="field-label">Upscale</label>
            <SegmentedControl
              :model-value="localPostUpscale"
              :options="[{ value: null, label: 'Off' }, { value: 2, label: '2x' }]"
              size="sm"
              @update:model-value="localPostUpscale = $event as number | null"
            />
          </div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">
            {{ shots.length }} shots, est. {{ estimateMinutes(shots) }} min gen time
          </div>
          <!-- Training readiness warning -->
          <div v-if="unreadyCharacters.length > 0" style="border-left: 3px solid var(--status-warning); background: rgba(160, 128, 80, 0.1); padding: 8px 10px; margin-top: 10px; border-radius: 0 4px 4px 0;">
            <div style="font-size: 11px; font-weight: 500; color: var(--status-warning); margin-bottom: 4px;">Characters without LoRA</div>
            <div v-for="c in unreadyCharacters" :key="c.slug" style="font-size: 11px; color: var(--text-secondary); margin-bottom: 2px;">
              {{ c.name }} — {{ c.reason }}
            </div>
            <button class="btn" style="font-size: 11px; padding: 2px 8px; margin-top: 6px;" @click="emit('go-to-training')">Go to Training tab</button>
          </div>
        </div>
      </div>

      <!-- Story Arc (collapsed) -->
      <div v-if="storyArcs.length > 0 || hasStoryContext" class="sidebar-group">
        <button class="section-toggle" @click="sectionOpen.storyArc = !sectionOpen.storyArc">
          <span class="toggle-chevron">{{ sectionOpen.storyArc ? '\u25BE' : '\u25B8' }}</span>
          Story Arc
        </button>
        <div v-if="sectionOpen.storyArc" class="section-body">
          <div v-if="storyArcs.length > 0" class="field-group">
            <label class="field-label">Story Arc</label>
            <select v-model="localStoryArc" class="field-input">
              <option value="">None</option>
              <option v-for="arc in storyArcs" :key="arc" :value="arc">{{ arc }}</option>
            </select>
          </div>
          <template v-if="hasStoryContext">
            <div v-if="storyline?.summary" style="margin-bottom: 8px;">
              <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">Summary</div>
              <div style="color: var(--text-secondary); line-height: 1.4; font-size: 12px;">{{ storyline.summary }}</div>
            </div>
            <div v-if="storyline?.theme" style="margin-bottom: 8px;">
              <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">Theme</div>
              <div style="color: var(--text-secondary); font-size: 12px;">{{ storyline.theme }}</div>
            </div>
            <div v-if="storyline?.tone" style="margin-bottom: 8px;">
              <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">Tone</div>
              <div style="color: var(--text-secondary); font-size: 12px;">{{ storyline.tone }}</div>
            </div>
            <div v-if="worldLocation" style="margin-bottom: 8px;">
              <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">World</div>
              <div style="color: var(--text-secondary); font-size: 12px;">{{ worldLocation }}</div>
            </div>
          </template>
        </div>
      </div>

      <!-- Audio (collapsible) -->
      <div class="sidebar-group">
        <button class="section-toggle" @click="sectionOpen.audio = !sectionOpen.audio">
          <span class="toggle-chevron">{{ sectionOpen.audio ? '\u25BE' : '\u25B8' }}</span>
          Audio
        </button>
        <div v-if="sectionOpen.audio" class="section-body">
          <SceneAudioPanel
            v-if="sceneId"
            :scene-id="sceneId"
            :audio="scene.audio ?? null"
            :scene-mood="(scene as any).mood || ''"
            :scene-description="(scene as any).description || ''"
            :time-of-day="(scene as any).time_of_day || ''"
            :has-dialogue="shots.some((s: any) => s.dialogue_text)"
            @audio-changed="(a: SceneAudio | null) => emit('audio-changed', a)"
          />
        </div>
      </div>

      <!-- Action buttons -->
      <div style="display: flex; gap: 8px; padding: 12px; flex-wrap: wrap; border-top: 1px solid var(--border-primary);">
        <button class="btn btn-primary" @click="emit('save')" :disabled="saving">Save</button>
        <button class="btn btn-success" :disabled="shots.length === 0 || generating" @click="emit('confirm-generate')">Generate</button>
        <button class="btn" :disabled="shots.length === 0 || allShotsHaveImages" @click="emit('auto-assign')" title="Auto-assign best source images to all unassigned shots">Auto-assign</button>
        <button
          class="btn"
          :disabled="!hasDialogueShots"
          @click="rehearsalOpen = true"
          title="Rehearse scene dialogue with voice playback"
          style="background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.3); color: #22c55e;"
        >Rehearse</button>
        <button class="btn" @click="emit('back')">Back</button>
      </div>
    </div>

    <!-- Middle: Storyboard Grid -->
    <StoryboardGrid
      :shots="shots"
      :selected-shot-idx="selectedShotIdx"
      :source-image-url="sourceImageUrl"
      :keyframe-blitz-busy="keyframeBlitzBusy"
      @select-shot="(idx: number) => emit('select-shot', idx)"
      @add-shot="emit('add-shot')"
      @batch-regen="() => { /* batch regen placeholder */ }"
      @keyframe-blitz="emit('keyframe-blitz')"
    />

    <!-- Right: Shot Inspector -->
    <ShotInspectorPanel
      v-if="selectedShotIdx >= 0 && shots[selectedShotIdx]"
      :shot="shots[selectedShotIdx]"
      :shot-video-src="shotVideoSrc"
      :source-image-url="sourceImageUrl"
      :characters="characters"
      :auto-dialogue-busy="autoDialogueBusy"
      @remove="emit('remove-shot', selectedShotIdx)"
      @browse-image="emit('browse-image')"
      @update-field="(field: string, value: unknown) => emit('update-shot-field', selectedShotIdx, field, value)"
      @auto-dialogue="emit('auto-dialogue')"
    />

    <!-- Rehearsal Mode -->
    <SceneRehearsalMode
      v-if="rehearsalOpen"
      :shots="shots"
      :scene-title="localScene.title || `Scene ${localScene.scene_number}`"
      :characters="characters"
      :source-image-url="sourceImageUrl"
      @close="rehearsalOpen = false"
      @update-shot="handleRehearsalUpdate"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch, type Reactive } from 'vue'
import type { BuilderScene, BuilderShot, SceneAudio, GapAnalysisCharacter } from '@/types'
import { useProjectStore } from '@/stores/project'
import ShotInspectorPanel from './ShotInspectorPanel.vue'
import StoryboardGrid from './StoryboardGrid.vue'
import SceneRehearsalMode from './SceneRehearsalMode.vue'
import EchoAssistButton from '../EchoAssistButton.vue'
import SceneAudioPanel from './SceneAudioPanel.vue'
import SegmentedControl from '../shared/SegmentedControl.vue'

const projectStore = useProjectStore()

const props = defineProps<{
  scene: Partial<BuilderScene>
  sceneId: string | null
  shots: Partial<BuilderShot>[]
  selectedShotIdx: number
  saving: boolean
  generating: boolean
  shotVideoSrc: string
  sourceImageUrl: (path: string) => string
  characters: { slug: string; name: string }[]
  gapCharacters?: Record<string, GapAnalysisCharacter>
  autoDialogueBusy?: boolean
  keyframeBlitzBusy?: boolean
}>()

const emit = defineEmits<{
  save: []
  'confirm-generate': []
  back: []
  'select-shot': [idx: number]
  'add-shot': []
  'remove-shot': [idx: number]
  'browse-image': []
  'auto-assign': []
  'update-shot-field': [idx: number, field: string, value: unknown]
  'update-scene': [scene: Partial<BuilderScene>]
  'audio-changed': [audio: SceneAudio | null]
  'go-to-training': []
  'auto-dialogue': []
  'keyframe-blitz': []
}>()

const allShotsHaveImages = computed(() =>
  props.shots.length > 0 && props.shots.every(s => !!s.source_image_path)
)

// Rehearsal mode
const rehearsalOpen = ref(false)
const hasDialogueShots = computed(() =>
  props.shots.some(s => (s as any).dialogue_text && (s as any).dialogue_character_slug)
)

function handleRehearsalUpdate(shotId: string, field: string, value: string) {
  const idx = props.shots.findIndex(s => (s as any).id === shotId)
  if (idx >= 0) {
    emit('update-shot-field', idx, field, value)
  }
}

const unreadyCharacters = computed((): Array<{ slug: string; name: string; reason: string }> => {
  if (!props.gapCharacters) return []
  const slugsSeen = new Set<string>()
  const result: Array<{ slug: string; name: string; reason: string }> = []
  for (const shot of props.shots) {
    const chars = (shot.characters_present as string[]) || []
    for (const slug of chars) {
      if (slugsSeen.has(slug)) continue
      slugsSeen.add(slug)
      const gc = props.gapCharacters[slug]
      if (gc && !gc.has_lora) {
        const reason = gc.approved_count < 10
          ? `${gc.approved_count} images (need 10+)`
          : 'LoRA not yet trained'
        result.push({ slug, name: gc.name, reason })
      }
    }
  }
  return result
})

const timeOptions = ['dawn', 'morning', 'midday', 'afternoon', 'sunset', 'evening', 'night']
const weatherOptions = ['clear', 'cloudy', 'rain', 'snow', 'fog', 'storm']

const timeSegmentOptions = [{ value: '', label: '--' }, ...timeOptions.map(t => ({ value: t, label: t }))]
const weatherSegmentOptions = [{ value: '', label: '--' }, ...weatherOptions.map(w => ({ value: w, label: w }))]

// Collapsible section state
const sectionOpen = reactive({
  environment: true,
  technical: false,
  storyArc: false,
  audio: false,
})

// Story context
const localStoryArc = ref('')

const storyline = computed(() => projectStore.currentProject?.storyline)
const worldSettings = computed(() => projectStore.worldSettings)

const worldLocation = computed(() => {
  const loc = worldSettings.value?.world_location
  if (!loc) return ''
  const parts = [loc.primary, loc.atmosphere].filter(Boolean)
  return parts.join(' — ')
})

const storyArcs = computed(() => storyline.value?.story_arcs || [])

const hasStoryContext = computed(() =>
  !!storyline.value?.summary || !!storyline.value?.theme || !!storyline.value?.tone || storyArcs.value.length > 0 || !!worldLocation.value
)

const echoScenePayload = computed(() => ({
  project_name: projectStore.currentProject?.name || undefined,
  project_genre: projectStore.currentProject?.genre || undefined,
  storyline_title: storyline.value?.title || undefined,
  storyline_summary: storyline.value?.summary || undefined,
  storyline_theme: storyline.value?.theme || undefined,
  concept_description: `Scene: ${localScene.title || ''}. Location: ${localScene.location || ''}. Mood: ${localScene.mood || ''}. Time: ${localScene.time_of_day || ''}.`,
}))

// Local reactive copy of scene data that syncs back to parent
const localScene = reactive<Partial<BuilderScene>>({ ...props.scene })
const localPostInterpolate = ref<number | null>(props.scene.post_interpolate_fps ?? null)
const localPostUpscale = ref<number | null>(props.scene.post_upscale_factor ?? null)

watch(() => props.scene, (newScene) => {
  Object.assign(localScene, newScene)
  localPostInterpolate.value = newScene.post_interpolate_fps ?? null
  localPostUpscale.value = newScene.post_upscale_factor ?? null
}, { deep: true })

watch(localScene, (val) => {
  emit('update-scene', { ...val })
}, { deep: true })

watch(localPostInterpolate, (val) => {
  localScene.post_interpolate_fps = val
})

watch(localPostUpscale, (val) => {
  localScene.post_upscale_factor = val
})

function estimateMinutes(shots: Partial<BuilderShot>[]): number {
  return shots.reduce((sum, s) => {
    const dur = s.duration_seconds || 3
    if (dur <= 2) return sum + 20
    if (dur <= 3) return sum + 13
    if (dur <= 5) return sum + 25
    return sum + 30
  }, 0)
}
</script>

<style scoped>
.field-group {
  margin-bottom: 10px;
}
.field-label {
  font-size: 12px;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 4px;
}
.field-input {
  width: 100%;
  padding: 6px 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: var(--font-primary);
}
.field-input:focus {
  border-color: var(--border-focus);
  outline: none;
}
.field-textarea {
  resize: vertical;
  min-height: 60px;
}
.field-row {
  display: flex;
  gap: 8px;
}
.field-row .field-group {
  flex: 1;
}

/* Collapsible sidebar sections */
.sidebar-group {
  border-bottom: 1px solid var(--border-primary);
  padding: 10px 12px;
}
.section-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-primary);
  padding: 0;
  width: 100%;
  text-align: left;
}
.section-toggle:hover {
  color: var(--text-primary);
}
.toggle-chevron {
  font-size: 10px;
  width: 12px;
  display: inline-block;
}
.section-body {
  margin-top: 8px;
}

.badge-draft {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.badge-generating {
  background: rgba(122, 162, 247, 0.2);
  color: var(--accent-primary);
}
.badge-completed {
  background: rgba(80, 160, 80, 0.2);
  color: var(--status-success);
}
.badge-partial {
  background: rgba(160, 128, 80, 0.2);
  color: var(--status-warning);
}
.badge-failed {
  background: rgba(160, 80, 80, 0.2);
  color: var(--status-error);
}
</style>
