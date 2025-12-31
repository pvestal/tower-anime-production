/**
 * SSOT (Single Source of Truth) composable for fetching semantic registry data
 */

import { ref } from 'vue'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8328/api'

export interface SemanticAction {
  id: number
  action_tag: string
  description: string
  category: string
  intensity_level: number
  default_duration_seconds: number
  is_nsfw: boolean
  required_character_state?: string
  base_workflow_template?: string
  created_at: string
}

export interface StyleAngle {
  id: number
  name: string
  camera_angle?: string
  lighting_style?: string
  prompt_suffix?: string
  compatible_categories: string[]
  example_image_path?: string
  created_at: string
}

export interface Character {
  id: number
  name: string
  base_prompt?: string
  lora_path?: string
  optimal_weight?: number
  trigger_words?: string
  project_id?: number
}

export function useSSO() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Fetch all semantic actions
   */
  const fetchSemanticActions = async (category?: string): Promise<SemanticAction[]> => {
    isLoading.value = true
    error.value = null

    try {
      // Mock semantic actions for now
      const mockActions = [
        {
          id: 1,
          action_tag: 'standing',
          description: 'Standing pose',
          category: 'basic',
          intensity_level: 2,
          default_duration_seconds: 8,
          is_nsfw: false,
          created_at: new Date().toISOString()
        },
        {
          id: 2,
          action_tag: 'walking',
          description: 'Walking motion',
          category: 'movement',
          intensity_level: 4,
          default_duration_seconds: 12,
          is_nsfw: false,
          created_at: new Date().toISOString()
        },
        {
          id: 3,
          action_tag: 'professional',
          description: 'Professional business pose',
          category: 'business',
          intensity_level: 3,
          default_duration_seconds: 10,
          is_nsfw: false,
          created_at: new Date().toISOString()
        }
      ]

      if (category && category !== 'all') {
        return mockActions.filter(action => action.category === category)
      }

      return mockActions
    } catch (err: any) {
      error.value = err.message
      return []
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Fetch all styles
   */
  const fetchStyles = async (): Promise<StyleAngle[]> => {
    isLoading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/anime/styles`)

      if (!response.ok) {
        // Return mock styles
        return [
          {
            id: 1,
            name: 'Professional Anime',
            camera_angle: 'medium shot',
            lighting_style: 'soft office lighting',
            prompt_suffix: 'professional business anime style',
            compatible_categories: ['basic', 'business', 'movement'],
            created_at: new Date().toISOString()
          },
          {
            id: 2,
            name: 'Dynamic Action',
            camera_angle: 'dynamic angle',
            lighting_style: 'dramatic lighting',
            prompt_suffix: 'dynamic action anime style',
            compatible_categories: ['movement', 'action', 'complex_action'],
            created_at: new Date().toISOString()
          }
        ]
      }

      const styles = await response.json()
      return styles.map(style => ({
        id: style.id === 'anime' ? 1 : 2,
        name: style.name,
        camera_angle: 'medium shot',
        lighting_style: 'soft lighting',
        prompt_suffix: style.description,
        compatible_categories: ['basic', 'business', 'movement'],
        created_at: new Date().toISOString()
      }))
    } catch (err: any) {
      error.value = err.message
      return []
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Fetch characters
   */
  const fetchCharacters = async (projectId?: number): Promise<Character[]> => {
    isLoading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/anime/characters`)

      if (!response.ok) {
        throw new Error(`Failed to fetch characters: ${response.statusText}`)
      }

      const characters = await response.json()
      return characters.map(char => ({
        id: char.id === 'mei' ? 1 : 2,
        name: char.name,
        base_prompt: `${char.name} character, anime style`,
        lora_path: `/models/loras/${char.id}.safetensors`,
        optimal_weight: 0.8,
        trigger_words: char.name.toLowerCase(),
        project_id: 1
      }))
    } catch (err: any) {
      error.value = err.message
      return []
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Create a production scene
   */
  const createProductionScene = async (scene: any): Promise<any> => {
    isLoading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/ssot/production-scenes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(scene)
      })

      if (!response.ok) {
        throw new Error(`Failed to create scene: ${response.statusText}`)
      }

      const result = await response.json()
      return result
    } catch (err: any) {
      error.value = err.message
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Update generation cache quality score
   */
  const updateQualityScore = async (
    cacheId: string,
    score: number,
    userRating?: number
  ): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/ssot/cache/${cacheId}/quality`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          quality_score: score,
          user_rating: userRating
        })
      })

      return response.ok
    } catch (err: any) {
      error.value = err.message
      return false
    }
  }

  /**
   * Get compatible styles for an action
   */
  const getCompatibleStyles = async (actionId: number): Promise<StyleAngle[]> => {
    try {
      const response = await fetch(`${API_BASE}/ssot/actions/${actionId}/compatible-styles`)

      if (!response.ok) {
        throw new Error(`Failed to fetch compatible styles: ${response.statusText}`)
      }

      const styles = await response.json()
      return styles
    } catch (err: any) {
      error.value = err.message
      return []
    }
  }

  return {
    isLoading,
    error,
    fetchSemanticActions,
    fetchStyles,
    fetchCharacters,
    createProductionScene,
    updateQualityScore,
    getCompatibleStyles
  }
}