/**
 * Episode Assembly API — episode CRUD, scene assignment, assembly, publishing.
 */
import type { Episode, EpisodeCreateRequest } from '@/types'
import { API_BASE, request } from './base'

export const episodesApi = {
  async listEpisodes(projectId: number): Promise<{ episodes: Episode[] }> {
    return request(`/episodes?project_id=${projectId}`)
  },

  async createEpisode(data: EpisodeCreateRequest): Promise<{ id: string; episode_number: number }> {
    return request('/episodes', { method: 'POST', body: JSON.stringify(data) })
  },

  async getEpisode(episodeId: string): Promise<Episode> {
    return request(`/episodes/${episodeId}`)
  },

  async updateEpisode(episodeId: string, data: Partial<EpisodeCreateRequest>): Promise<{ message: string }> {
    return request(`/episodes/${episodeId}`, { method: 'PATCH', body: JSON.stringify(data) })
  },

  async deleteEpisode(episodeId: string): Promise<{ message: string }> {
    return request(`/episodes/${episodeId}`, { method: 'DELETE' })
  },

  async addSceneToEpisode(episodeId: string, sceneId: string, position: number, transition: string = 'cut'): Promise<{ message: string }> {
    return request(`/episodes/${episodeId}/scenes`, {
      method: 'POST',
      body: JSON.stringify({ scene_id: sceneId, position, transition }),
    })
  },

  async removeSceneFromEpisode(episodeId: string, sceneId: string): Promise<{ message: string }> {
    return request(`/episodes/${episodeId}/scenes/${sceneId}`, { method: 'DELETE' })
  },

  async reorderEpisodeScenes(episodeId: string, sceneOrder: string[]): Promise<{ message: string }> {
    return request(`/episodes/${episodeId}/reorder`, {
      method: 'PUT',
      body: JSON.stringify({ scene_order: sceneOrder }),
    })
  },

  async assembleEpisode(episodeId: string): Promise<{
    message: string; video_path: string; duration_seconds: number;
    scenes_included: number; scenes_missing: string[]
  }> {
    return request(`/episodes/${episodeId}/assemble`, { method: 'POST' })
  },

  episodeVideoUrl(episodeId: string): string {
    return `${API_BASE}/episodes/${episodeId}/video`
  },

  async publishEpisode(episodeId: string, season: number = 1): Promise<{
    message: string; published_path: string; jellyfin_scan: string
  }> {
    return request(`/episodes/${episodeId}/publish?season=${season}`, { method: 'POST' })
  },
}
