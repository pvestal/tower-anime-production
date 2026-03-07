import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createRequest } from '@/api/base'

const request = createRequest('/api')

export interface StudioUser {
  id: number
  display_name: string
  email: string | null
  avatar_url: string | null
  role: 'admin' | 'creator' | 'viewer'
  max_rating: string
  ui_mode: 'easy' | 'advanced'
  onboarded: boolean
  preferences: Record<string, unknown>
  created_at: string | null
  last_login: string | null
}

export interface LocalProfile {
  id: number
  display_name: string
  avatar_url: string | null
  role: string
  max_rating: string
  ui_mode: string
  has_pin: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<StudioUser | null>(null)
  const authenticated = ref(false)
  const loading = ref(true)
  const profiles = ref<LocalProfile[]>([])

  const isAdmin = computed(() => user.value?.role === 'admin')
  const isAdvanced = computed(() => user.value?.ui_mode === 'advanced')
  const needsOnboarding = computed(() => authenticated.value && user.value && !user.value.onboarded)

  async function checkSession() {
    loading.value = true
    try {
      const resp = await request<{ authenticated: boolean; user: StudioUser }>('/studio/auth/me')
      authenticated.value = resp.authenticated
      if (resp.authenticated && resp.user) {
        user.value = resp.user
      } else {
        user.value = null
      }
    } catch {
      authenticated.value = false
      user.value = null
    } finally {
      loading.value = false
    }
  }

  async function fetchProfiles() {
    try {
      const resp = await request<{ profiles: LocalProfile[] }>('/studio/auth/profiles')
      profiles.value = resp.profiles
    } catch {
      profiles.value = []
    }
  }

  async function selectProfile(userId: number): Promise<{ requires_pin?: boolean }> {
    const result = await request<{ selected?: boolean; requires_pin?: boolean }>(
      `/studio/auth/local/select?user_id=${userId}`,
      { method: 'POST' }
    )
    if (result.selected) {
      await checkSession()
    }
    return result
  }

  async function verifyPin(userId: number, pin: string) {
    await request('/studio/auth/local/verify-pin', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, pin }),
    })
    await checkSession()
  }

  async function toggleMode() {
    if (!user.value) return
    const newMode = user.value.ui_mode === 'easy' ? 'advanced' : 'easy'
    await request('/studio/auth/me/preferences', {
      method: 'PATCH',
      body: JSON.stringify({ ui_mode: newMode }),
    })
    user.value.ui_mode = newMode
  }

  async function completeOnboarding() {
    await request('/studio/auth/me/preferences', {
      method: 'PATCH',
      body: JSON.stringify({ onboarded: true }),
    })
    if (user.value) {
      user.value.onboarded = true
    }
  }

  async function logout() {
    try {
      await request('/studio/auth/logout', { method: 'POST' })
    } catch { /* ignore */ }
    user.value = null
    authenticated.value = false
  }

  return {
    user,
    authenticated,
    loading,
    profiles,
    isAdmin,
    isAdvanced,
    needsOnboarding,
    checkSession,
    fetchProfiles,
    selectProfile,
    verifyPin,
    toggleMode,
    completeOnboarding,
    logout,
  }
})
