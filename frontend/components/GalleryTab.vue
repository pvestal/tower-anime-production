<template>
  <div class="gallery-root">
    <!-- Floating toolbar — sticks to top on scroll, snaps when scrolling stops -->
    <div ref="toolbarRef" class="gallery-toolbar" :class="{ 'toolbar-floating': isFloating }">
      <div class="search-box">
        <input
          v-model="searchInput"
          type="text"
          placeholder="Search by character, project, checkpoint, pose..."
          class="search-input"
          @keydown.enter="store.setSearch(searchInput)"
        />
        <button v-if="searchInput" class="search-clear" @click="searchInput = ''; store.setSearch('')">&#215;</button>
      </div>
      <button class="btn filter-toggle" @click="filtersOpen = !filtersOpen; lazyLoadFilters()">
        {{ filtersOpen ? 'Hide Filters' : 'Filters' }}
        <span v-if="store.activeFilterCount > 0" class="filter-count">{{ store.activeFilterCount }}</span>
      </button>
      <span class="result-count">{{ store.total.toLocaleString() }} {{ store.selectedMediaType === 'video' ? 'videos' : store.selectedMediaType === 'image' ? 'images' : 'media' }}</span>
    </div>
    <!-- Spacer when toolbar is floating to prevent content jump -->
    <div v-if="isFloating" :style="{ height: toolbarHeight + 'px' }"></div>

    <!-- Collapsible filters (also floats with toolbar) -->
    <Transition name="collapse">
      <div v-if="filtersOpen" class="filter-panel" :class="{ 'filters-floating': isFloating }">
        <div v-if="store.filtersLoading" class="filter-loading">Loading filters...</div>
        <template v-else-if="store.filters">
          <!-- Project -->
          <div v-if="store.filters.projects.length" class="filter-row">
            <span class="filter-label">Project</span>
            <div class="filter-chips">
              <button class="chip" :class="{ active: !store.selectedProject }" @click="store.setProject('')">All</button>
              <button
                v-for="p in store.filters.projects"
                :key="p"
                class="chip"
                :class="{ active: store.selectedProject === p }"
                @click="store.setProject(p)"
              >{{ p }}</button>
            </div>
          </div>
          <!-- Character -->
          <div v-if="store.filters.character_slugs.length" class="filter-row">
            <span class="filter-label">Character</span>
            <div class="filter-chips">
              <button class="chip" :class="{ active: !store.selectedCharacter }" @click="store.setCharacter('')">All</button>
              <button
                v-for="(slug, i) in store.filters.character_slugs"
                :key="slug"
                class="chip"
                :class="{ active: store.selectedCharacter === slug }"
                @click="store.setCharacter(slug)"
              >{{ store.filters.characters[i] }}</button>
            </div>
          </div>
          <!-- Checkpoint -->
          <div v-if="store.filters.checkpoints.length" class="filter-row">
            <span class="filter-label">Checkpoint</span>
            <div class="filter-chips">
              <button class="chip" :class="{ active: !store.selectedCheckpoint }" @click="store.setCheckpoint('')">All</button>
              <button
                v-for="ckpt in store.filters.checkpoints"
                :key="ckpt"
                class="chip chip-small"
                :class="{ active: store.selectedCheckpoint === ckpt }"
                @click="store.setCheckpoint(ckpt)"
              >{{ shortCheckpoint(ckpt) }}</button>
            </div>
          </div>
          <!-- Source -->
          <div v-if="store.filters?.sources?.length" class="filter-row">
            <span class="filter-label">Source</span>
            <div class="filter-chips">
              <button class="chip" :class="{ active: !store.selectedSource }" @click="store.setSource?.('')">All</button>
              <button
                v-for="src in store.filters.sources"
                :key="src"
                class="chip chip-small"
                :class="{ active: store.selectedSource === src }"
                @click="store.setSource?.(src)"
              >{{ src }}</button>
            </div>
          </div>
          <!-- Media type -->
          <div class="filter-row">
            <span class="filter-label">Media</span>
            <div class="filter-chips">
              <button class="chip" :class="{ active: !store.selectedMediaType }" @click="store.setMediaType('')">All</button>
              <button class="chip" :class="{ active: store.selectedMediaType === 'image' }" @click="store.setMediaType('image')">Images</button>
              <button class="chip" :class="{ active: store.selectedMediaType === 'video' }" @click="store.setMediaType('video')">Videos</button>
            </div>
          </div>
          <!-- Source -->
          <div v-if="store.filters?.sources?.length" class="filter-row">
            <span class="filter-label">Source</span>
            <div class="filter-chips">
              <button class="chip" :class="{ active: !store.selectedSource }" @click="store.setSource('')">All</button>
              <button
                v-for="src in store.filters.sources"
                :key="src"
                class="chip chip-small"
                :class="{ active: store.selectedSource === src }"
                @click="store.setSource(src)"
              >{{ src }}</button>
            </div>
          </div>
          <!-- Quick filters -->
          <div class="filter-row">
            <span class="filter-label">Quick</span>
            <div class="filter-chips">
              <button class="chip chip-accent" :class="{ active: store.search === 'altmotion' }" @click="quickSearch('altmotion')">Alt Motion</button>
              <button class="chip chip-accent" :class="{ active: store.search === 'loratest' }" @click="quickSearch('loratest')">LoRA Tests</button>
              <button class="chip chip-accent" :class="{ active: store.search === 'duo' }" @click="quickSearch('duo')">Dual Char</button>
              <button class="chip chip-accent" :class="{ active: store.search === 'keyframe' }" @click="quickSearch('keyframe')">Keyframes</button>
            </div>
          </div>
        </template>
      </div>
    </Transition>

    <!-- Masonry grid — true staggered layout via CSS columns -->
    <div class="masonry-grid" :style="{ columnCount: columns }">
      <div
        v-for="img in store.images"
        :key="img.filename"
        class="masonry-item"
        :class="{ 'masonry-video': img.media_type === 'video' }"
        @click="openLightbox(img)"
        @mouseenter="img.media_type === 'video' && playVideo($event)"
        @mouseleave="img.media_type === 'video' && pauseVideo($event)"
      >
        <!-- Video -->
        <template v-if="img.media_type === 'video'">
          <video
            :src="galleryImageUrl(img.filename)"
            :alt="img.filename"
            class="masonry-img"
            muted
            loop
            playsinline
            preload="metadata"
            @loadeddata="($event.target as HTMLVideoElement).parentElement?.classList.add('loaded')"
          />
          <div class="video-badge">VIDEO</div>
        </template>
        <!-- Image -->
        <template v-else>
          <img
            :src="galleryImageUrl(img.filename)"
            :alt="img.filename"
            loading="lazy"
            class="masonry-img"
            @load="($event.target as HTMLImageElement).parentElement?.classList.add('loaded')"
          />
        </template>
        <div class="masonry-overlay">
          <div class="masonry-meta-left">
            <span class="masonry-name">{{ formatName(img.filename) }}</span>
            <span v-if="img.project_name" class="masonry-project">{{ img.project_name }}</span>
            <span v-if="img.source && img.source !== 'manual'" class="masonry-source">{{ img.source }}</span>
          </div>
          <div class="masonry-meta-right">
            <span v-if="img.checkpoint_model" class="masonry-ckpt">{{ shortCheckpoint(img.checkpoint_model) }}</span>
            <span class="masonry-time">{{ relativeTime(img.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading / empty -->
    <div v-if="store.loading" class="loading-row">
      <div class="spinner"></div>
      Loading...
    </div>
    <div v-else-if="store.loadingMore" class="loading-row">
      <div class="spinner"></div>
      Loading more...
    </div>
    <div v-else-if="store.images.length === 0" class="empty-state">
      No media found{{ store.search || store.activeFilterCount ? ' for current filters' : '' }}.
    </div>

    <!-- Infinite scroll sentinel -->
    <div ref="sentinelRef" class="sentinel"></div>

    <!-- Lightbox -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="lightboxImage" class="lightbox-overlay" @click.self="lightboxImage = null">
          <div class="lightbox-content">
            <button class="lightbox-close" @click="lightboxImage = null">&#215;</button>
            <video v-if="lightboxImage.media_type === 'video'" :src="galleryImageUrl(lightboxImage.filename)" class="lightbox-img" controls autoplay loop playsinline />
            <img v-else :src="galleryImageUrl(lightboxImage.filename)" :alt="lightboxImage.filename" class="lightbox-img" />
            <div class="lightbox-info">
              <span class="lightbox-name">{{ lightboxImage.filename }}</span>
              <span v-if="lightboxImage.project_name" class="lightbox-detail">{{ lightboxImage.project_name }}</span>
              <span v-if="lightboxImage.checkpoint_model" class="lightbox-detail">{{ shortCheckpoint(lightboxImage.checkpoint_model) }}</span>
              <span class="lightbox-meta">{{ lightboxImage.size_kb }}KB &middot; {{ new Date(lightboxImage.created_at).toLocaleString() }}</span>
            </div>
            <button v-if="lightboxIndex > 0" class="lightbox-nav lightbox-prev" @click.stop="navLightbox(-1)">&#8249;</button>
            <button v-if="lightboxIndex < store.images.length - 1" class="lightbox-nav lightbox-next" @click.stop="navLightbox(1)">&#8250;</button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useGalleryStore, type GalleryItem } from '@/stores/gallery'
import { visualApi } from '@/api/visual'

const store = useGalleryStore()

const searchInput = ref(store.search)
const filtersOpen = ref(false)
const lightboxImage = ref<GalleryItem | null>(null)
const lightboxIndex = ref(0)
const sentinelRef = ref<HTMLElement | null>(null)
const toolbarRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

// ── Floating toolbar state ──
const isFloating = ref(false)
const toolbarHeight = ref(0)
let scrollTimeout: ReturnType<typeof setTimeout> | null = null
let toolbarOffsetTop = 0

function onScroll() {
  if (!toolbarRef.value) return

  // Float when scrolled past toolbar's original position
  const scrollY = window.scrollY
  if (scrollY > toolbarOffsetTop) {
    if (!isFloating.value) {
      toolbarHeight.value = toolbarRef.value.offsetHeight
      isFloating.value = true
    }
  } else {
    isFloating.value = false
  }

  // Snap: hide while actively scrolling, show when stopped
  toolbarRef.value.classList.add('toolbar-scrolling')
  if (scrollTimeout) clearTimeout(scrollTimeout)
  scrollTimeout = setTimeout(() => {
    toolbarRef.value?.classList.remove('toolbar-scrolling')
  }, 150)
}

// ── Responsive columns ──
const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1440)
const columns = computed(() => {
  const w = windowWidth.value
  if (w < 640) return 2
  if (w < 1024) return 3
  if (w < 1440) return 4
  if (w < 1920) return 5
  if (w < 2560) return 6
  return 7
})

function galleryImageUrl(filename: string): string {
  return visualApi.galleryImageUrl(filename)
}

function shortCheckpoint(ckpt: string): string {
  return ckpt.replace('.safetensors', '').replace(/_/g, ' ')
}

function formatName(filename: string): string {
  return filename.replace(/(_\d{10,}_\d+_\.(png|jpg|mp4)|\.png|\.jpg|\.mp4)$/i, '').replace(/_/g, ' ')
}

function playVideo(e: MouseEvent) {
  const video = (e.currentTarget as HTMLElement).querySelector('video')
  video?.play().catch(() => {})
}

function pauseVideo(e: MouseEvent) {
  const video = (e.currentTarget as HTMLElement).querySelector('video')
  if (video) { video.pause(); video.currentTime = 0 }
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function quickSearch(q: string) {
  const next = store.search === q ? '' : q
  searchInput.value = next
  store.setSearch(next)
}

function lazyLoadFilters() {
  if (filtersOpen.value) store.loadFilters()
}

function openLightbox(img: GalleryItem) {
  lightboxIndex.value = store.images.indexOf(img)
  lightboxImage.value = img
}

function navLightbox(dir: number) {
  const next = lightboxIndex.value + dir
  if (next >= 0 && next < store.images.length) {
    lightboxIndex.value = next
    lightboxImage.value = store.images[next]
  }
}

function onKeydown(e: KeyboardEvent) {
  if (!lightboxImage.value) return
  if (e.key === 'Escape') lightboxImage.value = null
  if (e.key === 'ArrowLeft') navLightbox(-1)
  if (e.key === 'ArrowRight') navLightbox(1)
}

function onResize() { windowWidth.value = window.innerWidth }

onMounted(() => {
  if (store.images.length === 0) {
    store.loadImages()
  }
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
  window.addEventListener('scroll', onScroll, { passive: true })

  // Capture toolbar's original offset for float detection
  nextTick(() => {
    if (toolbarRef.value) {
      toolbarOffsetTop = toolbarRef.value.offsetTop
    }

    if (sentinelRef.value) {
      observer = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting && store.hasMore && !store.loading && !store.loadingMore) {
            store.loadImages(true)
          }
        },
        { rootMargin: '400px' }
      )
      observer.observe(sentinelRef.value)
    }
  })
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('scroll', onScroll)
  observer?.disconnect()
  if (scrollTimeout) clearTimeout(scrollTimeout)
})
</script>

