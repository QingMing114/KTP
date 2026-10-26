import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ProfessionalReviewCard from '../features/workspace-assistant/ProfessionalReviewCard'
import type { ProfessionalReview, WorkspaceContext } from '../services/canonical/workspaceClient'

afterEach(cleanup)

const context: WorkspaceContext = {
  workspace_id: 'ws', revision: 6, professional_mode: true, execution_mode: 'live', farm_id: 'farm-zouping',
  aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'scene', imagery_snapshot: null,
  active_workflow_id: 'flow', draft_task_ids: ['crop', 'lai'],
}

const review: ProfessionalReview = {
  review_id: 'review-crop', workspace_id: 'ws', source_run_id: 'run', phase: 'crop', status: 'pending',
  title: '确认农作物识别结果', rationale: '7月山东邹平，冬小麦已收、夏玉米苗期。', detail: '等待确认',
  context, intent: { task_ids: ['crop', 'lai'], rationale: '' }, search: null, candidates: [],
  selected_imagery_id: 'scene', proposed_scene: null, workflow_id: 'flow', created_at: '',
  proposed_crop: {
    final_class_id: 0, final_name_zh: '玉米', source: 'llm', confidence: 'medium',
    rationale: '7月山东邹平，冬小麦已收、夏玉米苗期；模型最高为玉米29%。',
    phenology: '夏玉米苗期', observed_at: '2026-07-12T03:20:00Z',
    location: { label: '山东 · 邹平' }, fallback_reason: null,
  },
}

it('prefills the judged crop and lets the user change it before execution', async () => {
  const decide = vi.fn(async () => {})
  render(<ProfessionalReviewCard review={review} context={context} onDecision={decide} />)
  expect(screen.getByText(/^判定结果：/)).toBeVisible()
  expect(screen.getByText(/大模型结合地点与时序判定/)).toBeVisible()
  expect((screen.getByLabelText('确认地块作物类别') as HTMLSelectElement).value).toBe('0')
  fireEvent.change(screen.getByLabelText('确认地块作物类别'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: '确认并执行' }))
  await waitFor(() => expect(decide).toHaveBeenCalledExactlyOnceWith('review-crop', { decision: 'confirm', crop_class_id: 3 }))
})

it('shows the fallback reason when the model could not judge', () => {
  const fallback: ProfessionalReview = {
    ...review,
    proposed_crop: {
      ...review.proposed_crop!, source: 'model_fallback', final_name_zh: '春小麦', final_class_id: 3,
      fallback_reason: '大模型判定失败：excluded_classes.0.reason Field required',
      fallback_detail: { stage: 'llm_call', error_type: 'AgentLLMError', category: 'schema_mismatch',
                         status_code: 200, message: 'excluded_classes.0.reason Field required' },
    },
  }
  render(<ProfessionalReviewCard review={fallback} context={context} onDecision={vi.fn(async () => {})} />)
  expect(screen.getByText(/大模型不可用，回退模型最高分/)).toBeVisible()
  expect(screen.getByText(/回退原因：大模型判定失败/)).toBeVisible()
  expect(screen.getByText(/错误信息：excluded_classes.0.reason Field required/)).toBeVisible()
  expect((screen.getByLabelText('确认地块作物类别') as HTMLSelectElement).value).toBe('3')
})

it('disables confirmation when the professional context moved on', () => {
  render(<ProfessionalReviewCard review={review} context={{ ...context, professional_mode: false }} onDecision={vi.fn(async () => {})} />)
  expect(screen.getByRole('button', { name: '确认并执行' })).toBeDisabled()
  expect(screen.getByText(/请开启专业模式/)).toBeVisible()
})
