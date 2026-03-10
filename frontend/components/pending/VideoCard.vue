<template>
  <div
    ref="cardRef"
    class="video-card"
    :class="{ selected: isSelected }"
  >
    <!-- Selection checkbox -->
    <div class="select-check" @click.stop="$emit('toggle-selection', video.id)">
      <input type="checkbox" :checked="isSelected" />
    </div>

    <!-- Engine badge -->
    <span :class="['engine-badge', `engine-${video.video_engine}`]">
      {{ engineLabel }}
    </span>

    <!-- Video player (lazy-loaded when visible) -->
    <div class="video-container">
      <video
        v-if="isVisible"
        :src="videoUrl"
        controls
        preload="metadata"
        muted
        loop
        @mouseenter="($event.target as HTMLVideoElement)?.play()"
        @mouseleave="handleMouseLeave"
      />
      <div v-else class="video-placeholder" />
    </div>

    <div class="meta">
      <!-- Context line -->
      <div class="context-row">
        <span class="context-tag scene-tag" :title="video.scene_title">
          {{ video.scene_title }}
        </span>
        <span v-for="char in video.characters_present" :key="char" class="context-tag char-tag">
          {{ char }}
        </span>
        <span class="context-tag project-tag">{{ video.project_name }}</span>
      </div>

      <!-- Quality score bar -->
      <div v-if="video.quality_score != null" class="quality-row">
        <span class="quality-label" :style="{ color: qualityColor }">
          Q:{{ (video.quality_score * 100).toFixed(0) }}%
        </span>
        <div class="quality-bar">
          <div class="quality-fill" :style="{ width: (video.quality_score * 100) + '%', background: qualityColor }" />
        </div>
      </div>

      <!-- QC category breakdown -->
      <div v-if="hasCategoryAverages" class="category-breakdown">
        <div v-for="(val, key) in video.qc_category_averages" :key="key" class="cat-row">
          <span class="cat-label">{{ formatCatLabel(String(key)) }}</span>
          <div class="cat-bar">
            <div class="cat-fill" :style="{ width: (Number(val) / 10 * 100) + '%', background: catColor(Number(val)) }" />
          </div>
          <span class="cat-val">{{ Number(val).toFixed(1) }}</span>
        </div>
      </div>

      <!-- Issue tags -->
      <div v-if="video.qc_issues.length" class="issue-row">
        <span v-for="issue in video.qc_issues" :key="issue" class="issue-tag">
          {{ issue.replace('_', ' ') }}
        </span>
      </div>

      <!-- LoRA tag -->
      <div v-if="video.lora_name" class="lora-row">
        <span class="lora-tag" :title="video.lora_name">
          {{ loraLabel }}
        </span>
        <span v-if="video.lora_strength" class="lora-strength">{{ video.lora_strength }}</span>
      </div>

      <!-- Motion prompt (truncated) -->
      <div v-if="video.motion_prompt" class="motion-prompt" :title="video.motion_prompt">
        {{ video.motion_prompt }}
      </div>

      <!-- Gen info -->
      <div class="gen-info">
        <span v-if="video.generation_time_seconds">{{ video.generation_time_seconds.toFixed(0) }}s</span>
        <span v-if="video.steps">{{ video.steps }} steps</span>
        <span v-if="video.seed" class="seed" :title="String(video.seed)">seed:{{ video.seed }}</span>
      </div>

      <!-- Action buttons -->
      <div class="actions">
        <button class="btn btn-success" @click.stop="$emit('approve', video)">
          Approve
        </button>
        <button class="btn btn-danger" @click.stop="$emit('reject', video)">
          Reject
        </button>
        <button
          class="btn btn-outline"
          @click.stop="$emit('edit-shot', video)"
          title="Edit shot parameters and regenerate"
        >
          Edit
        </button>
        <button
          class="btn btn-danger-outline"
          @click.stop="$emit('reject-engine', video)"
          :title="`Reject & blacklist ${engineLabel} for ${video.characters_present[0] || 'character'}`"
        >
          Ban
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { PendingVideo } from '@/types'
import { scenesApi } from '@/api/scenes'

const props = defineProps<{
  video: PendingVideo
  isSelected: boolean
}>()

const cardRef = ref<HTMLElement | null>(null)
const isVisible = ref(false)
let observer: IntersectionObserver | null = null

onMounted(() => {
  const el = cardRef.value
  if (!el) return
  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        isVisible.value = true
        observer?.disconnect()
      }
    },
    { rootMargin: '200px' },
  )
  observer.observe(el)
})

onUnmounted(() => observer?.disconnect())

defineEmits<{
  (e: 'toggle-selection', id: string): void
  (e: 'approve', video: PendingVideo): void
  (e: 'reject', video: PendingVideo): void
  (e: 'reject-engine', video: PendingVideo): void
  (e: 'edit-shot', video: PendingVideo): void
}>()

const ENGINE_LABELS: Record<string, string> = {
  framepack: 'FramePack',
  framepack_f1: 'FramePack F1',
  ltx: 'LTX',
  wan: 'Wan 2.1',
  wan22: 'Wan 2.2',
  wan22_14b: 'Wan 14B',
}

const engineLabel = computed(() => ENGINE_LABELS[props.video.video_engine] || props.video.video_engine)

