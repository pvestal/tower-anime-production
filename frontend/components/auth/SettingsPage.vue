<template>
  <div style="padding: 24px 0;">
    <h2 style="font-size: 20px; font-weight: 500; margin-bottom: 24px;">Settings</h2>

    <!-- Profile Section -->
    <section class="settings-section">
      <h3>Profile</h3>
      <div class="settings-card">
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
          <div class="avatar-large">
            <img v-if="authStore.user?.avatar_url" :src="authStore.user.avatar_url" />
            <span v-else>{{ initials }}</span>
          </div>
          <div>
            <div style="font-size: 16px; font-weight: 500;">{{ authStore.user?.display_name }}</div>
            <div style="font-size: 13px; color: var(--text-muted);">{{ authStore.user?.email || 'Local profile' }}</div>
          </div>
        </div>
        <div class="field-row">
          <label>Interface Mode</label>
          <div class="mode-toggle-row">
            <button
              class="mode-option"
              :class="{ active: authStore.user?.ui_mode === 'easy' }"
              @click="setMode('easy')"
            >Easy</button>
            <button
              class="mode-option"
              :class="{ active: authStore.user?.ui_mode === 'advanced' }"
              @click="setMode('advanced')"
            >Advanced</button>
          </div>
          <p class="field-hint">
            Easy mode hides technical controls (CFG, samplers, orchestrator). Advanced shows everything.
          </p>
        </div>
      </div>
    </section>

    <!-- Admin Section -->
    <template v-if="authStore.isAdmin">
      <section class="settings-section">
        <h3>User Management</h3>
        <div class="settings-card">
          <table class="users-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Role</th>
                <th>Max Rating</th>
                <th>Mode</th>
                <th>Last Login</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td>
                  {{ u.display_name }}
                  <span v-if="u.has_pin" style="margin-left: 4px; color: var(--text-muted);" title="PIN protected">&#128274;</span>
                </td>
                <td>
                  <select :value="u.role" @change="updateUser(u.id, { role: ($event.target as HTMLSelectElement).value })">
                    <option value="admin">Admin</option>
                    <option value="creator">Creator</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </td>
                <td>
                  <select :value="u.max_rating" @change="updateUser(u.id, { max_rating: ($event.target as HTMLSelectElement).value })">
                    <option v-for="r in ratings" :key="r" :value="r">{{ r }}</option>
                  </select>
                </td>
                <td>{{ u.ui_mode }}</td>
                <td style="font-size: 12px; color: var(--text-muted);">{{ formatDate(u.last_login) }}</td>
                <td>
                  <button
                    v-if="u.id !== authStore.user?.id"
                    class="btn btn-sm"
                    style="color: var(--status-error);"
                    @click="deleteUser(u.id)"
                  >Delete</button>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Create User -->
          <div class="create-user-form">
            <input v-model="newUser.display_name" placeholder="Name" class="input-sm" />
            <select v-model="newUser.role" class="input-sm">
              <option value="viewer">Viewer</option>
              <option value="creator">Creator</option>
              <option value="admin">Admin</option>
            </select>
            <select v-model="newUser.max_rating" class="input-sm">
              <option v-for="r in ratings" :key="r" :value="r">{{ r }}</option>
            </select>
            <input v-model="newUser.pin" type="password" placeholder="PIN (optional)" class="input-sm" style="width: 100px;" />
            <button class="btn btn-primary btn-sm" @click="createUser">Add</button>
          </div>
        </div>
      </section>

      <!-- Share Links -->
      <section class="settings-section">
        <h3>Share Links</h3>
        <div class="settings-card">
          <!-- Create Share Link -->
          <div class="create-share-form">
            <select v-model="newShare.project_id" class="input-sm">
              <option :value="0" disabled>Select project...</option>
              <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <select v-model="newShare.max_rating" class="input-sm">
              <option v-for="r in ratings" :key="r" :value="r">{{ r }}</option>
            </select>
            <select v-model="newShare.expires_days" class="input-sm">
              <option :value="1">1 day</option>
              <option :value="7">7 days</option>
              <option :value="30">30 days</option>
            </select>
            <button class="btn btn-primary btn-sm" :disabled="!newShare.project_id" @click="createShareLink">Create Link</button>
          </div>

          <div v-if="shareLinks.length" class="share-links-list">
            <div v-for="sl in shareLinks" :key="sl.id" class="share-link-row" :class="{ expired: sl.expired || !sl.is_active }">
              <div>
                <strong>{{ sl.project_name }}</strong>
                <span class="share-meta">{{ sl.max_rating }} · {{ sl.comment_count }} comments · expires {{ formatDate(sl.expires_at) }}</span>
              </div>
              <div style="display: flex; gap: 8px; align-items: center;">
                <button v-if="sl.is_active && !sl.expired" class="btn btn-sm" @click="copyLink(sl.token)">Copy</button>
                <button v-if="sl.is_active" class="btn btn-sm" style="color: var(--status-error);" @click="revokeLink(sl.token)">Revoke</button>
                <span v-if="!sl.is_active" style="font-size: 12px; color: var(--status-error);">Revoked</span>
                <span v-else-if="sl.expired" style="font-size: 12px; color: var(--status-warning);">Expired</span>
              </div>
            </div>
          </div>
          <p v-else style="color: var(--text-muted); font-size: 13px;">No share links yet.</p>
        </div>
      </section>

      <!-- Reviewer Comments -->
      <section class="settings-section">
        <h3>Reviewer Comments</h3>
        <div class="settings-card">
          <div v-if="comments.length" class="comments-list">
            <div v-for="c in comments" :key="c.id" class="comment-row">
              <div>
                <strong>{{ c.reviewer_name }}</strong>
                <span class="comment-meta">on {{ c.project_name }} · {{ formatDate(c.created_at) }}</span>
              </div>
              <p style="margin-top: 4px; font-size: 13px;">{{ c.comment_text }}</p>
            </div>
          </div>
          <p v-else style="color: var(--text-muted); font-size: 13px;">No reviewer comments yet.</p>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { createRequest } from '@/api/base'

