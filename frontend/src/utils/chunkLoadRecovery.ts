export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '')
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i.test(message)
}

/** A deploy can invalidate an already open tab. Reload once, with a cooldown
 * so a persistent network/server failure still reaches the page error UI. */
export function installChunkLoadRecovery(): () => void {
  const recover = (event: Event) => {
    if (!isChunkLoadError((event as Event & { payload?: unknown }).payload)) return
    try {
      const now = Date.now()
      const key = 'ktp_chunk_reload_at'
      if (now - Number(window.sessionStorage.getItem(key) || 0) < 60_000) return
      window.sessionStorage.setItem(key, String(now))
    } catch { return /* Keep the error UI when storage is unavailable. */ }
    event.preventDefault()
    window.location.reload()
  }
  window.addEventListener('vite:preloadError', recover)
  return () => window.removeEventListener('vite:preloadError', recover)
}
