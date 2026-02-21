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
  VisionReviewResponse,
} from '@/types'
import { createRequest } from './base'

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

  // --- Gallery ---

  async getGallery(limit: number = 50): Promise<{ images: GalleryImage[] }> {
    return request(`/gallery?limit=${limit}`)
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
}
