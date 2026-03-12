<template>
  <div class="watch-library">
    <div v-if="loading" class="watch-loading">Loading shows...</div>

    <div v-else-if="shows.length === 0" class="watch-empty">
      <div class="empty-icon">&#127916;</div>
      <div class="empty-title">Nothing to watch yet</div>
      <div class="empty-sub">Episodes will appear here once they're assembled</div>
    </div>

    <template v-else>
      <!-- Show selector (if multiple projects) -->
      <div v-if="shows.length > 1" class="show-tabs">
        <button
          v-for="show in shows"
          :key="show.id"
          :class="['show-tab', { active: selectedShowId === show.id }]"
          @click="selectShow(show.id)"
        >
          {{ show.name }}
        </button>
      </div>

      <!-- Selected show's episodes -->
      <div v-if="selectedShow" class="show-view">
        <div class="show-header">
          <h2 class="show-name">{{ selectedShow.name }}</h2>
          <span v-if="selectedShow.genre" class="show-genre">{{ selectedShow.genre }}</span>
        </div>

        <div v-if="episodes.length === 0" class="watch-empty" style="padding: 40px 0;">
          <div class="empty-sub">No episodes ready yet for this show</div>
        </div>

        <div v-else class="episode-grid">
          <div
            v-for="ep in episodes"
            :key="ep.id"
            class="episode-card"
            :class="{ playable: ep.hasVideo }"
            @click="ep.hasVideo && playEpisode(ep)"
          >
            <div class="episode-thumb">
              <img
                v-if="ep.coverUrl"
                :src="ep.coverUrl"
                :alt="ep.title"
                @error="($event.target as HTMLImageElement).style.display = 'none'"
              />
              <div v-else class="thumb-placeholder">
                <span class="thumb-number">{{ ep.episode_number }}</span>
              </div>
              <div v-if="ep.hasVideo" class="play-overlay">
                <span class="play-icon">&#9654;</span>
              </div>
              <span v-if="ep.duration" class="duration-badge">{{ formatDuration(ep.duration) }}</span>
            </div>
            <div class="episode-label">
              <span class="ep-num">E{{ ep.episode_number }}</span>
              <span class="ep-title">{{ ep.title }}</span>
            </div>
            <div v-if="ep.description" class="ep-desc">{{ ep.description }}</div>
            <div v-if="!ep.hasVideo" class="ep-status">
              <span class="ep-status-badge">{{ ep.sceneCount }} scene{{ ep.sceneCount !== 1 ? 's' : '' }} &middot; {{ ep.status }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Video Player Modal -->
    <div v-if="playingVideo" class="video-modal" @click.self="playingVideo = null">
      <div class="video-container">
        <video :src="playingVideo" controls autoplay class="video-player"></video>
        <button class="video-close" @click="playingVideo = null">&times;</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storyApi } from '@/api/story'
import { episodesApi } from '@/api/episodes'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const RATING_LEVELS: Record<string, number> = {
  'G': 1, 'PG': 2, 'PG-13': 3, 'R': 4, 'NC-17': 5, 'XXX': 6,
}

interface ShowInfo {
  id: number
  name: string
  genre?: string
  content_rating: string | null
}

interface EpisodeInfo {
  id: string
  episode_number: number
  title: string
  description: string | null
  status: string
  hasVideo: boolean
  videoUrl: string | null
  coverUrl: string | null
  duration: number | null
  sceneCount: number
}

const loading = ref(true)
const shows = ref<ShowInfo[]>([])
const selectedShowId = ref<number>(0)
const episodes = ref<EpisodeInfo[]>([])
const playingVideo = ref<string | null>(null)

const selectedShow = computed(() => shows.value.find(s => s.id === selectedShowId.value) || null)

