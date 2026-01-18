# Comprehensive Test Plan for Anime Production Frontend

## Test Categories

### 1. Unit Tests (Components)
Test each Vue component in isolation with mocked dependencies.

#### Dashboard Component Tests
- Renders character count correctly
- Displays queue statistics
- Shows recent jobs list
- Handles empty state
- Updates on data refresh
- Error boundary catches component errors

#### Characters Component Tests
- Lists all characters from API
- Character card interactions (hover, click)
- Character creation form validation
- Character deletion confirmation
- Character edit mode toggle
- Search/filter functionality
- Pagination controls

#### Gallery Component Tests
- Image grid renders correctly
- Lazy loading of images
- Image modal/lightbox functionality
- Filter by character
- Sort by date/rating
- Delete image with confirmation
- Download image functionality

#### Generation Component Tests
- Form field validation
- Prompt character limit
- Settings sliders (CFG, steps, etc)
- Model selection dropdown
- Batch size validation (1-24)
- Submit button disabled states
- Progress indicator display
- Error message display

#### Chat Component Tests
- Message list rendering
- Input field character limit
- Send button states
- Message timestamp formatting
- Auto-scroll to latest
- Typing indicator
- Error message display
- Conversation history loading

### 2. Integration Tests (API + Store)

#### API Integration Tests
```javascript
// Test real API calls with test database
describe('API Integration', () => {
  test('Characters API returns valid data', async () => {
    const response = await api.getCharacters()
    expect(response.data).toBeArray()
    expect(response.data[0]).toHaveProperty('id')
    expect(response.data[0]).toHaveProperty('name')
  })

  test('Handles API errors gracefully', async () => {
    // Mock 500 error
    const response = await api.getCharacters()
    expect(store.error).toBeDefined()
    expect(ui.errorNotification).toBeVisible()
  })

  test('Retry logic on network failure', async () => {
    // Test exponential backoff
  })
})
```

#### Store Integration Tests
- State updates after API calls
- Optimistic updates rollback on error
- Cache invalidation
- Computed properties update
- Actions trigger correct mutations

### 3. End-to-End Tests (User Workflows)

#### Critical User Paths
```javascript
describe('Generate Image Workflow', () => {
  test('Complete image generation flow', async () => {
    // 1. Navigate to Generate page
    await page.goto('/anime/generate')

    // 2. Select character
    await page.select('#character', 'Kai Nakamura')

    // 3. Enter prompt
    await page.type('#prompt', 'cyberpunk warrior in neon city')

    // 4. Adjust settings
    await page.slide('#cfg-scale', 7.5)
    await page.slide('#steps', 30)

    // 5. Submit generation
    await page.click('#generate-btn')

    // 6. Verify progress indicator
    await expect(page).toHaveSelector('.progress-bar')

    // 7. Wait for completion
    await page.waitForSelector('.generation-complete', {timeout: 60000})

    // 8. Verify image displayed
    await expect(page).toHaveSelector('img.generated-image')

    // 9. Verify saved to gallery
    await page.goto('/anime/gallery')
    await expect(page).toHaveSelector('[data-prompt*="cyberpunk warrior"]')
  })
})
```

#### Other Critical Workflows
- Create new character → Generate image → View in gallery
- Start chat → Get suggestions → Generate from suggestion
- Create project → Add episode → Generate scenes
- Upload reference → Train model → Test generation

### 4. Visual Regression Tests

