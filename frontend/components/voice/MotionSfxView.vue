<template>
  <div>
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h3 style="font-size: 16px; font-weight: 500; margin-bottom: 4px;">Motion SFX Library</h3>
        <p style="font-size: 12px; color: var(--text-muted);">
          {{ totalSamples }} clips across {{ categoryCount }} actions — extracted from training footage
        </p>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <select v-model="filterStatus" style="padding: 6px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 4px; color: var(--text-primary); font-size: 13px;">
          <option value="">All status</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select v-model="filterCategory" style="padding: 6px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 4px; color: var(--text-primary); font-size: 13px;">
          <option value="">All actions</option>
          <option v-for="(cat, key) in catalog.categories" :key="key" :value="key">
            {{ cat.meta.label }} ({{ cat.count }})
          </option>
        </select>
      </div>
    </div>

    <!-- Stats bar -->
    <div v-if="totalSamples" style="display: flex; gap: 16px; margin-bottom: 20px; padding: 12px 16px; background: var(--bg-secondary); border-radius: 8px;">
      <div style="display: flex; align-items: center; gap: 6px;">
        <span style="width: 8px; height: 8px; border-radius: 50%; background: #eab308;"></span>
        <span style="font-size: 13px; color: var(--text-secondary);">
          <strong>{{ catalog.stats?.pending || 0 }}</strong> pending
        </span>
      </div>
      <div style="display: flex; align-items: center; gap: 6px;">
        <span style="width: 8px; height: 8px; border-radius: 50%; background: #22c55e;"></span>
        <span style="font-size: 13px; color: var(--text-secondary);">
          <strong>{{ catalog.stats?.approved || 0 }}</strong> approved
        </span>
      </div>
      <div style="display: flex; align-items: center; gap: 6px;">
        <span style="width: 8px; height: 8px; border-radius: 50%; background: #ef4444;"></span>
        <span style="font-size: 13px; color: var(--text-secondary);">
          <strong>{{ catalog.stats?.rejected || 0 }}</strong> rejected
        </span>
      </div>
      <div style="flex: 1;"></div>
      <!-- Batch actions for current category -->
      <button
        v-if="filterCategory"
        @click="batchApprove(true)"
        style="padding: 4px 12px; background: #22c55e20; color: #22c55e; border: 1px solid #22c55e40; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer;"
      >
        Approve All Pending
      </button>
      <button
        v-if="filterCategory"
        @click="batchApprove(false)"
        style="padding: 4px 12px; background: #ef444420; color: #ef4444; border: 1px solid #ef444440; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer;"
      >
        Reject All Pending
      </button>
    </div>

    <div v-if="loading" style="text-align: center; padding: 60px; color: var(--text-muted);">
      Loading motion SFX...
    </div>

    <div v-else-if="!totalSamples" style="text-align: center; padding: 60px; color: var(--text-muted);">
      No motion SFX found. Run <code>collect_motion_clips.py</code> first.
    </div>

    <!-- Category sections -->
    <div v-else>
      <div
        v-for="(cat, catKey) in filteredCategories"
        :key="catKey"
        style="margin-bottom: 32px;"
      >
        <!-- Category header -->
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
          <div :style="{
            width: '36px', height: '36px', borderRadius: '8px',
            background: cat.meta.color + '20',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '18px',
          }">
            {{ actionIcon(cat.meta.icon) }}
          </div>
          <div>
            <h4 style="font-size: 14px; font-weight: 500;">{{ cat.meta.label }}</h4>
            <p style="font-size: 11px; color: var(--text-muted);">{{ cat.meta.description }}</p>
          </div>
          <div style="margin-left: auto; display: flex; gap: 6px;">
            <span v-if="cat.stats?.approved" style="font-size: 10px; padding: 2px 6px; border-radius: 10px; background: #22c55e20; color: #22c55e;">
              {{ cat.stats.approved }} kept
            </span>
            <span v-if="cat.stats?.rejected" style="font-size: 10px; padding: 2px 6px; border-radius: 10px; background: #ef444420; color: #ef4444;">
              {{ cat.stats.rejected }} tossed
            </span>
            <span style="font-size: 10px; padding: 2px 6px; border-radius: 10px; background: var(--bg-tertiary); color: var(--text-muted);">
              {{ cat.count }} total
            </span>
          </div>
        </div>

        <!-- SFX card grid -->
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;">
          <SfxCard
            v-for="sample in filterSamples(cat.samples)"
            :key="sample.name"
            :sample="sample"
            :category-meta="cat.meta"
            :is-playing="playing === sample.name"
            :progress="playing === sample.name ? playProgress : 0"
            @toggle-play="togglePlay(sample)"
            @approve="approveSample(sample, true)"
            @reject="approveSample(sample, false)"
          />
        </div>

        <p
          v-if="filterSamples(cat.samples).length === 0"
          style="text-align: center; padding: 24px; color: var(--text-muted); font-size: 12px;"
        >
          No {{ filterStatus }} clips in this category.
        </p>
      </div>
    </div>

    <!-- Hidden audio element -->
    <audio
      ref="audioEl"
      @ended="onEnded"
      @timeupdate="onTimeUpdate"
      style="display: none;"
    ></audio>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { createRequest } from '@/api/base'
