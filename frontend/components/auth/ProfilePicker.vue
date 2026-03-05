<template>
  <div class="profile-page">
    <div class="profile-container">
      <h1>Who's watching?</h1>

      <div v-if="loading" class="loading-text">Loading profiles...</div>

      <div v-else class="profiles-grid">
        <button
          v-for="profile in authStore.profiles"
          :key="profile.id"
          class="profile-card"
          @click="selectProfile(profile)"
        >
          <div class="profile-avatar" :class="profile.role">
            <img v-if="profile.avatar_url" :src="profile.avatar_url" :alt="profile.display_name" />
            <span v-else>{{ profile.display_name.charAt(0).toUpperCase() }}</span>
            <div v-if="profile.has_pin" class="pin-badge" title="PIN protected">
              <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM12 17c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1s3.1 1.39 3.1 3.1v2z"/></svg>
            </div>
          </div>
          <span class="profile-name">{{ profile.display_name }}</span>
          <span class="profile-badge">{{ profile.max_rating }}</span>
        </button>

        <!-- Add Profile (admin only) -->
        <RouterLink v-if="authStore.isAdmin" to="/settings" class="profile-card add-profile">
          <div class="profile-avatar add">
            <svg viewBox="0 0 24 24" width="40" height="40"><path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
          </div>
          <span class="profile-name">Add Profile</span>
        </RouterLink>
      </div>

      <!-- PIN Modal -->
      <div v-if="pinModal" class="pin-overlay" @click.self="pinModal = null">
        <div class="pin-card">
          <h3>Enter PIN for {{ pinModal.display_name }}</h3>
          <input
            ref="pinInput"
            v-model="pinValue"
            type="password"
            maxlength="6"
            placeholder="PIN"
            class="pin-input"
            @keyup.enter="submitPin"
          />
          <div v-if="pinError" class="pin-error">{{ pinError }}</div>
          <div class="pin-actions">
            <button class="btn" @click="pinModal = null">Cancel</button>
            <button class="btn btn-primary" @click="submitPin">Enter</button>
          </div>
        </div>
      </div>

      <div class="footer-link">
        <RouterLink to="/login">Sign in with Google instead</RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore, type LocalProfile } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const loading = ref(true)

const pinModal = ref<LocalProfile | null>(null)
const pinValue = ref('')
const pinError = ref('')
const pinInput = ref<HTMLInputElement>()

onMounted(async () => {
  await authStore.fetchProfiles()
  loading.value = false
})

async function selectProfile(profile: LocalProfile) {
  if (profile.has_pin) {
    pinModal.value = profile
    pinValue.value = ''
    pinError.value = ''
    await nextTick()
    pinInput.value?.focus()
    return
  }

  try {
    const result = await authStore.selectProfile(profile.id)
    if (result.requires_pin) {
      pinModal.value = profile
      pinValue.value = ''
      pinError.value = ''
      await nextTick()
      pinInput.value?.focus()
    } else {
      router.push('/story')
    }
  } catch {
    // Error selecting profile
  }
}

async function submitPin() {
  if (!pinModal.value || !pinValue.value) return
  pinError.value = ''
  try {
    await authStore.verifyPin(pinModal.value.id, pinValue.value)
    pinModal.value = null
    router.push('/story')
  } catch {
    pinError.value = 'Incorrect PIN'
    pinValue.value = ''
  }
}
</script>

<style scoped>
.profile-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
}

.profile-container {
  text-align: center;
  padding: 48px;
}

.profile-container h1 {
  font-size: 28px;
  font-weight: 400;
  color: var(--text-primary);
  margin-bottom: 40px;
}

.loading-text {
  color: var(--text-muted);
  font-size: 14px;
}

.profiles-grid {
  display: flex;
  gap: 32px;
  justify-content: center;
  flex-wrap: wrap;
}

.profile-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 16px;
  border-radius: 8px;
  transition: transform 150ms;
  text-decoration: none;
}

.profile-card:hover {
  transform: scale(1.05);
}

.profile-card:hover .profile-avatar {
  border-color: var(--text-primary);
}

.profile-avatar {
  position: relative;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 3px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: border-color 150ms;
}

.profile-avatar.admin { background: linear-gradient(135deg, #7aa2f7, #4a7cf3); }
.profile-avatar.viewer { background: linear-gradient(135deg, #50a050, #308030); }
.profile-avatar.creator { background: linear-gradient(135deg, #a08050, #806030); }
.profile-avatar.add { background: var(--bg-tertiary); border: 2px dashed var(--border-primary); }

.profile-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.profile-avatar span {
  font-size: 36px;
  font-weight: 600;
  color: #fff;
}

.pin-badge {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.profile-name {
  font-size: 14px;
  color: var(--text-secondary);
}

.profile-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

/* PIN Modal */
.pin-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.pin-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  padding: 32px;
  min-width: 300px;
  text-align: center;
}

.pin-card h3 {
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 20px;
  color: var(--text-primary);
}

.pin-input {
  width: 120px;
  padding: 10px;
  text-align: center;
  font-size: 24px;
  letter-spacing: 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  color: var(--text-primary);
  outline: none;
}

.pin-input:focus {
  border-color: var(--accent-primary);
}

.pin-error {
  margin-top: 8px;
  font-size: 13px;
  color: var(--status-error);
}

.pin-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 20px;
}

.footer-link {
  margin-top: 48px;
}

.footer-link a {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 13px;
}

.footer-link a:hover {
  color: var(--accent-primary);
}
</style>
