import type { WorkspaceContext, WorkspacePartData, WorkspaceUiCard, WorkspaceUiState } from '../../services/canonical/workspaceClient'
import type { WorkflowTaskId } from '../../services/spatialClient'
import type { WorkspaceCandidateCardItem, WorkspaceTimelineItem } from './workspaceTimeline'
import { WORKSPACE_TASKS } from './workspaceTasks'

export function sameTaskSelection(first: WorkflowTaskId[], second: WorkflowTaskId[]): boolean {
  return first.length === second.length && first.every((id) => second.includes(id))
}

export function isWorkspacePartCurrent(data: WorkspacePartData | undefined, current: WorkspaceContext): boolean {
  return !!data && data.workspace_id === current.workspace_id && data.execution_mode === current.execution_mode && data.farm_id === current.farm_id && (!data.apsim_mode || data.apsim_mode === (current.apsim_mode ?? 'field')) && data.imagery_item_id === current.imagery_item_id && JSON.stringify(data.input_aoi) === JSON.stringify(current.aoi?.geometry ?? null)
}

export function canApplyAssistantDraft(original: WorkspaceContext, current: WorkspaceContext): boolean {
  return original.workspace_id === current.workspace_id && original.execution_mode === current.execution_mode && original.farm_id === current.farm_id && JSON.stringify(original.aoi?.geometry ?? null) === JSON.stringify(current.aoi?.geometry ?? null) && (original.apsim_mode ?? 'field') === (current.apsim_mode ?? 'field') && sameTaskSelection(original.draft_task_ids, current.draft_task_ids)
}

export function buildWorkspaceUiState(context: WorkspaceContext, stage: WorkspaceUiState['stage'], farm: { name: string; locationLabel: string; areaLabel: string }, candidates: WorkspaceCandidateCardItem[], timeline: WorkspaceTimelineItem[]): WorkspaceUiState {
  const options = candidates.slice(0, 60)
  const cards: WorkspaceUiCard[] = [{ card_id: 'current-farm', kind: 'farm', title: '当前农场', state: 'current', summary: farm.name, fields: { 位置: farm.locationLabel, 边界面积: farm.areaLabel } }]
  if (context.aoi) cards.push({ card_id: 'current-aoi', kind: 'aoi', title: '分析区域已就绪', state: 'current', fields: { 面积: `${context.aoi.area_hectares} ha` } })
  if (options.length) cards.push({ card_id: 'imagery-candidates', kind: 'imagery_candidates', title: `${options.length} 景候选影像`, state: 'current', candidate_ids: options.map((item) => item.id), selected_candidate_id: context.imagery_item_id })
  if (context.imagery_item_id) {
    cards.push({ card_id: 'imagery-selection', kind: 'imagery_selected', title: '影像已选定', state: 'current', selected_candidate_id: context.imagery_item_id, fields: { 影像: context.imagery_item_id, 观测日期: context.imagery_snapshot?.acquired_at ?? options.find((item) => item.id === context.imagery_item_id)?.date ?? '' } })
    cards.push({ card_id: 'professional-tasks', kind: 'task_selection', title: '选择专业任务', state: 'current', task_ids: context.draft_task_ids, selected_candidate_id: context.imagery_item_id, fields: { 影像准备分辨率: '20 m（固定）', 共享波段: 'B02 / B03 / B04 / B07 / B08' } })
  }
  const history: WorkspaceUiCard[] = []
  for (const item of timeline) {
    if (item.kind === 'workflow') {
      history.push({ card_id: item.eventId, kind: 'workflow', title: '专业任务工作流', state: item.workflow.workflow_id === context.active_workflow_id ? 'current' : 'historical', workflow_id: item.workflow.workflow_id, summary: item.workflow.detail.slice(0, 2500), task_ids: item.workflow.requested_task_ids, fields: { 状态: item.workflow.status, 影像: item.workflow.imagery_item_id } })
    } else if (item.kind === 'agent_part' && (item.part.type === 'analysis_plan' || item.part.type === 'parameter_set')) {
      const data = item.part.data
      const current = isWorkspacePartCurrent(data, context) && (item.part.type !== 'analysis_plan' || sameTaskSelection(data?.requested_task_ids ?? [], context.draft_task_ids))
      history.push({ card_id: item.eventId, kind: item.part.type, title: item.part.type === 'analysis_plan' ? '分析过程' : '参数配置', state: current ? 'current' : 'historical', summary: data?.rationale?.slice(0, 2500), task_ids: data?.requested_task_ids, missing_inputs: data?.missing_inputs?.slice(0, 10), source_run_id: item.runId, fields: Object.fromEntries((data?.parameters ?? []).slice(0, 16).map((parameter) => [parameter.name, `${parameter.value} ${parameter.unit ?? ''}`.trim()])) })
    }
  }
  return {
    stage, cards: [...cards, ...history.slice(-(12 - cards.length))],
    imagery_candidates: options.map((item) => ({ item_id: item.id, observed_at: item.date, cloud: item.cloud, recommended: item.recommended, selected: item.id === context.imagery_item_id })),
    task_options: WORKSPACE_TASKS.map((task) => ({ task_id: task.id, label: task.title, available: task.available && (context.execution_mode === 'live' || task.id === 'lai' || task.id === 'growth'), status: task.status })),
  }
}