<style scoped>
.gallery-root {
  display: flex;
  flex-direction: column;
}

/* ── Floating toolbar ── */
.gallery-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  transition: opacity 200ms ease, transform 200ms ease;
}
.gallery-toolbar.toolbar-floating {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-primary);
  padding: 10px 24px;
  margin-bottom: 0;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.4);
}
.gallery-toolbar.toolbar-floating.toolbar-scrolling {
  opacity: 0.3;
  transform: translateY(-2px);
  pointer-events: none;
}
.filter-panel.filters-floating {
  position: fixed;
  top: 52px;
  left: 0;
  right: 0;
  z-index: 99;
  margin: 0;
  border-radius: 0;
  border-left: none;
  border-right: none;
  padding: 12px 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.search-box {
  flex: 1;
  min-width: 200px;
  position: relative;
}
.search-input {
  width: 100%;
  padding: 8px 32px 8px 12px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  font-size: 13px;
  font-family: var(--font-primary);
  outline: none;
  transition: border-color 150ms;
}
.search-input:focus { border-color: var(--accent-primary); }
.search-clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  padding: 0 4px;
}
.filter-toggle { font-size: 12px; padding: 7px 14px; white-space: nowrap; }
.filter-count {
  display: inline-block;
  background: var(--accent-primary);
  color: #fff;
  font-size: 10px;
  padding: 0 5px;
  border-radius: 8px;
  margin-left: 4px;
}
.result-count { font-size: 12px; color: var(--text-muted); white-space: nowrap; }

