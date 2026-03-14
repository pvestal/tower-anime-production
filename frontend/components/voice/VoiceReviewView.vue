<template>
  <div>
    <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 16px;">Voice Sample Review</h3>

    <!-- Character selector -->
    <div style="margin-bottom: 20px;">
      <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
        Character
      </label>
      <select
        v-model="selectedCharacter"
        style="min-width: 240px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-primary); font-size: 14px;"
      >
        <option value="">All characters</option>
        <option v-for="c in characters" :key="c.slug" :value="c.slug">
          {{ c.name }}
        </option>
      </select>
    </div>

    <!-- Stats bar -->
    <div v-if="store.stats" style="display: flex; gap: 24px; margin-bottom: 20px; font-size: 13px;">
      <span style="color: var(--text-secondary);">Total: <strong>{{ store.stats.total }}</strong></span>
      <span style="color: #22c55e;">Approved: <strong>{{ store.stats.approved }}</strong></span>
      <span style="color: #ef4444;">Rejected: <strong>{{ store.stats.rejected }}</strong></span>
      <span style="color: var(--text-muted);">Pending: <strong>{{ store.stats.pending }}</strong></span>
      <span style="color: var(--accent-primary);">Duration: <strong>{{ store.stats.total_approved_duration?.toFixed(1) }}s</strong></span>
    </div>

    <!-- Batch actions -->
    <div v-if="store.selectedCount > 0" style="display: flex; gap: 8px; margin-bottom: 16px; padding: 12px; background: var(--bg-tertiary); border-radius: 6px;">
      <span style="font-size: 13px; color: var(--text-secondary); padding: 6px 0;">{{ store.selectedCount }} selected</span>
      <button @click="handleBatchApprove(true)" style="padding: 6px 14px; background: #22c55e; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;">
        Approve All
      </button>
      <button @click="handleBatchApprove(false)" style="padding: 6px 14px; background: #ef4444; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 13px;">
        Reject All
      </button>
      <button @click="store.clearSelection()" style="padding: 6px 14px; background: var(--bg-secondary); color: var(--text-secondary); border: 1px solid var(--border-primary); border-radius: 4px; cursor: pointer; font-size: 13px;">
        Clear
      </button>
    </div>

    <!-- Sample list -->
    <div v-if="store.loading" style="text-align: center; padding: 40px; color: var(--text-muted);">Loading samples...</div>

    <div v-else-if="filteredSamples.length === 0" style="text-align: center; padding: 40px; color: var(--text-muted);">
      No voice samples found. Extract audio and assign speakers first.
    </div>

    <div v-else style="display: flex; flex-direction: column; gap: 8px;">
      <div
        v-for="sample in filteredSamples"
        :key="sample.filename"
        :style="{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '12px 16px',
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-primary)',
          borderLeft: sample.approval_status === 'approved' ? '3px solid #22c55e' : sample.approval_status === 'rejected' ? '3px solid #ef4444' : '3px solid var(--border-primary)',
          borderRadius: '6px',
        }"
      >
        <!-- Checkbox -->
        <input
          type="checkbox"
          :checked="store.selectedSamples.has(sample.filename)"
          @change="store.toggleSample(sample.filename)"
          style="accent-color: var(--accent-primary);"
        />

        <!-- Audio player -->
        <audio
          :src="getAudioUrl(sample)"
          controls
          preload="none"
          style="height: 32px; min-width: 200px;"
        />

        <!-- Info -->
        <div style="flex: 1; display: flex; gap: 12px; align-items: center; font-size: 13px;">
          <span style="color: var(--text-primary); font-weight: 500; min-width: 120px;">{{ sample.filename }}</span>
          <span style="color: var(--text-muted);">{{ sample.duration_seconds?.toFixed(1) }}s</span>
          <span v-if="sample.snr_db" style="color: var(--text-muted);">SNR: {{ sample.snr_db?.toFixed(0) }}dB</span>
          <span v-if="sample.quality_score" :style="{ color: sample.quality_score >= 0.7 ? '#22c55e' : sample.quality_score >= 0.4 ? '#eab308' : '#ef4444' }">
            Q: {{ (sample.quality_score * 100).toFixed(0) }}%
          </span>
        </div>

        <!-- Transcript edit -->
        <input
          :value="store.transcripts[sample.filename] ?? ''"
          @input="store.updateTranscript(sample.filename, ($event.target as HTMLInputElement).value)"
          :placeholder="sample.transcript || 'Add transcript...'"
          style="width: 200px; padding: 4px 8px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 4px; color: var(--text-primary); font-size: 12px;"
        />

        <!-- Status badge -->
        <span
          :style="{
            fontSize: '11px',
            padding: '2px 8px',
            borderRadius: '4px',
            background: sample.approval_status === 'approved' ? 'rgba(34,197,94,0.15)' : sample.approval_status === 'rejected' ? 'rgba(239,68,68,0.15)' : 'rgba(234,179,8,0.15)',
            color: sample.approval_status === 'approved' ? '#22c55e' : sample.approval_status === 'rejected' ? '#ef4444' : '#eab308',
          }"
        >
          {{ sample.approval_status }}
        </span>

        <!-- Approve/Reject buttons -->
        <div style="display: flex; gap: 4px;">
          <button
            @click="handleApprove(sample, true)"
            :disabled="sample.approval_status === 'approved'"
            title="Approve"
            style="padding: 4px 10px; background: rgba(34,197,94,0.15); color: #22c55e; border: none; border-radius: 4px; cursor: pointer; font-size: 16px;"
          >
            &#10003;
          </button>
          <button
            @click="handleApprove(sample, false)"
            :disabled="sample.approval_status === 'rejected'"
            title="Reject"
            style="padding: 4px 10px; background: rgba(239,68,68,0.15); color: #ef4444; border: none; border-radius: 4px; cursor: pointer; font-size: 16px;"
          >
            &#10007;
          </button>
        </div>
      </div>
    </div>

    <div v-if="store.error" style="margin-top: 16px; padding: 12px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; color: #ef4444; font-size: 13px;">
      {{ store.error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { VoiceSample, Character } from '@/types'
import { voiceApi } from '@/api/voice'
import { useVoiceSamplesStore } from '@/stores/voiceSamples'

const props = defineProps<{
  projectName: string
  characters: Character[]
}>()

const store = useVoiceSamplesStore()

// Local UI state
const selectedCharacter = ref('')

const filteredSamples = computed(() => {
  if (!selectedCharacter.value) return store.allSamples
  return store.allSamples.filter(s => s.character_slug === selectedCharacter.value)
})

function getAudioUrl(sample: VoiceSample): string {
  return voiceApi.getSampleAudioUrl(sample.character_slug, sample.filename)
}

async function handleApprove(sample: VoiceSample, approved: boolean) {
  try {
    await store.approveSample(sample, approved)
    if (selectedCharacter.value) {
      await store.refreshStats(selectedCharacter.value)
    }
  } catch {
    // error is set in store
  }
}

async function handleBatchApprove(approved: boolean) {
  if (!selectedCharacter.value) return
  try {
    await store.batchApprove(selectedCharacter.value, approved)
    await store.refreshStats(selectedCharacter.value)
  } catch {
    // error is set in store
  }
}

watch(selectedCharacter, () => {
  store.reloadSamples(props.characters, selectedCharacter.value || undefined)
})

onMounted(() => {
  store.loadSamples(props.characters, selectedCharacter.value || undefined)
})
</script>
