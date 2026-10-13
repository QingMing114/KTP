import { canonicalJson, canonicalSseStream } from './canonical/request'
import { buildUrl, getApiKey, getJwtToken } from './api'
import { createUuid } from '../utils/uuid'

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
export interface CropAnalysisRequest { aoi: { geometry: object; source: 'drawn'; area_hectares: number }; imagery_item_id: string; imagery_snapshot: LiveImageryCandidate; farm_id?: string }
export interface CropClassScore { class_id: number; name: string; name_zh: string; score: number }
export interface CropAnalysis {
  analysis_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string
  progress_percent: number
  detail: string
  result: { predicted_class?: CropClassScore; class_scores?: CropClassScore[]; warnings?: string[]; input?: { valid_pixels: number; resolution_m: number }; report_uri?: string; error?: string }
}
export type WorkflowTaskId = 'crop' | 'lai' | 'growth' | 'potential' | 'yield_simple' | 'yield'
export type WorkflowStepId = 'imagery' | WorkflowTaskId
export interface YieldAgronomicInputs {
  confirmed_crop_class_id: number | null
  field_dataset_id: string | null
  cultivar: string | null
  sowing_date: string | null
}
export interface AnalysisWorkflowStep {
  step_id: WorkflowStepId
  depends_on: WorkflowStepId[]
  status: 'planned' | 'waiting' | 'running' | 'completed' | 'blocked' | 'failed' | 'skipped'
  progress_percent: number
  analysis_id?: string | null
  detail: string
  result: Record<string, unknown>
  updated_at?: string | null
}
export interface AnalysisWorkflow {
  data_mode?: 'live' | 'demo'
  demo_crop?: 'wheat' | 'maize' | null
  workflow_id: string
  parameters?: { target_resolution_m: number; reflectance_bands: string[]; parameter_source: string }
  conversation_id?: string | null
  run_id?: string | null
  report_uri?: string | null
  aoi: { geometry: object; source: 'drawn'; area_hectares: number }
  farm_id?: string | null
  status: 'planned' | 'running' | 'completed' | 'blocked' | 'failed' | 'cancelled'
  detail: string
  requested_task_ids: WorkflowTaskId[]
  effective_task_ids: WorkflowTaskId[]
  steps: AnalysisWorkflowStep[]
  imagery_item_id: string
  imagery_snapshot: LiveImageryCandidate
  yield_inputs: YieldAgronomicInputs
  created_at: string
  updated_at: string
}
export interface AnalysisWorkflowRequest {
  aoi: { geometry: object; source: 'drawn'; area_hectares: number }
  imagery_item_id: string
  imagery_snapshot: LiveImageryCandidate
  farm_id?: string
  requested_task_ids: WorkflowTaskId[]
  action_id?: string
  workspace_id?: string
  workspace_revision?: number
  conversation_id?: string | null
}
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

export async function createCropAnalysis(body: CropAnalysisRequest): Promise<CropAnalysis> {
  return canonicalJson<CropAnalysis>('/crop-analyses', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
}

export async function getCropAnalysis(analysisId: string): Promise<CropAnalysis> {
  return canonicalJson<CropAnalysis>(`/crop-analyses/${encodeURIComponent(analysisId)}`)
}

export async function createAnalysisWorkflow(body: AnalysisWorkflowRequest): Promise<AnalysisWorkflow> {
  const actionId = body.action_id ?? createUuid()
  return canonicalJson<AnalysisWorkflow>('/analysis-workflows', {
    method: 'POST', headers: { 'Idempotency-Key': actionId }, body: JSON.stringify({ ...body, action_id: actionId }),
  })
}

export async function getAnalysisWorkflow(workflowId: string): Promise<AnalysisWorkflow> {
  return canonicalJson<AnalysisWorkflow>(`/analysis-workflows/${encodeURIComponent(workflowId)}`)
}

export async function retryAnalysisWorkflowStep(
  workflowId: string, stepId: 'imagery' | 'crop' | 'lai' | 'potential' | 'yield_simple' | 'yield',
): Promise<AnalysisWorkflow> {
  return canonicalJson<AnalysisWorkflow>(`/analysis-workflows/${encodeURIComponent(workflowId)}/retry`, {
    method: 'POST', body: JSON.stringify({ step_id: stepId }),
  })
}

export async function updateAnalysisWorkflowYieldInputs(
  workflowId: string, yieldInputs: YieldAgronomicInputs,
): Promise<AnalysisWorkflow> {
  return canonicalJson<AnalysisWorkflow>(`/analysis-workflows/${encodeURIComponent(workflowId)}/yield-inputs`, {
    method: 'PUT', body: JSON.stringify({ yield_inputs: yieldInputs }),
  })
}

export async function loadHtmlReportObjectUrl(viewUrl: string): Promise<string> {
  const token = getJwtToken() || getApiKey()
  const response = await fetch(buildUrl(viewUrl), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new Error(`报告加载失败（HTTP ${response.status}）`)
  return URL.createObjectURL(await response.blob())
}

export const loadLaiReportObjectUrl = loadHtmlReportObjectUrl

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
