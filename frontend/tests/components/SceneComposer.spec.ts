/**
 * Unit tests for SceneComposer component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SceneComposer from '@/components/director/SceneComposer.vue'

// Mock the composables
vi.mock('@/composables/useOrchestrator', () => ({
  useOrchestrator: vi.fn(() => ({
    isLoading: ref(false),
    error: ref(null),
    submitGenerationJob: vi.fn(),
    pollJobStatus: vi.fn(),
    rapidRegenerate: vi.fn(),
    getCachedGenerations: vi.fn(),
    cancelJob: vi.fn()
  }))
}))

vi.mock('@/composables/useSSO', () => ({
  useSSO: vi.fn(() => ({
    isLoading: ref(false),
    error: ref(null),
    fetchSemanticActions: vi.fn(),
    fetchStyles: vi.fn(),
    fetchCharacters: vi.fn(),
    createProductionScene: vi.fn(),
    updateQualityScore: vi.fn(),
    getCompatibleStyles: vi.fn()
  }))
}))

vi.mock('@/composables/useNotification', () => ({
  useNotification: vi.fn(() => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showWarning: vi.fn()
  }))
}))

import { ref } from 'vue'
import { useOrchestrator } from '@/composables/useOrchestrator'
import { useSSO } from '@/composables/useSSO'

// Mock data
const mockCharacters = [
  {
    id: 1,
    name: 'Mei Kobayashi',
    base_prompt: 'young japanese woman',
    lora_path: 'mei_v1.safetensors',
    optimal_weight: 0.8
  },
  {
    id: 2,
    name: 'Kai Nakamura',
    base_prompt: 'japanese male protagonist',
    lora_path: 'kai_v1.safetensors',
    optimal_weight: 0.7
  }
]

const mockActions = [
  {
    id: 1,
    action_tag: 'desperate_masturbation',
    description: 'Solo intimate act with intense emotion',
    category: 'intimate',
    intensity_level: 9,
    is_nsfw: true,
    default_duration_seconds: 12
  },
  {
    id: 2,
    action_tag: 'bloody_last_stand',
    description: 'Desperate final battle sequence',
    category: 'violent',
    intensity_level: 9,
    is_nsfw: true,
    default_duration_seconds: 15
  },
  {
    id: 3,
    action_tag: 'walking_cycle',
    description: 'Normal walking animation',
    category: 'casual',
    intensity_level: 1,
    is_nsfw: false,
    default_duration_seconds: 8
  }
]

const mockStyles = [
  {
    id: 1,
    name: 'noir_cinematic',
    camera_angle: 'low_angle_dutch',
    lighting_style: 'volumetric_fog',
    compatible_categories: ['intimate', 'dramatic', 'violent']
  },
  {
    id: 2,
    name: 'romantic_soft_focus',
    camera_angle: 'eye_level',
    lighting_style: 'golden_hour',
    compatible_categories: ['intimate', 'casual']
  },
  {
    id: 3,
    name: 'action_dynamic',
    camera_angle: 'tracking_shot',
    lighting_style: 'motion_blur_lighting',
    compatible_categories: ['action', 'violent']
  }
]

describe('SceneComposer Component', () => {
  let wrapper: any
  let mockOrchestrator: any
  let mockSSO: any

  beforeEach(() => {
    // Reset mocks before each test
    mockOrchestrator = useOrchestrator()
    mockSSO = useSSO()

    // Set up default mock implementations
    mockSSO.fetchCharacters.mockResolvedValue(mockCharacters)
    mockSSO.fetchSemanticActions.mockResolvedValue(mockActions)
    mockSSO.fetchStyles.mockResolvedValue(mockStyles)
  })

  describe('Component Initialization', () => {
    it('loads semantic actions from SSOT on mount', async () => {
      wrapper = mount(SceneComposer)

      await flushPromises()

      expect(mockSSO.fetchSemanticActions).toHaveBeenCalled()
      expect(wrapper.vm.availableActions).toHaveLength(3)
      expect(wrapper.find('[data-test="character-select"]').exists()).toBe(true)
    })

    it('loads characters and styles on mount', async () => {
      wrapper = mount(SceneComposer)

      await flushPromises()

      expect(mockSSO.fetchCharacters).toHaveBeenCalled()
      expect(mockSSO.fetchStyles).toHaveBeenCalled()
      expect(wrapper.vm.availableCharacters).toHaveLength(2)
      expect(wrapper.vm.availableStyles).toHaveLength(3)
    })
  })

  describe('Mature Content Handling', () => {
    it('displays mature content labels', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      // Select mature action
      await wrapper.setData({
        selectedAction: mockActions[0] // desperate_masturbation
      })

      // Should show mature label but no warning
      const matureLabel = wrapper.find('span:contains("Mature")')
      expect(matureLabel.exists()).toBe(true)
    })

    it('allows generation of mature content without restrictions', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      await wrapper.setData({
        selectedCharacter: mockCharacters[0],
        selectedAction: mockActions[0], // Mature action
        selectedStyle: mockStyles[0]
      })

      const generateButton = wrapper.find('[data-test="generate-button"]')
      expect(generateButton.attributes('disabled')).toBeUndefined()
    })
  })

  describe('Payload Construction', () => {
    it('constructs correct API payload for generation', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      await wrapper.setData({
        selectedCharacter: mockCharacters[0],
        selectedAction: mockActions[0],
        selectedStyle: mockStyles[0],
        duration: 12
      })

      const payload = wrapper.vm.buildGenerationPayload()

      expect(payload).toEqual({
        character_id: 1,
        action_id: 1,
        style_angle_id: 1,
        duration_seconds: 12,
        workflow_tier: 'TIER_2_SVD',
        options: { enforce_consistency: true },
        estimated_duration: expect.any(Number)
      })
    })

    it('selects appropriate workflow tier based on duration and action', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      // Test Tier 1 (static)
      await wrapper.setData({
        selectedCharacter: mockCharacters[0],
        selectedAction: mockActions[2], // walking_cycle (low intensity)
        selectedStyle: mockStyles[1],
        duration: 3
      })
      let payload = wrapper.vm.buildGenerationPayload()
      expect(payload.workflow_tier).toBe('TIER_1_STATIC')

      // Test Tier 2 (SVD)
      await wrapper.setData({
        selectedAction: mockActions[0], // desperate_masturbation (high intensity intimate)
        duration: 12
      })
      payload = wrapper.vm.buildGenerationPayload()
      expect(payload.workflow_tier).toBe('TIER_2_SVD')

      // Test Tier 3 (AnimateDiff)
      await wrapper.setData({
        duration: 25 // Long duration
      })
      payload = wrapper.vm.buildGenerationPayload()
      expect(payload.workflow_tier).toBe('TIER_3_ANIMATEDIFF')
    })
  })

  describe('Style Compatibility', () => {
    it('filters styles based on action category', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      // Select intimate action
      await wrapper.setData({
        selectedAction: mockActions[0] // intimate category
      })

      const compatibleStyles = wrapper.vm.compatibleStyles
      expect(compatibleStyles).toHaveLength(2) // noir_cinematic and romantic_soft_focus

      // Select violent action
      await wrapper.setData({
        selectedAction: mockActions[1] // violent category
      })

      const violentStyles = wrapper.vm.compatibleStyles
      expect(violentStyles).toHaveLength(2) // noir_cinematic and action_dynamic
    })
  })

  describe('Generation Workflow', () => {
    it('submits generation job and starts polling', async () => {
      mockOrchestrator.submitGenerationJob.mockResolvedValue({
        job_id: 'test-job-123',
        status: 'submitted',
        estimated_duration: 45
      })

      mockOrchestrator.pollJobStatus.mockResolvedValueOnce({
        status: 'processing',
        progress: 50
      }).mockResolvedValueOnce({
        status: 'completed',
        output_url: '/output/test.mp4',
        cache_key: 'cache123'
      })

      wrapper = mount(SceneComposer)
      await flushPromises()

      await wrapper.setData({
        selectedCharacter: mockCharacters[0],
        selectedAction: mockActions[0],
        selectedStyle: mockStyles[0],
        duration: 12
      })

      // Click generate
      await wrapper.find('[data-test="generate-button"]').trigger('click')
      await flushPromises()

      expect(mockOrchestrator.submitGenerationJob).toHaveBeenCalled()
      expect(wrapper.vm.currentJob).toBeTruthy()
      expect(wrapper.vm.currentJob.id).toBe('test-job-123')
    })

    it('handles generation failures gracefully', async () => {
      mockOrchestrator.submitGenerationJob.mockRejectedValue(
        new Error('ComfyUI connection failed')
      )

      wrapper = mount(SceneComposer)
      await flushPromises()

      await wrapper.setData({
        selectedCharacter: mockCharacters[0],
        selectedAction: mockActions[2], // Non-NSFW for simplicity
        selectedStyle: mockStyles[1],
        duration: 8
      })

      await wrapper.find('[data-test="generate-button"]').trigger('click')
      await flushPromises()

      // Should show error notification (mocked)
      expect(wrapper.vm.currentJob).toBeFalsy()
    })
  })

  describe('Duration Control', () => {
    it('updates duration based on action default', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      // Select action with 15s default
      await wrapper.vm.selectAction(mockActions[1])

      expect(wrapper.vm.duration).toBe(15)
    })

    it('allows manual duration adjustment', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      const durationInput = wrapper.find('[data-test="duration-input"]')
      await durationInput.setValue(20)

      expect(wrapper.vm.duration).toBe(20)
    })
  })

  describe('Category Filtering', () => {
    it('filters actions by category', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      // Click intimate category
      await wrapper.find('[data-test="action-category-intimate"]').trigger('click')

      const filteredActions = wrapper.vm.filteredActions
      expect(filteredActions).toHaveLength(1)
      expect(filteredActions[0].category).toBe('intimate')

      // Click all category
      await wrapper.find('[data-test="action-category-all"]').trigger('click')

      expect(wrapper.vm.filteredActions).toHaveLength(3)
    })
  })

  describe('Rapid Regeneration', () => {
    it('shows rapid regeneration options after successful generation', async () => {
      wrapper = mount(SceneComposer)
      await flushPromises()

      await wrapper.setData({
        lastGeneration: {
          job_id: 'prev-job',
          cache_key: 'cache-abc'
        }
      })

      const rapidButton = wrapper.find('button:contains("Rapid Regenerate")')
      expect(rapidButton.exists()).toBe(true)
    })
  })
})