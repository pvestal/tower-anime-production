<template>
  <div class="character-carousel">
    <!-- Project filter pills -->
    <div class="filter-row">
      <button
        class="filter-pill"
        :class="{ active: !activeProject }"
        @click="activeProject = null"
      >
        All
      </button>
      <button
        v-for="p in projectNames"
        :key="p"
        class="filter-pill"
        :class="{ active: activeProject === p }"
        @click="activeProject = activeProject === p ? null : p"
      >
        {{ p }}
      </button>
    </div>

    <!-- Carousel -->
    <div class="carousel-wrapper">
      <button
        class="scroll-btn scroll-left"
        @click="scrollBy(-320)"
        :class="{ hidden: !canScrollLeft }"
      >
        &#x2039;
      </button>

      <div class="carousel-track" ref="trackEl" @scroll="updateScrollState">
        <button
          v-for="card in filteredCards"
          :key="card.slug"
          class="char-card"
          :class="{ selected: card.slug === selectedSlug }"
          @click="$emit('select', card.slug)"
        >
          <div class="card-thumb">
            <img
              v-if="card.thumbnailUrl"
              :src="card.thumbnailUrl"
              :alt="card.name"
              loading="lazy"
            />
            <div v-else class="thumb-placeholder">
              <span>&#x2606;</span>
            </div>
          </div>
          <div class="card-name">{{ card.name }}</div>
          <div class="card-project">{{ card.project_name }}</div>
        </button>
      </div>

      <button
        class="scroll-btn scroll-right"
        @click="scrollBy(320)"
        :class="{ hidden: !canScrollRight }"
      >
        &#x203A;
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import type { CharacterCard } from '@/stores/characterViewer'

const props = defineProps<{
  cards: CharacterCard[]
  projectNames: string[]
  selectedSlug: string
}>()

defineEmits<{ select: [slug: string] }>()

const activeProject = ref<string | null>(null)
const trackEl = ref<HTMLElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)

const filteredCards = computed(() =>
  activeProject.value
    ? props.cards.filter(c => c.project_name === activeProject.value)
    : props.cards
)

function scrollBy(px: number) {
  trackEl.value?.scrollBy({ left: px, behavior: 'smooth' })
}

function updateScrollState() {
  const el = trackEl.value
  if (!el) return
  canScrollLeft.value = el.scrollLeft > 10
  canScrollRight.value = el.scrollLeft < el.scrollWidth - el.clientWidth - 10
}

function scrollToSelected() {
  nextTick(() => {
    const el = trackEl.value
    if (!el) return
    const card = el.querySelector('.char-card.selected') as HTMLElement | null
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
    }
    updateScrollState()
  })
}

watch(() => props.selectedSlug, scrollToSelected)
watch(filteredCards, () => nextTick(updateScrollState))

onMounted(() => {
  nextTick(updateScrollState)
  if (props.selectedSlug) scrollToSelected()
})
</script>

<style scoped>
.character-carousel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

/* Filter pills */
.filter-row {
  display: flex;
  gap: 4px;
  padding: 0 16px;
  overflow-x: auto;
  scrollbar-width: none;
}
.filter-row::-webkit-scrollbar { display: none; }

.filter-pill {
  padding: 4px 12px;
  background: rgba(255,255,255,0.04);
  border: 1px solid transparent;
  border-radius: 14px;
  color: var(--text-muted, #888);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.filter-pill:hover {
  color: var(--text-primary, #e8e8e8);
  background: rgba(255,255,255,0.08);
}

.filter-pill.active {
  color: var(--accent-primary, #6366f1);
  background: rgba(99,102,241,0.12);
  border-color: rgba(99,102,241,0.3);
}

/* Carousel wrapper */
.carousel-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.scroll-btn {
  position: absolute;
  z-index: 2;
  width: 28px;
  height: 28px;
  background: rgba(20,20,30,0.9);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 50%;
  color: var(--text-primary, #e8e8e8);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.2s ease, background 0.2s ease;
  backdrop-filter: blur(6px);
}

.scroll-btn:hover {
  background: rgba(99,102,241,0.3);
  border-color: rgba(99,102,241,0.5);
}

.scroll-btn.hidden {
  opacity: 0;
  pointer-events: none;
}

.scroll-left { left: 4px; }
.scroll-right { right: 4px; }

/* Track */
.carousel-track {
  display: flex;
  gap: 10px;
  padding: 4px 16px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  scroll-padding: 16px;
}
.carousel-track::-webkit-scrollbar { display: none; }

/* Card */
.char-card {
  flex-shrink: 0;
  width: 100px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px;
  background: rgba(255,255,255,0.03);
  border: 2px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  font-family: inherit;
  scroll-snap-align: center;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.char-card:hover {
  background: rgba(255,255,255,0.06);
  border-color: rgba(255,255,255,0.1);
}

.char-card.selected {
  background: rgba(99,102,241,0.1);
  border-color: rgba(99,102,241,0.5);
  transform: scale(1.05);
}

/* Thumbnail */
.card-thumb {
  width: 80px;
  height: 100px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255,255,255,0.04);
}

.card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #555);
  font-size: 28px;
  opacity: 0.3;
}

/* Labels */
.card-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary, #e8e8e8);
  text-align: center;
  line-height: 1.2;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-project {
  font-size: 9px;
  color: var(--text-muted, #666);
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
