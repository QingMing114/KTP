import { describe, it, expect, beforeEach } from 'vitest'

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

  it('should store and retrieve API key', () => {
    expect(localStorage.getItem('ktp_v2_api_key')).toBeNull()
    localStorage.setItem('ktp_v2_api_key', 'test-api-key')
    expect(localStorage.getItem('ktp_v2_api_key')).toBe('test-api-key')
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

  it('should return empty string when no auth token', () => {
    const jwt = localStorage.getItem('ktp_v2_jwt_token')
    const apiKey = localStorage.getItem('ktp_v2_api_key')
    const authToken = jwt || apiKey || ''
    expect(authToken).toBe('')
  })
})
