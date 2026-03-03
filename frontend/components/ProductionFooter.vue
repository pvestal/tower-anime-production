<template>
  <footer class="production-footer">
    <div class="footer-left">
      <template v-if="gpuStatus">
        <span class="gpu-chip" :class="nvidiaBusy ? 'gpu-busy' : 'gpu-free'"
              :title="`NVIDIA ${gpuStatus.nvidia?.gpu_name || 'N/A'} — ${gpuStatus.nvidia ? gpuStatus.nvidia.used_mb + '/' + gpuStatus.nvidia.total_mb + 'MB' : 'offline'}`">
          NVIDIA {{ nvidiaBusy ? 'Busy' : gpuStatus.nvidia ? gpuStatus.nvidia.free_mb + 'MB' : 'off' }}
        </span>
        <span class="gpu-chip gpu-free"
              :title="`AMD ${gpuStatus.amd?.gpu_name || 'N/A'} — Ollama${ollamaModels.length ? ': ' + ollamaModels.join(', ') : ''}`">
          AMD {{ gpuStatus.amd ? gpuStatus.amd.free_mb + 'MB' : 'N/A' }}
        </span>
        <span v-if="comfyQueue.queue_running > 0 || comfyQueue.queue_pending > 0" class="gpu-chip gpu-busy">
          ComfyUI {{ comfyQueue.queue_running }}R / {{ comfyQueue.queue_pending }}Q
        </span>
      </template>
    </div>
    <div class="footer-right">
      <!-- Quick filter badges could go here in a future update -->
    </div>
  </footer>
</template>

<script setup lang="ts">
import { useGpuStatus } from '@/composables/useGpuStatus'

const { gpuStatus, nvidiaBusy, comfyQueue, ollamaModels } = useGpuStatus()
</script>

<style scoped>
.production-footer {
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-primary);
  font-size: 11px;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.gpu-chip {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
  border: 1px solid;
  white-space: nowrap;
}

.gpu-free {
  background: rgba(80, 160, 80, 0.1);
  color: var(--status-success, #4caf50);
  border-color: rgba(80, 160, 80, 0.3);
}

.gpu-busy {
  background: rgba(255, 152, 0, 0.1);
  color: var(--status-warning, #ff9800);
  border-color: rgba(255, 152, 0, 0.3);
}
</style>
