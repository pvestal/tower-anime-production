import { describe, it, expect } from 'vitest'
import fetch from 'node-fetch'
import https from 'https'

const API_BASE = 'https://vestal-garcia.duckdns.org/api/anime'

// Create HTTPS agent for self-signed certificates
const httpsAgent = new https.Agent({
  rejectUnauthorized: false
})

async function fetchAPI(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    agent: httpsAgent,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  })

  if (!response.ok && response.status !== 404 && response.status !== 405) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  return {
    status: response.status,
    data: await response.json()
  }
}

describe('API Integration Tests (Real)', () => {
  describe('Characters API', () => {
    it('GET /characters returns array of characters', async () => {
      const response = await fetchAPI('/characters')

      expect(response.status).toBe(200)
      expect(Array.isArray(response.data)).toBe(true)
      expect(response.data.length).toBeGreaterThan(0)

      if (response.data.length > 0) {
        const character = response.data[0]
        expect(character).toHaveProperty('id')
        expect(character).toHaveProperty('name')
      }
    })

    it('GET /characters/:id returns specific character', async () => {
      const characters = await fetchAPI('/characters')

      if (characters.data.length > 0) {
        const charId = characters.data[0].id
        const response = await fetchAPI(`/characters/${charId}`)

        expect(response.status).toBe(200)
        expect(response.data.id).toBe(charId)
      }
    })
  })

  describe('Projects API', () => {
    it('GET /projects returns projects list', async () => {
      const response = await fetchAPI('/projects')

      expect(response.status).toBe(200)
      expect(response.data).toHaveProperty('projects')
      expect(response.data).toHaveProperty('count')
      expect(Array.isArray(response.data.projects)).toBe(true)
    })
  })

  describe('Jobs API', () => {
    it('GET /jobs returns job list', async () => {
      const response = await fetchAPI('/jobs')

      expect(response.status).toBe(200)
      expect(response.data).toHaveProperty('jobs')
      expect(response.data).toHaveProperty('count')
      expect(Array.isArray(response.data.jobs)).toBe(true)
    })

    it('GET /jobs?limit=5 limits results', async () => {
      const response = await fetchAPI('/jobs?limit=5')

      expect(response.status).toBe(200)
      expect(response.data.jobs.length).toBeLessThanOrEqual(5)
    })
  })

  describe('Gallery API', () => {
    it('GET /gallery returns image list', async () => {
      const response = await fetchAPI('/gallery')

      expect(response.status).toBe(200)
      expect(response.data).toHaveProperty('images')
      expect(response.data).toHaveProperty('total')
      expect(Array.isArray(response.data.images)).toBe(true)
    })
  })

  describe('Health Check', () => {
    it('GET /health returns service status', async () => {
      const response = await fetchAPI('/health')

      expect(response.status).toBe(200)
      expect(response.data).toHaveProperty('status')
      expect(response.data.status).toBe('healthy')
      expect(response.data).toHaveProperty('service')
      expect(response.data).toHaveProperty('timestamp')
    })

    it('health check includes component status', async () => {
      const response = await fetchAPI('/health')

      expect(response.data).toHaveProperty('components')
      expect(response.data.components).toHaveProperty('comfyui')
      expect(response.data.components).toHaveProperty('gpu')
    })
  })

  describe('Response Time', () => {
    it('all GET endpoints respond under 2 seconds', async () => {
      const endpoints = ['/characters', '/projects', '/jobs', '/gallery', '/health']

      for (const endpoint of endpoints) {
        const start = Date.now()
        await fetchAPI(endpoint)
        const responseTime = Date.now() - start

        expect(responseTime).toBeLessThan(2000)
      }
    })
  })

  describe('Data Validation', () => {
    it('character data has correct structure', async () => {
      const response = await fetchAPI('/characters')

      if (response.data.length > 0) {
        const char = response.data[0]
        expect(typeof char.id).toBe('number')
        expect(typeof char.name).toBe('string')

        // Optional fields
        if (char.description !== null) {
          expect(typeof char.description).toBe('string')
        }
      }
    })

    it('project data has correct structure', async () => {
      const response = await fetchAPI('/projects')

      if (response.data.projects.length > 0) {
        const project = response.data.projects[0]
        expect(project).toHaveProperty('id')
        expect(project).toHaveProperty('name')
        expect(project).toHaveProperty('created_at')
      }
    })
  })
})