const request = createRequest('/api')
const authStore = useAuthStore()
const projectStore = useProjectStore()

const ratings = ['G', 'PG', 'PG-13', 'R', 'NC-17', 'XXX']
const users = ref<any[]>([])
const shareLinks = ref<any[]>([])
const comments = ref<any[]>([])

const newUser = ref({ display_name: '', role: 'viewer', max_rating: 'PG', pin: '' })
const newShare = ref({ project_id: 0, max_rating: 'PG-13', expires_days: 7 })

const projects = computed(() => projectStore.projects)

const initials = computed(() => {
  if (!authStore.user?.display_name) return '?'
  return authStore.user.display_name.split(' ').map((w: string) => w[0]).join('').toUpperCase().slice(0, 2)
})

onMounted(async () => {
  projectStore.fetchProjects()
  if (authStore.isAdmin) {
    await Promise.all([fetchUsers(), fetchShareLinks(), fetchComments()])
  }
})

async function fetchUsers() {
  try {
    const resp = await request<{ users: any[] }>('/studio/admin/users')
    users.value = resp.users
  } catch { /* */ }
}

async function fetchShareLinks() {
  try {
    const resp = await request<{ share_links: any[] }>('/studio/admin/share-links')
    shareLinks.value = resp.share_links
  } catch { /* */ }
}

async function fetchComments() {
  try {
    const resp = await request<{ comments: any[] }>('/studio/admin/comments')
    comments.value = resp.comments
  } catch { /* */ }
}

async function setMode(mode: string) {
  await request('/studio/auth/me/preferences', {
    method: 'PATCH',
    body: JSON.stringify({ ui_mode: mode }),
  })
  if (authStore.user) authStore.user.ui_mode = mode as 'easy' | 'advanced'
}

async function updateUser(id: number, data: Record<string, string>) {
  await request(`/admin/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
  await fetchUsers()
}

async function deleteUser(id: number) {
  if (!confirm('Delete this user?')) return
  await request(`/admin/users/${id}`, { method: 'DELETE' })
  await fetchUsers()
}

async function createUser() {
  if (!newUser.value.display_name) return
  await request('/studio/admin/users', {
    method: 'POST',
    body: JSON.stringify(newUser.value),
  })
  newUser.value = { display_name: '', role: 'viewer', max_rating: 'PG', pin: '' }
  await fetchUsers()
}

async function createShareLink() {
  const resp = await request<{ token: string }>('/studio/admin/share-links', {
    method: 'POST',
    body: JSON.stringify(newShare.value),
  })
  await fetchShareLinks()
  copyLink(resp.token)
}

function copyLink(token: string) {
  const url = `${window.location.origin}/anime-studio/shared/${token}`
  navigator.clipboard.writeText(url)
}

async function revokeLink(token: string) {
  await request(`/admin/share-links/${token}`, { method: 'DELETE' })
  await fetchShareLinks()
}

function formatDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString()
}
</script>

<style scoped>
.settings-section {
  margin-bottom: 32px;
}

.settings-section h3 {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.settings-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
  padding: 20px;
}

.avatar-large {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--accent-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.avatar-large img { width: 100%; height: 100%; object-fit: cover; }
.avatar-large span { font-size: 20px; font-weight: 600; color: #fff; }

.field-row { margin-top: 16px; }
.field-row label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; }
.field-hint { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

.mode-toggle-row { display: flex; gap: 8px; }

.mode-option {
  padding: 8px 20px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all 150ms;
}

.mode-option.active {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: rgba(122, 162, 247, 0.1);
}

/* Users table */
.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.users-table th {
  text-align: left;
  padding: 8px;
  color: var(--text-muted);
  font-weight: 500;
  border-bottom: 1px solid var(--border-primary);
}

.users-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border-secondary);
}

.users-table select {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  color: var(--text-primary);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.create-user-form,
.create-share-form {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-primary);
}

.input-sm {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 13px;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}

/* Share links */
.share-links-list { margin-top: 16px; }

.share-link-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-secondary);
}

.share-link-row.expired { opacity: 0.5; }

.share-meta,
.comment-meta {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
}

/* Comments */
.comments-list { max-height: 300px; overflow-y: auto; }

.comment-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-secondary);
}
</style>
