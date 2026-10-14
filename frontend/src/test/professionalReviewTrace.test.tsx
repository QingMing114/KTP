import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ProfessionalReviewTrace from '../features/workspace-assistant/ProfessionalReviewTrace'
import ProfessionalReviewList from '../features/workspace-assistant/ProfessionalReviewList'
import type { ProfessionalReview, WorkspaceContext } from '../services/canonical/workspaceClient'
import type { AnalysisWorkflow } from '../services/spatialClient'
import type { WorkspaceTimelineItem } from '../features/workspace-assistant/workspaceTimeline'

afterEach(cleanup)
const context: WorkspaceContext = { workspace_id: 'ws', revision: 1, professional_mode: true, execution_mode: 'live', aoi: null, imagery_item_id: null, imagery_snapshot: null, active_workflow_id: null, draft_task_ids: ['crop', 'lai'] }
const review: ProfessionalReview = { detail: '已按参数继续反演', review_id: 'review', workspace_id: 'ws', source_run_id: 'run', phase: 'lai', status: 'confirmed', title: '确认 LAI 反演参数', rationale: '推荐时的说明', context, intent: { summary: '识别作物并反演叶面积指数', task_ids: ['crop', 'lai'], rationale: '先用同一影像识别作物，再配置 LAI。' }, search: null, candidates: [], selected_imagery_id: 'recommended', proposed_scene: { source: 'llm', lai_range: [4, 5], cab_range: null, lidfa_range: null, psoil_range: null, reasoning: '依据影像月份和上游作物识别设置范围。', crop_type: '玉米', month: 7, context: { acquired_at: '2026-07-10T00:00:00Z' } }, workflow_id: 'flow', created_at: '2026-10-14T13:45:00Z', confirmed_parameters: { scene: { lai_range: [0, 2], cab_range: null, lidfa_range: null, psoil_range: null } } }
const workflow: AnalysisWorkflow = { workflow_id: 'flow', run_id: 'run', status: 'completed', detail: '已完成', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'chosen', imagery_snapshot: { item_id: 'chosen', collection: 'sentinel-2-l2a', acquired_at: '2026-07-10T00:00:00Z', is_recommended: false }, requested_task_ids: ['crop', 'lai'], effective_task_ids: ['crop', 'lai'], parameters: { target_resolution_m: 20, reflectance_bands: ['B02', 'B03'], parameter_source: 'algorithm_fixed' }, steps: [{ step_id: 'imagery', status: 'completed', progress_percent: 100, depends_on: [], detail: '波段准备完成', result: {} }, { step_id: 'crop', status: 'completed', progress_percent: 100, depends_on: ['imagery'], detail: '识别完成', result: {} }, { step_id: 'lai', status: 'completed', progress_percent: 100, depends_on: ['imagery'], detail: '反演完成', result: { constraint_application: { status: 'applied', effective: { lai_range: [0, 2] }, matched_rows: 26, used_rows: 26 } } }], yield_inputs: { confirmed_crop_class_id: null, field_dataset_id: null, sowing_date: null, cultivar: null }, created_at: '', updated_at: '' }

it('keeps recommended, user confirmed and actually applied ranges distinct', () => {
  const open = vi.fn()
  render(<ProfessionalReviewTrace review={review} workflow={workflow} onOpenWorkflow={open} />)
  const row = within(screen.getByRole('table', { name: 'LAI 参数对比' })).getAllByRole('row')[1]
  expect(within(row).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['LAI', '4–5 m²/m²', '0–2 m²/m²', '0–2 m²/m²'])
  expect(screen.getByText('依据影像月份和上游作物识别设置范围。')).toBeVisible()
  expect(screen.getByText('匹配参数组合：26 条')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '查看本轮任务进度与结果' }))
  expect(open).toHaveBeenCalledExactlyOnceWith('flow')
})

