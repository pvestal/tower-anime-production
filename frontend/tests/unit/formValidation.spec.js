import { describe, it, expect } from 'vitest'

describe('Form Validation Tests', () => {
  describe('Generation Form Validation', () => {
    const validatePrompt = (prompt) => {
      if (!prompt || prompt.trim().length === 0) {
        return { valid: false, error: 'Prompt is required' }
      }
      if (prompt.length > 1000) {
        return { valid: false, error: 'Prompt must be less than 1000 characters' }
      }
      return { valid: true }
    }

    const validateCfgScale = (cfg) => {
      const value = parseFloat(cfg)
      if (isNaN(value)) {
        return { valid: false, error: 'CFG scale must be a number' }
      }
      if (value < 1 || value > 20) {
        return { valid: false, error: 'CFG scale must be between 1 and 20' }
      }
      return { valid: true }
    }

    const validateSteps = (steps) => {
      const value = parseInt(steps)
      if (isNaN(value)) {
        return { valid: false, error: 'Steps must be a number' }
      }
      if (value < 1 || value > 150) {
        return { valid: false, error: 'Steps must be between 1 and 150' }
      }
      return { valid: true }
    }

    const validateBatchSize = (size) => {
      const value = parseInt(size)
      if (isNaN(value)) {
        return { valid: false, error: 'Batch size must be a number' }
      }
      if (value < 1 || value > 24) {
        return { valid: false, error: 'Batch size must be between 1 and 24' }
      }
      return { valid: true }
    }

    const validateDimensions = (width, height) => {
      if (width < 64 || width > 2048 || width % 64 !== 0) {
        return { valid: false, error: 'Width must be between 64-2048 and divisible by 64' }
      }
      if (height < 64 || height > 2048 || height % 64 !== 0) {
        return { valid: false, error: 'Height must be between 64-2048 and divisible by 64' }
      }
      return { valid: true }
    }

    describe('Prompt Validation', () => {
      it('rejects empty prompt', () => {
        expect(validatePrompt('')).toEqual({
          valid: false,
          error: 'Prompt is required'
        })
      })

      it('rejects whitespace-only prompt', () => {
        expect(validatePrompt('   ')).toEqual({
          valid: false,
          error: 'Prompt is required'
        })
      })

      it('rejects prompt over 1000 characters', () => {
        const longPrompt = 'a'.repeat(1001)
        expect(validatePrompt(longPrompt)).toEqual({
          valid: false,
          error: 'Prompt must be less than 1000 characters'
        })
      })

      it('accepts valid prompt', () => {
        expect(validatePrompt('cyberpunk warrior')).toEqual({ valid: true })
      })
    })

    describe('CFG Scale Validation', () => {
      it('rejects non-numeric values', () => {
        expect(validateCfgScale('abc')).toEqual({
          valid: false,
          error: 'CFG scale must be a number'
        })
      })

      it('rejects values below 1', () => {
        expect(validateCfgScale(0.5)).toEqual({
          valid: false,
          error: 'CFG scale must be between 1 and 20'
        })
      })

      it('rejects values above 20', () => {
        expect(validateCfgScale(25)).toEqual({
          valid: false,
          error: 'CFG scale must be between 1 and 20'
        })
      })

      it('accepts valid values', () => {
        expect(validateCfgScale(7.5)).toEqual({ valid: true })
        expect(validateCfgScale(1)).toEqual({ valid: true })
        expect(validateCfgScale(20)).toEqual({ valid: true })
      })
    })

    describe('Steps Validation', () => {
      it('rejects non-integer values', () => {
        expect(validateSteps('abc')).toEqual({
          valid: false,
          error: 'Steps must be a number'
        })
      })

      it('rejects values below 1', () => {
        expect(validateSteps(0)).toEqual({
          valid: false,
          error: 'Steps must be between 1 and 150'
        })
      })

      it('rejects values above 150', () => {
        expect(validateSteps(200)).toEqual({
          valid: false,
          error: 'Steps must be between 1 and 150'
        })
      })

      it('accepts valid values', () => {
        expect(validateSteps(30)).toEqual({ valid: true })
        expect(validateSteps(1)).toEqual({ valid: true })
        expect(validateSteps(150)).toEqual({ valid: true })
      })
    })

    describe('Batch Size Validation', () => {
      it('rejects values below 1', () => {
        expect(validateBatchSize(0)).toEqual({
          valid: false,
          error: 'Batch size must be between 1 and 24'
        })
      })

      it('rejects values above 24', () => {
        expect(validateBatchSize(50)).toEqual({
          valid: false,
          error: 'Batch size must be between 1 and 24'
        })
      })

      it('accepts valid values', () => {
        expect(validateBatchSize(4)).toEqual({ valid: true })
        expect(validateBatchSize(1)).toEqual({ valid: true })
        expect(validateBatchSize(24)).toEqual({ valid: true })
      })
    })

    describe('Dimension Validation', () => {
      it('rejects width below 64', () => {
        expect(validateDimensions(32, 512)).toEqual({
          valid: false,
          error: 'Width must be between 64-2048 and divisible by 64'
        })
      })

      it('rejects width above 2048', () => {
        expect(validateDimensions(4096, 512)).toEqual({
          valid: false,
          error: 'Width must be between 64-2048 and divisible by 64'
        })
      })

      it('rejects width not divisible by 64', () => {
        expect(validateDimensions(500, 512)).toEqual({
          valid: false,
          error: 'Width must be between 64-2048 and divisible by 64'
        })
      })

      it('accepts valid dimensions', () => {
        expect(validateDimensions(512, 768)).toEqual({ valid: true })
        expect(validateDimensions(1024, 1024)).toEqual({ valid: true })
      })
    })
  })

  describe('Character Form Validation', () => {
    const validateCharacterName = (name) => {
      if (!name || name.trim().length < 2) {
        return { valid: false, error: 'Name must be at least 2 characters' }
      }
      if (name.length > 100) {
        return { valid: false, error: 'Name must be less than 100 characters' }
      }
      if (!/^[a-zA-Z0-9\s\-_]+$/.test(name)) {
        return { valid: false, error: 'Name contains invalid characters' }
      }
      return { valid: true }
    }

    const validateAge = (age) => {
      const value = parseInt(age)
      if (isNaN(value) || value < 0 || value > 999) {
        return { valid: false, error: 'Age must be between 0 and 999' }
      }
      return { valid: true }
    }

    describe('Character Name Validation', () => {
      it('rejects short names', () => {
        expect(validateCharacterName('a')).toEqual({
          valid: false,
          error: 'Name must be at least 2 characters'
        })
      })

      it('rejects long names', () => {
        const longName = 'a'.repeat(101)
        expect(validateCharacterName(longName)).toEqual({
          valid: false,
          error: 'Name must be less than 100 characters'
        })
      })

      it('rejects special characters', () => {
        expect(validateCharacterName('Kai@#$')).toEqual({
          valid: false,
          error: 'Name contains invalid characters'
        })
      })

      it('accepts valid names', () => {
        expect(validateCharacterName('Kai Nakamura')).toEqual({ valid: true })
        expect(validateCharacterName('Mei-Lin_2')).toEqual({ valid: true })
      })
    })

    describe('Age Validation', () => {
      it('rejects negative ages', () => {
        expect(validateAge(-1)).toEqual({
          valid: false,
          error: 'Age must be between 0 and 999'
        })
      })

      it('rejects ages over 999', () => {
        expect(validateAge(1000)).toEqual({
          valid: false,
          error: 'Age must be between 0 and 999'
        })
      })

      it('accepts valid ages', () => {
        expect(validateAge(25)).toEqual({ valid: true })
        expect(validateAge(0)).toEqual({ valid: true })
        expect(validateAge(999)).toEqual({ valid: true })
      })
    })
  })

  describe('Input Sanitization', () => {
    const sanitizeInput = (input) => {
      // Remove HTML tags completely
      const cleaned = input.replace(/<[^>]*>/g, '')

      // Then escape remaining characters for safety
      return cleaned
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;')
    }

    it('removes script tags', () => {
      const input = '<script>alert("XSS")</script>Hello'
      expect(sanitizeInput(input)).toBe('alert(&quot;XSS&quot;)Hello')
    })

    it('escapes HTML entities', () => {
      const input = '<div>Test & "quotes"</div>'
      // Strips tags first, then escapes the content
      expect(sanitizeInput(input)).toBe('Test &amp; &quot;quotes&quot;')
    })

    it('handles nested scripts', () => {
      const input = '<script><script>alert("XSS")</script></script>'
      const result = sanitizeInput(input)
      // After stripping ALL tags, only text content remains
      expect(result).toBe('alert(&quot;XSS&quot;)')
    })

    it('preserves normal text', () => {
      const input = 'Normal text without issues'
      expect(sanitizeInput(input)).toBe('Normal text without issues')
    })
  })

  describe('Form State Management', () => {
    const formState = {
      fields: {},
      errors: {},
      touched: {},
      dirty: false,
      valid: true,

      setField(name, value) {
        this.fields[name] = value
        this.dirty = true
        this.validateField(name)
      },

      touchField(name) {
        this.touched[name] = true
      },

      validateField(name) {
        // Validation logic per field
        delete this.errors[name]

        if (name === 'prompt' && !this.fields.prompt) {
          this.errors.prompt = 'Required'
        }

        this.valid = Object.keys(this.errors).length === 0
      },

      reset() {
        this.fields = {}
        this.errors = {}
        this.touched = {}
        this.dirty = false
        this.valid = true
      }
    }

    it('tracks dirty state', () => {
      formState.reset()
      expect(formState.dirty).toBe(false)

      formState.setField('prompt', 'test')
      expect(formState.dirty).toBe(true)
    })

    it('tracks touched fields', () => {
      formState.reset()
      expect(formState.touched.prompt).toBeUndefined()

      formState.touchField('prompt')
      expect(formState.touched.prompt).toBe(true)
    })

    it('validates on field change', () => {
      formState.reset()
      formState.setField('prompt', '')
      expect(formState.errors.prompt).toBe('Required')
      expect(formState.valid).toBe(false)

      formState.setField('prompt', 'valid prompt')
      expect(formState.errors.prompt).toBeUndefined()
      expect(formState.valid).toBe(true)
    })

    it('resets form state', () => {
      formState.setField('prompt', 'test')
      formState.touchField('prompt')

      formState.reset()

      expect(formState.fields).toEqual({})
      expect(formState.errors).toEqual({})
      expect(formState.touched).toEqual({})
      expect(formState.dirty).toBe(false)
      expect(formState.valid).toBe(true)
    })
  })
})