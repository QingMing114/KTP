import { useState } from 'react'
import WorkspaceAnalysisPanel from '../features/workspace-assistant/WorkspaceAnalysisPanel'
import type { WorkspacePanelProps, AnalysisViewRequest } from '../features/workspace-assistant/workspacePanelTypes'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import WorkspaceAssistantPanel from '../features/workspace-assistant/WorkspaceAssistantPanel'
import type { AnalysisWorkflow } from '../services/spatialClient'
import type { WorkspaceContext } from '../services/canonical/workspaceClient'
import type { WorkspaceTimelineItem } from '../features/workspace-assistant/workspaceTimeline'

afterEach(cleanup)
const context: WorkspaceContext = { workspace_id: 'ws', revision: 2, execution_mode: 'live', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'image', imagery_snapshot: null, active_workflow_id: 'task-new', draft_task_ids: ['crop'] }
function flow(id: string, task: 'crop' | 'lai', status: 'running' | 'completed' = 'completed'): AnalysisWorkflow {
  return { workflow_id: id, run_id: 'run-'+id, aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'image', imagery_snapshot: { item_id: 'image', acquired_at: '2026-09-10T00:00:00Z', collection: 'sentinel-2-l2a', is_recommended: true }, status, detail: status === 'running' ? '正在读取影像' : '所选影像分析任务已完成', requested_task_ids: [task], effective_task_ids: [task], steps: [{ step_id: 'imagery', depends_on: [], status, progress_percent: status === 'running' ? 35 : 100, detail: '共享影像', result: {} }], yield_inputs: { confirmed_crop_class_id: null, field_dataset_id: null, sowing_date: null, cultivar: null }, created_at: '', updated_at: '' }
}
function message(runId: string, text = '已启动任务。当前分析卡片将持续显示进度和结果。'): WorkspaceTimelineItem {
  return { eventId: runId, runId, kind: 'agent_message', message: text, submissionId: 'submission-'+runId, status: 'completed', timestamp: '' }
}
function panel(workflow: AnalysisWorkflow | null, timeline: WorkspaceTimelineItem[], error = '', recover = vi.fn().mockResolvedValue(undefined)) {
  return <TestPanels farm={{ name: '测试', locationLabel: '甘肃', areaLabel: '8 ha' }} aoiReady aoiAreaLabel="8 ha" imagerySearchEndDate="2026-10-12" stage="ready" selectedImage="image" timeline={timeline} analysisError="" progress={0} detail="" elapsedSeconds={0} lastUpdateSeconds={null} delayed={false} connectionIssue={false} pixelProgress={null} reportUrl="" rasterUrl="" cropAnalysis={null} workflow={workflow} executionMode="live" workspaceContext={context} draftTaskIds={['crop']} assistantIsSending={false} assistantIsLaunching={!!error} imageryIsSearching={false} assistantError={error} onFindImagery={vi.fn()} onSelectCandidate={vi.fn()} onStartAnalysis={vi.fn()} onDraftTaskIds={vi.fn()} onRetryWorkflowStep={vi.fn()} onReset={vi.fn()} onUpdateYieldInputs={vi.fn()} onSendAssistantMessage={vi.fn()} onCancelAssistantMessage={vi.fn()} onRecoverTask={recover} />
}
function TestPanels(props: WorkspacePanelProps) {
  const [view, setView] = useState<AnalysisViewRequest | null>(null)
  return <><WorkspaceAnalysisPanel {...props} viewRequest={view} /><WorkspaceAssistantPanel {...props} onOpenAnalysis={(workflowId) => setView((previous) => ({ workflowId, requestId: (previous?.requestId ?? 0) + 1 }))} /></>
}
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
