<template>
  <div>
    <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 16px;">Voice Clone Status</h3>

    <!-- F5-TTS info -->
    <div style="background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 16px; margin-bottom: 24px;">
      <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 8px;">F5-TTS Zero-Shot Cloning</h4>
      <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">
        F5-TTS clones voices from reference audio — no training needed. Just approve voice samples
        for a character and synthesis will automatically use their cloned voice.
      </p>
      <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 16px;">
        Minimum: 6 seconds of clean speech. More audio = better quality. Currently installed and GPU-accelerated.
      </p>

      <!-- Character voice status -->
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div
          v-for="c in characters"
          :key="c.slug"
          style="display: flex; align-items: center; gap: 16px; padding: 10px 14px; background: var(--bg-secondary); border-radius: 6px;"
        >
          <span style="font-size: 13px; font-weight: 500; min-width: 120px;">{{ c.name }}</span>
          <span
            v-if="charStatus[c.slug]?.has_samples"
            style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(34,197,94,0.15); color: #22c55e;"
          >
            f5-tts ready ({{ charStatus[c.slug]?.sample_count }} samples)
          </span>
          <span
            v-else
            style="font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(234,179,8,0.15); color: #eab308;"
          >
            edge-tts fallback
          </span>
          <span style="font-size: 12px; color: var(--text-muted);">
            {{ charStatus[c.slug]?.engine || 'edge-tts' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Past training jobs (if any exist from before) -->
    <div v-if="jobs.length > 0">
      <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">Past Training Jobs</h4>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div
          v-for="job in jobs"
          :key="job.job_id"
          style="display: flex; align-items: center; gap: 16px; padding: 12px 16px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px;"
        >
          <span style="font-size: 13px; font-weight: 500; min-width: 120px;">{{ job.character_name || job.character_slug }}</span>
          <span style="font-size: 11px; padding: 2px 6px; background: var(--bg-secondary); border-radius: 3px; color: var(--text-muted); text-transform: uppercase;">
            {{ job.engine }}
          </span>
          <span style="font-size: 12px; color: var(--text-muted);">{{ job.approved_samples }} samples</span>
          <span
            :style="{
              fontSize: '12px', padding: '4px 10px', borderRadius: '4px', fontWeight: '500',
              background: job.status === 'completed' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
              color: job.status === 'completed' ? '#22c55e' : '#ef4444',
            }"
          >
            {{ job.status }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="error" style="margin-top: 16px; padding: 12px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; color: #ef4444; font-size: 13px;">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import type { VoiceTrainingJob, Character } from '@/types'
import { voiceApi } from '@/api/voice'
import { useVoiceSamplesStore } from '@/stores/voiceSamples'

const props = defineProps<{
  projectName: string
  characters: Character[]
}>()

const store = useVoiceSamplesStore()

const error = ref<string | null>(null)
const jobs = ref<VoiceTrainingJob[]>([])
const charStatus = reactive<Record<string, { has_samples: boolean; sample_count: number; engine: string }>>({})

// Approved sample counts from the shared store (avoids duplicate API calls if Review tab already loaded)
const approvedCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const sample of store.allSamples) {
    if (sample.approval_status === 'approved') {
      counts[sample.character_slug] = (counts[sample.character_slug] || 0) + 1
    }
  }
  return counts
})

async function loadStatus() {
  // Ensure samples are loaded in the shared store (will use cache if Review tab already loaded them)
  store.loadSamples(props.characters)

  for (const c of props.characters) {
    try {
      const models = await voiceApi.getVoiceModels(c.slug)
      const f5 = models.available_engines?.find((e: any) => e.engine === 'f5-tts')
      charStatus[c.slug] = {
        has_samples: !!f5,
        sample_count: (f5 as any)?.total_samples || 0,
        engine: models.preferred_engine || 'edge-tts',
      }
    } catch {
      charStatus[c.slug] = { has_samples: false, sample_count: 0, engine: 'edge-tts' }
    }
  }
}

async function loadJobs() {
  try {
    const resp = await voiceApi.getVoiceTrainingJobs({ project_name: props.projectName })
    jobs.value = resp.jobs || []
  } catch {
    // No jobs is fine
  }
}

onMounted(() => {
  loadStatus()
  loadJobs()
})
</script>
