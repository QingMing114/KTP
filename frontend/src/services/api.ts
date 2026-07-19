import type { SseEvent, SessionCreateResponse, RunReplayResponse, MetadataResponse } from '../types/api'
import type { Session, Run, Dataset, RunSummary, SystemManifest, PluginToolSpec, PluginToolTestResult, KnowledgeDocument, KnowledgeQueryResult } from '../types'
import { API } from '../constants/api'
import { logger } from '../utils/logger'

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

let _onAuthExpired: (() => void) | null = null

export function onAuthExpired(callback: (() => void) | null): void {
  _onAuthExpired = callback
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

const LAST_LOGIN_USER_KEY = "ktp_v2_last_login_user"

export function setLastLoginUser(userId: string): void {
  localStorage.setItem(LAST_LOGIN_USER_KEY, userId)
}

export function getLastLoginUser(): string {
  return localStorage.getItem(LAST_LOGIN_USER_KEY) || "admin"
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
        if (_onAuthExpired) _onAuthExpired()
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
        clearJwtToken()
        if (_onAuthExpired) _onAuthExpired()
        throw new Error("认证已过期，请重新登录")
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
      logger.error("Error in event stream:", error)
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
    // JSON 解析失败时保留原始数据，避免事件静默丢失
    return { event: eventType || "raw", raw_data: dataLines.join("\n") } as SseEvent
  }
}

export async function loadMetadata(): Promise<MetadataResponse> {
  try {
    const [tools, agents, packs] = await Promise.all([
      requestJson<MetadataResponse["tools"]>(API.V2.TOOLS),
      requestJson<MetadataResponse["agents"]>(API.V2.AGENTS),
      requestJson<MetadataResponse["packs"]>(API.V2.PACKS),
    ])
    return { tools, agents, packs }
  } catch (error) {
    logger.error("Error loading metadata:", error)
    throw error
  }
}

export async function createSession(title: string): Promise<{ session_id: string; title: string }> {
  const payload = await requestJson<SessionCreateResponse>(API.V2.SESSIONS, {
    method: "POST",
    body: JSON.stringify({
      title: title && title.trim().length > 0 ? title.trim() : "新对话",
      user_id: "web-user",
    }),
  })
  return payload.session
}

export async function getSessions(): Promise<Session[]> {
  const resp = await requestJson<unknown>(API.V2.SESSIONS)
  if (Array.isArray(resp)) return resp as Session[]
  const obj = resp as Record<string, unknown>
  return (obj.items || []) as Session[]
}

export async function getSession(sessionId: string) {
  return requestJson(`${API.V2.SESSIONS}/${sessionId}`)
}

export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson(`${API.V2.SESSIONS}/${sessionId}`, {
    method: "DELETE",
  })
}

export async function updateSession(sessionId: string, title: string): Promise<Session> {
  return requestJson<Session>(`${API.V2.SESSIONS}/${sessionId}`, {
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
    const response = await fetch(buildUrl(API.V2.UPLOAD), {
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
  const runSummaries = await requestJson<RunSummary[]>(`${API.V2.SESSIONS}/${sessionId}/runs`)
  const runDetails = await Promise.all(
    runSummaries.map((summary) => requestJson<Run>(`${API.V2.RUNS}/${summary.run_id}`)),
  )
  return runDetails
}

export async function replayRun(runId: string): Promise<RunReplayResponse> {
  return requestJson<RunReplayResponse>(`${API.V2.RUNS}/${runId}/replay`, {
    method: "POST",
  })
}

export async function authLogin(userId: string, password: string): Promise<{ access_token: string; user_id: string; role: string }> {
  const result = await requestJson<{ access_token: string; user_id: string; role: string }>(API.V2.AUTH.LOGIN, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password }),
  })
  setLastLoginUser(userId)
  return result
}

export async function authRegister(userId: string, password: string): Promise<{ user_id: string; role: string; access_token: string }> {
  return requestJson(API.V2.AUTH.REGISTER, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, password }),
  })
}

export async function authGetMe(): Promise<{ user_id: string; role: string; created_at?: string; last_login?: string }> {
  return requestJson(API.V2.AUTH.ME)
}

export async function authLogout(): Promise<void> {
  try {
    await requestJson(API.V2.AUTH.LOGOUT, { method: "POST" })
  } catch {
    // logout is best-effort
  }
}

