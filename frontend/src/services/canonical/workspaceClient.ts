import { canonicalJson } from './request'
import type { AnalysisWorkflow, LiveImageryCandidate, WorkflowTaskId } from '../spatialClient'

export interface WorkspaceContext {
  workspace_id: string
  revision: number
  execution_mode: 'live' | 'demo'
  auto_execute?: boolean
  professional_mode?: boolean
  imagery_search?: { start_date?: string; end_date?: string; max_cloud_cover?: number }
  farm_id?: string | null
  aoi: { geometry: object; source: 'drawn'; area_hectares: number } | null
  imagery_item_id: string | null
  imagery_snapshot: LiveImageryCandidate | null
  active_workflow_id: string | null
  apsim_mode?: 'field' | 'example'
  draft_task_ids: WorkflowTaskId[]
}

export interface WorkspaceUiCard {
  card_id: string
  kind: 'farm' | 'aoi' | 'imagery_candidates' | 'imagery_selected' | 'task_selection' | 'analysis_plan' | 'parameter_set' | 'workflow'
  title: string
  state: 'current' | 'historical'
  summary?: string
  task_ids?: WorkflowTaskId[]
  candidate_ids?: string[]
  selected_candidate_id?: string | null
  fields?: Record<string, string>
  missing_inputs?: string[]
  source_run_id?: string
  workflow_id?: string
}

export interface WorkspaceUiState {
  stage: 'idle' | 'candidates' | 'ready' | 'running' | 'done'
  cards: WorkspaceUiCard[]
  imagery_candidates: Array<{ item_id: string; observed_at: string; cloud: string; recommended: boolean; selected: boolean }>
  task_options: Array<{ task_id: WorkflowTaskId | 'forecast'; label: string; available: boolean; status: string }>
}

export interface ProductParameter {
  name: string
  value: string | number
  unit?: string
  source: string
  editable: boolean
}

export interface WorkspacePartData {
  review?: ProfessionalReview
  auto_execute?: boolean
  data_mode?: 'live' | 'demo' | 'apsim_example'
  apsim_mode?: 'field' | 'example'
  demo_crop?: 'wheat' | 'maize' | null
  plan_id?: string
  workspace_id?: string
  revision?: number
  input_aoi?: object | null
  imagery_item_id?: string | null
  farm_id?: string | null
  execution_mode?: 'live' | 'demo'
  requested_task_ids?: WorkflowTaskId[]
  effective_task_ids?: WorkflowTaskId[]
  steps?: Array<{ step_id: string; label: string; depends_on: string[] }>
  rationale?: string
  intent?: 'advise' | 'configure' | 'execute' | 'explain' | 'status'
  missing_inputs?: string[]
  state?: 'draft' | 'effective'
  parameters?: ProductParameter[]
  action_id?: string
  action?: 'draw_aoi' | 'search_imagery' | 'configure_tasks'
  title?: string
  task_ids?: WorkflowTaskId[]
  can_execute?: boolean
  executed?: boolean
  demo_started?: boolean
  workflow_id?: string
  status?: string
}

export interface CanonicalAssistantPart {
  type: string
  text?: string
  artifact_id?: string
  part_id?: string
  data?: WorkspacePartData
}

export async function syncWorkspaceContext(context: WorkspaceContext): Promise<WorkspaceContext> {
  return canonicalJson(`/workspaces/${encodeURIComponent(context.workspace_id)}/context`, {
    method: 'PUT', body: JSON.stringify(context),
  })
}

export async function getWorkspaceWorkflows(workspaceId: string): Promise<AnalysisWorkflow[]> {
  return canonicalJson(`/workspaces/${encodeURIComponent(workspaceId)}/workflows`)
}

export type LaiParameterRanges = Record<'lai_range' | 'cab_range' | 'lidfa_range' | 'psoil_range', [number, number] | null>
export interface ProfessionalReview {
  review_id: string
  workspace_id: string
  source_run_id: string
  phase: 'search' | 'workflow' | 'lai'
  status: 'pending' | 'processing' | 'confirmed' | 'cancelled' | 'failed'
  title: string
  rationale: string
  detail: string
  context: WorkspaceContext
  intent: { task_ids: WorkflowTaskId[]; apsim_mode?: 'field' | 'example'; rationale: string; summary?: string }
  search: { start_date: string; end_date: string; max_cloud_cover: number } | null
  candidates: LiveImageryCandidate[]
  selected_imagery_id: string | null
  proposed_scene: (Partial<LaiParameterRanges> & {
    source?: string; reasoning?: string; crop_type?: string | null; region?: string | null
    month?: number | null; growth_stage?: string | null; confidence?: number
    context?: { acquired_at?: string; imagery_item_id?: string; crop_prediction?: { name?: string; name_zh?: string } }
  }) | null
  workflow_id: string | null
  created_at: string
  confirmed_parameters?: Record<string, unknown> | null
}
export interface ProfessionalDecision {
  decision: 'confirm' | 'cancel'
  search?: { start_date: string; end_date: string; max_cloud_cover: number }
  imagery_item_id?: string
  task_ids?: WorkflowTaskId[]
  apsim_mode?: 'field' | 'example'
  scene?: LaiParameterRanges
}
export function getProfessionalReviews(workspaceId: string): Promise<ProfessionalReview[]> {
  return canonicalJson(`/workspaces/${encodeURIComponent(workspaceId)}/professional-reviews`)
}
export function decideProfessionalReview(reviewId: string, context: WorkspaceContext, decision: ProfessionalDecision): Promise<{ review: ProfessionalReview; next_review: ProfessionalReview | null; workflow: AnalysisWorkflow | null }> {
  return canonicalJson(`/professional-reviews/${encodeURIComponent(reviewId)}/decision`, {
    method: 'POST', headers: { 'Idempotency-Key': `review-${reviewId}-${decision.decision}` }, body: JSON.stringify({ context, ...decision }),
  })
}
