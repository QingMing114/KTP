import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ProfessionalReviewList from '../features/workspace-assistant/ProfessionalReviewList'
import type { ProfessionalReview, WorkspaceContext } from '../services/canonical/workspaceClient'
import type { WorkspaceTimelineItem } from '../features/workspace-assistant/workspaceTimeline'

afterEach(cleanup)
const context: WorkspaceContext = { workspace_id: 'ws', revision: 5, professional_mode: true, execution_mode: 'live', farm_id: 'farm', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'scene', imagery_snapshot: null, active_workflow_id: 'flow', draft_task_ids: ['lai'] }
const pending: ProfessionalReview = { review_id: 'pending', workspace_id: 'ws', source_run_id: 'run', phase: 'lai', status: 'pending', title: '确认 LAI 反演参数', rationale: '', detail: '等待确认', context, intent: { task_ids: ['lai'], rationale: '' }, search: null, candidates: [], selected_imagery_id: 'scene', proposed_scene: { lai_range: [4, 5], cab_range: null, lidfa_range: null, psoil_range: null }, workflow_id: 'flow', created_at: '2026-10-14T13:45:00Z' }
const timeline: WorkspaceTimelineItem[] = [{ kind: 'agent_user_message', eventId: 'user', message: '反演LAI', timestamp: '' }, { kind: 'agent_message', eventId: 'reply', runId: 'run', submissionId: 'submission', message: '等待确认', status: 'completed', timestamp: '' }]
const completed = Array.from({ length: 9 }, (_, i): ProfessionalReview => ({ ...pending, review_id: `confirmed-${i}`, status: 'confirmed', title: `历史参数 ${i}`, detail: '已按参数执行', confirmed_parameters: { scene: { lai_range: [0, 2], cab_range: null, lidfa_range: null, psoil_range: null } } }))
const decide = vi.fn().mockResolvedValue(undefined)
function list(reviews = [...completed, pending], items = timeline, workspace = context) {
  return <ProfessionalReviewList runId="run" reviews={reviews} context={workspace} timeline={items} busy={false} onDecision={decide} />
}

it('replaces completed cards with one history entry while keeping the current confirmation visible', () => {
  render(list())
  expect(screen.getByRole('button', { name: '本轮分析记录（9）' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getByRole('button', { name: '确认并执行' })).toBeVisible()
  expect(screen.getByText('历史参数 0 · 已确认')).not.toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '本轮分析记录（9）' }))
  const summary = screen.getByText('历史参数 0 · 已确认')
  expect(summary).toBeVisible()
  fireEvent.click(summary)
  // jsdom does not implement the browser's native summary toggle.
  summary.closest('details')!.open = true
  expect(within(summary.closest('details')!).getByRole('table', { name: 'LAI 参数对比' })).toHaveTextContent('0–2 m²/m²')
})

it('folds stale pending editors into history without permitting stale execution', () => {
  render(list([pending], timeline, { ...context, imagery_item_id: 'other' }))
  expect(screen.queryByRole('button', { name: '确认并执行' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '本轮分析记录（1）' }))
  const summary = screen.getByText('确认 LAI 反演参数 · 已失效')
  expect(summary).toBeVisible()
  expect(screen.getByLabelText('LAI最小值')).not.toBeVisible()
  summary.closest('details')!.open = true
  expect(screen.getByRole('button', { name: '确认并执行' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '取消' })).toBeEnabled()
})

it('collapses history on a new turn and retains edited drafts when the user returns to them', () => {
  const { rerender } = render(list())
  fireEvent.change(screen.getByLabelText('LAI最大值'), { target: { value: '7' } })
  fireEvent.click(screen.getByRole('button', { name: '本轮分析记录（9）' }))
  const next: WorkspaceTimelineItem[] = [...timeline, { kind: 'agent_user_message', eventId: 'next', message: '换个任务', timestamp: '' }]
  rerender(list([...completed, pending], next))
  expect(screen.getByRole('button', { name: '本轮分析记录（10）' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: '确认并执行' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '本轮分析记录（10）' }))
  screen.getByText('确认 LAI 反演参数 · 待确认').closest('details')!.open = true
  expect(screen.getByLabelText('LAI最大值')).toHaveValue(7)
})

it('shows a recovered current confirmation before conversation history is restored', () => {
  render(list([...completed, pending], []))
  expect(screen.getByRole('button', { name: '确认并执行' })).toBeVisible()
})

it('excludes records from other runs and workspaces even when their inputs match', () => {
  const oldPending = { ...pending, review_id: 'old-pending', source_run_id: 'old-run' }
  render(list([oldPending, pending, { ...pending, review_id: 'other-workspace', workspace_id: 'other' }]))
  expect(screen.getAllByRole('button', { name: '确认并执行' })).toHaveLength(1)
  expect(screen.queryByRole('button', { name: /本轮分析记录/ })).not.toBeInTheDocument()
})