/* Filters */
.filter-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.filter-loading { font-size: 12px; color: var(--text-muted); padding: 8px 0; }
.filter-row { display: flex; gap: 8px; align-items: flex-start; }
.filter-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 80px;
  padding-top: 4px;
}
.filter-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.chip {
  padding: 3px 10px;
  border-radius: 14px;
  border: 1px solid var(--border-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  font-family: var(--font-primary);
  transition: all 120ms ease;
  white-space: nowrap;
}
.chip:hover { border-color: var(--accent-primary); color: var(--text-primary); }
.chip.active { background: var(--accent-primary); border-color: var(--accent-primary); color: #fff; }
.chip-small { padding: 2px 8px; font-size: 10px; }
.chip-accent { border-color: rgba(122, 162, 247, 0.3); color: var(--accent-primary); }
.chip-accent.active { background: var(--accent-primary); color: #fff; }

/* Collapse transition */
.collapse-enter-active, .collapse-leave-active { transition: all 200ms ease; overflow: hidden; }
.collapse-enter-from, .collapse-leave-to { opacity: 0; max-height: 0; padding-top: 0; padding-bottom: 0; margin-bottom: 0; }
.collapse-enter-to, .collapse-leave-from { max-height: 400px; }

/* ── Masonry grid — true staggered Pinterest-style layout ──
   CSS columns naturally stagger because each image has a different
   aspect ratio / height. Items flow top-to-bottom per column,
   creating the uneven brick-wall effect. */
.masonry-grid {
  column-gap: 10px;
}
.masonry-item {
  break-inside: avoid;
  margin-bottom: 10px;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  cursor: pointer;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.masonry-item:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3); }
.masonry-item:not(.loaded) { min-height: 200px; }
.masonry-img { width: 100%; display: block; opacity: 0; transition: opacity 300ms ease; }
.masonry-item.loaded .masonry-img { opacity: 1; }
.video-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  font-size: 9px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  background: rgba(220, 50, 50, 0.85);
  color: #fff;
  letter-spacing: 0.5px;
  pointer-events: none;
  z-index: 2;
}
.masonry-video video { object-fit: cover; }
.masonry-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 28px 8px 6px;
  background: linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 100%);
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  opacity: 0;
  transition: opacity 150ms ease;
}
.masonry-item:hover .masonry-overlay { opacity: 1; }
.masonry-meta-left { display: flex; flex-direction: column; gap: 1px; max-width: 65%; }
.masonry-meta-right { display: flex; flex-direction: column; align-items: flex-end; gap: 1px; }
.masonry-name { font-size: 10px; color: #e0e0e0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.masonry-project { font-size: 9px; color: rgba(122, 162, 247, 0.9); }
.masonry-source { font-size: 8px; color: rgba(160, 200, 120, 0.8); }
.masonry-ckpt { font-size: 8px; color: rgba(255,255,255,0.5); white-space: nowrap; }
.masonry-time { font-size: 9px; color: rgba(255,255,255,0.5); white-space: nowrap; }

/* Loading */
.loading-row { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 24px; color: var(--text-muted); font-size: 13px; }
.empty-state { text-align: center; padding: 48px; color: var(--text-muted); font-size: 14px; }
.sentinel { height: 1px; }

/* Lightbox */
.lightbox-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.92); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.lightbox-content { position: relative; max-width: 90vw; max-height: 90vh; display: flex; flex-direction: column; align-items: center; }
.lightbox-close { position: absolute; top: -32px; right: 0; background: none; border: none; color: #fff; font-size: 28px; cursor: pointer; z-index: 10; }
.lightbox-img { max-width: 90vw; max-height: 80vh; border-radius: 6px; object-fit: contain; }
.lightbox-info { margin-top: 10px; display: flex; flex-direction: column; align-items: center; gap: 2px; }
.lightbox-name { font-size: 12px; color: #ccc; word-break: break-all; text-align: center; }
.lightbox-detail { font-size: 11px; color: var(--accent-primary); }
.lightbox-meta { font-size: 11px; color: #888; }
.lightbox-nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2);
  border-radius: 50%; color: #fff; width: 40px; height: 40px; font-size: 24px;
  cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 100ms;
}
.lightbox-nav:hover { background: rgba(255,255,255,0.15); }
.lightbox-prev { left: -60px; }
.lightbox-next { right: -60px; }

.fade-enter-active, .fade-leave-active { transition: opacity 150ms; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
