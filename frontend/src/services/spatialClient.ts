import { canonicalJson, canonicalSseStream } from './canonical/request'

export interface LiveFarm { farm_id: string; name: string; location_label: string; area_hectares: number; geometry: unknown }
export interface LiveImageryCandidate {
  item_id: string
  collection: string
  acquired_at: string
  cloud_cover?: number
  coverage_percent?: number
  thumbnail_url?: string
  platform?: string
  item_version?: string
  asset_fingerprint?: string
  selection_token?: string
  is_recommended: boolean
}
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
  completed_at?: string
  artifact_ids: string[]
  result: Record<string, unknown>
}
export interface LaiAnalysisEvent {
  event_id?: string
  kind: 'progress' | 'result' | 'error'
  stage: string
  detail: string
  progress_percent?: number
  data: Record<string, unknown>
  timestamp?: string
}
export interface LaiColorStop { value: number; color: string }
export interface LaiMapOverlay {
  url: string
  bounds: [number, number, number, number]
  opacity: number
  colorScale: LaiColorStop[]
}
export interface LaiAnalysisProducts {
  reportUrl: string
  rasterUrl: string
  overlay: LaiMapOverlay | null
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function readLaiAnalysisProducts(result: Record<string, unknown>): LaiAnalysisProducts {
  const overlay = recordValue(result.map_overlay)
  const rawBounds = overlay?.bounds
  const bounds = Array.isArray(rawBounds) && rawBounds.length === 4 && rawBounds.every((value) => typeof value === 'number' && Number.isFinite(value))
    ? rawBounds as [number, number, number, number]
    : null
  const rawScale = Array.isArray(overlay?.color_scale) ? overlay.color_scale : []
  const colorScale = rawScale.flatMap((stop) => (
    Array.isArray(stop)
    && stop.length === 2
    && typeof stop[0] === 'number'
    && Number.isFinite(stop[0])
    && typeof stop[1] === 'string'
      ? [{ value: stop[0], color: stop[1] }]
      : []
  ))
  const overlayUrl = typeof overlay?.url === 'string' ? overlay.url : ''
  const opacity = typeof overlay?.opacity === 'number' && Number.isFinite(overlay.opacity)
    ? Math.min(1, Math.max(0, overlay.opacity))
    : 0.72

  return {
    reportUrl: typeof result.report_uri === 'string' ? result.report_uri : '',
    rasterUrl: typeof result.lai_raster_uri === 'string' ? result.lai_raster_uri : '',
    overlay: overlayUrl && bounds ? { url: overlayUrl, bounds, opacity, colorScale } : null,
  }
}

export async function fetchLiveFarms(): Promise<LiveFarm[]> {
  const payload = await canonicalJson<{ items: LiveFarm[] }>('/farms')
  return payload.items
}

export async function searchLiveImagery(body: object): Promise<LiveImageryCandidate[]> {
  const payload = await canonicalJson<{ items: LiveImageryCandidate[] }>('/imagery/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return payload.items
}

export async function createLaiAnalysis(body: LaiAnalysisRequest): Promise<LaiAnalysis> {
  return canonicalJson<LaiAnalysis>('/lai-analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function getLaiAnalysis(analysisId: string): Promise<LaiAnalysis> {
  return canonicalJson<LaiAnalysis>(`/lai-analyses/${encodeURIComponent(analysisId)}`)
}

export function streamLaiAnalysis(
  analysisId: string,
  onEvent: (event: LaiAnalysisEvent) => void,
  onError: () => void,
  onOpen?: () => void,
): () => void {
  return canonicalSseStream<LaiAnalysisEvent>(
    `/lai-analyses/${encodeURIComponent(analysisId)}/events`,
    onEvent,
    () => onError(),
    onOpen,
  )
}
