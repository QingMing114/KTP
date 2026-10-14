import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ProfessionalReviewCard from '../features/workspace-assistant/ProfessionalReviewCard'
import type { ProfessionalReview, WorkspaceContext } from '../services/canonical/workspaceClient'

afterEach(cleanup)
const context: WorkspaceContext = { workspace_id: 'ws', revision: 5, professional_mode: true, execution_mode: 'live', farm_id: 'farm', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'scene', imagery_snapshot: null, active_workflow_id: 'flow', draft_task_ids: ['lai'] }
const review: ProfessionalReview = { review_id: 'review', workspace_id: 'ws', source_run_id: 'run', phase: 'lai', status: 'pending', title: '确认 LAI 反演参数', rationale: '依据作物和影像月份', detail: '等待确认', context, intent: { task_ids: ['lai'], rationale: '' }, search: null, candidates: [], selected_imagery_id: 'scene', proposed_scene: { lai_range: [4, 5], cab_range: [40, 80], lidfa_range: null, psoil_range: null, source: 'llm' }, workflow_id: 'flow', created_at: '' }

it('waits for a click and sends edited ranges with nulls preserved', async () => {
  const decide = vi.fn(async () => {})
  render(<ProfessionalReviewCard review={review} context={context} onDecision={decide} />)
  expect(decide).not.toHaveBeenCalled()
  expect(screen.getByText(/20 m 分辨率/)).toBeVisible()
  fireEvent.change(screen.getByLabelText('LAI最小值'), { target: { value: '0' } })
  fireEvent.change(screen.getByLabelText('LAI最大值'), { target: { value: '2' } })
  expect(decide).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '确认并执行' }))
  await waitFor(() => expect(decide).toHaveBeenCalledExactlyOnceWith('review', { decision: 'confirm', scene: { lai_range: [0, 2], cab_range: [40, 80], lidfa_range: null, psoil_range: null } }))
})

it('retains edited values after a server rejection so they can be corrected', async () => {
  const decide = vi.fn().mockRejectedValueOnce(new Error('范围在当前 LUT 中不足 10 条'))
  render(<ProfessionalReviewCard review={review} context={context} onDecision={decide} />)
  fireEvent.change(screen.getByLabelText('LAI最大值'), { target: { value: '10' } })
  fireEvent.click(screen.getByRole('button', { name: '确认并执行' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('不足 10 条')
  expect(screen.getByLabelText('LAI最大值')).toHaveValue(10)
  fireEvent.change(screen.getByLabelText('LAI最小值'), { target: { value: '11' } })
  fireEvent.click(screen.getByRole('button', { name: '确认并执行' }))
  expect(screen.getByRole('alert')).toHaveTextContent('从小到大')
  expect(decide).toHaveBeenCalledOnce()
})

it('blocks a stale proposal while still allowing cancellation', async () => {
  const decide = vi.fn(async () => {})
  render(<ProfessionalReviewCard review={review} context={{ ...context, imagery_item_id: 'other' }} onDecision={decide} />)
  expect(screen.getByRole('button', { name: '确认并执行' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  await waitFor(() => expect(decide).toHaveBeenCalledWith('review', { decision: 'cancel' }))
})

it('edits search limits before invoking search', async () => {
  const decide = vi.fn(async () => {})
  const searchReview: ProfessionalReview = { ...review, phase: 'search', title: '确认影像搜索参数', search: { start_date: '2026-01-01', end_date: '2026-10-14', max_cloud_cover: 20 } }
  render(<ProfessionalReviewCard review={searchReview} context={context} onDecision={decide} />)
  fireEvent.change(screen.getByLabelText('确认搜索开始日期'), { target: { value: '2026-06-01' } })
  fireEvent.change(screen.getByLabelText('确认搜索云量上限'), { target: { value: '5' } })
  fireEvent.click(screen.getByRole('button', { name: '确认并执行' }))
  await waitFor(() => expect(decide).toHaveBeenCalledWith('review', { decision: 'confirm', search: { start_date: '2026-06-01', end_date: '2026-10-14', max_cloud_cover: 5 } }))
})