const loraLabel = computed(() => {
  const name = props.video.lora_name || ''
  // Extract just the meaningful part: wan22_nsfw/wan22_doggy_back_HIGH.safetensors -> doggy_back HIGH
  const base = name.split('/').pop()?.replace('.safetensors', '') || name
  return base
    .replace(/^wan22_/, '')
    .replace(/^wan2\.2_/, '')
    .replace(/_i2v_/g, '_')
    .replace(/_wan22/g, '')
    .replace(/_high_noise$/i, ' HIGH')
    .replace(/_low_noise$/i, ' LOW')
    .replace(/_HIGH$/i, ' HIGH')
    .replace(/_LOW$/i, ' LOW')
})

const videoUrl = computed(() => {
  return scenesApi.shotVideoUrl(props.video.scene_id, props.video.id)
})

const qualityColor = computed(() => {
  const s = props.video.quality_score ?? 0
  if (s >= 0.7) return 'var(--status-success)'
  if (s >= 0.4) return 'var(--status-warning)'
  return 'var(--status-error)'
})

const hasCategoryAverages = computed(() => {
  return props.video.qc_category_averages && Object.keys(props.video.qc_category_averages).length > 0
})

function formatCatLabel(key: string): string {
  const labels: Record<string, string> = {
    visual_quality: 'Visual',
    motion_coherence: 'Motion',
    character_consistency: 'Character',
    composition: 'Compose',
  }
  return labels[key] || key.replace('_', ' ')
}

function catColor(val: number): string {
  if (val >= 7) return 'var(--status-success)'
  if (val >= 4) return 'var(--status-warning)'
  return 'var(--status-error)'
}

function handleMouseLeave(e: Event) {
  const vid = e.target as HTMLVideoElement
  vid.pause()
  vid.currentTime = 0
}
</script>

<style scoped>
.video-card {
  position: relative;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  overflow: hidden;
  transition: all 200ms ease;
}
.video-card:hover {
  border-color: var(--accent-primary);
}
.video-card.selected {
  border-color: var(--accent-primary);
  box-shadow: 0 0 8px rgba(80, 120, 200, 0.25);
}

.select-check {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 2;
  cursor: pointer;
}
.select-check input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent-primary);
}

.engine-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 2;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 3px;
  color: #fff;
}
.engine-framepack { background: #2d8a4e; }
.engine-framepack_f1 { background: #3ba55d; }
.engine-ltx { background: #4e7dd4; }
.engine-wan { background: #d4844e; }
.engine-wan22 { background: #c46e3a; }
.engine-wan22_14b { background: #a04e2a; }

.video-container {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: #000;
}
.video-container video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.video-placeholder {
  width: 100%;
  height: 100%;
  background: var(--bg-primary);
}

.meta {
  padding: 8px;
}

.context-row {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.context-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 2px;
  border: 1px solid var(--border-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}
.char-tag {
  background: rgba(80, 120, 200, 0.12);
  color: var(--accent-primary);
  border-color: var(--accent-primary);
  font-weight: 500;
}
.scene-tag {
  background: rgba(120, 80, 200, 0.12);
  color: #9070d0;
  border-color: #9070d0;
}
.project-tag {
  background: rgba(120, 120, 120, 0.12);
  color: var(--text-muted);
  border-color: var(--border-primary);
}

.quality-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.quality-label {
  font-size: 11px;
  font-weight: 600;
  min-width: 40px;
}
.quality-bar {
  flex: 1;
  height: 4px;
  background: var(--bg-primary);
  border-radius: 2px;
  overflow: hidden;
}
.quality-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 300ms ease;
}

.category-breakdown {
  margin-bottom: 6px;
}
.cat-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
}
.cat-label {
  font-size: 9px;
  color: var(--text-muted);
  min-width: 52px;
}
.cat-bar {
  flex: 1;
  height: 3px;
  background: var(--bg-primary);
  border-radius: 2px;
  overflow: hidden;
}
.cat-fill {
  height: 100%;
  border-radius: 2px;
}
.cat-val {
  font-size: 9px;
  color: var(--text-secondary);
  min-width: 20px;
  text-align: right;
}

.issue-row {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.issue-tag {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 2px;
  background: rgba(200, 80, 80, 0.12);
  color: var(--status-error);
  border: 1px solid var(--status-error);
  text-transform: capitalize;
}

.gen-info {
  display: flex;
  gap: 8px;
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.gen-info .seed {
  font-family: monospace;
  cursor: help;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
}

.actions {
  display: flex;
  gap: 4px;
}
.actions .btn {
  flex: 1;
  font-size: 11px;
  padding: 4px 6px;
}
.btn-outline {
  background: transparent;
  color: var(--accent-primary);
  border: 1px solid var(--accent-primary);
}
.btn-outline:hover {
  background: rgba(122, 162, 247, 0.15);
}
.btn-danger-outline {
  background: transparent;
  color: var(--status-error);
  border: 1px solid var(--status-error);
}
.btn-danger-outline:hover {
  background: rgba(200, 80, 80, 0.15);
}

.lora-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}
.lora-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 2px;
  background: rgba(200, 120, 50, 0.15);
  color: #d4844e;
  border: 1px solid #d4844e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}
.lora-strength {
  font-size: 9px;
  color: var(--text-muted);
  font-family: monospace;
}

.motion-prompt {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.4;
  cursor: help;
}
</style>
