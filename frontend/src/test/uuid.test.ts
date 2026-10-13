import { afterEach, describe, expect, it, vi } from 'vitest'
import { createUuid } from '../utils/uuid'

afterEach(() => vi.unstubAllGlobals())

describe('LAN HTTP identifiers', () => {
  it('creates distinct valid UUIDs when randomUUID is unavailable', () => {
    const getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto)
    vi.stubGlobal('crypto', { getRandomValues })
    const identifiers = Array.from({ length: 100 }, () => createUuid())
    expect(new Set(identifiers).size).toBe(100)
    for (const identifier of identifiers) {
      expect(identifier).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    }
  })
})
