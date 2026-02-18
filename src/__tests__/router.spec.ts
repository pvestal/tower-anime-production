import { describe, it, expect } from 'vitest'
import { router } from '@/router'

describe('router', () => {
  it('has 7 named routes', () => {
    const named = router.getRoutes().filter(r => r.name)
    expect(named).toHaveLength(7)
  })

  it('defines all expected route names', () => {
    const names = router.getRoutes().map(r => r.name).filter(Boolean)
    expect(names).toContain('Ingest')
    expect(names).toContain('Approve')
    expect(names).toContain('Characters')
    expect(names).toContain('Train')
    expect(names).toContain('Generate')
    expect(names).toContain('Gallery')
    expect(names).toContain('Echo')
  })

  it('redirects / to /characters', () => {
    const redirectRoute = router.options.routes.find(r => r.path === '/')
    expect(redirectRoute).toBeDefined()
    expect(redirectRoute!.redirect).toBe('/characters')
  })

  it('resolves each route path', () => {
    const paths = ['/ingest', '/approve', '/characters', '/train', '/generate', '/gallery', '/echo']
    for (const path of paths) {
      const resolved = router.resolve(path)
      expect(resolved.matched.length).toBeGreaterThan(0)
    }
  })

  it('uses /anime-studio/ as base path', () => {
    // createWebHistory('/anime-studio/') means base is /anime-studio/
    expect(router.options.history.base).toBe('/anime-studio')
  })
})
