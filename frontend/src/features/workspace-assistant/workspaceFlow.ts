import type { AnalysisWorkflow, WorkflowTaskId } from '../../services/spatialClient'
import type { CanonicalAssistantPart, WorkspaceContext } from '../../services/canonical/workspaceClient'
import type { WorkspaceTimelineItem } from './workspaceTimeline'
import { isWorkspacePartCurrent, sameTaskSelection } from './workspaceUiContext'

export type WorkspacePhase = 'draw' | 'search' | 'choose' | 'configure' | 'ready' | 'launching' | 'running' | 'result'

export function simpleYieldBlockedLabel(reason: unknown): string {
  if (reason === 'crop_confirmation_required') return '待确认作物'
  if (reason === 'season_in_progress') return '等待季末观测'
  if (typeof reason === 'string' && reason.startsWith('weather_')) return '气象数据未就绪'
  return '时序数据不足'
}

export function workspacePhase(context: WorkspaceContext, candidates: number, workflow: AnalysisWorkflow | null, stage: string, launching: boolean): WorkspacePhase {
  if (launching) return 'launching'
  if (workflow) return ['planned', 'running'].includes(workflow.status) ? 'running' : 'result'
  if (stage === 'running' || stage === 'done') return stage === 'running' ? 'running' : 'result'
  if (!context.aoi) return 'draw'
  if (!context.imagery_item_id) return candidates ? 'choose' : 'search'
  return context.draft_task_ids.length ? 'ready' : 'configure'
}

const LABELS: Record<string, string> = { imagery: '准备共享影像', crop: '农作物识别', lai: 'LAI 反演', growth: '作物长势评估', potential: '遥感冠层指数', yield_simple: '自动简化估产（试验）', yield: 'APSIM 产量估计' }

export function workflowTitle(taskIds: WorkflowTaskId[]): string {
  return taskIds.map((id) => LABELS[id]).join('、') || '分析任务'
}

export function workflowStatusLabel(workflow: AnalysisWorkflow): string {
  const simple = workflow.steps.find((step) => step.step_id === 'yield_simple' && step.status === 'blocked')
  if (workflow.status === 'blocked' && simple) return simpleYieldBlockedLabel(simple.result.reason_code)
  return { planned: '等待执行', running: '执行中', completed: '已完成', blocked: '待补充输入', failed: '执行失败', cancelled: '已取消' }[workflow.status]
}

/** Associate tasks by canonical references, including restored and late-loaded runs. */
export function conversationWorkflowLinks(timeline: WorkspaceTimelineItem[], current: AnalysisWorkflow | null) {
  const workflows = new Map<string, AnalysisWorkflow>()
  for (const item of timeline) if (item.kind === 'workflow') workflows.set(item.workflow.workflow_id, item.workflow)
  if (current) workflows.set(current.workflow_id, current)
  const byRun = new Map<string, string[]>()
  for (const item of timeline) {
    if (item.kind !== 'agent_part' || !item.runId || item.part.type !== 'workflow_reference' || !item.part.data?.workflow_id) continue
    const ids = byRun.get(item.runId) ?? []
    if (!ids.includes(item.part.data.workflow_id)) ids.push(item.part.data.workflow_id)
    byRun.set(item.runId, ids)
  }
  for (const flow of workflows.values()) {
    if (!flow.run_id) continue
    const ids = byRun.get(flow.run_id) ?? []
    if (!ids.includes(flow.workflow_id)) ids.push(flow.workflow_id)
    byRun.set(flow.run_id, ids)
  }
  const attached = new Set(timeline.flatMap((item) => item.kind === 'agent_message' && item.runId ? byRun.get(item.runId) ?? [] : []))
  return { workflows, byRun, unattached: [...workflows.values()].filter((flow) => !attached.has(flow.workflow_id)) }
}

/** Preview the same dependencies as the server; execution uses its verified plan. */
export function previewSteps(requested: WorkflowTaskId[]) {
  const effective = new Set(requested)
  if (effective.has('growth') || effective.has('potential') || effective.has('yield')) effective.add('lai')
  if (effective.has('potential') || effective.has('yield') || effective.has('yield_simple')) effective.add('crop')
  return ['imagery', 'crop', 'lai', 'growth', 'potential', 'yield_simple', 'yield'].filter((id) => id === 'imagery' || effective.has(id as WorkflowTaskId)).map((step_id) => ({
    step_id, label: LABELS[step_id], depends_on: step_id === 'imagery' ? [] : step_id === 'growth' ? ['lai'] : step_id === 'yield_simple' ? ['crop'] : step_id === 'potential' || step_id === 'yield' ? ['crop', 'lai'] : ['imagery'],
  }))
}

export function currentAnalysisDetails(context: WorkspaceContext, timeline: WorkspaceTimelineItem[], areaLabel: string, date: string): CanonicalAssistantPart[] {
  const latestPlan = [...timeline].reverse().find((item) => item.kind === 'agent_part' && item.part.type === 'analysis_plan' && isWorkspacePartCurrent(item.part.data, context) && sameTaskSelection(item.part.data?.requested_task_ids ?? [], context.draft_task_ids))
  return [
    { type: 'analysis_plan', data: { rationale: latestPlan?.kind === 'agent_part' ? latestPlan.part.data?.rationale : '所有任务共用当前选区和影像，所需前置任务会自动加入。', steps: context.draft_task_ids.length ? previewSteps(context.draft_task_ids) : [] } },
    { type: 'parameter_set', data: { state: 'draft', parameters: [
      { name: '区域面积', value: areaLabel, source: 'user', editable: false },
      { name: '观测日期', value: date || '待选择', source: 'imagery', editable: false },
      { name: '影像', value: context.imagery_item_id || '待选择', source: 'user', editable: false },
      { name: '影像准备分辨率', value: 20, unit: 'm', source: 'algorithm_fixed', editable: false },
      { name: '共享反射率波段', value: 'B02 / B03 / B04 / B07 / B08', source: 'algorithm_fixed', editable: false },
    ] } },
  ]
}
