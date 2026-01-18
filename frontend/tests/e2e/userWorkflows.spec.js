import { test, expect } from '@playwright/test'

const BASE_URL = 'https://vestal-garcia.duckdns.org/anime'

test.describe('User Workflows', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL)
  })

  test.describe('Navigation', () => {
    test('can navigate between all pages', async ({ page }) => {
      // Start at dashboard
      await expect(page.locator('h1')).toContainText('Dashboard')

      // Navigate to Projects
      await page.click('text=Projects')
      await expect(page.url()).toContain('/projects')

      // Navigate to Characters
      await page.click('text=Characters')
      await expect(page.url()).toContain('/characters')

      // Navigate to Studio
      await page.click('text=Studio')
      await expect(page.url()).toContain('/studio')

      // Navigate to Generate
      await page.click('text=Generate')
      await expect(page.url()).toContain('/generate')

      // Navigate to Gallery
      await page.click('text=Gallery')
      await expect(page.url()).toContain('/gallery')

      // Navigate to Chat
      await page.click('text=Chat')
      await expect(page.url()).toContain('/chat')

      // Return to Dashboard
      await page.click('text=Dashboard')
      await expect(page.locator('h1')).toContainText('Dashboard')
    })

    test('navigation maintains dark theme', async ({ page }) => {
      const pages = ['/', '/projects', '/characters', '/generate', '/gallery']

      for (const path of pages) {
        await page.goto(`${BASE_URL}${path}`)
        const bgColor = await page.evaluate(() =>
          window.getComputedStyle(document.body).backgroundColor
        )
        expect(bgColor).toBe('rgb(10, 10, 10)') // #0a0a0a
      }
    })
  })

  test.describe('Character Management', () => {
    test('can view character list', async ({ page }) => {
      await page.goto(`${BASE_URL}/characters`)

      // Wait for characters to load
      await page.waitForSelector('.character-card', { timeout: 5000 })

      // Check characters are displayed
      const characters = await page.locator('.character-card').count()
      expect(characters).toBeGreaterThan(0)
    })

    test('can search/filter characters', async ({ page }) => {
      await page.goto(`${BASE_URL}/characters`)
      await page.waitForSelector('.character-card')

      // Type in search
      await page.fill('input[placeholder*="Search"]', 'Kai')

      // Check filtered results
      const visibleCards = await page.locator('.character-card:visible').count()
      const allCards = await page.locator('.character-card').count()
      expect(visibleCards).toBeLessThanOrEqual(allCards)
    })

    test('can view character details', async ({ page }) => {
      await page.goto(`${BASE_URL}/characters`)
      await page.waitForSelector('.character-card')

      // Click first character
      await page.locator('.character-card').first().click()

      // Check details are shown
      await expect(page.locator('.character-details')).toBeVisible()
      await expect(page.locator('.character-name')).toBeVisible()
    })
  })

  test.describe('Image Generation Flow', () => {
    test('generation form validation works', async ({ page }) => {
      await page.goto(`${BASE_URL}/generate`)

      // Try to submit empty form
      await page.click('button[type="submit"]')

      // Check for validation errors
      await expect(page.locator('.error-message')).toBeVisible()

      // Fill in required fields
      await page.fill('#prompt', 'cyberpunk warrior in neon city')

      // Check submit button enabled
      const submitBtn = page.locator('button[type="submit"]')
      await expect(submitBtn).not.toBeDisabled()
    })

    test('settings sliders work correctly', async ({ page }) => {
      await page.goto(`${BASE_URL}/generate`)

      // Test CFG scale slider
      const cfgSlider = page.locator('#cfg-scale')
      await cfgSlider.fill('12')
      await expect(cfgSlider).toHaveValue('12')

      // Test steps slider
      const stepsSlider = page.locator('#steps')
      await stepsSlider.fill('50')
      await expect(stepsSlider).toHaveValue('50')

      // Test batch size
      const batchSize = page.locator('#batch-size')
      await batchSize.fill('4')
      await expect(batchSize).toHaveValue('4')
    })

    test('model selection dropdown works', async ({ page }) => {
      await page.goto(`${BASE_URL}/generate`)

      // Click model dropdown
      const modelSelect = page.locator('#model-select')
      await modelSelect.click()

      // Check options are visible
      await expect(page.locator('.model-option')).toBeVisible()

      // Select a model
      await page.locator('.model-option').first().click()

      // Check model is selected
      await expect(modelSelect).not.toHaveValue('')
    })
  })

  test.describe('Gallery', () => {
    test('can view gallery images', async ({ page }) => {
      await page.goto(`${BASE_URL}/gallery`)

      // Wait for gallery to load
      await page.waitForSelector('.gallery-grid', { timeout: 5000 })

      // Check if images exist or empty state is shown
      const hasImages = await page.locator('.gallery-item').count() > 0
      const hasEmptyState = await page.locator('.empty-state').isVisible()

      expect(hasImages || hasEmptyState).toBe(true)
    })

    test('can filter gallery by character', async ({ page }) => {
      await page.goto(`${BASE_URL}/gallery`)

      // Check if character filter exists
      const characterFilter = page.locator('#character-filter')

      if (await characterFilter.isVisible()) {
        await characterFilter.click()
        await page.locator('.filter-option').first().click()

        // Check URL updated with filter
        await expect(page.url()).toContain('character')
      }
    })

    test('image modal opens on click', async ({ page }) => {
      await page.goto(`${BASE_URL}/gallery`)

      const images = await page.locator('.gallery-item img').count()

      if (images > 0) {
        // Click first image
        await page.locator('.gallery-item img').first().click()

        // Check modal opened
        await expect(page.locator('.image-modal')).toBeVisible()

        // Check close button works
        await page.click('.modal-close')
        await expect(page.locator('.image-modal')).not.toBeVisible()
      }
    })
  })

  test.describe('Chat Interface', () => {
    test('can send messages', async ({ page }) => {
      await page.goto(`${BASE_URL}/chat`)

      // Type message
      await page.fill('#chat-input', 'Hello, can you help me generate an image?')

      // Send message
      await page.click('#send-button')

      // Check message appears in chat
      await expect(page.locator('.message.user')).toContainText('Hello')
    })

    test('chat input validation', async ({ page }) => {
      await page.goto(`${BASE_URL}/chat`)

      // Try to send empty message
      await page.click('#send-button')

      // Button should be disabled or show error
      const sendBtn = page.locator('#send-button')
      const isDisabled = await sendBtn.isDisabled()
      const hasError = await page.locator('.error-message').isVisible()

      expect(isDisabled || hasError).toBe(true)
    })

    test('chat history loads', async ({ page }) => {
      await page.goto(`${BASE_URL}/chat`)

      // Check if history loads or shows empty state
      await page.waitForSelector('.chat-container', { timeout: 5000 })

      const hasMessages = await page.locator('.message').count() > 0
      const hasEmptyState = await page.locator('.chat-empty').isVisible()

      expect(hasMessages || hasEmptyState).toBe(true)
    })
  })

  test.describe('Responsive Design', () => {
    test('mobile navigation works', async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 667 })
      await page.goto(BASE_URL)

      // Check hamburger menu exists
      const hamburger = page.locator('.mobile-menu-toggle')

      if (await hamburger.isVisible()) {
        await hamburger.click()

        // Check mobile menu opened
        await expect(page.locator('.mobile-nav')).toBeVisible()

        // Navigate to a page
        await page.click('.mobile-nav text=Characters')
        await expect(page.url()).toContain('/characters')
      }
    })

    test('tablet layout adjusts correctly', async ({ page }) => {
      await page.setViewportSize({ width: 768, height: 1024 })
      await page.goto(BASE_URL)

      // Check grid layouts adjust
      const statsGrid = page.locator('.stats-grid')
      const gridColumns = await statsGrid.evaluate(el =>
        window.getComputedStyle(el).gridTemplateColumns
      )

      expect(gridColumns).toContain('repeat')
    })
  })

  test.describe('Error States', () => {
    test('handles 404 pages gracefully', async ({ page }) => {
      await page.goto(`${BASE_URL}/nonexistent-page`)

      // Should show 404 or redirect to valid page
      const has404 = await page.locator('text=404').isVisible()
      const redirected = page.url().includes('/anime')

      expect(has404 || redirected).toBe(true)
    })

    test('handles API errors gracefully', async ({ page }) => {
      // Intercept API calls and force error
      await page.route('**/api/anime/characters', route =>
        route.fulfill({ status: 500, body: 'Server Error' })
      )

      await page.goto(`${BASE_URL}/characters`)

      // Should show error message
      await expect(page.locator('.error-message, .error-state')).toBeVisible()
    })

    test('retry button works on error', async ({ page }) => {
      // Force initial error
      let requestCount = 0
      await page.route('**/api/anime/characters', route => {
        requestCount++
        if (requestCount === 1) {
          route.fulfill({ status: 500 })
        } else {
          route.continue()
        }
      })

      await page.goto(`${BASE_URL}/characters`)

      // Click retry
      const retryBtn = page.locator('button:has-text("Retry")')

      if (await retryBtn.isVisible()) {
        await retryBtn.click()

        // Should retry and succeed
        await page.waitForSelector('.character-card', { timeout: 5000 })
      }
    })
  })

  test.describe('Performance', () => {
    test('page loads within acceptable time', async ({ page }) => {
      const start = Date.now()
      await page.goto(BASE_URL)
      await page.waitForLoadState('networkidle')
      const loadTime = Date.now() - start

      expect(loadTime).toBeLessThan(3000)
    })

    test('images lazy load in gallery', async ({ page }) => {
      await page.goto(`${BASE_URL}/gallery`)

      // Get initial loaded images
      const initialImages = await page.evaluate(() =>
        Array.from(document.querySelectorAll('img')).filter(img => img.complete).length
      )

      // Scroll down
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
      await page.waitForTimeout(1000)

      // Check more images loaded
      const afterScrollImages = await page.evaluate(() =>
        Array.from(document.querySelectorAll('img')).filter(img => img.complete).length
      )

      expect(afterScrollImages).toBeGreaterThanOrEqual(initialImages)
    })
  })
})