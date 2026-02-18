/**
 * Learning & Autonomy domain: quality insights, drift detection, recommendations.
 */
import type {
  LearningStats,
  EventBusStats,
  ParamRecommendation,
  DriftAlert,
  QualityCharacterSummary,
  QualityTrendPoint,
  RejectionPattern,
  CheckpointRanking,
  ReplenishmentStatus,
  ReadinessResponse,
} from '@/types'
import { request } from './base'

export interface DatasetCharacterStats {
  slug: string
  name: string
  project_name: string
  approved: number
  pending: number
  rejected: number
  total: number
  approval_rate: number
}

export interface DatasetStatsResponse {
  characters: DatasetCharacterStats[]
  totals: { approved: number; pending: number; rejected: number; total: number }
}

export const learningApi = {
  // --- Dataset Stats (real filesystem counts) ---

  async getDatasetStats(projectName?: string): Promise<DatasetStatsResponse> {
    const qs = projectName ? `?project_name=${encodeURIComponent(projectName)}` : ''
    return request(`/dataset-stats${qs}`)
  },

  // --- Learning System ---

  async getLearningStats(): Promise<LearningStats> {
    return request('/learning/stats')
  },

  async getSuggestions(slug: string): Promise<{ character_slug: string; suggestions: ParamRecommendation | null; reason?: string }> {
    return request(`/learning/suggest/${encodeURIComponent(slug)}`)
  },

  async getRejectionPatterns(slug: string): Promise<{ character_slug: string; patterns: RejectionPattern[] }> {
    return request(`/learning/rejections/${encodeURIComponent(slug)}`)
  },

  async getCheckpointRankings(projectName: string): Promise<{ project_name: string; rankings: CheckpointRanking[] }> {
    return request(`/learning/checkpoints/${encodeURIComponent(projectName)}`)
  },

  async getQualityTrend(params: { character_slug?: string; project_name?: string; days?: number }): Promise<{ trend: QualityTrendPoint[] }> {
    const qs = new URLSearchParams()
    if (params.character_slug) qs.set('character_slug', params.character_slug)
    if (params.project_name) qs.set('project_name', params.project_name)
    if (params.days) qs.set('days', String(params.days))
    return request(`/learning/trend?${qs}`)
  },

  // --- Model Selector & Drift ---

  async getRecommendation(slug: string): Promise<{ character_slug: string; recommendation: ParamRecommendation }> {
    return request(`/recommend/${encodeURIComponent(slug)}`)
  },

  async getDriftAlerts(params?: { character_slug?: string; project_name?: string }): Promise<{ alerts: DriftAlert[]; count: number }> {
    const qs = new URLSearchParams()
    if (params?.character_slug) qs.set('character_slug', params.character_slug)
    if (params?.project_name) qs.set('project_name', params.project_name)
    return request(`/drift?${qs}`)
  },

  async getQualitySummary(projectName: string): Promise<{ project_name: string; characters: QualityCharacterSummary[] }> {
    return request(`/quality/summary/${encodeURIComponent(projectName)}`)
  },

  // --- EventBus ---

  async getEventStats(): Promise<EventBusStats> {
    return request('/events/stats')
  },

  // --- Replenishment Loop ---

  async getReplenishmentStatus(): Promise<ReplenishmentStatus> {
    return request('/replenishment/status')
  },

  async toggleReplenishment(enabled: boolean): Promise<{ replenishment_enabled: boolean }> {
    return request(`/replenishment/toggle?enabled=${enabled}`, { method: 'POST' })
  },

  async setReplenishmentTarget(target: number, characterSlug?: string): Promise<{ target: number; scope: string }> {
    const qs = new URLSearchParams({ target: String(target) })
    if (characterSlug) qs.set('character_slug', characterSlug)
    return request(`/replenishment/target?${qs}`, { method: 'POST' })
  },

  async getCharacterReadiness(projectName?: string): Promise<ReadinessResponse> {
    const qs = projectName ? `?project_name=${encodeURIComponent(projectName)}` : ''
    return request(`/replenishment/readiness${qs}`)
  },
}
