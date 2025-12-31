/**
 * End-to-End tests for complete generation workflow
 */

import { test, expect } from '@playwright/test'

// Test configuration
const BASE_URL = process.env.VITE_APP_URL || 'http://localhost:5173'

test.describe('Complete Generation Workflow', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the director interface
    await page.goto(`${BASE_URL}/director`)

    // Wait for components to load
    await page.waitForSelector('[data-test="character-select"]', { timeout: 10000 })
  })

  test('creates and executes a 12s NSFW scene from start to finish', async ({ page }) => {
    // 1. Select character
    await page.selectOption('[data-test="character-select"]', 'Mei Kobayashi')

    // 2. Choose action category
    await page.click('[data-test="action-category-intimate"]')
    await page.waitForTimeout(500) // Wait for filtering

    // 3. Select specific action
    await page.click('[data-test="action-desperate_masturbation"]')

    // 4. Choose style
    await page.click('[data-test="style-noir_cinematic"]')

    // 5. Set duration
    const durationInput = page.locator('[data-test="duration-input"]')
    await durationInput.fill('12')

    // Verify generate button is enabled
    const generateButton = page.locator('[data-test="generate-button"]')
    await expect(generateButton).not.toBeDisabled()

    // 6. Submit generation
    await generateButton.click()

    // 7. Verify job starts
    await expect(page.locator('[data-test="job-status"]'))
      .toContainText(/submitting|processing/, { timeout: 10000 })

    // 8. Monitor progress (with reasonable timeout for actual generation)
    const maxWaitTime = 120000 // 2 minutes
    const startTime = Date.now()

    while (Date.now() - startTime < maxWaitTime) {
      const statusText = await page.locator('[data-test="job-status"]').textContent()

      if (statusText?.includes('completed')) {
        break
      }

      if (statusText?.includes('failed')) {
        throw new Error('Generation failed')
      }

      await page.waitForTimeout(5000) // Check every 5 seconds
    }

    // 9. Verify video preview appears
    await expect(page.locator('[data-test="video-preview"]'))
      .toBeVisible({ timeout: 10000 })

    // 10. Verify video duration
    const durationText = await page.locator('[data-test="video-duration"]').textContent()
    const duration = parseFloat(durationText || '0')

    expect(duration).toBeGreaterThan(11.5)
    expect(duration).toBeLessThan(12.5)
  })

  test('handles style compatibility filtering', async ({ page }) => {
    // Select a violent action
    await page.click('[data-test="action-category-violent"]')
    await page.click('[data-test="action-bloody_last_stand"]')

    // Get available styles
    const styles = await page.locator('[data-test*="style-"]').count()

    // Should only show compatible styles (noir_cinematic and action_dynamic)
    expect(styles).toBeLessThanOrEqual(2)

    // Verify romantic_soft_focus is not available
    const romanticStyle = page.locator('[data-test="style-romantic_soft_focus"]')
    await expect(romanticStyle).not.toBeVisible()
  })

  test('prevents generation without required selections', async ({ page }) => {
    // Only select character
    await page.selectOption('[data-test="character-select"]', 'Kai Nakamura')

    // Generate button should be disabled
    const generateButton = page.locator('[data-test="generate-button"]')
    await expect(generateButton).toBeDisabled()

    // Select action
    await page.click('[data-test="action-category-casual"]')
    await page.click('[data-test="action-walking_cycle"]')

    // Still disabled without style
    await expect(generateButton).toBeDisabled()

    // Select style
    await page.click('[data-test="style-romantic_soft_focus"]')

    // Now should be enabled
    await expect(generateButton).not.toBeDisabled()
  })

  test('rapid regeneration workflow', async ({ page }) => {
    // First create a generation (simplified)
    await page.selectOption('[data-test="character-select"]', 'Mei Kobayashi')
    await page.click('[data-test="action-category-casual"]')
    await page.click('[data-test="action-walking_cycle"]')
    await page.click('[data-test="style-romantic_soft_focus"]')

    // Mock a completed generation
    await page.evaluate(() => {
      // This would normally be set by a successful generation
      (window as any).lastGeneration = {
        job_id: 'mock-job-123',
        cache_key: 'mock-cache-key'
      }
    })

    // Click rapid regenerate button
    const rapidButton = page.locator('button:has-text("Rapid Regenerate")')
    await rapidButton.click()

    // Verify modal appears
    await expect(page.locator('text="Rapid Regeneration"')).toBeVisible()

    // Adjust parameters
    await page.fill('input[type="number"]', '54321') // Seed
    await page.locator('input[type="range"]').first().fill('0.5') // Motion intensity

    // Submit regeneration
    await page.click('button:has-text("Regenerate")')

    // Verify job starts
    await expect(page.locator('[data-test="job-status"]'))
      .toContainText(/regenerating/, { timeout: 5000 })
  })

  test('duration affects workflow tier selection', async ({ page }) => {
    await page.selectOption('[data-test="character-select"]', 'Kai Nakamura')
    await page.click('[data-test="action-category-action"]')
    await page.click('[data-test="action-heroic_charge"]')
    await page.click('[data-test="style-action_dynamic"]')

    // Set short duration (should use Tier 1 or 2)
    await page.locator('[data-test="duration-input"]').fill('4')
    await page.waitForTimeout(500)

    let previewText = await page.locator('.generation-preview').textContent()
    expect(previewText).toContain('TIER_1_STATIC')

    // Set medium duration (should use Tier 2)
    await page.locator('[data-test="duration-input"]').fill('10')
    await page.waitForTimeout(500)

    previewText = await page.locator('.generation-preview').textContent()
    expect(previewText).toContain('TIER_2_SVD')

    // Set long duration (should use Tier 3)
    await page.locator('[data-test="duration-input"]').fill('25')
    await page.waitForTimeout(500)

    previewText = await page.locator('.generation-preview').textContent()
    expect(previewText).toContain('TIER_3_ANIMATEDIFF')
  })

  test('batch generation for episode', async ({ page }) => {
    // Navigate to episode management
    await page.goto(`${BASE_URL}/director/episode`)

    // Select multiple scenes
    await page.click('[data-test="scene-1-checkbox"]')
    await page.click('[data-test="scene-2-checkbox"]')
    await page.click('[data-test="scene-3-checkbox"]')

    // Click batch generate
    await page.click('[data-test="batch-generate-button"]')

    // Verify batch job starts
    await expect(page.locator('[data-test="batch-status"]'))
      .toContainText('Processing 3 scenes', { timeout: 5000 })

    // Verify individual scene progress
    await expect(page.locator('[data-test="scene-1-status"]')).toBeVisible()
    await expect(page.locator('[data-test="scene-2-status"]')).toBeVisible()
    await expect(page.locator('[data-test="scene-3-status"]')).toBeVisible()
  })
})