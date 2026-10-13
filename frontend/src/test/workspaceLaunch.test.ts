import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkspaceConversation } from '../features/workspace-assistant/useWorkspaceConversation'
import type { WorkspaceContext } from '../services/canonical/workspaceClient'
import type { SubmissionSseEvent } from '../services/canonical/request'

const mock = vi.hoisted(() => ({ create: vi.fn(), subscribe: vi.fn(), cancel: vi.fn(), run: vi.fn() }))
vi.mock('../services/canonical/conversationClient', () => ({ createConversation: async () => ({ conversation_id: 'conv' }) }))
vi.mock('../services/canonical/workspaceClient', () => ({ syncWorkspaceContext: async (value: unknown) => value }))
vi.mock('../services/canonical/runClient', () => ({ getRun: mock.run, getConversationRuns: async () => [] }))
vi.mock('../services/canonical/submissionClient', () => ({ createSubmission: mock.create, subscribeSubmissionEvents: mock.subscribe, cancelSubmission: mock.cancel, getSubmission: async () => ({ status: 'running' }) }))

const context: WorkspaceContext = { workspace_id: 'ws', revision: 1, execution_mode: 'live', aoi: null, imagery_item_id: 'image', imagery_snapshot: null, active_workflow_id: null, draft_task_ids: ['lai'] }
let emit: (event: SubmissionSseEvent) => void
beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  mock.create.mockResolvedValue({ submission_id: 'sub', run_id: 'run' })
  mock.cancel.mockResolvedValue({ status: 'cancelled' })
  mock.run.mockResolvedValue({ assistant: { summary: '完成', parts: [] } })
  mock.subscribe.mockImplementation((_id, callback) => { emit = callback })
})
afterEach(cleanup)
function setup(onWorkflowLinked = vi.fn(async () => {})) {
  return renderHook(() => useWorkspaceConversation(vi.fn(), { context, onWorkflowLinked, onDraftTasks: vi.fn(), onDemoStart: vi.fn() }))
}
function event(event: string, data: Record<string, unknown> = {}) { return { event, submission_id: 'sub', run_id: 'run', data } as SubmissionSseEvent }
const reference = { type: 'workflow_reference', part_id: 'ref', data: { workflow_id: 'workflow', workspace_id: 'ws', revision: 1 } }

describe('one task launch lifecycle', () => {
  it('carries the explicit demo crop through the same idempotent submission lifecycle', async () => {
    const demoContext: WorkspaceContext = { ...context, draft_task_ids: ['yield_simple'] }
    const { result } = renderHook(() => useWorkspaceConversation(vi.fn(), { context: demoContext, onWorkflowLinked: vi.fn(), onDraftTasks: vi.fn(), onDemoStart: vi.fn() }))
    let pending!: Promise<void>
    act(() => { pending = result.current.executeTasks('maize'); void result.current.executeTasks('maize') })
    await waitFor(() => expect(mock.subscribe).toHaveBeenCalledOnce())
    expect(mock.create).toHaveBeenCalledOnce()
    expect(mock.create.mock.calls[0][1].workspace_action).toMatchObject({ task_ids: ['yield_simple'], yield_demo_crop: 'maize' })
    await act(async () => { emit(event('run.completed')); await pending })
  })
  it('submits a typed confirmation once and keeps the launch locked until task adoption', async () => {
    let adopted!: () => void
    const link = vi.fn(() => new Promise<void>((resolve) => { adopted = resolve }))
    const { result } = setup(link)
    let pending!: Promise<void>
    act(() => { pending = result.current.executeTasks(); void result.current.executeTasks() })
    await waitFor(() => expect(mock.subscribe).toHaveBeenCalledOnce())
    expect(mock.create).toHaveBeenCalledOnce()
    expect(mock.create.mock.calls[0][1].workspace_action.task_ids).toEqual(['lai'])
    expect(mock.create.mock.calls[0][1].workspace_action.source_run_id).toBeUndefined()
    act(() => { emit(event('workflow.linked', { part: reference })); emit(event('workflow.linked', { part: reference })); emit(event('run.completed')) })
    expect(link).toHaveBeenCalledOnce()
    expect(result.current.isLaunching).toBe(true)
    await act(async () => { adopted(); await pending })
    expect(result.current.isLaunching).toBe(false)
  })

  it('recovers an already submitted task after a status fetch failure without starting again', async () => {
    const link = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValue(undefined)
    const { result } = setup(link)
    let pending!: Promise<void>
    act(() => { pending = result.current.executeTasks() })
    await waitFor(() => expect(mock.subscribe).toHaveBeenCalledOnce())
    await act(async () => { emit(event('workflow.linked', { part: reference })); emit(event('run.completed')); await pending })
    expect(result.current.isLaunching).toBe(true)
    expect(result.current.error).toContain('恢复任务状态')
    await act(async () => { await result.current.executeTasks(); await result.current.recoverWorkflow() })
    expect(mock.create).toHaveBeenCalledOnce()
    expect(link).toHaveBeenCalledTimes(2)
    expect(result.current.isLaunching).toBe(false)
  })

  it('releases the conversation lock immediately when a question is cancelled', async () => {
    const { result } = setup()
    let pending!: Promise<void>
    act(() => { pending = result.current.sendMessage('解释参数') })
    await waitFor(() => expect(mock.subscribe).toHaveBeenCalledOnce())
    await act(async () => { await result.current.cancelMessage(); await pending })
    expect(result.current.isSending).toBe(false)
    act(() => { pending = result.current.sendMessage('继续解释') })
    await waitFor(() => expect(mock.create).toHaveBeenCalledTimes(2))
    await act(async () => { emit(event('run.completed')); await pending })
  })

  it('retains a late task reference in history without adopting it on changed map inputs', async () => {
    const link = vi.fn(async () => {})
    const { result, rerender } = renderHook(({ current }) => useWorkspaceConversation(vi.fn(), { context: current, onWorkflowLinked: link, onDraftTasks: vi.fn(), onDemoStart: vi.fn() }), { initialProps: { current: context } })
    let pending!: Promise<void>
    act(() => { pending = result.current.sendMessage('开始执行') })
    await waitFor(() => expect(mock.subscribe).toHaveBeenCalledOnce())
    rerender({ current: { ...context, revision: 2, imagery_item_id: 'other-image' } })
    await act(async () => { emit(event('workflow.linked', { part: reference })); emit(event('run.completed')); await pending })
    expect(link).toHaveBeenCalledWith('workflow', false)
    expect(result.current.isLaunching).toBe(false)
  })
})
