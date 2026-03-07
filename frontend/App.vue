<template>
  <div id="app" style="display: flex; flex-direction: column; min-height: 100vh; background: var(--bg-primary); color: var(--text-primary);">

    <!-- ==================== KID-FRIENDLY CHROME ==================== -->
    <template v-if="isViewer && showChrome">
      <header class="kid-header">
        <RouterLink to="/" class="kid-logo">Anime Studio</RouterLink>
        <nav class="kid-nav">
          <RouterLink
            v-for="link in kidNavLinks"
            :key="link.to"
            :to="link.to"
            class="kid-nav-link"
            :class="link.color"
          >
            <span class="kid-nav-icon" v-html="link.icon"></span>
            <span class="kid-nav-label">{{ link.label }}</span>
          </RouterLink>
        </nav>
        <div class="kid-user">
          <button class="kid-avatar-btn" @click="showUserMenu = !showUserMenu">
            <span class="kid-avatar-circle">{{ initials }}</span>
          </button>
          <div v-if="showUserMenu" class="kid-dropdown">
            <button class="dropdown-item" @click="switchProfile">Switch Person</button>
          </div>
        </div>
      </header>

      <main style="flex: 1; max-width: 1400px; width: 100%; margin: 0 auto; padding: 24px;">
        <RouterView />
      </main>
    </template>

    <!-- ==================== STANDARD ADMIN/CREATOR CHROME ==================== -->
    <template v-else>
      <header v-if="showChrome" style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); padding: 16px 24px;">
        <div style="max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <h1 style="font-size: 20px; font-weight: 500; color: var(--text-primary);">Anime Studio</h1>
            <p style="font-size: 13px; color: var(--text-muted);">Story &rarr; Cast &rarr; Script &rarr; Produce &rarr; Review &rarr; Publish</p>
          </div>
          <div style="display: flex; align-items: center; gap: 16px;">
            <EchoFloatingPanel />
            <!-- Easy/Advanced toggle (admin only) -->
            <div v-if="authStore.user && authStore.isAdmin" style="display: flex; align-items: center; gap: 8px;">
              <label
                class="mode-toggle"
                :title="authStore.isAdvanced ? 'Switch to Easy mode' : 'Switch to Advanced mode'"
              >
                <span style="font-size: 12px; color: var(--text-muted);">{{ authStore.isAdvanced ? 'Advanced' : 'Easy' }}</span>
                <input type="checkbox" :checked="authStore.isAdvanced" @change="authStore.toggleMode()" />
                <span class="mode-slider"></span>
              </label>
            </div>
            <!-- User avatar/menu -->
            <div v-if="authStore.user" class="user-menu">
              <button class="user-avatar-btn" @click="showUserMenu = !showUserMenu">
                <img
                  v-if="authStore.user.avatar_url"
                  :src="authStore.user.avatar_url"
                  :alt="authStore.user.display_name"
                  style="width: 32px; height: 32px; border-radius: 50%;"
                />
                <span v-else class="avatar-placeholder">{{ initials }}</span>
                <span style="font-size: 13px; color: var(--text-secondary);">{{ authStore.user.display_name }}</span>
              </button>
              <div v-if="showUserMenu" class="user-dropdown">
                <div style="padding: 8px 12px; border-bottom: 1px solid var(--border-primary); font-size: 12px; color: var(--text-muted);">
                  {{ authStore.user.role }} &middot; {{ authStore.user.max_rating }}
                </div>
                <RouterLink to="/settings" class="dropdown-item" @click="showUserMenu = false">Settings</RouterLink>
                <button class="dropdown-item" @click="switchProfile">Switch Profile</button>
                <button class="dropdown-item" @click="doLogout">Log Out</button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <nav v-if="showChrome && !isViewer" style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary);">
        <div style="max-width: 1400px; margin: 0 auto; padding: 0 24px; display: flex; gap: 0;">
          <RouterLink
            v-for="link in navLinks"
            :key="link.to"
            :to="link.to"
            class="nav-link"
          >
            {{ link.label }}
            <span v-if="link.count !== undefined && link.count > 0" style="margin-left: 6px; font-size: 11px; padding: 1px 6px; border-radius: 10px; background: var(--accent-primary); color: #fff;">
              {{ link.count }}
            </span>
          </RouterLink>
        </div>
      </nav>

      <main :style="mainStyle">
        <RouterView />
      </main>

      <ProductionFooter v-if="showChrome && authStore.user" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApprovalStore } from '@/stores/approval'
import { useCharactersStore } from '@/stores/characters'
import { useAuthStore } from '@/stores/auth'
import EchoFloatingPanel from '@/components/EchoFloatingPanel.vue'
import ProductionFooter from '@/components/ProductionFooter.vue'

const route = useRoute()
const routerInstance = useRouter()
const approvalStore = useApprovalStore()
const charactersStore = useCharactersStore()
const authStore = useAuthStore()

const showUserMenu = ref(false)

