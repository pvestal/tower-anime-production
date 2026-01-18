import { test, expect } from '@playwright/test'

test.describe('Studio Route', () => {
  test('can navigate to studio page', async ({ page }) => {
    // Navigate directly to studio
    await page.goto('https://vestal-garcia.duckdns.org/anime/studio')

    // Check we're on studio page
    await expect(page.url()).toContain('/studio')

    // Check studio content loads
    await expect(page.locator('h1')).toContainText('Character Studio')

    // Check tabs are visible using more specific selectors
    await expect(page.locator('button.tab').filter({ hasText: 'Character' })).toBeVisible()
    await expect(page.locator('button.tab').filter({ hasText: 'LoRA Training' })).toBeVisible()
    await expect(page.locator('button.tab').filter({ hasText: 'Generation' })).toBeVisible()
  })

  test('can navigate to studio via menu', async ({ page }) => {
    // Start at home
    await page.goto('https://vestal-garcia.duckdns.org/anime/')

    // Click Studio link
    await page.locator('a:has-text("Studio")').click()

    // Check navigation worked
    await expect(page.url()).toContain('/studio')
    await expect(page.locator('h1')).toContainText('Character Studio')
  })
})