/**
 * Lightweight logger — only outputs in development mode.
 * In production builds (Vite drop_console), all console calls are stripped anyway.
 * This provides an extra safety net for non-Vite builds.
 */

// Vite provides import.meta.env at runtime; declare for TypeScript
declare const import_meta_env: { DEV?: boolean } | undefined

const isDev = typeof import.meta !== 'undefined' && (import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV === true

export const logger = {
  error: (...args: unknown[]) => { if (isDev) console.error('[KTP]', ...args) },
  warn: (...args: unknown[]) => { if (isDev) console.warn('[KTP]', ...args) },
  info: (...args: unknown[]) => { if (isDev) console.info('[KTP]', ...args) },
}
