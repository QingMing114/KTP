import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

describe('JWT Token Management', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.clearAllMocks()
  })

  it('stores and retrieves JWT token', async () => {
    const { setJwtToken, getJwtToken } = await import('../services/api')
    setJwtToken('test-token-123')
    expect(getJwtToken()).toBe('test-token-123')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('ktp_v2_jwt_token', 'test-token-123')
  })

  it('returns empty string when no JWT token', async () => {
    const { getJwtToken } = await import('../services/api')
    expect(getJwtToken()).toBe('')
  })

  it('clears JWT token', async () => {
    const { setJwtToken, clearJwtToken, getJwtToken } = await import('../services/api')
    setJwtToken('test-token')
    clearJwtToken()
    expect(getJwtToken()).toBe('')
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('ktp_v2_jwt_token')
  })

  it('stores last login user', async () => {
    const { setLastLoginUser, getLastLoginUser } = await import('../services/api')
    setLastLoginUser('admin')
    expect(getLastLoginUser()).toBe('admin')
  })

  it('returns default user when none stored', async () => {
    const { getLastLoginUser } = await import('../services/api')
    expect(getLastLoginUser()).toBe('admin')
  })
})

describe('API Base URL Management', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.clearAllMocks()
  })

  it('returns empty string as default base URL', async () => {
    const { getApiBaseUrl } = await import('../services/api')
    expect(getApiBaseUrl()).toBe('')
  })

  it('stores and retrieves custom base URL', async () => {
    const { setApiBaseUrl, getApiBaseUrl } = await import('../services/api')
    setApiBaseUrl('http://localhost:8005')
    expect(getApiBaseUrl()).toBe('http://localhost:8005')
  })
})

describe('buildUrl', () => {
  beforeEach(() => {
    localStorageMock.clear()
  })

  it('returns path as-is when no base URL', async () => {
    const { buildUrl } = await import('../services/api')
    expect(buildUrl('/v2/sessions')).toBe('/v2/sessions')
  })

  it('combines base URL with path', async () => {
    const { setApiBaseUrl, buildUrl } = await import('../services/api')
    setApiBaseUrl('http://localhost:8005')
    expect(buildUrl('/v2/sessions')).toBe('http://localhost:8005/v2/sessions')
  })
})
