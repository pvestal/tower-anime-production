<template>
  <div class="shared-page">
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Loading project...</p>
    </div>

    <div v-else-if="error" class="error-state">
      <h2>Link Expired or Invalid</h2>
      <p>{{ error }}</p>
      <RouterLink to="/login" class="btn btn-primary" style="margin-top: 16px;">Sign In</RouterLink>
    </div>

    <div v-else-if="project" class="shared-content">
      <!-- Hero -->
      <header class="project-hero">
        <div class="hero-inner">
          <h1>{{ project.name }}</h1>
          <p v-if="project.genre" class="genre-badge">{{ project.genre }}</p>
          <p v-if="project.description" class="project-desc">{{ project.description }}</p>
          <p v-if="project.premise" class="project-premise">{{ project.premise }}</p>
        </div>
      </header>

      <!-- Characters -->
      <section v-if="characters.length" class="content-section">
        <h2>Characters</h2>
        <div class="character-grid">
          <div v-for="c in characters" :key="c.id" class="character-card">
            <div class="char-avatar">{{ c.name.charAt(0) }}</div>
            <span>{{ c.name }}</span>
          </div>
        </div>
      </section>

      <!-- Episodes -->
      <section v-if="episodes.length" class="content-section">
        <h2>Episodes</h2>
        <div class="episodes-list">
          <div v-for="ep in episodes" :key="ep.id" class="episode-card">
            <div class="ep-number">E{{ ep.episode_number }}</div>
            <div class="ep-info">
              <strong>{{ ep.title }}</strong>
              <p v-if="ep.description">{{ ep.description }}</p>
              <span class="ep-meta">
                {{ ep.status }}
                <template v-if="ep.duration_seconds"> · {{ Math.round(ep.duration_seconds) }}s</template>
              </span>
            </div>
          </div>
        </div>
      </section>

      <!-- Comments -->
      <section class="content-section">
        <h2>Comments</h2>

        <!-- Existing comments -->
        <div v-if="comments.length" class="comments-thread">
          <div v-for="c in comments" :key="c.id" class="comment">
            <div class="comment-header">
              <strong>{{ c.reviewer_name }}</strong>
              <span>{{ formatDate(c.created_at) }}</span>
            </div>
            <p>{{ c.comment_text }}</p>
          </div>
        </div>

        <!-- Add comment form -->
        <div class="comment-form">
          <textarea
            v-model="newComment"
            placeholder="Leave feedback on this project..."
            rows="3"
          ></textarea>
          <button class="btn btn-primary" :disabled="!newComment.trim()" @click="submitComment">
            Post Comment
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { createRequest } from '@/api/base'

const request = createRequest('/api')
const route = useRoute()

const loading = ref(true)
const error = ref('')
const project = ref<any>(null)
const characters = ref<any[]>([])
const episodes = ref<any[]>([])
const comments = ref<any[]>([])
const newComment = ref('')

onMounted(async () => {
  const token = route.params.token as string
  try {
    const resp = await request<any>(`/studio/shared/${token}`)
    project.value = resp.project
    characters.value = resp.characters || []
    episodes.value = resp.episodes || []
    comments.value = resp.comments || []
  } catch (e: any) {
    error.value = e?.message || 'Failed to load shared project'
  } finally {
    loading.value = false
  }
})

async function submitComment() {
  if (!newComment.value.trim()) return
  const token = route.params.token as string
  try {
    await request(`/studio/shared/${token}/comments`, {
      method: 'POST',
      body: JSON.stringify({ comment_text: newComment.value }),
    })
    comments.value.unshift({
      id: Date.now(),
      reviewer_name: 'You',
      comment_text: newComment.value,
      created_at: new Date().toISOString(),
    })
    newComment.value = ''
  } catch { /* */ }
}

function formatDate(d: string | null) {
  if (!d) return ''
  return new Date(d).toLocaleDateString()
}
</script>

<style scoped>
.shared-page {
  min-height: 100vh;
  background: var(--bg-primary);
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  color: var(--text-muted);
}

.error-state h2 {
  font-size: 20px;
  color: var(--text-primary);
  margin-bottom: 8px;
}

/* Hero */
.project-hero {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-primary);
  padding: 48px 24px;
}

.hero-inner {
  max-width: 800px;
  margin: 0 auto;
}

.project-hero h1 {
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 8px;
}

.genre-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  background: var(--bg-tertiary);
  color: var(--accent-primary);
  font-size: 13px;
  margin-bottom: 16px;
}

.project-desc {
  font-size: 15px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.project-premise {
  font-size: 14px;
  color: var(--text-muted);
  margin-top: 8px;
  font-style: italic;
}

/* Content sections */
.content-section {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px 24px;
}

.content-section h2 {
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 16px;
  color: var(--text-primary);
}

/* Characters */
.character-grid {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.character-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
}

.char-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
}

/* Episodes */
.episodes-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.episode-card {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
}

.ep-number {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent-primary);
  min-width: 40px;
}

.ep-info strong {
  display: block;
  margin-bottom: 4px;
}

.ep-info p {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.ep-meta {
  font-size: 12px;
  color: var(--text-muted);
}

/* Comments */
.comments-thread {
  margin-bottom: 24px;
}

.comment {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-secondary);
}

.comment-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.comment-header span {
  font-size: 12px;
  color: var(--text-muted);
}

.comment p {
  font-size: 14px;
  color: var(--text-secondary);
}

.comment-form textarea {
  width: 100%;
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  color: var(--text-primary);
  font-family: var(--font-primary);
  font-size: 14px;
  resize: vertical;
  margin-bottom: 8px;
}

.comment-form textarea:focus {
  border-color: var(--accent-primary);
  outline: none;
}
</style>
