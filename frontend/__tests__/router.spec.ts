import { describe, it, expect } from 'vitest'
import { router } from '@/router'

describe('router', () => {
  it('has 8 named routes', () => {
    const named = router.getRoutes().filter(r => r.name)
    expect(named).toHaveLength(8)
  })

  it('defines all expected route names', () => {
    const names = router.getRoutes().map(r => r.name).filter(Boolean)
    expect(names).toContain('Project')
    expect(names).toContain('Characters')
    expect(names).toContain('Generate')
    expect(names).toContain('Review')
    expect(names).toContain('Train')
    expect(names).toContain('Voice')
    expect(names).toContain('Scenes')
    expect(names).toContain('Analytics')
  })

  it('redirects / to /project', () => {
    const redirectRoute = router.options.routes.find(r => r.path === '/')
    expect(redirectRoute).toBeDefined()
    expect(redirectRoute!.redirect).toBe('/project')
  })

  it('resolves each route path', () => {
    const paths = ['/project', '/characters', '/generate', '/review', '/train', '/voice', '/scenes', '/analytics']
    for (const path of paths) {
      const resolved = router.resolve(path)
      expect(resolved.matched.length).toBeGreaterThan(0)
    }
  })

  it('uses /anime-studio/ as base path', () => {
    expect(router.options.history.base).toBe('/anime-studio')
  })

  it('has legacy redirects', () => {
    const legacyPaths = ['/story', '/create', '/approve', '/library', '/gallery', '/dashboard', '/echo', '/ingest', '/voices']
    for (const path of legacyPaths) {
      const route = router.options.routes.find(r => r.path === path)
      expect(route, `redirect for ${path}`).toBeDefined()
      expect(route!.redirect).toBeDefined()
    }
  })
})
