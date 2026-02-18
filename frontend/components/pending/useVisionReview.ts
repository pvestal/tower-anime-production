import { ref } from 'vue'
import { api } from '@/api/client'
import type { PendingImage } from '@/types'

interface CharacterGroup {
  [characterName: string]: PendingImage[]
}

interface ProjectGroup {
  characters: CharacterGroup
  total: number
  checkpoint: string
  style: string
}

export function useVisionReview(
  showToast: (message: string, type: 'approve' | 'reject' | 'regen', durationMs?: number) => void,
  fetchPendingImages: () => Promise<void>,
) {
  const visionReviewing = ref<string | null>(null)

  async function runVisionReviewProject(projectName: string, projectGroup: ProjectGroup) {
    if (visionReviewing.value) return
    visionReviewing.value = `project:${projectName}`
    const totalImages = projectGroup.total

    const est = totalImages * 8
    showToast(`Vision reviewing ${totalImages} images across ${Object.keys(projectGroup.characters).length} characters (gemma3:12b, ~${est}s)...`, 'regen', est * 1000)

    try {
      const result = await api.visionReview({ project_name: projectName, max_images: totalImages })

      const parts = [`${result.reviewed} reviewed`]
      if (result.auto_approved) parts.push(`${result.auto_approved} auto-approved`)
      if (result.auto_rejected) parts.push(`${result.auto_rejected} auto-rejected`)
      if (result.regen_queued) parts.push(`${result.regen_queued} regen queued`)
      const still = result.results.filter(r => r.action === 'pending').length
      if (still) parts.push(`${still} need manual review`)

      showToast(`${projectName}: ${parts.join(', ')}`, 'regen', 8000)

      await fetchPendingImages()
    } catch (err) {
      showToast(`Vision review failed for ${projectName}`, 'reject')
      console.error('Vision project review failed:', err)
    } finally {
      visionReviewing.value = null
    }
  }

  async function runVisionReview(charName: string, images: PendingImage[]) {
    if (visionReviewing.value) return
    visionReviewing.value = charName
    const slug = images[0]?.character_slug
    if (!slug) { visionReviewing.value = null; return }

    const est = images.length * 8
    showToast(`Vision reviewing ${images.length} ${charName} images (gemma3:12b, ~${est}s)...`, 'regen', est * 1000)

    try {
      const result = await api.visionReview({ character_slug: slug, max_images: images.length })

      const parts = [`${result.reviewed} reviewed`]
      if (result.auto_approved) parts.push(`${result.auto_approved} auto-approved`)
      if (result.auto_rejected) parts.push(`${result.auto_rejected} auto-rejected`)
      if (result.regen_queued) parts.push(`${result.regen_queued} regen queued`)
      const still = result.results.filter(r => r.action === 'pending').length
      if (still) parts.push(`${still} need manual review`)

      showToast(`${charName}: ${parts.join(', ')}`, 'regen', 8000)

      await fetchPendingImages()
    } catch (err) {
      showToast(`Vision review failed for ${charName}`, 'reject')
      console.error('Vision review failed:', err)
    } finally {
      visionReviewing.value = null
    }
  }

  return {
    visionReviewing,
    runVisionReviewProject,
    runVisionReview,
  }
}
