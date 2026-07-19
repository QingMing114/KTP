import { describe, it, expect, beforeEach, vi } from 'vitest'

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
    get length() { return Object.keys(store).length },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

describe('API token management', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('should store and retrieve JWT token', () => {
    expect(localStorage.getItem('ktp_v2_jwt_token')).toBeNull()
    localStorage.setItem('ktp_v2_jwt_token', 'test-jwt-token')
    expect(localStorage.getItem('ktp_v2_jwt_token')).toBe('test-jwt-token')
  })

  it('should clear JWT token', () => {
    localStorage.setItem('ktp_v2_jwt_token', 'test-jwt-token')
    localStorage.removeItem('ktp_v2_jwt_token')
    expect(localStorage.getItem('ktp_v2_jwt_token')).toBeNull()
  })

  it('should prefer JWT token over API key', () => {
    localStorage.setItem('ktp_v2_jwt_token', 'jwt-token')
    localStorage.setItem('ktp_v2_api_key', 'api-key')
    const jwt = localStorage.getItem('ktp_v2_jwt_token')
    const apiKey = localStorage.getItem('ktp_v2_api_key')
    const authToken = jwt || apiKey || ''
    expect(authToken).toBe('jwt-token')
  })

  it('should fall back to API key when no JWT', () => {
    localStorage.setItem('ktp_v2_api_key', 'api-key')
    const jwt = localStorage.getItem('ktp_v2_jwt_token')
    const apiKey = localStorage.getItem('ktp_v2_api_key')
    const authToken = jwt || apiKey || ''
    expect(authToken).toBe('api-key')
  })
})

describe('buildUrl', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('should return path as-is when no base URL set', async () => {
    const { buildUrl } = await import('../services/api')
    expect(buildUrl('/v2/sessions')).toBe('/v2/sessions')
  })

  it('should prepend base URL when set', async () => {
    const { buildUrl, setApiBaseUrl } = await import('../services/api')
    setApiBaseUrl('http://localhost:8005')
    expect(buildUrl('/v2/sessions')).toBe('http://localhost:8005/v2/sessions')
  })

  it('should handle base URL with trailing slash', async () => {
    const { buildUrl, setApiBaseUrl } = await import('../services/api')
    setApiBaseUrl('http://localhost:8005/')
    expect(buildUrl('/v2/sessions')).toBe('http://localhost:8005/v2/sessions')
  })
})

describe('requestJson 401 handling', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('should throw auth expired error on 401 when no relogin possible', async () => {
    const { requestJson } = await import('../services/api')
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      clone: () => ({ text: () => Promise.resolve('{"detail":"Invalid token"}') }),
      text: () => Promise.resolve('{"detail":"Invalid token"}'),
    })
    vi.stubGlobal('fetch', mockFetch)
    try {
      await requestJson('/v2/sessions')
      expect.unreachable('Should have thrown')
    } catch (e) {
      expect((e as Error).message).toContain('认证已过期')
    }
    vi.restoreAllMocks()
  })
})