#### Screenshot Comparisons
```javascript
describe('Visual Regression', () => {
  test('Dashboard layout', async () => {
    await page.goto('/anime/')
    const screenshot = await page.screenshot()
    expect(screenshot).toMatchImageSnapshot()
  })

  test('Dark theme consistency', async () => {
    // Check all pages maintain dark theme
    const pages = ['/', '/characters', '/gallery', '/generate']
    for (const path of pages) {
      await page.goto(`/anime${path}`)
      const bgColor = await page.evaluate(() =>
        getComputedStyle(document.body).backgroundColor
      )
      expect(bgColor).toBe('rgb(10, 10, 10)') // #0a0a0a
    }
  })

  test('Responsive breakpoints', async () => {
    const viewports = [
      {width: 320, height: 568},  // Mobile
      {width: 768, height: 1024}, // Tablet
      {width: 1920, height: 1080} // Desktop
    ]
    for (const viewport of viewports) {
      await page.setViewport(viewport)
      await page.goto('/anime/')
      const screenshot = await page.screenshot()
      expect(screenshot).toMatchImageSnapshot({
        customSnapshotIdentifier: `dashboard-${viewport.width}`
      })
    }
  })
})
```

### 5. Form Validation Tests

#### Input Validation Matrix
```javascript
describe('Form Validation', () => {
  const testCases = [
    // Field, Input, Expected Error
    ['prompt', '', 'Prompt is required'],
    ['prompt', 'a'.repeat(1001), 'Prompt must be less than 1000 characters'],
    ['cfg_scale', -1, 'CFG must be between 1 and 20'],
    ['cfg_scale', 25, 'CFG must be between 1 and 20'],
    ['steps', 0, 'Steps must be between 1 and 150'],
    ['batch_size', 100, 'Batch size must be between 1 and 24'],
    ['character_name', 'a', 'Name must be at least 2 characters'],
    ['character_name', 'a'.repeat(101), 'Name must be less than 100 characters'],
  ]

  test.each(testCases)('%s field with "%s" shows "%s"',
    async (field, input, error) => {
      await page.type(`#${field}`, input)
      await page.click('#submit')
      await expect(page).toHaveText(`.error-${field}`, error)
      expect(await page.$('#submit')).toBeDisabled()
    }
  )
})
```

### 6. State Management Tests

#### Pinia Store Tests
```javascript
describe('Character Store', () => {
  test('loadCharacters updates state', async () => {
    const store = useCharacterStore()
    expect(store.characters).toEqual({})
    await store.loadCharacters()
    expect(Object.keys(store.characters).length).toBeGreaterThan(0)
    expect(store.loading).toBe(false)
  })

  test('optimistic update with rollback', async () => {
    const store = useCharacterStore()
    const original = {...store.characters}

    // Optimistic update
    store.updateCharacter('123', {name: 'New Name'})
    expect(store.characters['123'].name).toBe('New Name')

    // Simulate API failure
    mockAPI.fail()
    await store.saveCharacter('123')

    // Should rollback
    expect(store.characters).toEqual(original)
    expect(store.error).toBeDefined()
  })
})
```

### 7. Error Handling Tests

#### Error Scenarios
```javascript
describe('Error Handling', () => {
  test('Network timeout shows retry button', async () => {
    mockAPI.timeout(30000)
    await page.goto('/anime/characters')
    await expect(page).toHaveText('.error-message', 'Connection timeout')
    await expect(page).toHaveSelector('button.retry')
  })

  test('401 redirects to login', async () => {
    mockAPI.respondWith(401)
    await page.goto('/anime/characters')
    expect(page.url()).toContain('/login')
  })

  test('Invalid data shows fallback UI', async () => {
    mockAPI.respondWith({data: 'invalid'})
    await page.goto('/anime/characters')
    await expect(page).toHaveText('.error-boundary', 'Something went wrong')
    await expect(page).toHaveSelector('button.reload')
  })
})
```

### 8. Performance Tests

#### Load Time Metrics
```javascript
describe('Performance', () => {
  test('Initial page load under 3s', async () => {
    const start = Date.now()
    await page.goto('/anime/')
    await page.waitForSelector('.main-content')
    const loadTime = Date.now() - start
    expect(loadTime).toBeLessThan(3000)
  })

  test('API response times', async () => {
    const endpoints = [
      '/api/anime/characters',
      '/api/anime/projects',
      '/api/anime/gallery'
    ]

    for (const endpoint of endpoints) {
      const start = Date.now()
      await fetch(endpoint)
      const responseTime = Date.now() - start
      expect(responseTime).toBeLessThan(500)
    }
  })

  test('Image lazy loading', async () => {
    await page.goto('/anime/gallery')
    const initialImages = await page.$$eval('img', imgs => imgs.length)
    await page.scroll(0, 1000)
    await page.waitForTimeout(500)
    const afterScrollImages = await page.$$eval('img', imgs => imgs.length)
    expect(afterScrollImages).toBeGreaterThan(initialImages)
  })
})
```

### 9. Accessibility Tests

#### A11y Compliance
```javascript
describe('Accessibility', () => {
  test('Keyboard navigation', async () => {
    await page.goto('/anime/')

    // Tab through navigation
    await page.keyboard.press('Tab') // Skip to content
    await page.keyboard.press('Tab') // Dashboard link
    await page.keyboard.press('Tab') // Projects link

    const focused = await page.evaluate(() => document.activeElement.textContent)
    expect(focused).toBe('Projects')

    // Enter to navigate
    await page.keyboard.press('Enter')
    expect(page.url()).toContain('/projects')
  })

  test('Screen reader labels', async () => {
    await page.goto('/anime/generate')

    const labels = await page.$$eval('label[for]', labels =>
      labels.map(l => ({
        for: l.getAttribute('for'),
        text: l.textContent
      }))
    )

    for (const label of labels) {
      const input = await page.$(`#${label.for}`)
      expect(input).toBeDefined()
      expect(label.text).not.toBe('')
    }
  })

  test('ARIA attributes', async () => {
    await page.goto('/anime/')

    // Check landmarks
    await expect(page).toHaveSelector('nav[role="navigation"]')
    await expect(page).toHaveSelector('main[role="main"]')

    // Check buttons
    const buttons = await page.$$('button')
    for (const button of buttons) {
      const label = await button.evaluate(b =>
        b.getAttribute('aria-label') || b.textContent
      )
      expect(label).not.toBe('')
    }
  })
})
```

### 10. Cross-Browser Tests

#### Browser Matrix
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Chrome Mobile
- Safari iOS

### 11. Security Tests

#### Input Sanitization
```javascript
describe('Security', () => {
  test('XSS prevention', async () => {
    const xssPayloads = [
      '<script>alert("XSS")</script>',
      '"><script>alert("XSS")</script>',
      "'; alert('XSS'); //",
      '<img src=x onerror=alert("XSS")>'
    ]

    for (const payload of xssPayloads) {
      await page.type('#prompt', payload)
      await page.click('#submit')

      // Check rendered output doesn't execute
      const alerts = await page.evaluate(() => window.alertCount || 0)
      expect(alerts).toBe(0)

      // Check escaped in display
      const displayed = await page.$eval('.prompt-display', el => el.textContent)
      expect(displayed).not.toContain('<script>')
    }
  })

  test('SQL injection prevention', async () => {
    const sqlPayloads = [
      "'; DROP TABLE characters; --",
      "1' OR '1'='1",
      "admin'--"
    ]

    for (const payload of sqlPayloads) {
      await page.type('#character_name', payload)
      await page.click('#create')

      // Should either sanitize or reject
      const response = await page.waitForResponse('/api/anime/characters')
      expect(response.status()).not.toBe(500)
    }
  })
})
```

## Test Execution Strategy

### Continuous Integration Pipeline
```yaml
name: Frontend Tests
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: pnpm install
      - run: pnpm test:unit

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:13
    steps:
      - run: pnpm test:integration

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pnpm test:e2e

  visual-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pnpm test:visual
```

### Local Development Testing
```bash
# Run all tests
pnpm test

# Run specific suite
pnpm test:unit
pnpm test:integration
pnpm test:e2e

# Watch mode
pnpm test:watch

# Coverage report
pnpm test:coverage
```

## Success Criteria
- Unit test coverage > 80%
- Integration test coverage > 70%
- E2E critical paths 100% covered
- Zero security vulnerabilities
- Performance metrics within targets
- Accessibility WCAG 2.1 AA compliant
- Cross-browser compatibility verified