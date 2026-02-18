/**
 * Tests for the API client (frontend/api/client.ts).
 * Mocks global fetch to verify request URLs, methods, and bodies.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch before importing the module
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Helper to create a mock Response
function mockResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  } as unknown as Response
}

// Import after mocking fetch
import { api } from '@/api/client'

beforeEach(() => {
  mockFetch.mockReset()
})

describe('generateForCharacter', () => {
  it('POSTs to /api/visual/generate/{slug} with JSON body', async () => {
    const responseData = {
      prompt_id: 'abc-123',
      character: 'mario',
      generation_type: 'image',
      prompt_used: 'Mario in a field',
      checkpoint: 'realcartoonPixar_v12.safetensors',
      seed: 42,
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.generateForCharacter('mario', {
      generation_type: 'image',
      prompt_override: 'Mario in a field',
    })

    expect(mockFetch).toHaveBeenCalledOnce()
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/visual/generate/mario')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.generation_type).toBe('image')
    expect(body.prompt_override).toBe('Mario in a field')
    expect(result.prompt_id).toBe('abc-123')
  })
})

describe('getGenerationStatus', () => {
  it('GETs /api/visual/generate/{promptId}/status', async () => {
    const responseData = { status: 'completed', progress: 1.0, images: ['out.png'] }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.getGenerationStatus('abc-123')

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/visual/generate/abc-123/status')
    expect(options.method).toBeUndefined() // GET is default
    expect(result.status).toBe('completed')
  })
})

describe('getGallery', () => {
  it('passes limit param', async () => {
    const responseData = { images: [{ filename: 'img.png', created_at: '2026-01-01', size_kb: 100 }] }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    await api.getGallery(10)

    const [url] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/visual/gallery?limit=10')
  })
})

describe('galleryImageUrl', () => {
  it('returns correct URL string', () => {
    const url = api.galleryImageUrl('test_image.png')
    expect(url).toBe('/api/visual/gallery/image/test_image.png')
  })

  it('encodes special characters', () => {
    const url = api.galleryImageUrl('image with spaces.png')
    expect(url).toContain('image%20with%20spaces.png')
  })
})

describe('echoChat', () => {
  it('sends message and optional character_slug', async () => {
    const responseData = { response: 'Echo reply', context_used: true, character_context: 'Mario context' }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    await api.echoChat('Tell me about Mario', 'mario')

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/echo/chat')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.message).toBe('Tell me about Mario')
    expect(body.character_slug).toBe('mario')
  })

  it('sends without character_slug when omitted', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ response: 'reply', context_used: false }))

    await api.echoChat('general question')

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.character_slug).toBeUndefined()
  })
})

describe('echoNarrate', () => {
  it('POSTs to /api/echo/narrate with context_type and payload', async () => {
    const responseData = {
      suggestion: 'An epic adventure in the stars...',
      confidence: 0.85,
      sources: ['memory_1', 'memory_2'],
      execution_time_ms: 1234,
      context_type: 'storyline',
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.echoNarrate({
      context_type: 'storyline',
      project_name: 'Super Mario Galaxy',
      project_genre: 'anime',
      current_value: 'Mario saves the galaxy',
    })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/echo/narrate')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.context_type).toBe('storyline')
    expect(body.project_name).toBe('Super Mario Galaxy')
    expect(body.current_value).toBe('Mario saves the galaxy')
    expect(result.suggestion).toBe('An epic adventure in the stars...')
    expect(result.confidence).toBe(0.85)
    expect(result.execution_time_ms).toBe(1234)
  })

  it('sends concept type with concept_description', async () => {
    const responseData = {
      suggestion: '{"name":"Neon Tokyo","genre":"cyberpunk"}',
      confidence: 0.7,
      sources: [],
      execution_time_ms: 2000,
      context_type: 'concept',
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    await api.echoNarrate({
      context_type: 'concept',
      concept_description: 'A cyberpunk detective story',
    })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.context_type).toBe('concept')
    expect(body.concept_description).toBe('A cyberpunk detective story')
  })
})

describe('echoEnhancePrompt', () => {
  it('sends prompt and optional slug', async () => {
    const responseData = {
      original_prompt: 'Mario standing',
      echo_brain_context: ['memory 1'],
      suggestion: 'improved prompt',
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.echoEnhancePrompt('Mario standing', 'mario')

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.prompt).toBe('Mario standing')
    expect(body.character_slug).toBe('mario')
    expect(result.echo_brain_context).toEqual(['memory 1'])
  })
})

describe('error handling', () => {
  it('throws ApiError with correct status on 404', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ detail: 'Not found' }, 404))

    await expect(api.getGenerationStatus('bad-id')).rejects.toThrow()

    try {
      mockFetch.mockResolvedValueOnce(mockResponse({ detail: 'Not found' }, 404))
      await api.getGenerationStatus('bad-id')
    } catch (err: unknown) {
      expect((err as { name: string }).name).toBe('ApiError')
      expect((err as { status: number }).status).toBe(404)
    }
  })
})

describe('clearStuckGenerations', () => {
  it('POSTs to /api/training/generate/clear-stuck', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ message: 'Cleared 0', cancelled: 0 }))

    const result = await api.clearStuckGenerations()

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/training/generate/clear-stuck')
    expect(options.method).toBe('POST')
    expect(result.cancelled).toBe(0)
  })
})

// --- Project Configuration API tests ---

describe('getProjectDetail', () => {
  it('GETs /api/story/projects/{id}', async () => {
    const responseData = {
      project: {
        id: 41, name: 'Test Project', description: 'desc', genre: 'anime',
        status: 'active', default_style: 'test_style',
        style: { checkpoint_model: 'test.safetensors', cfg_scale: 7, steps: 25, sampler: 'DPM++ 2M Karras', scheduler: null, width: 768, height: 768, positive_prompt_template: '', negative_prompt_template: '' },
        storyline: null,
      }
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.getProjectDetail(41)

    const [url] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/story/projects/41')
    expect(result.project.id).toBe(41)
    expect(result.project.style?.checkpoint_model).toBe('test.safetensors')
  })
})

describe('createProject', () => {
  it('POSTs to /api/story/projects with JSON body', async () => {
    const responseData = { project_id: 99, style_name: 'my_project_style', message: 'Created' }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.createProject({
      name: 'My Project',
      checkpoint_model: 'cyberrealistic_v9.safetensors',
      steps: 30,
    })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/story/projects')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.name).toBe('My Project')
    expect(body.checkpoint_model).toBe('cyberrealistic_v9.safetensors')
    expect(body.steps).toBe(30)
    expect(result.project_id).toBe(99)
  })
})

describe('updateProject', () => {
  it('PUTs to /api/story/projects/{id}', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ message: 'Updated' }))

    await api.updateProject(41, { name: 'Renamed', description: 'New desc' })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/story/projects/41')
    expect(options.method).toBe('PUT')
    const body = JSON.parse(options.body)
    expect(body.name).toBe('Renamed')
    expect(body.description).toBe('New desc')
  })
})

describe('upsertStoryline', () => {
  it('PUTs to /api/story/projects/{id}/storyline', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ message: 'Saved' }))

    await api.upsertStoryline(41, { title: 'Epic Story', summary: 'A great tale' })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/story/projects/41/storyline')
    expect(options.method).toBe('PUT')
    const body = JSON.parse(options.body)
    expect(body.title).toBe('Epic Story')
    expect(body.summary).toBe('A great tale')
  })
})

describe('updateStyle', () => {
  it('PUTs to /api/story/projects/{id}/style', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ message: 'Updated' }))

    await api.updateStyle(41, { checkpoint_model: 'new.safetensors', steps: 40, cfg_scale: 8.5 })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/story/projects/41/style')
    expect(options.method).toBe('PUT')
    const body = JSON.parse(options.body)
    expect(body.checkpoint_model).toBe('new.safetensors')
    expect(body.steps).toBe(40)
    expect(body.cfg_scale).toBe(8.5)
  })
})

describe('visionReview', () => {
  it('POSTs to /api/visual/approval/vision-review with params', async () => {
    const responseData = {
      reviewed: 3,
      character_slug: 'mario',
      project: null,
      results: [
        { image: 'img_001.png', character_slug: 'mario', quality_score: 0.73, solo: true, issues: [] },
        { image: 'img_002.png', character_slug: 'mario', quality_score: 0.5, solo: false, issues: ['multiple characters'] },
        { image: 'img_003.png', character_slug: 'mario', quality_score: 0.83, solo: true, issues: [] },
      ],
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.visionReview({ character_slug: 'mario', max_images: 5 })

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/visual/approval/vision-review')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.character_slug).toBe('mario')
    expect(body.max_images).toBe(5)
    expect(result.reviewed).toBe(3)
    expect(result.results).toHaveLength(3)
    expect(result.results[0].quality_score).toBe(0.73)
  })

  it('accepts project_name for project-wide review', async () => {
    const responseData = { reviewed: 2, character_slug: null, project: 'Test Project', results: [] }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    await api.visionReview({ project_name: 'Test Project', update_captions: true })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.project_name).toBe('Test Project')
    expect(body.update_captions).toBe(true)
  })
})

describe('getCheckpoints', () => {
  it('GETs /api/story/checkpoints', async () => {
    const responseData = {
      checkpoints: [
        { filename: 'cyberrealistic_v9.safetensors', size_mb: 2048 },
        { filename: 'realcartoonPixar_v12.safetensors', size_mb: 1800 },
      ]
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.getCheckpoints()

    const [url] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/story/checkpoints')
    expect(result.checkpoints).toHaveLength(2)
    expect(result.checkpoints[0].filename).toBe('cyberrealistic_v9.safetensors')
  })
})

// --- FramePack Video Generation API tests ---

describe('generateFramePack', () => {
  it('POSTs to /api/generate/framepack with character_slug and params', async () => {
    const responseData = {
      prompt_id: 'fp-uuid-123',
      character: 'rina_suzuki',
      model: 'i2v',
      seconds: 3.0,
      source_image: 'gen_rina_suzuki_00002.png',
      total_sections: 2,
      total_steps: 50,
      sampler_node_id: '10',
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.generateFramePack('rina_suzuki', {
      seconds: 3,
      steps: 25,
    })

    expect(mockFetch).toHaveBeenCalledOnce()
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/generate/framepack')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.character_slug).toBe('rina_suzuki')
    expect(body.seconds).toBe(3)
    expect(body.steps).toBe(25)
    expect(result.prompt_id).toBe('fp-uuid-123')
    expect(result.total_sections).toBe(2)
    expect(result.total_steps).toBe(50)
    expect(result.sampler_node_id).toBe('10')
    expect(result.source_image).toBe('gen_rina_suzuki_00002.png')
  })

  it('sends all optional FramePack params', async () => {
    const responseData = {
      prompt_id: 'fp-uuid-456',
      character: 'mario',
      model: 'f1',
      seconds: 5.0,
      source_image: 'custom_ref.png',
      total_sections: 4,
      total_steps: 60,
      sampler_node_id: '10',
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    await api.generateFramePack('mario', {
      prompt_override: 'Mario jumping',
      negative_prompt: 'blurry, ugly',
      image_path: 'custom_ref.png',
      seconds: 5,
      steps: 15,
      use_f1: true,
      seed: 42,
      gpu_memory_preservation: 4.0,
    })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.character_slug).toBe('mario')
    expect(body.prompt_override).toBe('Mario jumping')
    expect(body.negative_prompt).toBe('blurry, ugly')
    expect(body.image_path).toBe('custom_ref.png')
    expect(body.seconds).toBe(5)
    expect(body.steps).toBe(15)
    expect(body.use_f1).toBe(true)
    expect(body.seed).toBe(42)
    expect(body.gpu_memory_preservation).toBe(4.0)
  })

  it('sends minimal params when no overrides given', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({
      prompt_id: 'fp-min', character: 'test', model: 'i2v',
      seconds: 3, source_image: 'auto.png',
      total_sections: 2, total_steps: 50, sampler_node_id: '10',
    }))

    await api.generateFramePack('test', {})

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.character_slug).toBe('test')
    expect(body.prompt_override).toBeUndefined()
    expect(body.seed).toBeUndefined()
  })
})

describe('getFramePackStatus', () => {
  it('GETs /api/generate/framepack/{promptId}/status', async () => {
    const responseData = {
      status: 'running',
      progress: 0.5,
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.getFramePackStatus('fp-uuid-123')

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/generate/framepack/fp-uuid-123/status')
    expect(options.method).toBeUndefined() // GET is default
    expect(result.status).toBe('running')
    expect(result.progress).toBe(0.5)
  })

  it('returns completed with output_files', async () => {
    const responseData = {
      status: 'completed',
      progress: 1.0,
      output_files: ['framepack_1234567890_00001.mp4'],
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.getFramePackStatus('fp-done')

    expect(result.status).toBe('completed')
    expect(result.output_files).toEqual(['framepack_1234567890_00001.mp4'])
  })

  it('encodes special characters in prompt_id', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ status: 'unknown', progress: 0 }))

    await api.getFramePackStatus('id with spaces')

    const [url] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/generate/framepack/id%20with%20spaces/status')
  })
})

describe('comfyWsUrl', () => {
  it('returns WebSocket URL using current host', () => {
    const url = api.comfyWsUrl()
    // In test env, location.protocol is 'http:' and location.host is 'localhost'
    expect(url).toMatch(/^wss?:\/\/.*\/comfyui\/ws$/)
  })
})
