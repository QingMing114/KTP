import type { SseEvent, SessionCreateResponse, RunReplayResponse, MetadataResponse } from '../types/api'
import type { Session, Run, Dataset, RunSummary, SystemManifest } from '../types'

const DEFAULT_API_BASE_URL = ""
const API_BASE_STORAGE_KEY = "ktp_v2_api_base_url"

const API_KEY_STORAGE_KEY = "ktp_v2_api_key"
const JWT_TOKEN_STORAGE_KEY = "ktp_v2_jwt_token"

const DEFAULT_TIMEOUT = 30000
const SSE_TIMEOUT = 600000

export function getJwtToken(): string {
  return localStorage.getItem(JWT_TOKEN_STORAGE_KEY) || ""
}

export function setJwtToken(token: string): void {
  localStorage.setItem(JWT_TOKEN_STORAGE_KEY, token)
}

export function clearJwtToken(): void {
  localStorage.removeItem(JWT_TOKEN_STORAGE_KEY)
}

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE_KEY) || ""
}

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE_KEY, key)
}

function getAuthToken(): string {
  const jwt = getJwtToken()
  if (jwt) return jwt
  return getApiKey()
}

export function getApiBaseUrl(): string {
  const stored = localStorage.getItem(API_BASE_STORAGE_KEY)
  return stored !== null ? stored : DEFAULT_API_BASE_URL
}

export function setApiBaseUrl(url: string): void {
  localStorage.setItem(API_BASE_STORAGE_KEY, url)
}

function withTrailingSlash(value: string): string {
  return value.endsWith("/") ? value : `${value}/`
}

export function buildUrl(path: string): string {
  const base = getApiBaseUrl()
  if (!base) return path
  return new URL(path, withTrailingSlash(base)).toString()
}

export async function requestJson<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set("Content-Type", "application/json")
  const authToken = getAuthToken()
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`)
  }
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT)
  try {
    const response = await fetch(buildUrl(path), {
      ...init,
      headers,
      signal: init?.signal ?? controller.signal,
    })
    if (!response.ok) {
      let detail = response.statusText
      try {
        const cloned = response.clone()
        const text = await cloned.text()
        try {
          const payload = JSON.parse(text)
          detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail)
        } catch {
          detail = text
        }
      } catch {
        detail = response.statusText
      }
      if (response.status === 401) {
        clearJwtToken()
        throw new Error("认证已过期，请重新登录")
      }
      if (response.status === 429) {
        throw new Error("请求过于频繁，请稍后再试")
      }
      throw new Error(`${response.status} ${detail}`)
    }
    const text = await response.text()
    if (!text) return {} as T
    return JSON.parse(text) as T
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function requestEventStream(
  path: string, 
  init: RequestInit, 
  onEvent: (event: SseEvent) => void,
  onError?: (error: Error) => void,
  signal?: AbortSignal
): Promise<void> {
  const headers = new Headers(init?.headers)
  headers.set("Content-Type", "application/json")
  headers.set("Accept", "text/event-stream")
  const authToken = getAuthToken()
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`)
  }
  
  try {
    const response = await fetch(buildUrl(path), {
      ...init,
      headers,
      signal,
    })
    
    if (!response.ok) {
      let detail = response.statusText
      try {
        const cloned = response.clone()
        detail = await cloned.text()
      } catch {
        detail = response.statusText
      }
      if (response.status === 401) {
        throw new Error("认证失败：请检查 API Key 配置")
      }
      if (response.status === 429) {
        throw new Error("请求过于频繁，请稍后再试")
      }
      throw new Error(`${response.status} ${detail}`)
    }
    
    if (response.body === null) {
      throw new Error("Missing event stream body.")
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: true })
      const blocks = buffer.split("\n\n")
      buffer = blocks.pop() ?? ""
      
      blocks.forEach((block) => {
        if (block.startsWith(": ")) return
        const event = parseSseBlock(block)
        if (event !== null) {
          onEvent(event)
        }
      })
    }
    
    if (buffer.trim()) {
      const event = parseSseBlock(buffer)
      if (event !== null) {
        onEvent(event)
      }
    }
  } catch (error) {
    if (onError) {
      onError(error instanceof Error ? error : new Error(String(error)))
    } else {
      console.error("Error in event stream:", error)
    }
  }
}

function parseSseBlock(block: string): SseEvent | null {
  let eventType: string | undefined
  const dataLines: string[] = []
  
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim())
    } else if (line.startsWith(": ")) {
      continue
    }
  }
  
  if (dataLines.length === 0) {
    return null
  }
  
  try {
    const parsed = JSON.parse(dataLines.join("\n"))
    if (eventType && !parsed.event) {
      parsed.event = eventType
    }
    return parsed
  } catch {
    console.error("Failed to parse SSE block:", block)
    return null
  }
}

