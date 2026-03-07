import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/components/kid/KidHome.vue'),
  },
  // ===== Auth routes (no guard) =====
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/components/auth/LoginPage.vue'),
    meta: { public: true },
  },
  {
    path: '/profiles',
    name: 'Profiles',
    component: () => import('@/components/auth/ProfilePicker.vue'),
    meta: { public: true },
  },
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('@/components/auth/OnboardingCarousel.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/components/auth/SettingsPage.vue'),
  },
  {
    path: '/shared/:token',
    name: 'SharedProject',
    component: () => import('@/components/shared/SharedProjectView.vue'),
    meta: { public: true },
  },
  // ===== Primary routes (creative pipeline order) =====
  {
    path: '/story',
    name: 'Story',
    component: () => import('@/components/ProjectTab.vue'),
    meta: { creatorOnly: true },
  },
  {
    path: '/cast',
    component: () => import('@/components/CastTab.vue'),
    redirect: '/cast/characters',
    children: [
      {
        path: 'characters',
        name: 'CastCharacters',
        component: () => import('@/components/CharactersTab.vue'),
        props: { hideSubTabs: true, initialSubTab: 'characters' },
      },
      {
        path: 'ingest',
        name: 'CastIngest',
        component: () => import('@/components/CharactersTab.vue'),
        props: { hideSubTabs: true, initialSubTab: 'ingest' },
        meta: { creatorOnly: true },
      },
      {
        path: 'voice',
        name: 'CastVoice',
        component: () => import('@/components/VoiceTab.vue'),
        meta: { creatorOnly: true },
      },
    ],
  },
  {
    path: '/script',
    component: () => import('@/components/ScriptTab.vue'),
    redirect: '/script/scenes',
    meta: { creatorOnly: true },
    children: [
      {
        path: 'scenes',
        name: 'ScriptScenes',
        component: () => import('@/components/SceneBuilderTab.vue'),
      },
      {
        path: 'screenplay',
        name: 'ScriptScreenplay',
        component: () => import('@/components/script/ScreenplayView.vue'),
      },
    ],
  },
  {
    path: '/produce',
    name: 'Produce',
    component: () => import('@/components/ProduceTab.vue'),
    meta: { creatorOnly: true },
  },
  {
    path: '/review',
    component: () => import('@/components/ReviewTab.vue'),
    redirect: '/review/images',
    meta: { creatorOnly: true },
    children: [
      {
        path: 'images',
        name: 'ReviewImages',
        component: () => import('@/components/PendingTab.vue'),
      },
      {
        path: 'videos',
        name: 'ReviewVideos',
        component: () => import('@/components/PendingVideosTab.vue'),
      },
      {
        path: 'library',
        name: 'ReviewLibrary',
        component: () => import('@/components/LibraryTab.vue'),
      },
    ],
  },
  {
    path: '/publish',
    component: () => import('@/components/PublishTab.vue'),
    redirect: '/publish/episodes',
    children: [
      {
        path: 'episodes',
        name: 'PublishEpisodes',
        component: () => import('@/components/publish/PublishEpisodesView.vue'),
        meta: { creatorOnly: true },
      },
      {
        path: 'library',
        name: 'PublishLibrary',
        component: () => import('@/components/publish/PublishedLibrary.vue'),
      },
    ],
  },
  {
    path: '/play',
    name: 'Play',
    component: () => import('@/components/PlayTab.vue'),
  },
  // ===== Legacy redirects =====
  { path: '/project', redirect: '/story' },
  { path: '/characters', redirect: '/cast/characters' },
  { path: '/create', redirect: '/cast/characters' },
  { path: '/generate', redirect: '/cast/characters' },
  { path: '/ingest', redirect: '/cast/ingest' },
  { path: '/voice', redirect: '/cast/voice' },
  { path: '/voices', redirect: '/cast/voice' },
  { path: '/production', redirect: '/produce' },
  { path: '/train', redirect: '/produce' },
  { path: '/scenes', redirect: '/script/scenes' },
  { path: '/analytics', redirect: '/produce' },
  { path: '/dashboard', redirect: '/produce' },
  { path: '/echo', redirect: '/produce' },
  { path: '/approve', redirect: '/review/images' },
  { path: '/library', redirect: '/review/library' },
  { path: '/gallery', redirect: '/review/library' },
  { path: '/interactive', redirect: '/play' },
]

export const router = createRouter({
  history: createWebHistory('/anime-studio/'),
  routes,
})

// Navigation guard — check auth state
router.beforeEach(async (to, _from, next) => {
  // Public routes skip auth check
  if (to.meta?.public) {
    return next()
  }

  // Import auth store lazily to avoid circular deps
  const { useAuthStore } = await import('@/stores/auth')
  const authStore = useAuthStore()

  // Only check session once (on first navigation)
  if (authStore.loading) {
    await authStore.checkSession()
  }

  // Onboarding redirect
  if (authStore.needsOnboarding && to.name !== 'Onboarding') {
    return next('/onboarding')
  }

  const isViewer = authStore.user?.role === 'viewer'

  // Viewers landing on / get KidHome; non-viewers skip to /story
  if (to.name === 'Home' && !isViewer) {
    return next('/story')
  }

  // Block creator/admin routes for viewers
  if (to.meta?.creatorOnly && isViewer) {
    return next('/')
  }

  next()
})
