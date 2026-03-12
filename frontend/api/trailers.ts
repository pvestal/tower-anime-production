/**
 * Trailer API client — scorecard, generation, assembly, approval.
 */
import { createRequest } from './base'

const request = createRequest('/api/trailers')

export const trailersApi = {
  listTrailers: (projectId: number) =>
    request<any[]>(`?project_id=${projectId}`),

  getTrailer: (id: string) =>
    request<any>(`/${id}`),

  getScorecard: (id: string, refresh = false) =>
    request<any>(`/${id}/scorecard${refresh ? '?refresh=true' : ''}`),

  refreshScorecard: (id: string) =>
    request<any>(`/${id}/scorecard/refresh`, { method: 'POST' }),

  createTrailer: (projectId: number, title?: string) =>
    request<any>('/create', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, title }),
    }),

  generateKeyframes: (id: string) =>
    request<any>(`/${id}/generate-keyframes`, { method: 'POST' }),

  generateVideos: (id: string, shotIds?: string[]) =>
    request<any>(`/${id}/generate-videos`, {
      method: 'POST',
      body: JSON.stringify({ shot_ids: shotIds }),
      timeoutMs: 300000,
    }),

  assembleTrailer: (id: string) =>
    request<any>(`/${id}/assemble`, { method: 'POST', timeoutMs: 60000 }),

  updateShot: (trailerId: string, shotId: string, updates: Record<string, any>) =>
    request<any>(`/${trailerId}/shots/${shotId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    }),

  shotAction: (trailerId: string, shotId: string, action: string, value?: string) =>
    request<any>(`/${trailerId}/shots/${shotId}/action`, {
      method: 'POST',
      body: JSON.stringify({ action, value }),
    }),

  approveTrailer: (id: string, notes = '') =>
    request<any>(`/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    }),
}
