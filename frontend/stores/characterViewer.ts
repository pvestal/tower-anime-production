import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Character, AppearanceData } from '@/types'
import { storyApi } from '@/api/story'
import { visualApi } from '@/api/visual'
import type { GenerationStatus } from '@/types'

export interface CharacterCard {
  name: string
  slug: string
  project_name: string
  thumbnailUrl: string | null
}

export type BodyPart = 'hair' | 'eyes' | 'face' | 'skin' | 'body' | 'outfit' | 'weapons' | 'accessories' | 'identity'

export const BODY_PARTS: { key: BodyPart; label: string }[] = [
  { key: 'identity', label: 'Identity' },
  { key: 'hair', label: 'Hair' },
  { key: 'eyes', label: 'Eyes' },
  { key: 'face', label: 'Face' },
  { key: 'skin', label: 'Skin' },
  { key: 'body', label: 'Body' },
  { key: 'outfit', label: 'Outfit' },
  { key: 'weapons', label: 'Weapons' },
  { key: 'accessories', label: 'Accessories' },
]

export const useCharacterViewerStore = defineStore('characterViewer', () => {
  // State
  const character = ref<Character | null>(null)
  const appearance = ref<AppearanceData>({})
  const activePart = ref<BodyPart>('identity')
  const dirty = ref(false)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  // Generation
  const generating = ref(false)
  const genPromptId = ref<string | null>(null)
  const genStatus = ref<GenerationStatus | null>(null)
  const portraitUrl = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  // Character list for selector
  const characters = ref<{ name: string; slug: string; project_name: string }[]>([])
  const thumbnails = ref<Record<string, string>>({})

  // Computed
  const slug = computed(() => character.value?.slug || '')
  const name = computed(() => character.value?.name || '')
  const designPrompt = computed(() => character.value?.design_prompt || '')

  // Computed: characters enriched with thumbnail URLs
  const characterCards = computed<CharacterCard[]>(() =>
    characters.value.map(c => ({
      ...c,
      thumbnailUrl: thumbnails.value[c.slug]
        ? visualApi.datasetImageUrl(thumbnails.value[c.slug])
        : null,
    }))
  )

  // Unique project names for filter pills
  const projectNames = computed(() =>
    [...new Set(characters.value.map(c => c.project_name))].sort()
  )

  // Actions
  async function loadCharacters(projectId?: number) {
    try {
      const [charResp, thumbResp] = await Promise.all([
        storyApi.getCharacters(),
        visualApi.getCharacterThumbnails(),
      ])
      characters.value = charResp.characters
        .filter((c: any) => !projectId || c.project_id === projectId)
        .map((c: any) => ({ name: c.name, slug: c.slug, project_name: c.project_name }))
      thumbnails.value = thumbResp.thumbnails
    } catch (e) {
      console.error('Failed to load characters:', e)
    }
  }

  async function selectCharacter(charSlug: string) {
    loading.value = true
    error.value = null
    try {
      const detail = await storyApi.getCharacterDetail(charSlug)
      character.value = detail
      appearance.value = detail.appearance_data ? { ...detail.appearance_data } : {}
      dirty.value = false
      // Try to find a portrait
      await loadPortrait(charSlug)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load character'
    } finally {
      loading.value = false
    }
  }

  async function loadPortrait(charSlug: string) {
    try {
      const resp = await visualApi.getGallery(20)
      const match = resp.images.find((img: any) =>
        img.filename?.includes(charSlug) || img.character_slug === charSlug
      )
      if (match) {
        portraitUrl.value = visualApi.galleryImageUrl(match.filename)
      } else {
        portraitUrl.value = null
      }
    } catch {
      portraitUrl.value = null
    }
  }

  function setActivePart(part: BodyPart) {
    activePart.value = part
  }

  function updateAppearanceField(path: string, value: any) {
    const keys = path.split('.')
    let obj: any = appearance.value
    for (let i = 0; i < keys.length - 1; i++) {
      if (!obj[keys[i]] || typeof obj[keys[i]] !== 'object') {
        obj[keys[i]] = {}
      }
      obj = obj[keys[i]]
    }
    obj[keys[keys.length - 1]] = value
    dirty.value = true
  }

  function updateIdentityField(field: string, value: any) {
    if (!character.value) return
    ;(character.value as any)[field] = value
    dirty.value = true
  }

  async function save() {
    if (!character.value?.slug) return
    saving.value = true
    error.value = null
    try {
      // Save appearance_data
      await storyApi.updateCharacter(character.value.slug, {
        appearance_data: appearance.value,
      } as any)
      // Save identity fields if changed
      const identityFields: Record<string, any> = {}
      for (const f of ['description', 'personality', 'background', 'age', 'character_role']) {
        if ((character.value as any)[f] !== undefined) {
          identityFields[f] = (character.value as any)[f]
        }
      }
      if (Object.keys(identityFields).length > 0) {
        await storyApi.updateCharacter(character.value.slug, identityFields as any)
      }
      dirty.value = false
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to save'
    } finally {
      saving.value = false
    }
  }

  async function generatePortrait() {
    if (!character.value?.slug) return
    generating.value = true
    genStatus.value = null
    error.value = null
    try {
      const resp = await visualApi.generateForCharacter(character.value.slug, {
        generation_type: 'image',
      } as any)
      genPromptId.value = resp.prompt_id
      startPolling()
    } catch (e) {
      generating.value = false
      error.value = e instanceof Error ? e.message : 'Generation failed'
    }
  }

  function startPolling() {
    stopPolling()
    if (!genPromptId.value) return
    pollTimer = setInterval(async () => {
      if (!genPromptId.value) return
      try {
        const status = await visualApi.getGenerationStatus(genPromptId.value)
        genStatus.value = status
        if (status.status === 'completed') {
          stopPolling()
          generating.value = false
          // Refresh portrait
          if (character.value?.slug) {
            await loadPortrait(character.value.slug)
          }
        } else if (status.status === 'error') {
          stopPolling()
          generating.value = false
          error.value = 'Generation failed'
        }
      } catch {
        stopPolling()
        generating.value = false
      }
    }, 2000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function reset() {
    stopPolling()
    character.value = null
    appearance.value = {}
    activePart.value = 'identity'
    dirty.value = false
    loading.value = false
    saving.value = false
    generating.value = false
    genPromptId.value = null
    genStatus.value = null
    portraitUrl.value = null
    error.value = null
  }

  return {
    character, appearance, activePart, dirty, loading, saving, error,
    generating, genStatus, portraitUrl, characters, thumbnails,
    characterCards, projectNames,
    slug, name, designPrompt,
    loadCharacters, selectCharacter, setActivePart,
    updateAppearanceField, updateIdentityField,
    save, generatePortrait, reset,
  }
})
