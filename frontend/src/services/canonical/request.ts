/** Reusable HTTP helpers for canonical API clients.
 *
 * Reuses base URL from the existing V2 api service
 * so both protocols coexist until Phase C.3.
 */

import { getApiKey, getJwtToken, buildUrl, handleAuthExpired } from '../api'
import { IncrementalSseDecoder } from '../sseDecoder'

const CANONICAL_PREFIX = '/api/product/v1'

function getAuthToken(): string {
  const jwt = getJwtToken()
  if (jwt) return jwt
  return getApiKey()
}

function canonicalUrl(path: string): string {
  return buildUrl(`${CANONICAL_PREFIX}${path}`)
}

function authHeaders(source?: HeadersInit, extra?: Record<string, string>): Headers {
  const h = new Headers(source)
  Object.entries(extra ?? {}).forEach(([key, value]) => h.set(key, value))
  const token = getAuthToken()
  if (token) h.set('Authorization', `Bearer ${token}`)
  return h
}

async function canonicalError(response: Response): Promise<Error> {
  let message = response.statusText || `HTTP ${response.status}`
  try {
    const payload = await response.json() as {
      error?: { message?: unknown; detail?: { reason?: unknown } }
      detail?: unknown
    }
    if (typeof payload.error?.message === 'string') message = payload.error.message
    if (typeof payload.error?.detail?.reason === 'string' && payload.error.detail.reason !== message) {
      message = `${message}（${payload.error.detail.reason}）`
    } else if (typeof payload.detail === 'string') message = payload.detail
  } catch { /* keep status text */ }
  if (response.status === 401) {
    handleAuthExpired()
    return new Error('认证已过期，请重新登录')
  }
  return new Error(message)
}

/** Generic JSON request helper (parallels requestJson from ../api). */
export async function canonicalJson<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = authHeaders(init?.headers, { 'Content-Type': 'application/json' })
  const response = await fetch(canonicalUrl(path), { ...init, headers })
  if (!response.ok) throw await canonicalError(response)
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
    headers: authHeaders(init.headers, { 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
    signal,
  })
    .then(async (response) => {
      if (!response.ok) throw await canonicalError(response)
      if (!response.body) throw new Error('Missing event stream body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      const eventDecoder = new IncrementalSseDecoder(parseCanonicalSseBlock)
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        eventDecoder.push(chunk).forEach(onEvent)
      }
      eventDecoder.push(decoder.decode()).forEach(onEvent)
      eventDecoder.finish().forEach(onEvent)
    })
    .catch((err) => onError?.(err instanceof Error ? err : new Error(String(err))))
}

/** Generic authenticated canonical SSE stream used by map and submission clients. */
export function canonicalSseStream<T>(
  path: string,
  onEvent: (event: T) => void,
  onError: (error: Error) => void,
  onOpen?: () => void,
): () => void {
  const controller = new AbortController()
  fetch(canonicalUrl(path), {
    method: 'GET',
    headers: authHeaders(undefined, { Accept: 'text/event-stream' }),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) throw await canonicalError(response)
    if (!response.body) throw new Error('Missing event stream body')
    onOpen?.()
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const eventDecoder = new IncrementalSseDecoder((block) => parseCanonicalDataBlock<T>(block))
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      eventDecoder.push(decoder.decode(value, { stream: true })).forEach(onEvent)
    }
    eventDecoder.push(decoder.decode()).forEach(onEvent)
    eventDecoder.finish().forEach(onEvent)
  }).catch((error) => {
    if (!controller.signal.aborted) onError(error instanceof Error ? error : new Error(String(error)))
  })
  return () => controller.abort()
}

function parseCanonicalDataBlock<T>(block: string): T | null {
  const data = block.split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
  if (!data.length) return null
  try { return JSON.parse(data.join('\n')) as T } catch { return null }
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

export function parseCanonicalSseBlock(block: string): SubmissionSseEvent | null {
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
