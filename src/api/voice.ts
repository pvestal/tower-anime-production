/**
 * Voice pipeline domain: diarization, sample management, training, synthesis.
 */
import type {
  VoiceSpeaker,
  VoiceSample,
  VoiceTrainingJob,
  VoiceSynthesisResult,
  VoiceModelsResponse,
  VoiceSampleStats,
  DiarizationResult,
  SceneDialogueResult,
} from '@/types'
import { request } from './base'

export const voiceApi = {
  // --- Diarization ---

  async diarize(projectName: string): Promise<DiarizationResult> {
    return request('/voice/diarize', {
      method: 'POST',
      body: JSON.stringify({ project_name: projectName }),
    })
  },

  async getSpeakers(projectName: string): Promise<{ project_name: string; speakers: VoiceSpeaker[]; total: number }> {
    return request(`/voice/speakers/${encodeURIComponent(projectName)}`)
  },

  // --- Speaker Assignment ---

  async assignSpeaker(speakerId: number, characterSlug: string, characterId?: number): Promise<{ speaker_id: number; character_slug: string; segments_copied: number }> {
    return request(`/voice/speakers/${speakerId}/assign`, {
      method: 'POST',
      body: JSON.stringify({ character_slug: characterSlug, character_id: characterId }),
    })
  },

  // --- Sample Management ---

  async getSamples(characterSlug: string): Promise<{ character_slug: string; samples: VoiceSample[]; total: number; approved: number; total_approved_duration: number }> {
    return request(`/voice/samples/${encodeURIComponent(characterSlug)}`)
  },

  getSampleAudioUrl(characterSlug: string, filename: string): string {
    return `/api/lora/voice/samples/${encodeURIComponent(characterSlug)}/segment/${encodeURIComponent(filename)}`
  },

  async approveSample(characterSlug: string, filename: string, approved: boolean, opts?: { feedback?: string; transcript?: string; rejection_categories?: string[] }): Promise<{ character_slug: string; filename: string; status: string }> {
    return request('/voice/samples/approve', {
      method: 'POST',
      body: JSON.stringify({
        character_slug: characterSlug,
        filename,
        approved,
        ...opts,
      }),
    })
  },

  async batchApproveSamples(characterSlug: string, filenames: string[], approved: boolean, feedback?: string): Promise<{ character_slug: string; processed: number; results: any[] }> {
    return request('/voice/samples/batch-approve', {
      method: 'POST',
      body: JSON.stringify({
        character_slug: characterSlug,
        filenames,
        approved,
        feedback,
      }),
    })
  },

  async getSampleStats(characterSlug: string): Promise<VoiceSampleStats> {
    return request(`/voice/samples/${encodeURIComponent(characterSlug)}/stats`)
  },

  // --- Training ---

  async trainSovits(characterSlug: string, opts?: { character_name?: string; project_name?: string; epochs?: number }): Promise<VoiceTrainingJob> {
    return request('/voice/train/sovits', {
      method: 'POST',
      body: JSON.stringify({ character_slug: characterSlug, ...opts }),
    })
  },

  async trainRvc(characterSlug: string, opts?: { character_name?: string; project_name?: string; epochs?: number }): Promise<VoiceTrainingJob> {
    return request('/voice/train/rvc', {
      method: 'POST',
      body: JSON.stringify({ character_slug: characterSlug, ...opts }),
    })
  },

  async getVoiceTrainingJobs(params?: { project_name?: string; character_slug?: string }): Promise<{ jobs: VoiceTrainingJob[]; total: number }> {
    const qs = new URLSearchParams()
    if (params?.project_name) qs.set('project_name', params.project_name)
    if (params?.character_slug) qs.set('character_slug', params.character_slug)
    const query = qs.toString() ? `?${qs}` : ''
    return request(`/voice/train/jobs${query}`)
  },

  async getTrainingJob(jobId: string): Promise<VoiceTrainingJob> {
    return request(`/voice/train/jobs/${encodeURIComponent(jobId)}`)
  },

  async getTrainingLog(jobId: string, lines?: number): Promise<{ job_id: string; log: string }> {
    const qs = lines ? `?lines=${lines}` : ''
    return request(`/voice/train/jobs/${encodeURIComponent(jobId)}/log${qs}`)
  },

  async cancelTraining(jobId: string): Promise<{ job_id: string; status: string }> {
    return request(`/voice/train/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' })
  },

  // --- Synthesis ---

  async synthesize(characterSlug: string, text: string, engine?: string): Promise<VoiceSynthesisResult> {
    return request('/voice/synthesize', {
      method: 'POST',
      body: JSON.stringify({ character_slug: characterSlug, text, engine }),
    })
  },

  async getSynthesisResult(jobId: string): Promise<any> {
    return request(`/voice/synthesis/${encodeURIComponent(jobId)}`)
  },

  getSynthesisAudioUrl(jobId: string): string {
    return `/api/lora/voice/synthesis/${encodeURIComponent(jobId)}/audio`
  },

  async generateSceneDialogue(sceneId: string, opts: { dialogue_list?: Array<{ character_slug: string; text: string }>; description?: string; characters?: string[]; pause_seconds?: number }): Promise<SceneDialogueResult> {
    return request(`/voice/scene/${encodeURIComponent(sceneId)}/dialogue`, {
      method: 'POST',
      body: JSON.stringify(opts),
    })
  },

  async getVoiceModels(characterSlug: string): Promise<VoiceModelsResponse> {
    return request(`/voice/models/${encodeURIComponent(characterSlug)}`)
  },
}
