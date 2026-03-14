<template>
  <div
    :style="{
      background: 'var(--bg-secondary)',
      borderRadius: '10px',
      overflow: 'hidden',
      border: borderStyle,
      cursor: 'pointer',
      transition: 'border-color 0.2s, box-shadow 0.2s, opacity 0.2s',
      boxShadow: isPlaying ? `0 0 16px ${categoryMeta.color}30` : 'none',
      opacity: sample.status === 'rejected' ? 0.45 : 1,
    }"
  >
    <!-- Video/visual preview area -->
    <div
      :style="{
        position: 'relative',
        width: '100%',
        paddingTop: '56.25%',
        background: `linear-gradient(135deg, ${categoryMeta.color}15, ${categoryMeta.color}05)`,
        overflow: 'hidden',
      }"
      @click="$emit('togglePlay')"
    >
      <!-- Video preview -->
      <video
        v-if="sample.has_video"
        ref="videoEl"
        :src="videoUrl"
        :style="{
          position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
          objectFit: 'cover',
          opacity: isPlaying ? 1 : 0.7,
          transition: 'opacity 0.3s',
        }"
        muted
        loop
        playsinline
        preload="metadata"
        @mouseenter="hoverPreview"
        @mouseleave="stopPreview"
      ></video>

      <!-- Fallback: action icon overlay when no video -->
      <div
        v-else
        :style="{
          position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '48px', opacity: 0.3,
        }"
      >
        {{ actionEmoji }}
      </div>

      <!-- Play/stop overlay button -->
      <div :style="{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '44px', height: '44px', borderRadius: '50%',
        background: isPlaying ? categoryMeta.color : 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'background 0.2s, transform 0.15s',
        boxShadow: isPlaying ? `0 0 20px ${categoryMeta.color}60` : '0 2px 8px rgba(0,0,0,0.4)',
      }">
        <svg v-if="!isPlaying" width="18" height="18" viewBox="0 0 24 24" fill="white">
          <polygon points="6,3 20,12 6,21" />
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="white">
          <rect x="5" y="3" width="5" height="18" rx="1" />
          <rect x="14" y="3" width="5" height="18" rx="1" />
        </svg>
      </div>

      <!-- Progress bar -->
      <div :style="{
        position: 'absolute', bottom: 0, left: 0, width: '100%',
        height: '3px', background: 'rgba(0,0,0,0.3)',
      }">
        <div :style="{
          height: '100%',
          width: progress + '%',
          background: categoryMeta.color,
          transition: 'width 0.1s linear',
          borderRadius: '0 2px 2px 0',
        }"></div>
      </div>

      <!-- Status badge top-left -->
      <span
        v-if="sample.status !== 'pending'"
        :style="{
          position: 'absolute', top: '8px', left: '8px',
          fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
          background: sample.status === 'approved' ? '#22c55e' : '#ef4444',
          color: 'white', fontWeight: 600,
          backdropFilter: 'blur(4px)',
        }"
      >
        {{ sample.status === 'approved' ? 'APPROVED' : 'REJECTED' }}
      </span>

      <!-- Category badge top-right -->
      <span :style="{
        position: 'absolute', top: '8px', right: '8px',
        fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
        background: categoryMeta.color + '30',
        color: categoryMeta.color,
        fontWeight: 500,
        backdropFilter: 'blur(4px)',
      }">
        {{ categoryMeta.label.split(' \u2014 ')[0] }}
      </span>
    </div>

    <!-- Info + approve/reject bar -->
    <div style="padding: 10px 12px;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 12px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px;">
          {{ sample.name.replace(sample.category + '_', '') }}
        </span>
        <span style="font-size: 10px; color: var(--text-muted);">
          {{ sample.size_kb }}kb
        </span>
      </div>

      <!-- Approve / Reject buttons -->
      <div style="display: flex; gap: 6px; margin-top: 8px;">
        <button
          @click.stop="$emit('approve', sample)"
          :style="{
            flex: 1, padding: '5px 0', borderRadius: '5px', border: 'none',
            fontSize: '11px', fontWeight: 600, cursor: 'pointer',
            transition: 'background 0.15s',
            background: sample.status === 'approved' ? '#22c55e' : 'var(--bg-tertiary)',
            color: sample.status === 'approved' ? 'white' : '#22c55e',
          }"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="vertical-align: -2px; margin-right: 2px;">
            <polyline points="20,6 9,17 4,12" />
          </svg>
          Keep
        </button>
        <button
          @click.stop="$emit('reject', sample)"
          :style="{
            flex: 1, padding: '5px 0', borderRadius: '5px', border: 'none',
            fontSize: '11px', fontWeight: 600, cursor: 'pointer',
            transition: 'background 0.15s',
            background: sample.status === 'rejected' ? '#ef4444' : 'var(--bg-tertiary)',
            color: sample.status === 'rejected' ? 'white' : '#ef4444',
          }"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="vertical-align: -2px; margin-right: 2px;">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
          Toss
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface CategoryMeta {
  label: string
  icon: string
  color: string
  description: string
}

interface MotionSample {
  name: string
  filename: string
  category: string
  has_video: boolean
  size_kb: number
  status: 'pending' | 'approved' | 'rejected'
}

const props = defineProps<{
  sample: MotionSample
  categoryMeta: CategoryMeta
  isPlaying: boolean
  progress: number
}>()

defineEmits<{
  togglePlay: []
  approve: [sample: MotionSample]
  reject: [sample: MotionSample]
}>()

const videoEl = ref<HTMLVideoElement | null>(null)

const borderStyle = computed(() => {
  if (props.isPlaying) return `2px solid ${props.categoryMeta.color}`
  if (props.sample.status === 'approved') return '2px solid #22c55e40'
  if (props.sample.status === 'rejected') return '2px solid #ef444430'
  return '2px solid transparent'
})

const videoUrl = computed(() =>
  `/api/voice/sfx/motion/video/${props.sample.category}/${props.sample.name}.mp4`
)

const actionEmoji = computed(() => {
  const icons: Record<string, string> = {
    walk: '\u{1F6B6}',
    run: '\u{1F3C3}',
    talk: '\u{1F5E3}',
    hug: '\u{1FAC2}',
    jump: '\u{2B06}',
    cook: '\u{1F373}',
    kiss: '\u{1F48B}',
    swim: '\u{1F3CA}',
  }
  return icons[props.categoryMeta.icon] || '\u{1F3B5}'
})

function hoverPreview() {
  if (videoEl.value && !props.isPlaying) {
    videoEl.value.currentTime = 0
    videoEl.value.play().catch(() => {})
  }
}

function stopPreview() {
  if (videoEl.value && !props.isPlaying) {
    videoEl.value.pause()
    videoEl.value.currentTime = 0
  }
}

watch(() => props.isPlaying, (playing) => {
  if (!videoEl.value) return
  if (playing) {
    videoEl.value.currentTime = 0
    videoEl.value.play().catch(() => {})
  } else {
    videoEl.value.pause()
    videoEl.value.currentTime = 0
  }
})
</script>