const isViewer = computed(() => authStore.user?.role === 'viewer')

// Hide chrome on auth pages and shared view
const showChrome = computed(() => {
  const name = route.name as string
  return !['Login', 'Profiles', 'Onboarding', 'SharedProject'].includes(name)
})

const isSceneEditor = computed(() => route.name === 'ScriptScenes')

const mainStyle = computed(() => {
  if (!showChrome.value) return ''
  if (isSceneEditor.value) {
    return 'flex: 1; overflow: hidden;'
  }
  return 'max-width: 1400px; margin: 0 auto; padding: 24px;'
})

const initials = computed(() => {
  if (!authStore.user?.display_name) return '?'
  return authStore.user.display_name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
})

onMounted(async () => {
  await authStore.checkSession()
  if (!isViewer.value) {
    approvalStore.fetchPendingImages()
  }
  charactersStore.fetchCharacters()
})

// Kid nav — colorful icon links
const kidNavLinks = [
  {
    to: '/cast/characters',
    label: 'Characters',
    color: 'kid-purple',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/></svg>',
  },
  {
    to: '/publish/library',
    label: 'Watch',
    color: 'kid-teal',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polygon points="5,3 19,12 5,21"/></svg>',
  },
  {
    to: '/play',
    label: 'Play',
    color: 'kid-orange',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="6" width="20" height="12" rx="4"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="12" r="2"/></svg>',
  },
]

// Standard admin/creator nav
const navLinks = computed(() => [
  { to: '/story', label: 'Story' },
  { to: '/cast', label: 'Cast' },
  { to: '/script', label: 'Script' },
  { to: '/produce', label: 'Produce' },
  { to: '/review', label: 'Review', count: approvalStore.pendingImages.length },
  { to: '/publish', label: 'Publish' },
  { to: '/play', label: 'Play' },
])

function switchProfile() {
  showUserMenu.value = false
  routerInstance.push('/profiles')
}

async function doLogout() {
  showUserMenu.value = false
  await authStore.logout()
  routerInstance.push('/login')
}

// Close dropdown on outside click
if (typeof document !== 'undefined') {
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    if (!target.closest('.user-menu') && !target.closest('.kid-user')) {
      showUserMenu.value = false
    }
  })
}
</script>

<style scoped>
/* ==================== KID CHROME ==================== */
.kid-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: var(--bg-secondary);
  border-bottom: 2px solid var(--border-primary);
}

.kid-logo {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  text-decoration: none;
}

.kid-nav {
  display: flex;
  gap: 8px;
}

.kid-nav-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 50px;
  text-decoration: none;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  transition: transform 150ms ease, box-shadow 150ms ease;
}

.kid-nav-link:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.kid-nav-link.router-link-active {
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.3);
}

.kid-purple { background: linear-gradient(135deg, #7c5dc7, #a07de8); }
.kid-teal { background: linear-gradient(135deg, #2d8d7e, #40b8a0); }
.kid-orange { background: linear-gradient(135deg, #c06040, #e88060); }

.kid-nav-icon {
  display: flex;
  align-items: center;
}

.kid-nav-label {
  letter-spacing: 0.3px;
}

.kid-user {
  position: relative;
}

.kid-avatar-btn {
  background: none;
  border: 2px solid var(--border-primary);
  border-radius: 50%;
  padding: 0;
  cursor: pointer;
  transition: border-color 150ms;
}

.kid-avatar-btn:hover {
  border-color: var(--accent-primary);
}

.kid-avatar-circle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e88060, #c06040);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
}

.kid-dropdown {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 8px;
  min-width: 160px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  overflow: hidden;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

/* ==================== STANDARD CHROME ==================== */
.nav-link {
  padding: 12px 16px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  font-family: var(--font-primary);
  transition: color 150ms ease;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.nav-link.router-link-active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
}

.user-menu {
  position: relative;
}

.user-avatar-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: 1px solid var(--border-primary);
  border-radius: 20px;
  padding: 4px 12px 4px 4px;
  cursor: pointer;
  color: var(--text-primary);
}

.user-avatar-btn:hover {
  border-color: var(--border-focus);
}

.avatar-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--accent-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.user-dropdown {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  min-width: 180px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  overflow: hidden;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}

.dropdown-item {
  display: block;
  width: 100%;
  padding: 10px 16px;
  text-align: left;
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  text-decoration: none;
}

.dropdown-item:hover {
  background: var(--bg-hover);
}

/* Mode toggle switch */
.mode-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.mode-toggle input {
  display: none;
}

.mode-slider {
  position: relative;
  width: 36px;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  transition: background 200ms;
}

.mode-slider::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--text-secondary);
  border-radius: 50%;
  transition: transform 200ms, background 200ms;
}

.mode-toggle input:checked + .mode-slider {
  background: var(--accent-primary);
}

.mode-toggle input:checked + .mode-slider::after {
  transform: translateX(16px);
  background: #fff;
}
</style>
