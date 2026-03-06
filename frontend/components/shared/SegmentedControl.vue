<template>
  <div class="segmented-control" :class="'sc-' + size">
    <button
      v-for="opt in options"
      :key="opt.value"
      class="sc-btn"
      :class="{ active: modelValue === opt.value }"
      :title="opt.hint"
      @click="$emit('update:modelValue', opt.value)"
    >{{ opt.label }}</button>
  </div>
</template>

<script setup lang="ts">
export interface SegmentedOption {
  value: string | number | null
  label: string
  hint?: string
}

defineProps<{
  modelValue: string | number | null
  options: SegmentedOption[]
  size?: 'sm' | 'md'
}>()

defineEmits<{
  'update:modelValue': [value: string | number | null]
}>()
</script>

<style scoped>
.segmented-control {
  display: inline-flex;
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  overflow: hidden;
  background: var(--bg-primary);
}

.sc-btn {
  padding: 4px 10px;
  font-size: 12px;
  font-family: var(--font-primary);
  border: none;
  border-right: 1px solid var(--border-primary);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: background 100ms, color 100ms;
}

.sc-btn:last-child {
  border-right: none;
}

.sc-btn:hover {
  background: var(--bg-hover, rgba(122, 162, 247, 0.06));
}

.sc-btn.active {
  background: rgba(122, 162, 247, 0.18);
  color: var(--accent-primary);
  font-weight: 600;
}

/* Size variants */
.sc-sm .sc-btn {
  padding: 3px 8px;
  font-size: 11px;
}

.sc-md .sc-btn {
  padding: 5px 12px;
  font-size: 13px;
}
</style>
