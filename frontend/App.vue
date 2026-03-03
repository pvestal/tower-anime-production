<template>
  <div id="app" style="display: flex; flex-direction: column; min-height: 100vh; background: var(--bg-primary); color: var(--text-primary);">
    <header v-if="showChrome" style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); padding: 16px 24px;">
      <div style="max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <h1 style="font-size: 20px; font-weight: 500; color: var(--text-primary);">Anime Studio</h1>
          <p style="font-size: 13px; color: var(--text-muted);">Story → Cast → Script → Produce → Review → Publish</p>
        </div>
        <div style="display: flex; align-items: center; gap: 16px;">
          <EchoFloatingPanel />
          <!-- Easy/Advanced toggle -->
          <div v-if="authStore.user" style="display: flex; align-items: center; gap: 8px;">
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
                {{ authStore.user.role }} · {{ authStore.user.max_rating }}
              </div>
              <RouterLink to="/settings" class="dropdown-item" @click="showUserMenu = false">Settings</RouterLink>
              <button class="dropdown-item" @click="switchProfile">Switch Profile</button>
              <button class="dropdown-item" @click="doLogout">Log Out</button>
            </div>
          </div>
        </div>
      </div>
    </header>

    <nav v-if="showChrome" style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary);">
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
  approvalStore.fetchPendingImages()
  charactersStore.fetchCharacters()
})

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
    if (!target.closest('.user-menu')) {
      showUserMenu.value = false
    }
  })
}
</script>

<style scoped>
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
  padding: 8px 12px;
  text-align: left;
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: 13px;
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
