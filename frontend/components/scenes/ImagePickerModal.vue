<template>
  <div
    v-if="visible"
    style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center;"
    @click.self="$emit('close')"
  >
    <div class="card" style="width: 700px; max-height: 80vh; overflow-y: auto;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <div style="font-size: 14px; font-weight: 500;">Select Source Image</div>
        <button class="btn" style="font-size: 11px; padding: 2px 8px;" @click="$emit('close')">Close</button>
      </div>

      <!-- Filter hint -->
      <div v-if="charactersPresent && charactersPresent.length > 0" style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px; display: flex; align-items: center; gap: 6px;">
        <span>Filtered for:</span>
        <span v-for="c in charactersPresent" :key="c" style="padding: 1px 6px; background: rgba(122,162,247,0.15); color: var(--accent-primary); border-radius: 10px; font-size: 10px;">{{ c }}</span>
        <button style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 11px; font-family: var(--font-primary);" @click="showAll = !showAll">
          {{ showAll ? 'Show matching only' : 'Show all' }}
        </button>
      </div>

      <div v-if="loading" style="color: var(--text-muted); font-size: 13px;">Loading approved images...</div>
      <div v-else>
        <!-- Matching characters first, then others -->
        <div v-for="(charData, slug) in sortedImages" :key="slug" style="margin-bottom: 16px;">
          <div style="font-size: 13px; font-weight: 500; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
            <span :style="{ color: isMatchingCharacter(slug as string) ? 'var(--accent-primary)' : 'var(--text-secondary)' }">
              {{ charData.character_name }}
            </span>
            <span v-if="isMatchingCharacter(slug as string)" style="font-size: 10px; color: var(--status-success);">match</span>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            <div
              v-for="img in charData.images"
              :key="img"
              style="cursor: pointer; border: 2px solid transparent; border-radius: 4px;"
              @click="$emit('select', slug as string, img)"
            >
              <img
                :src="imageUrl(slug as string, img)"
                style="width: 100px; height: 100px; object-fit: cover; border-radius: 3px;"
                @error="($event.target as HTMLImageElement).style.display = 'none'"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  visible: boolean
  loading: boolean
  approvedImages: Record<string, { character_name: string; images: string[] }>
  imageUrl: (slug: string, imageName: string) => string
  charactersPresent?: string[]
}>()

defineEmits<{
  close: []
  select: [slug: string, imageName: string]
}>()

const showAll = ref(false)

function isMatchingCharacter(slug: string): boolean {
  if (!props.charactersPresent || props.charactersPresent.length === 0) return false
  return props.charactersPresent.includes(slug)
}

const sortedImages = computed(() => {
  const entries = Object.entries(props.approvedImages)
  if (!props.charactersPresent || props.charactersPresent.length === 0 || showAll.value) {
    // Sort matching characters first
    return Object.fromEntries(
      entries.sort(([a], [b]) => {
        const aMatch = isMatchingCharacter(a) ? 0 : 1
        const bMatch = isMatchingCharacter(b) ? 0 : 1
        return aMatch - bMatch
      })
    )
  }
  // Filter to matching characters only
  const filtered = entries.filter(([slug]) => isMatchingCharacter(slug))
  if (filtered.length === 0) {
    // No matches — show all with matching sorted first
    showAll.value = true
    return props.approvedImages
  }
  return Object.fromEntries(filtered)
})
</script>
