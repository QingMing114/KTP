import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useWorkspaceHistoryVisibility } from '../features/workspace-assistant/useWorkspaceHistoryVisibility'
import { setLastLoginUser } from '../services/api'
import type { ProfessionalReview, WorkspaceContext } from '../services/canonical/workspaceClient'
import type { WorkspaceTimelineItem } from '../features/workspace-assistant/workspaceTimeline'
import type { AnalysisWorkflow } from '../services/spatialClient'

beforeEach(() => { localStorage.clear(); setLastLoginUser('alice') })
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear() })
const context: WorkspaceContext = { workspace_id: 'ws', revision: 1, execution_mode: 'live', professional_mode: true, aoi: null, imagery_item_id: null, imagery_snapshot: null, active_workflow_id: null, draft_task_ids: ['lai'] }
function round(runId: string, prefix = ''): WorkspaceTimelineItem[] {
  return [{ kind: 'agent_user_message', eventId: prefix + 'user-' + runId, message: runId, timestamp: '' }, { kind: 'agent_message', eventId: prefix + 'assistant-' + runId, runId, submissionId: '', message: '回答', status: 'completed', timestamp: '' }]
}
function useVisibility(items = round('old'), workspace = context, reviews: ProfessionalReview[] = [], flows: ReadonlyMap<string, AnalysisWorkflow> = new Map(), unattached: AnalysisWorkflow[] = []) {
  return useWorkspaceHistoryVisibility(items, workspace, reviews, flows, unattached)
}

it('hides paired messages without changing the timeline, and restores them after reload aliases change', () => {
  const items = round('old')
  const original = JSON.stringify(items)
  const first = renderHook(() => useVisibility(items))
  act(() => first.result.current.clear())
  expect(first.result.current.messages.every(first.result.current.isHiddenMessage)).toBe(true)
  expect(JSON.stringify(items)).toBe(original)
  first.unmount()
  const restoredItems = round('old', 'history-')
  const refreshed = renderHook(() => useVisibility(restoredItems))
  expect(refreshed.result.current.messages.every(refreshed.result.current.isHiddenMessage)).toBe(true)
  act(() => refreshed.result.current.restore())
  expect(refreshed.result.current.messages.some(refreshed.result.current.isHiddenMessage)).toBe(false)
})

it('leaves messages arriving later visible even if their timestamps are earlier', () => {
  const { result, rerender } = renderHook(({ items }) => useVisibility(items), { initialProps: { items: round('old') } })
  act(() => result.current.clear())
  rerender({ items: [...round('old'), ...round('new')] })
  expect(result.current.messages.slice(0, 2).every(result.current.isHiddenMessage)).toBe(true)
  expect(result.current.messages.slice(2).some(result.current.isHiddenMessage)).toBe(false)
})

it('isolates preferences by account and workspace', () => {
  const first = renderHook(() => useVisibility())
  act(() => first.result.current.clear())
  first.unmount()
  setLastLoginUser('bob')
  const otherUser = renderHook(() => useVisibility())
  expect(otherUser.result.current.hasHidden).toBe(false)
  setLastLoginUser('alice')
  const otherWorkspace = renderHook(() => useVisibility(round('old'), { ...context, workspace_id: 'other' }))
  expect(otherWorkspace.result.current.hasHidden).toBe(false)
})

it('preserves a pending professional confirmation while clearing older replies', () => {
  const review: ProfessionalReview = { review_id: 'review', workspace_id: 'ws', source_run_id: 'current', status: 'pending', phase: 'search', title: '确认搜索', rationale: '', detail: '', context, intent: { task_ids: ['lai'], rationale: '' }, candidates: [], search: null, selected_imagery_id: null, proposed_scene: null, workflow_id: null, created_at: '' }
  const { result } = renderHook(() => useVisibility([...round('old'), ...round('current')], context, [review]))
  act(() => result.current.clear())
  expect(result.current.messages.slice(0, 2).every(result.current.isHiddenMessage)).toBe(true)
  expect(result.current.messages.slice(2).some(result.current.isHiddenMessage)).toBe(false)
})

it('retains running and blocked current tasks while hiding completed unattached receipts', () => {
  // Only identity/status are needed by the visibility boundary.
  const running = { workflow_id: 'running', run_id: 'current', status: 'running' } as AnalysisWorkflow
  const completed = { workflow_id: 'old-flow', run_id: 'old', status: 'completed' } as AnalysisWorkflow
  const { result } = renderHook(() => useVisibility([...round('old'), ...round('current')], context, [], new Map([['running', running], ['old-flow', completed]]), [running, completed]))
  act(() => result.current.clear())
  expect(result.current.isHiddenWorkflow(completed)).toBe(true)
  expect(result.current.isHiddenWorkflow(running)).toBe(false)
  expect(result.current.messages.slice(2).some(result.current.isHiddenMessage)).toBe(false)
})

it('reports a persistence failure without pretending the list was cleared', () => {
  const { result } = renderHook(() => useVisibility())
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
  act(() => result.current.clear())
  expect(result.current.hasHidden).toBe(false)
  expect(result.current.error).toContain('未能保存')
})

it('restores this conversation without changing another conversation visibility', () => {
  const old = renderHook(() => useVisibility(round('old')))
  act(() => old.result.current.clear()); old.unmount()
  const other = renderHook(() => useVisibility(round('other')))
  act(() => other.result.current.clear())
  act(() => other.result.current.restore()); other.unmount()
  const oldAgain = renderHook(() => useVisibility(round('old')))
  expect(oldAgain.result.current.hasHidden).toBe(true)
})
