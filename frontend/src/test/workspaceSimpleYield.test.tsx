import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import WorkspaceAnalysisPanel from '../features/workspace-assistant/WorkspaceAnalysisPanel'
import { previewSteps } from '../features/workspace-assistant/workspaceFlow'
import type { AnalysisWorkflow } from '../services/spatialClient'
import type { WorkspaceContext } from '../services/canonical/workspaceClient'

afterEach(cleanup)
const context: WorkspaceContext = { workspace_id: 'ws', revision: 1, execution_mode: 'live', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'image', imagery_snapshot: null, active_workflow_id: 'flow', draft_task_ids: ['yield_simple'] }
const workflow: AnalysisWorkflow = {
  workflow_id: 'flow', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, status: 'blocked', detail: '请确认作物',
  requested_task_ids: ['yield_simple'], effective_task_ids: ['crop', 'yield_simple'], imagery_item_id: 'image',
  imagery_snapshot: { item_id: 'image', collection: 'sentinel-2-l2a', acquired_at: '2026-10-10T00:00:00Z', is_recommended: false },
  yield_inputs: { confirmed_crop_class_id: null, cultivar: null, sowing_date: null, field_dataset_id: null }, created_at: '', updated_at: '',
  steps: [{ step_id: 'yield_simple', depends_on: ['crop'], status: 'blocked', detail: '请确认本季作物', progress_percent: 0, result: { reason_code: 'crop_confirmation_required' } }],
}
function panel(flow: AnalysisWorkflow, save = vi.fn().mockResolvedValue(undefined)) {
  return <WorkspaceAnalysisPanel farm={{ name: '测试', locationLabel: '甘肃', areaLabel: '8 ha' }} aoiReady aoiAreaLabel="8 ha" imagerySearchEndDate="2026-10-12" stage="ready" selectedImage="image" timeline={[]} analysisError="" progress={0} detail="" elapsedSeconds={0} lastUpdateSeconds={null} delayed={false} connectionIssue={false} pixelProgress={null} reportUrl="" rasterUrl="" cropAnalysis={null} workflow={flow} executionMode="live" workspaceContext={context} draftTaskIds={['yield_simple']} assistantIsSending={false} assistantIsLaunching={false} imageryIsSearching={false} assistantError="" onFindImagery={vi.fn()} onSelectCandidate={vi.fn()} onStartAnalysis={vi.fn()} onDraftTaskIds={vi.fn()} onRetryWorkflowStep={vi.fn()} onReset={vi.fn()} onUpdateYieldInputs={save} onSendAssistantMessage={vi.fn()} onCancelAssistantMessage={vi.fn()} onRecoverTask={vi.fn()} />
}
it('previews crop and simplified yield without APSIM or LAI', () => {
  expect(previewSteps(['yield_simple']).map(step => step.step_id)).toEqual(['imagery', 'crop', 'yield_simple'])
  expect(previewSteps(['yield_simple']).at(-1)?.depends_on).toEqual(['crop'])
})
it('asks only for crop and continues the existing task without dates', async () => {
  const save = vi.fn().mockResolvedValue(undefined)
  const { container } = render(panel(workflow, save))
  expect(container.querySelector('input[type=date]')).toBeNull()
  expect(screen.queryByText('已核验地块数据集 ID')).toBeNull()
  expect(screen.queryByRole('button', { name: '重试此步骤' })).toBeNull()
  fireEvent.change(screen.getByLabelText('简化估产作物'), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: '确认并继续估产' }))
  await waitFor(() => expect(save).toHaveBeenCalledWith({ ...workflow.yield_inputs, confirmed_crop_class_id: 0 }))
})
it('shows season delay without an input form and labels dry-grain scenarios on completion', () => {
  const waiting: AnalysisWorkflow = { ...workflow, steps: [{ ...workflow.steps[0], result: { reason_code: 'season_in_progress' } }] }
  const { rerender } = render(panel(waiting))
  expect(screen.getAllByText('等待季末观测').length).toBeGreaterThan(0)
  expect(screen.queryByLabelText('简化估产作物')).toBeNull()
  rerender(panel({ ...workflow, status: 'completed', steps: [{ ...workflow.steps[0], status: 'completed', result: { estimated_yield_t_ha: 4.2, parameter_scenario_range_t_ha: [3.2, 5.5], crop_label: '玉米', season: { start: '2026-04-20', end: '2026-09-30', observations: 12 } } }] }))
  expect(screen.getByText(/粮食干重试验估计 4\.20/)).toBeInTheDocument()
  expect(screen.getByText(/3.20.*5.50/)).toHaveTextContent('参数情景范围')
  expect(screen.getByText(/参数范围不是置信区间/)).toBeInTheDocument()
})
