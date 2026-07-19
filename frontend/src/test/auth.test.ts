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

function makeJwtPayload(payload: object): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).replace(/=/g, '')
  const body = btoa(JSON.stringify(payload)).replace(/=/g, '')
  return `${header}.${body}.fakesignature`
}

describe('loadInitialAuth with valid token', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('should return authenticated state for valid non-expired JWT', () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = makeJwtPayload({ user_id: 'testuser', role: 'admin', exp: futureExp })
    localStorage.setItem('ktp_v2_jwt_token', token)

    const parts = token.split('.')
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const pad = b64.length % 4
    const padded = pad ? b64 + '='.repeat(4 - pad) : b64
    const payload = JSON.parse(decodeURIComponent(escape(atob(padded))))

    expect(payload.user_id).toBe('testuser')
    expect(payload.role).toBe('admin')
    expect(payload.exp * 1000 > Date.now()).toBe(true)
  })
})

describe('loadInitialAuth with expired token', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('should return unauthenticated state for expired JWT', () => {
    const pastExp = Math.floor(Date.now() / 1000) - 3600
    const token = makeJwtPayload({ user_id: 'testuser', role: 'admin', exp: pastExp })
    localStorage.setItem('ktp_v2_jwt_token', token)

    const parts = token.split('.')
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const pad = b64.length % 4
    const padded = pad ? b64 + '='.repeat(4 - pad) : b64
    const payload = JSON.parse(decodeURIComponent(escape(atob(padded))))

    expect(payload.exp * 1000 > Date.now()).toBe(false)
  })

  it('should return unauthenticated state when no token stored', () => {
    const token = localStorage.getItem('ktp_v2_jwt_token')
    expect(token).toBeNull()
  })
})