function isRatingAllowed(rating: string | null): boolean {
  const userMax = authStore.user?.max_rating || 'PG'
  const userLevel = RATING_LEVELS[userMax] ?? 2
  if (!rating) return true
  const projLevel = RATING_LEVELS[rating.toUpperCase()] ?? 3
  return projLevel <= userLevel
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}:${s.toString().padStart(2, '0')}` : `${s}s`
}

async function selectShow(id: number) {
  selectedShowId.value = id
  await loadEpisodes(id)
}

async function loadEpisodes(projectId: number) {
  try {
    const resp = await episodesApi.listEpisodes(projectId)
    episodes.value = (resp.episodes || []).map((ep: any) => ({
      id: ep.id,
      episode_number: ep.episode_number,
      title: ep.title || `Episode ${ep.episode_number}`,
      description: ep.description,
      status: ep.status || 'draft',
      hasVideo: !!ep.final_video_path,
      videoUrl: ep.final_video_path ? episodesApi.episodeVideoUrl(ep.id) : null,
      coverUrl: (ep.cover_frame_path || ep.thumbnail_path) ? episodesApi.episodeCoverUrl(ep.id) : null,
      duration: ep.actual_duration_seconds,
      sceneCount: ep.scene_count || 0,
    }))
  } catch (e) {
    console.error('Failed to load episodes:', e)
    episodes.value = []
  }
}

function playEpisode(ep: EpisodeInfo) {
  if (ep.videoUrl) {
    playingVideo.value = ep.videoUrl
  }
}

onMounted(async () => {
  try {
    const resp = await storyApi.getProjects()
    shows.value = (resp.projects || [])
      .map((p: any) => ({
        id: p.id,
        name: p.name,
        genre: p.genre || null,
        content_rating: p.content_rating || null,
      }))
      .filter((s: ShowInfo) => isRatingAllowed(s.content_rating))

    if (shows.value.length > 0) {
      await selectShow(shows.value[0].id)
    }
  } catch (e) {
    console.error('Failed to load shows:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.watch-library {
  max-width: 1000px;
  margin: 0 auto;
}

.watch-loading {
  text-align: center;
  padding: 80px 0;
  color: var(--text-muted);
  font-size: 16px;
}

.watch-empty {
  text-align: center;
  padding: 80px 0;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.empty-sub {
  font-size: 15px;
  color: var(--text-muted);
}

.show-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.show-tab {
  padding: 10px 20px;
  border-radius: 50px;
  border: 2px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 200ms;
}

.show-tab:hover {
  border-color: var(--accent-primary);
  color: var(--text-primary);
}

.show-tab.active {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: #fff;
}

.show-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 24px;
}

.show-name {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.show-genre {
  font-size: 13px;
  color: var(--text-muted);
  text-transform: capitalize;
}

.episode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 20px;
}

.episode-card {
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  transition: transform 200ms, box-shadow 200ms;
}

.episode-card.playable {
  cursor: pointer;
}

.episode-card.playable:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.episode-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  background: var(--bg-tertiary);
  overflow: hidden;
}

.episode-thumb img {
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
  background: linear-gradient(135deg, rgba(122, 162, 247, 0.15), rgba(80, 160, 120, 0.15));
}

.thumb-number {
  font-size: 36px;
  font-weight: 700;
  color: var(--text-muted);
  opacity: 0.4;
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  opacity: 0;
  transition: opacity 200ms;
}

.episode-card:hover .play-overlay {
  opacity: 1;
}

.play-icon {
  font-size: 40px;
  color: #fff;
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.5));
}

.duration-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.episode-label {
  padding: 10px 12px 2px;
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.ep-num {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-primary);
}

.ep-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ep-desc {
  padding: 0 12px 8px;
  font-size: 12px;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ep-status {
  padding: 0 12px 10px;
}

.ep-status-badge {
  font-size: 11px;
  color: var(--text-muted);
}

/* Video player modal */
.video-modal {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-container {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
}

.video-player {
  max-width: 100%;
  max-height: 85vh;
  border-radius: 8px;
}

.video-close {
  position: absolute;
  top: -40px;
  right: 0;
  background: none;
  border: none;
  color: #fff;
  font-size: 32px;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 150ms;
}

.video-close:hover {
  opacity: 1;
}
</style>