it('does not present confirmation as application when no inversion results exist', () => {
  render(<ProfessionalReviewTrace review={review} />)
  const cells = within(screen.getByRole('table', { name: 'LAI 参数对比' })).getAllByRole('row')[1].textContent
  expect(cells).toContain('0–2 m²/m²尚未记录')
  expect(screen.queryByText('实际使用参数组合：26 条')).not.toBeInTheDocument()
})

it('compares the original search proposal with the user edited limits', () => {
  render(<ProfessionalReviewTrace review={{ ...review, phase: 'search', search: { start_date: '2026-01-01', end_date: '2026-10-14', max_cloud_cover: 20 }, confirmed_parameters: { search: { start_date: '2026-06-01', end_date: '2026-09-30', max_cloud_cover: 5 } } }} />)
  const table = screen.getByRole('table', { name: '影像搜索条件' })
  expect(table).toHaveTextContent('2026-01-012026-06-01')
  expect(table).toHaveTextContent('20%5%')
})

it('records an alternative image choice and actual professional task dependencies', () => {
  const candidates = [{ ...workflow.imagery_snapshot, item_id: 'recommended', is_recommended: true, cloud_cover: 0, coverage_percent: 100, recommendation_reason: '候选影像中云量最低。' }, { ...workflow.imagery_snapshot, item_id: 'chosen', cloud_cover: 3, coverage_percent: 98 }]
  render(<ProfessionalReviewTrace review={{ ...review, phase: 'workflow', candidates, confirmed_parameters: { imagery_item_id: 'chosen', task_ids: ['crop', 'lai'] } }} workflow={workflow} />)
  expect(screen.getByText('候选推荐说明（系统）：候选影像中云量最低。')).toBeVisible()
  const table = screen.getByRole('table', { name: '候选影像对比' })
  expect(table).toHaveTextContent('0%100.0%系统推荐')
  expect(table).toHaveTextContent('3%98.0%用户确认')
  expect(screen.getAllByText('依赖：影像准备')).toHaveLength(2)
  expect(screen.getByText('分辨率：20 m')).toBeVisible()
})

it('labels cancelled and missing records without inventing an explanation or confirmation', () => {
  render(<ProfessionalReviewTrace review={{ ...review, status: 'cancelled', rationale: '', proposed_scene: null }} />)
  expect(screen.getByText('该轮未保存参数配置说明。')).toBeVisible()
  expect(screen.getAllByText('未确认')).toHaveLength(4)
  expect(screen.queryByText('0–2 m²/m²')).not.toBeInTheDocument()
})

it('keeps one run separate and associates its phases with the correct workflow', () => {
  const timelines: WorkspaceTimelineItem[] = [{ eventId: 'user', kind: 'agent_user_message', message: '本轮真实需求', timestamp: '' }, { eventId: 'reply', kind: 'agent_message', message: '任务配置', runId: 'run', submissionId: '', status: 'completed', timestamp: '' }]
  const records: ProfessionalReview[] = [{ ...review, review_id: 'search', phase: 'search' }, { ...review, review_id: 'old', source_run_id: 'old-run', workflow_id: 'other-flow' }, { ...review, review_id: 'workflow', phase: 'workflow' }, { ...review, review_id: 'unloaded', title: '未同步的反演', workflow_id: 'unloaded-flow' }]
  const { container } = render(<ProfessionalReviewList runId="run" reviews={records} context={context} timeline={timelines} busy={false} onDecision={vi.fn()} workflows={new Map([['flow', workflow]])} />)
  fireEvent.click(screen.getByRole('button', { name: '本轮分析记录（3）' }))
  expect(container.querySelectorAll('[data-history-run="run"]')).toHaveLength(1)
  expect(container.querySelectorAll('[data-history-run="old-run"]')).toHaveLength(0)
  expect(screen.getAllByText('需求：本轮真实需求')).toHaveLength(1)
  const oldSummary = screen.getByText('未同步的反演 · 已确认')
  oldSummary.closest('details')!.open = true
  expect(within(oldSummary.closest('details')!).queryByText('匹配参数组合：26 条')).not.toBeInTheDocument()
})
