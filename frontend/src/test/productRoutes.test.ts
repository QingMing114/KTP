// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { CHAT_PATH, DEFAULT_PRODUCT_PATH, hasProductAccess, YIELD_ESTIMATE_PATH } from '../productRoutes'

describe('product route contract', () => {
  it('uses the map workspace as the authenticated default and keeps chat explicit', () => {
    expect(DEFAULT_PRODUCT_PATH).toBe('/workspace')
    expect(CHAT_PATH).toBe('/chat')
    expect(YIELD_ESTIMATE_PATH).toBe('/yield-estimate')
  })

  it('requires a JWT-authenticated state or explicit product API key', () => {
    expect(hasProductAccess(false, '')).toBe(false)
    expect(hasProductAccess(true, '')).toBe(true)
    expect(hasProductAccess(false, 'product-key')).toBe(true)
  })
})
