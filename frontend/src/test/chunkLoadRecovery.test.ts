// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installChunkLoadRecovery } from '../utils/chunkLoadRecovery'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

function browser(storageUnavailable = false) {
  const target = new EventTarget()
  const entries = new Map<string, string>()
  const reload = vi.fn()
  vi.stubGlobal('window', {
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
    sessionStorage: {
      getItem: (key: string) => { if (storageUnavailable) throw new Error('storage unavailable'); return entries.get(key) ?? null },
      setItem: (key: string, value: string) => entries.set(key, value),
    },
    location: { reload },
  })
  const fail = (message: string) => {
    const event = Object.assign(new Event('vite:preloadError', { cancelable: true }), { payload: new Error(message) })
    target.dispatchEvent(event)
    return event
  }
  return { reload, fail }
}

describe('chunk loading after a deployment', () => {
  it('reloads once and preserves the error UI for a persistent failure', () => {
    const { reload, fail } = browser()
    const dispose = installChunkLoadRecovery()
    expect(fail('Failed to fetch dynamically imported module: /assets/page-old.js').defaultPrevented).toBe(true)
    expect(fail('Failed to fetch dynamically imported module: /assets/page-old.js').defaultPrevented).toBe(false)
    expect(reload).toHaveBeenCalledTimes(1)
    dispose()
  })

  it('leaves unrelated exceptions visible', () => {
    const { reload, fail } = browser()
    const dispose = installChunkLoadRecovery()
    expect(fail('Cannot read properties of undefined').defaultPrevented).toBe(false)
    expect(reload).not.toHaveBeenCalled()
    dispose()
  })

  it('avoids an automatic reload loop when session storage is unavailable', () => {
    const { reload, fail } = browser(true)
    const dispose = installChunkLoadRecovery()
    expect(fail('Importing a module script failed').defaultPrevented).toBe(false)
    expect(reload).not.toHaveBeenCalled()
    dispose()
  })
})
