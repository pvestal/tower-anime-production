/**
 * Shared API base: constants, error class, and fetch helper.
 * Domain-specific API modules import from here.
 */

export const API_BASE = '/api/lora'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Generic JSON request helper. Prepends API_BASE to the endpoint,
 * sets Content-Type to application/json, and throws ApiError on non-2xx.
 */
export async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new ApiError(response.status, errorText)
  }

  return response.json()
}

/** Alias kept for readability in domain modules. */
export const fetchApi = request
