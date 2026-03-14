<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
      <div>
        <h3 style="font-size: 16px; font-weight: 500; margin-bottom: 4px;">Explicit Vocal SFX Library</h3>
        <p style="font-size: 12px; color: var(--text-muted);">
          {{ totalSamples }} samples across {{ categoryCount }} categories — {{ totalDuration }}s total
        </p>
      </div>
      <div style="display: flex; gap: 8px;">
        <select v-model="filterGender" style="padding: 6px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 4px; color: var(--text-primary); font-size: 13px;">
          <option value="">All genders</option>
          <option value="female">Female</option>
          <option value="male">Male</option>
        </select>
      </div>
    </div>

    <div v-if="loading" style="text-align: center; padding: 40px; color: var(--text-muted);">
      Loading SFX catalog...
    </div>

    <div v-else-if="!totalSamples" style="text-align: center; padding: 40px; color: var(--text-muted);">
      No SFX samples found. Generate them first with <code>generate_explicit_sfx.py</code>
    </div>

    <div v-else>
      <div v-for="(samples, category) in filteredCategories" :key="category" style="background: var(--bg-secondary); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
        <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 12px; color: var(--accent-primary); text-transform: capitalize;">
          {{ formatCategory(category) }}
          <span style="font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 8px;">
            {{ samples.length }} samples
          </span>
        </h4>

        <div v-for="s in samples" :key="s.name" style="display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border-primary);">
          <button @click="togglePlay(s)" :style="{
            width: '32px', height: '32px', borderRadius: '50%', border: 'none',
            background: playing === s.name ? 'var(--accent-danger)' : 'var(--accent-primary)',
            color: 'white', cursor: 'pointer', fontSize: '14px', flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }">
            {{ playing === s.name ? '⏹' : '▶' }}
          </button>

          <span :style="{
            fontSize: '12px', padding: '2px 8px', borderRadius: '3px', flexShrink: 0,
            background: s.gender === 'female' ? '#ff69b4' : '#4169e1', color: 'white',
          }">
            {{ s.gender === 'female' ? 'F' : 'M' }}
          </span>

          <span style="font-weight: 500; min-width: 160px; font-size: 13px;">{{ s.name }}</span>

          <span style="flex: 1; font-style: italic; color: var(--text-muted); font-size: 12px;">
            "{{ s.text }}"
          </span>

          <span style="font-size: 11px; color: var(--text-muted); min-width: 80px; text-align: right;">
            {{ s.voice?.split('-').slice(-1)[0] }}<br>{{ s.duration?.toFixed(1) }}s
          </span>
        </div>
      </div>
    </div>

    <!-- Hidden audio element for playback -->
    <audio ref="audioEl" @ended="playing = ''" style="display: none;"></audio>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { createRequest } from '@/api/base'

interface SfxSample {
  name: string
  status: string
  duration: number
  path: string
  job_id: string
  category: string
  gender: string
  voice: string
  text: string
}

interface SfxCatalog {
  total: number
  categories: Record<string, SfxSample[]>
  samples: SfxSample[]
}

const API_BASE = '/api/voice/sfx'
const sfxRequest = createRequest(API_BASE)
const loading = ref(true)
const catalog = ref<SfxCatalog>({ total: 0, categories: {}, samples: [] })
const filterGender = ref('')
const playing = ref('')
const audioEl = ref<HTMLAudioElement | null>(null)

const totalSamples = computed(() => catalog.value.total)
const categoryCount = computed(() => Object.keys(catalog.value.categories).length)
const totalDuration = computed(() =>
  catalog.value.samples.reduce((s, x) => s + (x.duration || 0), 0).toFixed(1)
)

const filteredCategories = computed(() => {
  const result: Record<string, SfxSample[]> = {}
  for (const [cat, samples] of Object.entries(catalog.value.categories)) {
    const filtered = filterGender.value
      ? samples.filter(s => s.gender === filterGender.value)
      : samples
    if (filtered.length > 0) result[cat] = filtered
  }
  return result
})

function formatCategory(cat: string): string {
  return cat.replace(/_/g, ' ')
}

function togglePlay(sample: SfxSample) {
  if (!audioEl.value) return

  if (playing.value === sample.name) {
    audioEl.value.pause()
    playing.value = ''
    return
  }

  const url = `${API_BASE}/audio/${sample.category}/${sample.name}.wav`
  audioEl.value.src = url
  audioEl.value.play()
  playing.value = sample.name
}

onMounted(async () => {
  try {
    catalog.value = await sfxRequest<SfxCatalog>('/catalog')
  } catch (e) {
    console.error('Failed to load SFX catalog:', e)
  } finally {
    loading.value = false
  }
})
</script>
