/** Reusable HTTP helpers for canonical API clients.
 *
 * Reuses base URL from the existing V2 api service
 * so both protocols coexist until Phase C.3.
 */

import { getApiKey, getJwtToken, buildUrl } from '../api'

const CANONICAL_PREFIX = '/api/product/v1'

function getAuthToken(): string {
  const jwt = getJwtToken()
  if (jwt) return jwt
  return getApiKey()
}

function canonicalUrl(path: string): string {
  return buildUrl(`${CANONICAL_PREFIX}${path}`)
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...extra }
  const token = getAuthToken()
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

/** Generic JSON request helper (parallels requestJson from ../api). */
export async function canonicalJson<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = authHeaders({ 'Content-Type': 'application/json' })
  const response = await fetch(canonicalUrl(path), { ...init, headers })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const text = await response.clone().text()
      try { detail = JSON.parse(text).detail ?? text } catch { detail = text }
    } catch { /* keep statusText */ }
    throw new Error(`${response.status} ${detail}`)
  }
  const text = await response.text()
  return text ? (JSON.parse(text) as T) : ({} as T)
}

/** Fetch an SSE event stream for canonical submissions. */
export function canonicalEventStream(
  path: string,
  init: RequestInit,
  onEvent: (event: SubmissionSseEvent) => void,
  onError?: (error: Error) => void,
  signal?: AbortSignal,
): void {
  fetch(canonicalUrl(path), {
    ...init,
    headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
    signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
      if (!response.body) throw new Error('Missing event stream body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        for (const block of buffer.split('\n\n')) {
          const idx = block.lastIndexOf('\n\n')
          if (idx >= 0) { buffer = block.slice(idx + 2); continue }
          const event = parseCanonicalSseBlock(block)
          if (event) onEvent(event)
        }
      }
    })
    .catch((err) => onError?.(err instanceof Error ? err : new Error(String(err))))
}

/** Canonical SSE event shape. */
export interface SubmissionSseEvent {
  event: string
  submission_id: string
  run_id?: string
  stage?: string
  detail?: string
  data?: Record<string, unknown>
  timestamp: string
}

function parseCanonicalSseBlock(block: string): SubmissionSseEvent | null {
  if (!block.trim()) return null
  let eventType = ''
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) eventType = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  try {
    const parsed = JSON.parse(dataLines.join('\n')) as SubmissionSseEvent
    if (eventType && !parsed.event) parsed.event = eventType
    return parsed
  } catch {
    return null
  }
}