export async function authChangePassword(oldPassword: string, newPassword: string): Promise<{ status: string; detail: string }> {
  return requestJson(API.V2.AUTH.CHANGE_PASSWORD, {
    method: "POST",
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
}

export async function authListUsers(): Promise<Array<{ user_id: string; role: string; created_at: string; last_login: string | null }>> {
  return requestJson(API.V2.AUTH.USERS)
}

export async function getDatasets(): Promise<Dataset[]> {
  const resp = await requestJson<{ items?: Dataset[]; datasets?: Dataset[] }>(API.V2.DATASETS)
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
  return requestJson(`${API.V2.DATASETS}/register`, {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  return requestJson(`${API.V2.DATASETS}/${datasetId}`)
}

export async function getAllRuns(limit: number = 50, offset: number = 0): Promise<{ items: RunSummary[]; total: number }> {
  const resp = await requestJson<unknown>(`${API.V2.RUNS}?limit=${limit}&offset=${offset}`)
  if (Array.isArray(resp)) {
    return { items: resp as RunSummary[], total: resp.length }
  }
  const obj = resp as Record<string, unknown>
  return { items: (obj.items || []) as RunSummary[], total: (obj.total || 0) as number }
}

export async function getRunDetail(runId: string): Promise<Run> {
  return requestJson(`${API.V2.RUNS}/${runId}`)
}

export async function getSystemManifest(): Promise<SystemManifest> {
  return requestJson(`${API.V2.SYSTEM}/manifest`)
}

export async function cleanupSystem(maxAgeDays?: number): Promise<{ deleted_sessions: number; deleted_runs: number }> {
  return requestJson(`${API.V2.SYSTEM}/cleanup`, {
    method: "POST",
    body: JSON.stringify(maxAgeDays ? { max_age_days: maxAgeDays } : {}),
  })
}

export async function registerPluginTool(spec: PluginToolSpec): Promise<{ status: string; name: string }> {
  return requestJson(API.V2.PLUGINS.TOOLS, {
    method: "POST",
    body: JSON.stringify(spec),
  })
}

export async function unregisterPluginTool(toolName: string): Promise<{ status: string; name: string }> {
  return requestJson(`${API.V2.PLUGINS.TOOLS}/${encodeURIComponent(toolName)}`, {
    method: "DELETE",
  })
}

export async function listPluginTools(): Promise<Array<{ name: string; display_name: string; category: string; pack_name: string }>> {
  return requestJson(API.V2.PLUGINS.TOOLS)
}

export async function testPluginTool(toolName: string, toolInput: Record<string, unknown>): Promise<PluginToolTestResult> {
  return requestJson(`${API.V2.PLUGINS.TOOLS}/${encodeURIComponent(toolName)}/test`, {
    method: "POST",
    body: JSON.stringify(toolInput),
  })
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  return requestJson<KnowledgeDocument[]>(API.V2.KNOWLEDGE.DOCUMENTS)
}

export async function getKnowledgeDocument(documentId: string): Promise<KnowledgeDocument> {
  return requestJson(`${API.V2.KNOWLEDGE.DOCUMENTS}/${encodeURIComponent(documentId)}`)
}

export async function deleteKnowledgeDocument(documentId: string): Promise<{ status: string; document_id: string }> {
  return requestJson(`${API.V2.KNOWLEDGE.DOCUMENTS}/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  })
}

export async function ingestKnowledgeDocument(data: {
  document_id: string;
  title: string;
  source?: string;
  text: string;
  metadata?: Record<string, unknown>;
}): Promise<{ document_id: string; chunk_count: number; success: boolean; message: string }> {
  return requestJson(API.V2.KNOWLEDGE.INGEST, {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function queryKnowledge(data: {
  query: string;
  top_k?: number;
  task_type?: string;
  region?: string;
  crop_type?: string;
}): Promise<{ request_id: string; success: boolean; query: string; results: KnowledgeQueryResult[]; message: string }> {
  return requestJson(API.V2.KNOWLEDGE.QUERY, {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function runInference(data: {
  image_path: string;
  region?: string;
  crop_type?: string;
  task_type?: string;
  use_mock?: boolean;
  extra_params?: Record<string, unknown>;
}): Promise<{
  request_id: string;
  success: boolean;
  message: string;
  result?: {
    mask_uri: string;
    affected_area: number;
    confidence: number;
    model_name: string;
    model_version: string;
    artifact_uri: string;
    class_distribution?: Array<{ class_value: number; label?: string; count: number; ratio: number; mean_confidence?: number }>;
    class_labels?: Record<string, string>;
    polygons?: Array<{ id: string; points: Array<[number, number]> }>;
  };
}> {
  return requestJson(API.V2.INFERENCE.RUN, {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function batchInference(tasks: Array<{
  image_path?: string;
  region?: string;
  crop_type?: string;
  task_type?: string;
  use_mock?: boolean;
  extra_params?: Record<string, unknown>;
}>): Promise<{
  total: number;
  succeeded: number;
  failed: number;
  results: Array<{
    request_id: string;
    success: boolean;
    message: string;
    result?: Record<string, unknown>;
  }>;
}> {
  return requestJson(API.V2.INFERENCE.BATCH, {
    method: "POST",
    body: JSON.stringify({ tasks }),
  })
}
