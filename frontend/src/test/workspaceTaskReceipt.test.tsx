import { useState } from 'react'
import WorkspaceAnalysisPanel from '../features/workspace-assistant/WorkspaceAnalysisPanel'
import type { WorkspacePanelProps, AnalysisViewRequest } from '../features/workspace-assistant/workspacePanelTypes'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import WorkspaceAssistantPanel from '../features/workspace-assistant/WorkspaceAssistantPanel'
import type { AnalysisWorkflow } from '../services/spatialClient'
import type { ProfessionalReview, WorkspaceContext } from '../services/canonical/workspaceClient'
import type { WorkspaceTimelineItem } from '../features/workspace-assistant/workspaceTimeline'

afterEach(() => { cleanup(); localStorage.clear() })
const context: WorkspaceContext = { workspace_id: 'ws', revision: 2, execution_mode: 'live', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'image', imagery_snapshot: null, active_workflow_id: 'task-new', draft_task_ids: ['crop'] }
function flow(id: string, task: 'crop' | 'lai', status: 'running' | 'completed' = 'completed'): AnalysisWorkflow {
  return { workflow_id: id, run_id: 'run-'+id, aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'image', imagery_snapshot: { item_id: 'image', acquired_at: '2026-09-10T00:00:00Z', collection: 'sentinel-2-l2a', is_recommended: true }, status, detail: status === 'running' ? '正在读取影像' : '所选影像分析任务已完成', requested_task_ids: [task], effective_task_ids: [task], steps: [{ step_id: 'imagery', depends_on: [], status, progress_percent: status === 'running' ? 35 : 100, detail: '共享影像', result: {} }], yield_inputs: { confirmed_crop_class_id: null, field_dataset_id: null, sowing_date: null, cultivar: null }, created_at: '', updated_at: '' }
}
function message(runId: string, text = '已启动任务。当前分析卡片将持续显示进度和结果。'): WorkspaceTimelineItem {
  return { eventId: runId, runId, kind: 'agent_message', message: text, submissionId: 'submission-'+runId, status: 'completed', timestamp: '' }
}
function panel(workflow: AnalysisWorkflow | null, timeline: WorkspaceTimelineItem[], error = '', recover = vi.fn().mockResolvedValue(undefined), reviews: ProfessionalReview[] = []) {
  return <TestPanels professionalReviews={reviews} onProfessionalDecision={vi.fn().mockResolvedValue(undefined)} farm={{ name: '测试', locationLabel: '甘肃', areaLabel: '8 ha' }} aoiReady aoiAreaLabel="8 ha" imagerySearchEndDate="2026-10-12" stage="ready" selectedImage="image" timeline={timeline} analysisError="" progress={0} detail="" elapsedSeconds={0} lastUpdateSeconds={null} delayed={false} connectionIssue={false} pixelProgress={null} reportUrl="" rasterUrl="" cropAnalysis={null} workflow={workflow} executionMode="live" workspaceContext={context} draftTaskIds={['crop']} assistantIsSending={false} assistantIsLaunching={!!error} imageryIsSearching={false} assistantError={error} onFindImagery={vi.fn()} onSelectCandidate={vi.fn()} onStartAnalysis={vi.fn()} onDraftTaskIds={vi.fn()} onRetryWorkflowStep={vi.fn()} onReset={vi.fn()} onUpdateYieldInputs={vi.fn()} onSendAssistantMessage={vi.fn()} onCancelAssistantMessage={vi.fn()} onRecoverTask={recover} />
}
function TestPanels(props: WorkspacePanelProps) {
  const [view, setView] = useState<AnalysisViewRequest | null>(null)
  return <><WorkspaceAnalysisPanel {...props} viewRequest={view} /><WorkspaceAssistantPanel {...props} onOpenAnalysis={(workflowId) => setView((previous) => ({ workflowId, requestId: (previous?.requestId ?? 0) + 1 }))} /></>
}
it('opens the automatic execution record on completion and folds it on the next user turn', () => {
  const task = flow('auto-process-task', 'lai', 'running')
  const timeline: WorkspaceTimelineItem[] = [message(task.run_id!), { eventId: 'auto-process-ref', kind: 'agent_part', runId: task.run_id!, timestamp: '', part: { type: 'workflow_reference', data: { workflow_id: task.workflow_id, auto_execute: true } } }]
  const { rerender } = render(panel(task, timeline))
  const record = screen.getByRole('button', { name: '本轮分析记录' })
  expect(record).toHaveAttribute('aria-expanded', 'false')
  rerender(panel({ ...task, status: 'completed' }, timeline))
  expect(record).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByText('任务执行过程')).toBeVisible()
  const next: WorkspaceTimelineItem = { kind: 'agent_user_message', eventId: 'after-auto-process', message: '下一个任务', timestamp: '' }
  rerender(panel({ ...task, status: 'completed' }, [...timeline, next]))
  expect(record).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getByText('任务执行过程')).not.toBeVisible()
})
it('directly opens all completed professional phase details in the current round', () => {
  const task = flow('professional-process-task', 'lai')
  const records = (['search', 'workflow', 'lai'] as const).map((phase): ProfessionalReview => ({ review_id: `process-${phase}`, workspace_id: 'ws', source_run_id: task.run_id!, phase, status: 'confirmed', title: `已完成阶段 ${phase}`, rationale: '保存的阶段依据', detail: '确认完成', context, intent: { task_ids: ['lai'], rationale: '原始任务依据' }, search: null, candidates: [], selected_imagery_id: 'image', proposed_scene: null, workflow_id: task.workflow_id, created_at: '' }))
  render(panel(task, [message(task.run_id!)], '', undefined, records))
  expect(screen.getByRole('button', { name: '本轮分析记录（3）' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('table', { name: '影像搜索条件' })).toBeVisible()
  expect(screen.getByRole('table', { name: 'LAI 参数对比' })).toBeVisible()
})
it('clears the assistant list without clearing the analysis panel or losing recoverable history', () => {
  const task = flow('clear-history-task', 'lai')
  const timeline: WorkspaceTimelineItem[] = [{ kind: 'agent_user_message', eventId: 'clear-user', message: '历史请求', timestamp: '' }, message(task.run_id!, '历史回答')]
  const { rerender } = render(panel(task, timeline))
  fireEvent.click(screen.getByRole('button', { name: '清空列表' }))
  expect(screen.getByText('历史请求')).not.toBeVisible()
  expect(screen.getByText('历史回答')).not.toBeVisible()
  expect(screen.getByText('列表已清空，聊天记录和任务结果仍保留。')).toBeVisible()
  expect(screen.getByRole('heading', { name: '任务进度与结果' })).toBeVisible()
  expect(screen.getByRole('button', { name: '清空列表' })).toBeDisabled()
  rerender(panel(task, [...timeline, message('fresh', '新的回复')]))
  expect(screen.getByText('新的回复')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '恢复历史' }))
  expect(screen.getByText('历史回答')).toBeVisible()
  expect(screen.queryByRole('button', { name: '恢复历史' })).not.toBeInTheDocument()
})
it('attaches independent histories to their own replies and excludes other conversations', () => {
  const records = ['first', 'second', 'foreign'].flatMap((runId) => (['search', 'workflow', 'lai'] as const).map((phase): ProfessionalReview => ({
    review_id: `${runId}-${phase}`, workspace_id: 'ws', source_run_id: runId, phase, status: 'confirmed',
    title: `${runId} ${phase}`, rationale: `${runId} 的依据`, detail: '已确认', context,
    intent: { task_ids: ['lai'], rationale: `${runId} 的计划` }, search: null, candidates: [],
    selected_imagery_id: 'image', proposed_scene: null, workflow_id: null, created_at: '',
  })))
  const timeline: WorkspaceTimelineItem[] = [
    { kind: 'agent_user_message', eventId: 'u1', message: '第一轮需求', timestamp: '' }, message('first'),
    { kind: 'agent_user_message', eventId: 'u2', message: '第二轮需求', timestamp: '' }, message('second'),
  ]
  const { container, rerender } = render(panel(null, timeline, '', undefined, records))
  const first = container.querySelector('[data-assistant-run="first"]') as HTMLElement
  const second = container.querySelector('[data-assistant-run="second"]') as HTMLElement
  const firstHistory = within(first).getByRole('button', { name: '本轮分析记录（3）' })
  const secondHistory = within(second).getByRole('button', { name: '本轮分析记录（3）' })
  expect(screen.getAllByRole('button', { name: '本轮分析记录（3）' })).toHaveLength(2)
  expect(screen.queryByText('foreign lai · 已确认')).not.toBeInTheDocument()
  expect(within(first).queryByText('second lai · 已确认')).not.toBeInTheDocument()
  fireEvent.click(firstHistory)
  expect(within(first).getByText('first lai · 已确认')).toBeVisible()
  expect(secondHistory).toHaveAttribute('aria-expanded', 'false')
  expect(within(second).getByText('second lai · 已确认')).not.toBeVisible()
  fireEvent.click(secondHistory)
  expect(firstHistory).toHaveAttribute('aria-expanded', 'true')
  const next: WorkspaceTimelineItem = { kind: 'agent_user_message', eventId: 'u3', message: '第三轮需求', timestamp: '' }
  rerender(panel(null, [...timeline, next], '', undefined, records))
  expect(firstHistory).toHaveAttribute('aria-expanded', 'false')
  expect(secondHistory).toHaveAttribute('aria-expanded', 'false')
  expect(container.querySelector('[data-professional-run="first"]')).toBe(first.querySelector('[data-professional-run]'))
})
it('announces automatic completion only after the workflow finishes and can open the result', () => {
  const task = flow('task-new', 'crop', 'running')
  const timeline: WorkspaceTimelineItem[] = [message(task.run_id!), { eventId: 'auto-ref', kind: 'agent_part', runId: task.run_id!, timestamp: '', part: { type: 'workflow_reference', data: { workflow_id: task.workflow_id, auto_execute: true } } }]
  const { rerender } = render(panel(task, timeline))
  expect(screen.queryByText(/自动执行已完成/)).not.toBeInTheDocument()
  rerender(panel({ ...task, status: 'completed' }, timeline))
  expect(screen.getByRole('status', { name: '自动执行结果' })).toHaveTextContent('自动执行已完成：农作物识别')
  fireEvent.click(screen.getByRole('button', { name: '查看分析结果与报告' }))
  expect(screen.getByRole('heading', { name: '任务进度与结果' })).toBeVisible()
  rerender(panel({ ...task, status: 'completed' }, timeline))
  expect(screen.getAllByText(/自动执行已完成/)).toHaveLength(1)
  rerender(panel({ ...task, status: 'blocked', detail: '请补充核验资料' }, timeline))
  expect(screen.getByRole('status', { name: '自动执行结果' })).toHaveTextContent('自动执行需要补充信息')
  expect(screen.queryByText(/自动执行已完成/)).not.toBeInTheDocument()
})
it('attaches the live task to its launch reply and expands it there without duplicating the configuration', () => {
  const task = flow('task-new', 'crop', 'running')
  const { container, rerender } = render(panel(task, [message(task.run_id!)]))
  const reply = container.querySelector('[data-assistant-run="run-task-new"]') as HTMLElement
  const receipt = within(reply).getByRole('region', { name: '任务卡片：农作物识别' })
  expect(within(receipt).getByText('执行中')).toBeVisible()
  expect(within(reply).getByText(/左侧分析面板/)).toBeVisible()
  expect(screen.getByRole('region', { name: '当前分析面板' })).toContainElement(screen.getByRole('heading', { name: '任务进度与结果' }))
  fireEvent.click(within(receipt).getByRole('button', { name: '查看农作物识别的进度与结果' }))
  expect(receipt).not.toContainElement(screen.getByRole('heading', { name: '任务进度与结果' }))
  expect(screen.getByRole('region', { name: '当前分析面板' })).not.toContainElement(receipt)
  rerender(panel({ ...task, status: 'completed' }, [message(task.run_id!)]))
  expect(within(receipt).getByText('已完成')).toBeVisible()
  expect(container.querySelectorAll('[data-workflow-id]')).toHaveLength(1)
})
it('keeps previous task results on their own replies and leaves a later status reply free of duplicate cards', () => {
  const old = flow('task-old', 'lai'), current = flow('task-new', 'crop')
  const timeline: WorkspaceTimelineItem[] = [message(old.run_id!), { eventId: 'old-task', kind: 'workflow', workflow: old, timestamp: '' }, message(current.run_id!), message('status-run', '最新状态说明')]
  const { container } = render(panel(current, timeline))
  const oldReply = container.querySelector('[data-assistant-run="run-task-old"]') as HTMLElement
  fireEvent.click(within(oldReply).getByRole('button', { name: '查看LAI 反演的进度与结果' }))
  expect(within(screen.getByRole('region', { name: '当前分析面板' })).getByRole('heading', { name: '任务进度与结果' })).toBeVisible()
  expect(within(oldReply).getByText(/历史任务/)).toBeVisible()
  expect(screen.queryByRole('button', { name: '基于当前 AOI 再次分析' })).toBeNull()
  const currentReply = container.querySelector('[data-assistant-run="run-task-new"]') as HTMLElement
  fireEvent.click(within(currentReply).getByRole('button', { name: '查看农作物识别的进度与结果' }))
  expect(screen.getAllByRole('heading', { name: '任务进度与结果' })).toHaveLength(1)
  expect(currentReply).not.toContainElement(screen.getByRole('heading', { name: '任务进度与结果' }))
  expect(container.querySelector('[data-assistant-run="status-run"]')?.querySelector('[data-workflow-id]')).toBeNull()
})
it('shows one recoverable receipt before task retrieval succeeds, and updates that receipt in place', () => {
  const recover = vi.fn().mockResolvedValue(undefined)
  const timeline: WorkspaceTimelineItem[] = [message('launch-run'), { eventId: 'ref', kind: 'agent_part', runId: 'launch-run', timestamp: '', part: { type: 'workflow_reference', data: { workflow_id: 'task-new' } } }, { eventId: 'plan', kind: 'agent_part', runId: 'launch-run', timestamp: '', part: { type: 'analysis_plan', data: { requested_task_ids: ['crop'] } } }]
  const { container, rerender } = render(panel(null, timeline, '同步中断', recover))
  const receipt = container.querySelector('[data-workflow-id="task-new"]')
  expect(screen.getAllByRole('button', { name: '恢复任务状态' })).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: '恢复任务状态' }))
  expect(recover).toHaveBeenCalledOnce()
  rerender(panel({ ...flow('task-new', 'crop'), run_id: 'launch-run' }, timeline))
  expect(container.querySelector('[data-workflow-id="task-new"]')).toBe(receipt)
  expect(screen.getByRole('button', { name: '查看农作物识别的进度与结果' })).toBeVisible()
})
it('keeps the independent task details visible while new chat messages arrive', () => {
  const task = flow('task-new', 'crop')
  const timeline = [message(task.run_id!)]
  const { rerender } = render(panel(task, timeline))
  fireEvent.click(screen.getByRole('button', { name: '查看农作物识别的进度与结果' }))
  rerender(panel(task, [...timeline, message('later-run', '新的助手说明')]))
  expect(screen.getByRole('heading', { name: '任务进度与结果' })).toBeVisible()
  rerender(panel(task, [...timeline, message('later-run', '新的助手说明'), { kind: 'agent_user_message', eventId: 'next-user', message: '继续询问', timestamp: '' }]))
  expect(screen.getByRole('heading', { name: '任务进度与结果' })).toBeVisible()
  expect(screen.getByText('继续询问')).toBeVisible()
})