export async function loadMetadata(): Promise<MetadataResponse> {
  try {
    const [tools, agents, packs] = await Promise.all([
      requestJson<MetadataResponse["tools"]>("/v2/tools"),
      requestJson<MetadataResponse["agents"]>("/v2/agents"),
      requestJson<MetadataResponse["packs"]>("/v2/domain-packs"),
    ])
    return { tools, agents, packs }
  } catch (error) {
    console.error("Error loading metadata:", error)
    throw error
  }
}

export async function createSession(title: string): Promise<{ session_id: string; title: string }> {
  const payload = await requestJson<SessionCreateResponse>("/v2/sessions", {
    method: "POST",
    body: JSON.stringify({
      title: title && title.trim().length > 0 ? title.trim() : "New chat",
      user_id: "web-user",
    }),
  })
  return payload.session
}

export async function getSessions(): Promise<Session[]> {
  const resp = await requestJson<unknown>("/v2/sessions")
  if (Array.isArray(resp)) return resp as Session[]
  const obj = resp as Record<string, unknown>
  return (obj.items || []) as Session[]
}

export async function getSession(sessionId: string) {
  return requestJson(`/v2/sessions/${sessionId}`)
}

export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson(`/v2/sessions/${sessionId}`, {
    method: "DELETE",
  })
}

export async function updateSession(sessionId: string, title: string): Promise<Session> {
  return requestJson<Session>(`/v2/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  })
}

export async function uploadFile(file: File): Promise<{ path: string; name: string; size: number }> {
  const formData = new FormData()
  formData.append("file", file)
  const headers = new Headers()
  const authToken = getAuthToken()
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`)
  }
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), SSE_TIMEOUT)
  try {
    const response = await fetch(buildUrl("/v2/upload"), {
      method: "POST",
      headers,
      body: formData,
      signal: controller.signal,
    })
    if (!response.ok) {
      let detail = response.statusText
      try {
        const payload = await response.json()
        detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail)
      } catch {
        detail = await response.text()
      }
      throw new Error(`上传失败: ${response.status} ${detail}`)
    }
    return response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function getSessionRuns(sessionId: string): Promise<Run[]> {
  const runSummaries = await requestJson<RunSummary[]>(`/v2/sessions/${sessionId}/runs`)
  const runDetails = await Promise.all(
    runSummaries.map((summary) => requestJson<Run>(`/v2/runs/${summary.run_id}`)),
  )
  return runDetails
}

export async function replayRun(runId: string): Promise<RunReplayResponse> {
  return requestJson<RunReplayResponse>(`/v2/runs/${runId}/replay`, {
    method: "POST",
  })
}

export async function authLogin(userId: string, password: string): Promise<{ access_token: string; user_id: string }> {
  return requestJson("/v2/auth/login", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password }),
  })
}

export async function authRegister(userId: string, password: string): Promise<{ user_id: string; role: string }> {
  return requestJson("/v2/auth/register", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password }),
  })
}

export async function authGetMe(): Promise<{ user_id: string; role: string }> {
  return requestJson("/v2/auth/me")
}

export async function getDatasets(): Promise<Dataset[]> {
  const resp = await requestJson<{ items?: Dataset[]; datasets?: Dataset[] }>("/v2/datasets")
  return resp.items || resp.datasets || []
}

export async function registerDataset(data: {
  name: string;
  description?: string;
  data_type?: string;
  region?: string;
  source_path?: string;
  metadata?: Record<string, unknown>;
}): Promise<Dataset> {
  return requestJson("/v2/datasets/register", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  return requestJson(`/v2/datasets/${datasetId}`)
}

export async function getAllRuns(limit: number = 50, offset: number = 0): Promise<{ items: RunSummary[]; total: number }> {
  const resp = await requestJson<unknown>(`/v2/runs?limit=${limit}&offset=${offset}`)
  if (Array.isArray(resp)) {
    return { items: resp as RunSummary[], total: resp.length }
  }
  const obj = resp as Record<string, unknown>
  return { items: (obj.items || []) as RunSummary[], total: (obj.total || 0) as number }
}

export async function getRunDetail(runId: string): Promise<Run> {
  return requestJson(`/v2/runs/${runId}`)
}

export async function getSystemManifest(): Promise<SystemManifest> {
  return requestJson("/v2/system/manifest")
}

export async function cleanupSystem(maxAgeDays?: number): Promise<{ deleted_sessions: number; deleted_runs: number }> {
  return requestJson("/v2/system/cleanup", {
    method: "POST",
    body: JSON.stringify(maxAgeDays ? { max_age_days: maxAgeDays } : {}),
  })
}
