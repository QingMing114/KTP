import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useWorkspaceAttention } from '../features/workspace-assistant/useWorkspaceAttention'
import type { AnalysisWorkflow } from '../services/spatialClient'

afterEach(() => { cleanup(); vi.useRealTimers() })
const base = { workflow: null as AnalysisWorkflow | null, viewRequest: null as { workflowId: string | null; requestId: number } | null, restoredWorkflowId: null as string | null, aoiReady: false, selectedImage: '', draftSignature: '', candidateSignature: '', imageryIsSearching: false, isLaunching: false, analysisError: '' }
function flow(status: AnalysisWorkflow['status'] = 'running', code = ''): AnalysisWorkflow {
  return { workflow_id: 'task', status, detail: '', run_id: 'run', aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, requested_task_ids: ['yield_simple'], effective_task_ids: ['crop', 'yield_simple'], imagery_item_id: 'image', imagery_snapshot: { item_id: 'image', collection: 'sentinel-2-l2a', acquired_at: '2026-09-10', is_recommended: true }, yield_inputs: { confirmed_crop_class_id: null, cultivar: null, sowing_date: null, field_dataset_id: null }, created_at: '', updated_at: '', steps: [{ step_id: 'yield_simple', depends_on: ['crop'], status: status === 'blocked' ? 'blocked' : status === 'failed' ? 'failed' : 'running', progress_percent: 20, detail: '', result: { reason_code: code } }] }
}
it('highlights a new task once and ignores repeated polling and percentage changes', () => {
  const { result, rerender } = renderHook(useWorkspaceAttention, { initialProps: base })
  const task = flow()
  rerender({ ...base, workflow: task })
  const started = result.current.attention
  expect(started).toMatchObject({ active: true, tone: 'info', workflowId: 'task' })
  rerender({ ...base, workflow: { ...task, steps: [{ ...task.steps[0], progress_percent: 80, detail: '新的进度文字' }], updated_at: 'later' } })
  expect(result.current.attention).toBe(started)
})
it('stops motion after six seconds, retains an unread cue, and clears it on acknowledgement', () => {
  vi.useFakeTimers()
  const { result, rerender } = renderHook(useWorkspaceAttention, { initialProps: base })
  rerender({ ...base, workflow: flow('completed') })
  expect(result.current.attention?.tone).toBe('success')
  act(() => vi.advanceTimersByTime(6000))
  expect(result.current.attention).toMatchObject({ active: false, unread: true })
  act(() => result.current.acknowledge())
  expect(result.current.attention).toMatchObject({ active: false, unread: false })
})
it('distinguishes crop confirmation, season delay, and execution failure', () => {
  const { result, rerender } = renderHook(useWorkspaceAttention, { initialProps: { ...base, workflow: flow() } })
  rerender({ ...base, workflow: flow('blocked', 'crop_confirmation_required') })
  expect(result.current.attention?.message).toContain('确认作物')
  const cropCue = result.current.attention?.id
  rerender({ ...base, workflow: flow('blocked', 'season_in_progress') })
  expect(result.current.attention?.message).toContain('季末')
  expect(result.current.attention?.id).not.toBe(cropCue)
  rerender({ ...base, workflow: flow('failed') })
  expect(result.current.attention).toMatchObject({ tone: 'error', message: '任务执行失败，请查看原因' })
})
it('keeps restored results quiet but alerts when a restored running task finishes', () => {
  const props = { ...base, restoredWorkflowId: 'task' }
  const { result, rerender } = renderHook(useWorkspaceAttention, { initialProps: props })
  rerender({ ...props, workflow: flow() })
  expect(result.current.attention).toBeNull()
  rerender({ ...props, workflow: flow('completed') })
  expect(result.current.attention?.tone).toBe('success')
})
it('replays an explicit task location without changing the workflow', () => {
  const props = { ...base, workflow: flow('blocked', 'crop_confirmation_required') }
  const { result, rerender } = renderHook(useWorkspaceAttention, { initialProps: props })
  rerender({ ...props, viewRequest: { workflowId: 'task', requestId: 1 } })
  expect(result.current.attention).toMatchObject({ workflowId: 'task', tone: 'warning', active: true })
  const first = result.current.attention?.id
  act(() => result.current.acknowledge())
  rerender({ ...props, viewRequest: { workflowId: 'task', requestId: 2 } })
  expect(result.current.attention?.id).not.toBe(first)
  expect(result.current.attention?.active).toBe(true)
})
it('notifies when asynchronously loaded imagery is ready for selection', () => {
  const { result, rerender } = renderHook(useWorkspaceAttention, { initialProps: { ...base, aoiReady: true, imageryIsSearching: true } })
  rerender({ ...base, aoiReady: true, imageryIsSearching: false, candidateSignature: 'image-1,image-2' })
  expect(result.current.attention?.message).toContain('选择影像')
})

it('replaces a ready-to-start reminder during submission and explains recovery errors', () => {
  const props = { ...base, aoiReady: true, selectedImage: 'image' }
  const { result, rerender } = renderHook(useWorkspaceAttention, { initialProps: props })
  rerender({ ...props, draftSignature: 'crop' })
  expect(result.current.attention?.message).toContain('开始执行')
  rerender({ ...props, draftSignature: 'crop', isLaunching: true })
  expect(result.current.attention?.message).toContain('正在提交')
  rerender({ ...props, draftSignature: 'crop', isLaunching: true, analysisError: '任务已提交，但状态同步失败' })
  expect(result.current.attention).toMatchObject({ tone: 'error' })
  expect(result.current.attention?.message).toContain('恢复入口')
})
