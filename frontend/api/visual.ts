/**
 * Visual domain: image generation, FramePack video, gallery, vision review.
 * Backend: /api/visual/*
 */
import type {
  GenerateParams,
  GenerateResponse,
  GenerationStatus,
  FramePackParams,
  FramePackResponse,
  GalleryImage,
  VisionReview,
  VisionReviewResponse,
} from '@/types'

export interface DirectVisionReviewResponse {
  image_path: string
  character_name: string
  design_prompt: string
  quality_score: number
  review: VisionReview & {
    is_human?: boolean
    gender_match?: boolean
    has_anatomical_defects?: boolean
    common_error_hits?: string[]
    species_verified?: boolean
  }
  categories: string[]
}
import { ApiError, createRequest } from './base'

const request = createRequest('/api/visual')
const sceneRequest = createRequest('/api')
const VISUAL_BASE = '/api/visual'

export const visualApi = {
  // --- Generation ---

  async generateForCharacter(slug: string, params: GenerateParams): Promise<GenerateResponse> {
    return request(`/generate/${encodeURIComponent(slug)}`, {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },

  async getGenerationStatus(promptId: string): Promise<GenerationStatus> {
    return request(`/generate/${encodeURIComponent(promptId)}/status`)
  },

  // --- FramePack Video (on scene_router → /api/generate/framepack) ---

  async generateFramePack(slug: string, params: FramePackParams): Promise<FramePackResponse> {
    return sceneRequest('/generate/framepack', {
      method: 'POST',
      body: JSON.stringify({ character_slug: slug, ...params }),
    })
  },

  async getFramePackStatus(promptId: string): Promise<GenerationStatus> {
    return sceneRequest(`/generate/framepack/${encodeURIComponent(promptId)}/status`)
  },

  comfyWsUrl(): string {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}/comfyui/ws`
  },

  // --- Character Thumbnails ---

  async getCharacterThumbnails(): Promise<{ thumbnails: Record<string, string> }> {
    return request('/character-thumbnails')
  },

  datasetImageUrl(path: string): string {
    return `${VISUAL_BASE}/${path}`
  },

  // --- Gallery ---

  async getGallery(params: number | {
    limit?: number; offset?: number; search?: string;
    character?: string; project?: string; checkpoint?: string; pose?: string;
    source?: string; media_type?: string;
  } = {}): Promise<{ images: GalleryImage[]; total: number; has_more: boolean }> {
    if (typeof params === 'number') {
      params = { limit: params }
    }
    const qs = new URLSearchParams()
    if (params.limit) qs.set('limit', String(params.limit))
    if (params.offset) qs.set('offset', String(params.offset))
    if (params.search) qs.set('search', params.search)
    if (params.character) qs.set('character', params.character)
    if (params.project) qs.set('project', params.project)
    if (params.checkpoint) qs.set('checkpoint', params.checkpoint)
    if (params.pose) qs.set('pose', params.pose)
    if (params.source) qs.set('source', params.source)
    if (params.media_type) qs.set('media_type', params.media_type)
    return request(`/gallery?${qs.toString()}`)
  },

  async getGalleryFilters(): Promise<{
    projects: string[]; characters: string[]; character_slugs: string[]; checkpoints: string[]; sources: string[];
  }> {
    return request('/gallery/filters')
  },

  galleryImageUrl(filename: string): string {
    return `${VISUAL_BASE}/gallery/image/${encodeURIComponent(filename)}`
  },

  // --- Vision Review ---

  async visionReview(params: { character_slug?: string; project_name?: string; update_captions?: boolean; max_images?: number }): Promise<VisionReviewResponse> {
    return request('/approval/vision-review', {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },

  async visionReviewDirect(params: {
    character_slug?: string; image_name?: string; image_path?: string;
    character_name?: string; design_prompt?: string; model?: string;
  }): Promise<DirectVisionReviewResponse> {
    return request('/vision-review-direct', {
      method: 'POST',
      body: JSON.stringify(params),
      timeoutMs: 120000,  // vision review can take up to 90s
    })
  },

  async visionReviewUpload(file: File, characterName?: string, designPrompt?: string): Promise<DirectVisionReviewResponse> {
    const formData = new FormData()
    formData.append('file', file)
    if (characterName) formData.append('character_name', characterName)
    if (designPrompt) formData.append('design_prompt', designPrompt)

    const response = await fetch(`${VISUAL_BASE}/vision-review-upload`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new ApiError(response.status, errorText)
    }
    return response.json()
  },
}