import SfxCard from './SfxCard.vue'

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

interface CategoryStats {
  approved: number
  rejected: number
  pending: number
}

interface MotionCategory {
  meta: CategoryMeta
  samples: MotionSample[]
  count: number
  stats: CategoryStats
}

interface MotionCatalog {
  categories: Record<string, MotionCategory>
  total: number
  stats: CategoryStats
}

const API_BASE = '/api/voice/sfx/motion'
const motionRequest = createRequest(API_BASE)

const loading = ref(true)
const catalog = ref<MotionCatalog>({ categories: {}, total: 0, stats: { approved: 0, rejected: 0, pending: 0 } })
const filterCategory = ref('')
const filterStatus = ref('')
const playing = ref('')
const playProgress = ref(0)
const audioEl = ref<HTMLAudioElement | null>(null)

const totalSamples = computed(() => catalog.value.total)
const categoryCount = computed(() => Object.keys(catalog.value.categories).length)

const filteredCategories = computed(() => {
  if (!filterCategory.value) return catalog.value.categories
  const key = filterCategory.value
  if (catalog.value.categories[key]) {
    return { [key]: catalog.value.categories[key] }
  }
  return {}
})

function filterSamples(samples: MotionSample[]): MotionSample[] {
  if (!filterStatus.value) return samples
  return samples.filter(s => s.status === filterStatus.value)
}

function actionIcon(icon: string): string {
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
  return icons[icon] || '\u{1F3B5}'
}

function togglePlay(sample: MotionSample) {
  if (!audioEl.value) return

  if (playing.value === sample.name) {
    audioEl.value.pause()
    playing.value = ''
    playProgress.value = 0
    return
  }

  audioEl.value.src = `${API_BASE}/audio/${sample.category}/${sample.filename}`
  audioEl.value.play()
  playing.value = sample.name
  playProgress.value = 0
}

async function approveSample(sample: MotionSample, approved: boolean) {
  try {
    await motionRequest('/approve', {
      method: 'POST',
      body: JSON.stringify({
        category: sample.category,
        filename: sample.filename,
        approved,
      }),
    })
    // Update local state immediately
    sample.status = approved ? 'approved' : 'rejected'
    recalcStats()
  } catch (e) {
    console.error('Failed to update approval:', e)
  }
}

async function batchApprove(approved: boolean) {
  const cat = filterCategory.value
  if (!cat || !catalog.value.categories[cat]) return
  const pendingFiles = catalog.value.categories[cat].samples
    .filter(s => s.status === 'pending')
    .map(s => s.filename)
  if (!pendingFiles.length) return

  try {
    await motionRequest('/batch-approve', {
      method: 'POST',
      body: JSON.stringify({
        category: cat,
        filenames: pendingFiles,
        approved,
      }),
    })
    // Update local state
    const status = approved ? 'approved' : 'rejected'
    for (const s of catalog.value.categories[cat].samples) {
      if (s.status === 'pending') s.status = status
    }
    recalcStats()
  } catch (e) {
    console.error('Batch approve failed:', e)
  }
}

function recalcStats() {
  const global = { approved: 0, rejected: 0, pending: 0 }
  for (const cat of Object.values(catalog.value.categories)) {
    const cs = { approved: 0, rejected: 0, pending: 0 }
    for (const s of cat.samples) {
      cs[s.status] = (cs[s.status] || 0) + 1
      global[s.status] = (global[s.status] || 0) + 1
    }
    cat.stats = cs
  }
  catalog.value.stats = global
}

function onTimeUpdate() {
  if (audioEl.value && audioEl.value.duration) {
    playProgress.value = (audioEl.value.currentTime / audioEl.value.duration) * 100
  }
}

function onEnded() {
  playing.value = ''
  playProgress.value = 0
}

onMounted(async () => {
  try {
    catalog.value = await motionRequest<MotionCatalog>('/catalog')
  } catch (e) {
    console.error('Failed to load motion SFX catalog:', e)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (audioEl.value) {
    audioEl.value.pause()
  }
})
</script>
