<template>
  <div class="body-part-nav">
    <button
      v-for="part in parts"
      :key="part.key"
      class="nav-pill"
      :class="{ active: modelValue === part.key }"
      @click="$emit('update:modelValue', part.key)"
    >
      <span class="pill-icon">{{ icons[part.key] }}</span>
      <span class="pill-label">{{ part.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { BODY_PARTS, type BodyPart } from '@/stores/characterViewer'

defineProps<{ modelValue: BodyPart }>()
defineEmits<{ 'update:modelValue': [value: BodyPart] }>()

const parts = BODY_PARTS

const icons: Record<BodyPart, string> = {
  identity: '\u2606',    // star
  hair: '\u223F',        // sine wave
  eyes: '\u25C9',        // fisheye
  face: '\u25CB',        // circle
  skin: '\u2B22',        // hexagon
  body: '\u2B24',        // filled circle
  outfit: '\u2318',      // cmd
  weapons: '\u2694',     // swords
  accessories: '\u2726', // 4-star
}
</script>

<style scoped>
.body-part-nav {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  overflow-x: auto;
  scrollbar-width: none;
}
.body-part-nav::-webkit-scrollbar { display: none; }

.nav-pill {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: rgba(255,255,255,0.04);
  border: 1px solid transparent;
  border-radius: 20px;
  color: var(--text-muted, #888);
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.nav-pill:hover {
  color: var(--text-primary, #e8e8e8);
  background: rgba(255,255,255,0.08);
  border-color: rgba(255,255,255,0.1);
}

.nav-pill.active {
  color: var(--accent-primary, #6366f1);
  background: rgba(99,102,241,0.12);
  border-color: rgba(99,102,241,0.3);
  transform: scale(1.05);
}

.pill-icon {
  font-size: 13px;
  line-height: 1;
}

.pill-label {
  font-weight: 500;
}
</style>
