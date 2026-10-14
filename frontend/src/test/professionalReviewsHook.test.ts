import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useProfessionalReviews } from '../features/workspace-assistant/useProfessionalReviews'
import type { WorkspaceContext } from '../services/canonical/workspaceClient'

const api = vi.hoisted(() => ({ list: vi.fn(), decide: vi.fn(), sync: vi.fn() }))
vi.mock('../services/canonical/workspaceClient', () => ({ getProfessionalReviews: api.list, decideProfessionalReview: api.decide, syncWorkspaceContext: api.sync }))
const context: WorkspaceContext = { workspace_id: 'ws', revision: 1, professional_mode: true, execution_mode: 'live', aoi: null, imagery_item_id: null, imagery_snapshot: null, active_workflow_id: null, draft_task_ids: [] }
beforeEach(() => {
  vi.clearAllMocks()
  api.list.mockResolvedValue([])
  api.sync.mockResolvedValue(context)
  api.decide.mockResolvedValue({ review: { review_id: 'review', status: 'confirmed' }, next_review: null, workflow: { workflow_id: 'flow', created_at: '' } })
})
afterEach(cleanup)
it('recovers a confirmed workflow without confirming or running it again', async () => {
  const link = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValue(undefined)
  const { result } = renderHook(() => useProfessionalReviews(context, false, link, vi.fn()))
  await act(async () => { await result.current.decide('review', { decision: 'confirm' }) })
  expect(result.current.isLaunching).toBe(true)
  expect(result.current.error).toContain('恢复任务状态')
  await act(async () => { await result.current.recover() })
  expect(link).toHaveBeenCalledTimes(2)
  expect(api.decide).toHaveBeenCalledOnce()
  expect(result.current.isLaunching).toBe(false)
})
it('restores pending proposals while retaining them during a connection failure', async () => {
  api.list.mockResolvedValueOnce([{ review_id: 'review', status: 'pending' }]).mockRejectedValue(new Error('offline'))
  const { result, rerender } = renderHook(({ sending }) => useProfessionalReviews(context, sending, vi.fn(), vi.fn()), { initialProps: { sending: false } })
  await waitFor(() => expect(result.current.reviews).toHaveLength(1))
  rerender({ sending: true })
  await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2))
  expect(result.current.reviews[0].status).toBe('pending')
})
