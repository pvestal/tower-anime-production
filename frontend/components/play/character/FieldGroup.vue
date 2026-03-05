<template>
  <label class="field-group">
    <span class="field-label">{{ label }}</span>
    <slot />
  </label>
</template>

<script setup lang="ts">
defineProps<{ label: string }>()
</script>

<style scoped>
.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted, #888);
}
</style>
