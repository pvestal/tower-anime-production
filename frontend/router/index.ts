import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/project',
  },
  {
    path: '/project',
    name: 'Project',
    component: () => import('@/components/ProjectTab.vue'),
  },
  {
    path: '/characters',
    name: 'Characters',
    component: () => import('@/components/CharactersTab.vue'),
  },
  {
    path: '/generate',
    name: 'Generate',
    component: () => import('@/components/CreateTab.vue'),
  },
  {
    path: '/review',
    name: 'Review',
    component: () => import('@/components/ReviewTab.vue'),
  },
  {
    path: '/train',
    name: 'Train',
    component: () => import('@/components/TrainingTab.vue'),
  },
  {
    path: '/voice',
    name: 'Voice',
    component: () => import('@/components/VoiceTab.vue'),
  },
  {
    path: '/scenes',
    name: 'Scenes',
    component: () => import('@/components/SceneBuilderTab.vue'),
  },
  {
    path: '/analytics',
    name: 'Analytics',
    component: () => import('@/components/AnalyticsTab.vue'),
  },
  // Legacy redirects
  { path: '/story', redirect: '/project' },
  { path: '/create', redirect: '/generate' },
  { path: '/approve', redirect: '/review' },
  { path: '/library', redirect: '/review' },
  { path: '/gallery', redirect: '/review' },
  { path: '/dashboard', redirect: '/analytics' },
  { path: '/echo', redirect: '/analytics' },
  { path: '/ingest', redirect: '/characters' },
  { path: '/voices', redirect: '/voice' },
]

export const router = createRouter({
  history: createWebHistory('/anime-studio/'),
  routes,
})
