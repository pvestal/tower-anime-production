import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Project, CheckpointFile, ProjectCreate, ProjectUpdate, StorylineUpsert, StyleUpdate, WorldSettings, WorldSettingsUpsert } from '@/types'
import { api } from '@/api/client'

export interface ProjectListItem {
  id: number
  name: string
  default_style: string
  character_count: number
}

export const useProjectStore = defineStore('project', () => {
  const projects = ref<ProjectListItem[]>([])
  const currentProject = ref<Project | null>(null)
  const worldSettings = ref<WorldSettings | null>(null)
  const checkpoints = ref<CheckpointFile[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function fetchProjects() {
    loading.value = true
    error.value = null
    try {
      const resp = await api.getProjects()
      projects.value = resp.projects
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch projects'
    } finally {
      loading.value = false
    }
  }

  async function fetchProjectDetail(projectId: number) {
    loading.value = true
    error.value = null
    try {
      const resp = await api.getProjectDetail(projectId)
      currentProject.value = resp.project
      // world_settings is now included in project detail response
      worldSettings.value = resp.project.world_settings || null
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch project detail'
    } finally {
      loading.value = false
    }
  }

  async function fetchWorldSettings(projectId: number) {
    try {
      const resp = await api.getWorldSettings(projectId)
      worldSettings.value = resp.world_settings
    } catch (err) {
      console.warn('Failed to fetch world settings:', err)
    }
  }

  async function updateWorldSettings(projectId: number, data: WorldSettingsUpsert) {
    saving.value = true
    error.value = null
    try {
      await api.updateWorldSettings(projectId, data)
      await fetchWorldSettings(projectId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update world settings'
    } finally {
      saving.value = false
    }
  }

  async function fetchCheckpoints() {
    try {
      const resp = await api.getCheckpoints()
      checkpoints.value = resp.checkpoints
    } catch (err) {
      console.warn('Failed to fetch checkpoints:', err)
    }
  }

  async function createProject(data: ProjectCreate): Promise<number | null> {
    saving.value = true
    error.value = null
    try {
      const resp = await api.createProject(data)
      await fetchProjects()
      return resp.project_id
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create project'
      return null
    } finally {
      saving.value = false
    }
  }

  async function updateProject(projectId: number, data: ProjectUpdate) {
    saving.value = true
    error.value = null
    try {
      await api.updateProject(projectId, data)
      await fetchProjectDetail(projectId)
      await fetchProjects()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update project'
    } finally {
      saving.value = false
    }
  }

  async function upsertStoryline(projectId: number, data: StorylineUpsert) {
    saving.value = true
    error.value = null
    try {
      await api.upsertStoryline(projectId, data)
      await fetchProjectDetail(projectId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to save storyline'
    } finally {
      saving.value = false
    }
  }

  async function updateStyle(projectId: number, data: StyleUpdate) {
    saving.value = true
    error.value = null
    try {
      await api.updateStyle(projectId, data)
      await fetchProjectDetail(projectId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update style'
    } finally {
      saving.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    projects,
    currentProject,
    worldSettings,
    checkpoints,
    loading,
    saving,
    error,
    fetchProjects,
    fetchProjectDetail,
    fetchCheckpoints,
    fetchWorldSettings,
    updateWorldSettings,
    createProject,
    updateProject,
    upsertStoryline,
    updateStyle,
    clearError,
  }
})
