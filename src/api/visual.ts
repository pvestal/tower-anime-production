/**
 * Visual domain: image generation, FramePack video, gallery, vision review.
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
import { API_BASE, request } from './base'

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

  async clearStuckGenerations(): Promise<{ message: string; cancelled: number }> {
    return request('/generate/clear-stuck', { method: 'POST' })
  },

  // --- FramePack Video ---

  async generateFramePack(slug: string, params: FramePackParams): Promise<FramePackResponse> {
    return request('/generate/framepack', {
      method: 'POST',
      body: JSON.stringify({ character_slug: slug, ...params }),
    })
  },

  async getFramePackStatus(promptId: string): Promise<GenerationStatus> {
    return request(`/generate/framepack/${encodeURIComponent(promptId)}/status`)
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
    return `${API_BASE}/gallery/image/${encodeURIComponent(filename)}`
  },

  // --- Vision Review ---

  async visionReview(params: { character_slug?: string; project_name?: string; update_captions?: boolean; max_images?: number }): Promise<VisionReviewResponse> {
    return request('/approval/vision-review', {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },
}
