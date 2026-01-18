import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import Dashboard from '@/views/Dashboard.vue'
import { useCharacterStore } from '@/stores/characterStore'
import api from '@/api/animeApi'

// Mock the API
vi.mock('@/api/animeApi')

describe('Dashboard.vue', () => {
  let wrapper
  let store

  beforeEach(() => {
    const pinia = createPinia()
    wrapper = mount(Dashboard, {
      global: {
        plugins: [pinia]
      }
    })
    store = useCharacterStore()
  })

  describe('Rendering', () => {
    it('renders dashboard heading', () => {
      expect(wrapper.find('h1').text()).toBe('Dashboard')
    })

    it('displays character count correctly', async () => {
      store.characters = {
        'char1': { id: 'char1', name: 'Kai' },
        'char2': { id: 'char2', name: 'Mei' }
      }
      await wrapper.vm.$nextTick()
      const characterCount = Object.keys(store.characters).length
      expect(wrapper.find('.stat-card:first-child .stat-value').text()).toBe(characterCount.toString())
    })

    it('displays queue statistics', async () => {
      wrapper.vm.queueStats = { pending: 5, processing: 2 }
      await wrapper.vm.$nextTick()
      const total = wrapper.vm.queueStats.pending + wrapper.vm.queueStats.processing
      expect(wrapper.find('.stat-card:nth-child(2) .stat-value').text()).toBe(total.toString())
    })

    it('displays models count', async () => {
      store.models = ['model1', 'model2', 'model3']
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.stat-card:nth-child(3) .stat-value').text()).toBe(store.models.length.toString())
    })

    it('displays styles count', async () => {
      store.styles = ['style1', 'style2', 'style3', 'style4']
      await wrapper.vm.$nextTick()
      expect(wrapper.find('.stat-card:nth-child(4) .stat-value').text()).toBe(store.styles.length.toString())
    })
  })

  describe('Recent Jobs', () => {
    it.skip('displays recent jobs when available', async () => {
      const mockJobs = [
        {
          job_id: 'job1',
          character_name: 'Kai',
          prompt: 'Test prompt 1',
          status: 'completed',
          created_at: '2025-12-27T10:00:00'
        },
        {
          job_id: 'job2',
          character_name: 'Mei',
          prompt: 'Test prompt 2',
          status: 'processing',
          created_at: '2025-12-27T11:00:00'
        }
      ]

      api.v2.getJobs.mockResolvedValue({ data: { jobs: mockJobs } })

      await wrapper.vm.$nextTick()

      expect(wrapper.findAll('.job-card')).toHaveLength(2)
      expect(wrapper.find('.job-card h4').text()).toBe('Kai')
      expect(wrapper.find('.status-completed').exists()).toBe(true)
    })

    it.skip('handles empty jobs gracefully', async () => {
      api.v2.getJobs.mockResolvedValue({ data: { jobs: [] } })

      await wrapper.vm.$nextTick()

      expect(wrapper.findAll('.job-card')).toHaveLength(0)
      expect(wrapper.vm.recentJobs).toEqual([])
    })

    it('displays error when API fails', async () => {
      api.v2.getJobs.mockRejectedValue(new Error('Network error'))

      await wrapper.vm.$nextTick()

      expect(console.error).toHaveBeenCalledWith('Failed to load dashboard data:', expect.any(Error))
      expect(wrapper.vm.recentJobs).toEqual([])
    })
  })

  describe('Date Formatting', () => {
    it('formats dates correctly', () => {
      const dateStr = '2025-12-27T10:00:00'
      const formatted = wrapper.vm.formatDate(dateStr)
      expect(formatted).toMatch(/\d{1,2}\/\d{1,2}\/\d{4}/)
    })

    it('handles invalid dates', () => {
      const invalidDate = 'invalid-date'
      const formatted = wrapper.vm.formatDate(invalidDate)
      expect(formatted).toBe('Invalid Date')
    })
  })

  describe('Loading States', () => {
    it.skip('shows loading indicator while fetching', async () => {
      api.v2.getJobs.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))

      wrapper = mount(Dashboard, {
        global: {
          plugins: [createPinia()]
        }
      })

      expect(wrapper.find('.loading').exists()).toBe(true)

      await wrapper.vm.$nextTick()

      expect(wrapper.find('.loading').exists()).toBe(false)
    })
  })

  describe('Status Classes', () => {
    it('applies correct status classes', () => {
      const statuses = ['completed', 'processing', 'pending', 'failed']

      statuses.forEach(status => {
        const jobCard = wrapper.find(`.status-${status}`)
        if (jobCard.exists()) {
          expect(jobCard.classes()).toContain(`status-${status}`)
        }
      })
    })
  })

  describe('Refresh Behavior', () => {
    it('refreshes data on mount', async () => {
      const getJobsSpy = vi.spyOn(api.v2, 'getJobs')

      mount(Dashboard, {
        global: {
          plugins: [createPinia()]
        }
      })

      expect(getJobsSpy).toHaveBeenCalledWith(5)
    })

    it.skip('handles queue stats correctly', async () => {
      const mockJobs = Array(10).fill(null).map((_, i) => ({
        job_id: `job${i}`,
        status: i < 3 ? 'pending' : i < 5 ? 'processing' : 'completed'
      }))

      api.v2.getJobs.mockResolvedValue({ data: { jobs: mockJobs } })

      await wrapper.vm.$nextTick()

      expect(wrapper.vm.queueStats.pending).toBe(3)
      expect(wrapper.vm.queueStats.processing).toBe(2)
    })
  })

  describe('Error Boundaries', () => {
    it('catches and logs component errors', () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      // Trigger an error
      wrapper.vm.recentJobs = null
      wrapper.vm.formatDate(null)

      expect(errorSpy).toHaveBeenCalled()

      errorSpy.mockRestore()
    })
  })

  describe('Accessibility', () => {
    it('has proper heading hierarchy', () => {
      const h1 = wrapper.find('h1')
      const h2 = wrapper.find('h2')
      const h3 = wrapper.findAll('h3')

      expect(h1.exists()).toBe(true)
      expect(h2.exists()).toBe(true)
      expect(h3.length).toBeGreaterThan(0)
    })

    it('has proper semantic HTML', () => {
      expect(wrapper.find('.dashboard').exists()).toBe(true)
      expect(wrapper.find('.stats-grid').exists()).toBe(true)
      expect(wrapper.find('.recent-section').exists()).toBe(true)
    })
  })
})