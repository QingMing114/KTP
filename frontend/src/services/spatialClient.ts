export interface LiveFarm { farm_id: string; name: string; location_label: string; area_hectares: number; geometry: unknown }
export interface LiveImageryCandidate { item_id: string; acquired_at: string; cloud_cover?: number; thumbnail_url?: string; is_recommended: boolean }
export interface LaiAnalysisRequest { aoi: { geometry: object; source: 'drawn'; area_hectares: number }; imagery_item_id: string; imagery_snapshot?: LiveImageryCandidate; farm_id?: string; parameters?: { target_resolution_m?: number } }
export interface LaiPixelProgress {
  processed_pixels: number
  current_pixel: number
  total_pixels: number
}
export interface LaiAnalysis {
  analysis_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  stage: string
  progress_percent: number
  detail: string
  progress_data: Partial<LaiPixelProgress>
  updated_at?: string
  artifact_ids: string[]
  result: Record<string, unknown>
}
export interface LaiAnalysisEvent {
  kind: 'progress' | 'result' | 'error'
  stage: string
  detail: string
  progress_percent?: number
  data: Record<string, unknown>
  timestamp?: string
}

const base = '/api/product/v1'

function firstValidationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null
  const message = detail.find((item) => item && typeof item === 'object' && 'msg' in item)?.msg
  return typeof message === 'string' ? message : null
}

async function apiErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json() as {
      error?: { message?: unknown; detail?: { reason?: unknown } }
      detail?: unknown
    }
    const message = typeof payload.error?.message === 'string' ? payload.error.message : null
    const reason = typeof payload.error?.detail?.reason === 'string' ? payload.error.detail.reason : null
    if (message && reason && reason !== message) return `${message}（${reason}）`
    if (message) return message
    if (typeof payload.detail === 'string') return payload.detail
    const validationMessage = firstValidationMessage(payload.detail)
    if (validationMessage) return `${fallback}：${validationMessage}`
  } catch {
    // Some proxy failures return HTML or an empty response body.
  }
  return `${fallback}（HTTP ${response.status}）`
}

async function requestJson<T>(input: RequestInfo | URL, init: RequestInit | undefined, fallback: string): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) throw new Error(await apiErrorMessage(response, fallback))
  return response.json() as Promise<T>
}

export async function fetchLiveFarms(): Promise<LiveFarm[]> {
  const payload = await requestJson<{ items: LiveFarm[] }>(`${base}/farms`, undefined, '无法加载示范农场')
  return payload.items
}

export async function searchLiveImagery(body: object): Promise<LiveImageryCandidate[]> {
  const payload = await requestJson<{ items: LiveImageryCandidate[] }>(`${base}/imagery/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, 'Sentinel 影像检索失败')
  return payload.items
}

export async function createLaiAnalysis(body: LaiAnalysisRequest): Promise<LaiAnalysis> {
  return requestJson<LaiAnalysis>(`${base}/lai-analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, '无法创建 LAI 分析任务')
}

export async function getLaiAnalysis(analysisId: string): Promise<LaiAnalysis> {
  return requestJson<LaiAnalysis>(`${base}/lai-analyses/${encodeURIComponent(analysisId)}`, undefined, '无法获取 LAI 分析状态')
}

export function streamLaiAnalysis(
  analysisId: string,
  onEvent: (event: LaiAnalysisEvent) => void,
  onError: () => void,
  onOpen?: () => void,
): () => void {
  const source = new EventSource(`${base}/lai-analyses/${encodeURIComponent(analysisId)}/events`)
  source.onopen = () => onOpen?.()
  source.addEventListener('analysis.event', (message) => {
    try {
      onEvent(JSON.parse((message as MessageEvent<string>).data) as LaiAnalysisEvent)
    } catch {
      onError()
    }
  })
  // Keep the source open: EventSource reconnects automatically using the server retry hint.
  source.onerror = () => onError()
  return () => source.close()
}
