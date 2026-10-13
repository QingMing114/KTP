import { useCallback, useEffect, useRef, useState } from 'react'
import { getLastLoginUser } from '../../services/api'
import { createConversation } from '../../services/canonical/conversationClient'
import { getRun, getConversationRuns, type CanonicalRun } from '../../services/canonical/runClient'
import { cancelSubmission, createSubmission, getSubmission, subscribeSubmissionEvents } from '../../services/canonical/submissionClient'
import { syncWorkspaceContext, type WorkspaceContext, type WorkspaceUiState, type CanonicalAssistantPart } from '../../services/canonical/workspaceClient'
import { getAnalysisWorkflow, type WorkflowTaskId } from '../../services/spatialClient'
import type { SubmissionSseEvent } from '../../services/canonical/request'
import { createWorkspaceTimelineEventId, type WorkspaceTimelineItem } from './workspaceTimeline'
import { canApplyAssistantDraft, isWorkspacePartCurrent } from './workspaceUiContext'
import { WORKSPACE_TASKS } from './workspaceTasks'

type WorkspaceAction = { action_id: string; task_ids: WorkflowTaskId[]; source_run_id?: string; yield_demo_crop?: 'wheat' | 'maize' }

interface ActiveSubmission {
  submissionId: string
  assistantEventId: string
  runId?: string
  controller: AbortController
}

export interface WorkspaceConversationState {
  conversationId: string | null
  isSending: boolean
  isLaunching: boolean
  error: string
  sendMessage: (message: string, action?: WorkspaceAction) => Promise<void>
  executeTasks: (demoCrop?: 'wheat' | 'maize') => Promise<void>
  recoverWorkflow: () => Promise<void>
  cancelMessage: () => Promise<void>
}

function conversationStorageKey(): string {
  return `ktp_workspace_conversation:${getLastLoginUser()}`
}

export function extractAssistantText(run: CanonicalRun | null, streamedText: string): string {
  const summary = run?.assistant?.summary?.trim()
  if (summary) return summary
  const parts = (run?.assistant?.parts ?? [])
    .map((part) => part.text?.trim() ?? '')
    .filter(Boolean)
  if (parts.length) return parts.join('\n\n')
  return streamedText.trim()
}

function assistantPart(event: SubmissionSseEvent): string {
  const value = event.data?.assistant_part_text
  return typeof value === 'string' ? value : ''
}

/**
 * Keeps the Workspace conversation separate from /chat while reusing the
 * canonical Submission and authenticated SSE clients.
 */
export function useWorkspaceConversation(
  onTimelineItem: (item: WorkspaceTimelineItem) => void,
  options?: {
    context: WorkspaceContext
    ui?: WorkspaceUiState
    onWorkflowLinked: (workflowId: string, activate?: boolean) => Promise<void>
    onDraftTasks: (tasks: WorkflowTaskId[]) => void
    onDemoStart: (tasks: WorkflowTaskId[]) => void
  },
): WorkspaceConversationState {
  const [conversationId, setConversationId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    return window.localStorage.getItem(conversationStorageKey())
  })
  const [isSending, setIsSending] = useState(false)
  const [isLaunching, setIsLaunching] = useState(false)
  const [pendingWorkflowId, setPendingWorkflowId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const activeSubmissionRef = useRef<ActiveSubmission | null>(null)
  const cancelledRef = useRef(false)
  const sendingRef = useRef(false)
  const optionsRef = useRef(options)
  optionsRef.current = options
  const handledActions = useRef(new Set<string>())
  const pendingMessage = useRef<ActiveSubmission | null>(null)

  useEffect(() => {
    if (!options?.context) return
    void syncWorkspaceContext(options.context).catch((cause) => setError(cause instanceof Error ? cause.message : '工作台上下文同步失败'))
  }, [options?.context])

  useEffect(() => {
    if (!conversationId) return
    let disposed = false
    void getConversationRuns(conversationId).then((runs) => {
      if (disposed || sendingRef.current) return
      runs.forEach((run, index) => {
        const timestamp = run.created_at ?? new Date(index).toISOString()
        if (run.input_message) onTimelineItem({ eventId: `history-user-${run.run_id}`, kind: 'agent_user_message', message: run.input_message, timestamp })
        onTimelineItem({ eventId: `history-agent-${run.run_id}`, kind: 'agent_message', message: extractAssistantText(run, ''), submissionId: '', runId: run.run_id, status: run.status === 'failed' ? 'failed' : 'completed', timestamp })
        run.assistant?.parts?.filter((part) => part.data && part.part_id).forEach((part) => onTimelineItem({ eventId: part.part_id!, kind: 'agent_part', part, runId: run.run_id, timestamp }))
        run.assistant?.parts?.filter((part) => part.type === 'workflow_reference' && part.data?.workflow_id).forEach((part) => {
          void getAnalysisWorkflow(part.data!.workflow_id!).then((workflow) => {
            if (!disposed) onTimelineItem({ eventId: `workflow-${workflow.workflow_id}`, kind: 'workflow', workflow, timestamp: workflow.created_at })
          }).catch(() => { /* Retain the historical reference when task retrieval fails. */ })
        })
      })
    }).catch(() => { /* Sending validates a saved conversation independently. */ })
    return () => { disposed = true }
  }, [conversationId, onTimelineItem])

  useEffect(() => () => activeSubmissionRef.current?.controller.abort(), [])

  const sendMessage = useCallback(async (message: string, action?: WorkspaceAction) => {
    const trimmedMessage = message.trim()
    if (!trimmedMessage || sendingRef.current) return
    sendingRef.current = true
    const workspace = optionsRef.current?.context
    const workspaceUi = optionsRef.current?.ui
    const key = action?.action_id ?? createWorkspaceTimelineEventId('submission')

    const timestamp = new Date().toISOString()
    onTimelineItem({
      eventId: createWorkspaceTimelineEventId('agent-user'),
      kind: 'agent_user_message',
      message: trimmedMessage,
      timestamp,
    })
    setError('')
    setIsSending(true)
    setIsLaunching(!!action)
    cancelledRef.current = false

    let activeConversationId = conversationId
    let active: ActiveSubmission | null = null
    let streamedText = ''
    let runId: string | undefined
    const linkedWorkflows: Promise<void>[] = []
    let activeWorkflowLinked = false

    try {
      if (workspace) await syncWorkspaceContext(workspace)
      if (!activeConversationId) {
        const conversation = await createConversation('地图工作台助手')
        activeConversationId = conversation.conversation_id
        setConversationId(activeConversationId)
        if (typeof window !== 'undefined') window.localStorage.setItem(conversationStorageKey(), activeConversationId)
      }

      const submission = await createSubmission(activeConversationId, {
        message: trimmedMessage,
        mode: { interaction: 'chat', delivery: 'async' },
        context: { inherit: 'latest', workspace, workspace_ui: workspaceUi },
        workspace_action: action,
        idempotency_key: key,
        client: { name: 'workspace-assistant', version: '2' },
      })
      runId = submission.run_id
      active = {
        submissionId: submission.submission_id,
        assistantEventId: `agent-message-${submission.submission_id}`,
        runId,
        controller: new AbortController(),
      }
      activeSubmissionRef.current = active
      onTimelineItem({
        eventId: active.assistantEventId,
        kind: 'agent_message',
        message: action ? '正在提交所选任务…' : '正在理解你的请求…',
        submissionId: active.submissionId,
        runId,
        status: 'streaming',
        timestamp: new Date().toISOString(),
      })

      const acceptPart = (part: CanonicalAssistantPart, timestamp: string) => {
        if (!part.part_id || !part.data) return
        if (active) active.runId = runId
        onTimelineItem({ eventId: part.part_id, kind: 'agent_part', part, runId, timestamp })
        const current = optionsRef.current
        if (!current || !workspace) return
        const sameInputs = isWorkspacePartCurrent({ ...workspace, input_aoi: workspace.aoi?.geometry ?? null }, current.context)
        if (sameInputs && part.type === 'analysis_plan' && part.data.intent === 'execute' && !part.data.missing_inputs?.length && part.data.requested_task_ids?.length) setIsLaunching(true)
        const actionKey = part.data.workflow_id ?? (part.data.demo_started ? part.data.action_id : undefined)
        if (!actionKey || handledActions.current.has(actionKey)) return
        handledActions.current.add(actionKey)
        if (part.type === 'workflow_reference' && part.data.workflow_id) {
          const workflowId = part.data.workflow_id
          if (sameInputs) {
            activeWorkflowLinked = true
            pendingMessage.current = active
            setPendingWorkflowId(workflowId)
          }
          const pending = current.onWorkflowLinked(workflowId, sameInputs).then(() => setPendingWorkflowId((id) => id === workflowId ? null : id))
          // Attach a rejection handler immediately; finalization awaits adoption.
          pending.catch(() => {})
          linkedWorkflows.push(pending)
        }
        if (part.data.demo_started && sameInputs) current.onDemoStart(part.data.task_ids ?? [])
      }

      await new Promise<void>((resolve, reject) => {
        const onAbort = () => settle(new Error('已停止本次问答。'))
        let pollFailures = 0
        const timer = window.setInterval(() => {
          void getSubmission(active!.submissionId).then((current) => {
            pollFailures = 0
            runId = current.run_id || runId
            if (current.status === 'completed') { window.clearInterval(timer); resolve() }
            if (current.status === 'failed' || current.status === 'cancelled') { window.clearInterval(timer); reject(new Error('本次回答未完成，请查看任务状态后重试。')) }
          }).catch(() => {
            pollFailures += 1
            if (pollFailures >= 3) { window.clearInterval(timer); reject(new Error('连接中断，请刷新恢复对话与任务状态。')) }
          })
        }, 2500)
        const settle = (cause?: Error) => { window.clearInterval(timer); active!.controller.signal.removeEventListener('abort', onAbort); cause ? reject(cause) : resolve() }
        active!.controller.signal.addEventListener('abort', onAbort, { once: true })
        subscribeSubmissionEvents(
          active!.submissionId,
          (event) => {
            runId = event.run_id || runId
            const productPart = event.data?.part as CanonicalAssistantPart | undefined
            if (productPart) acceptPart(productPart, event.timestamp || new Date().toISOString())
            const part = assistantPart(event)
            if (part) {
              streamedText += part
              onTimelineItem({
                eventId: active!.assistantEventId,
                kind: 'agent_message',
                message: streamedText,
                submissionId: active!.submissionId,
                runId,
                status: 'streaming',
                timestamp: event.timestamp || new Date().toISOString(),
              })
            }
            if (event.event === 'run.completed') {
              settle()
            } else if (event.event === 'run.failed' || event.event === 'submission.cancelled') {
              settle(new Error(event.detail || '遥感分析助手未能完成本次回答。'))
            }
          },
          () => { /* Polling recovers terminal state when SSE disconnects. */ },
          active!.controller.signal,
        )
      })

      let run: CanonicalRun | null = null
      if (runId) {
        try { run = await getRun(runId) } catch { /* retain streamed text when final retrieval is unavailable */ }
      }
      run?.assistant?.parts?.forEach((part) => acceptPart(part, new Date().toISOString()))
      await Promise.all(linkedWorkflows)
      const plan = run?.assistant?.parts?.find((part) => part.type === 'analysis_plan')?.data
      const current = optionsRef.current
      if (plan?.requested_task_ids && workspace && current && (plan.intent === 'configure' || plan.intent === 'execute') && !run?.assistant?.parts?.some((part) => part.type === 'workflow_reference' || part.data?.demo_started) && !plan.missing_inputs?.some((missing) => missing.includes('仍在运行')) && canApplyAssistantDraft(workspace, current.context)) current.onDraftTasks(plan.requested_task_ids)
      const finalText = extractAssistantText(run, streamedText) || '本次回答已完成。'
      onTimelineItem({
        eventId: active.assistantEventId,
        kind: 'agent_message',
        message: finalText,
        submissionId: active.submissionId,
        runId,
        status: 'completed',
        timestamp: new Date().toISOString(),
      })
    } catch (sendError) {
      if (cancelledRef.current) return
      const detail = activeWorkflowLinked ? '任务已提交，但状态同步失败。请点击“恢复任务状态”。' : sendError instanceof Error ? sendError.message : '发送给遥感分析助手失败。'
      setError(detail)
      onTimelineItem({
        eventId: createWorkspaceTimelineEventId('agent-error'),
        kind: 'error',
        detail,
        timestamp: new Date().toISOString(),
      })
      if (active) {
        onTimelineItem({
          eventId: active.assistantEventId,
          kind: 'agent_message',
          message: detail,
          submissionId: active.submissionId,
          runId,
          status: 'failed',
          timestamp: new Date().toISOString(),
        })
      }
    } finally {
      if (activeSubmissionRef.current === active) activeSubmissionRef.current = null
      active?.controller.abort()
      sendingRef.current = false
      setIsSending(false)
      setIsLaunching(false)
    }
  }, [conversationId, onTimelineItem])

  const cancelMessage = useCallback(async () => {
    const active = activeSubmissionRef.current
    if (!active) return
    cancelledRef.current = true
    active.controller.abort()
    activeSubmissionRef.current = null
    try { await cancelSubmission(active.submissionId) } catch { /* local cancellation still stops rendering */ }
    onTimelineItem({
      eventId: active.assistantEventId,
      kind: 'agent_message',
      message: '已取消本次问答。',
      submissionId: active.submissionId,
      status: 'failed',
      timestamp: new Date().toISOString(),
    })
  }, [onTimelineItem])

  const executeTasks = useCallback(async (demoCrop?: 'wheat' | 'maize') => {
    const context = optionsRef.current?.context
    if (!context?.draft_task_ids.length || sendingRef.current || pendingWorkflowId) return
    const labels = context.draft_task_ids.map((id) => WORKSPACE_TASKS.find((task) => task.id === id)?.title ?? id)
    await sendMessage(demoCrop ? `使用${demoCrop === 'wheat' ? '小麦' : '玉米'}模拟数据演示${labels.join('和')}` : `执行${labels.join('和')}`, { action_id: createWorkspaceTimelineEventId('launch'), task_ids: context.draft_task_ids, ...(demoCrop ? { yield_demo_crop: demoCrop } : {}) })
  }, [sendMessage, pendingWorkflowId])

  const recoverWorkflow = useCallback(async () => {
    if (!pendingWorkflowId || !optionsRef.current || sendingRef.current) return
    setIsLaunching(true)
    setError('')
    try {
      await optionsRef.current.onWorkflowLinked(pendingWorkflowId)
      setPendingWorkflowId(null)
      if (pendingMessage.current) onTimelineItem({ eventId: pendingMessage.current.assistantEventId, kind: 'agent_message', submissionId: pendingMessage.current.submissionId, runId: pendingMessage.current.runId, message: '任务状态已恢复，进度和结果已同步。', status: 'completed', timestamp: new Date().toISOString() })
      pendingMessage.current = null
    } catch {
      setError('任务仍在后台，请稍后再次恢复状态。')
    } finally { setIsLaunching(false) }
  }, [pendingWorkflowId, onTimelineItem])

  return { conversationId, isSending, isLaunching: isLaunching || !!pendingWorkflowId, error, sendMessage, executeTasks, recoverWorkflow, cancelMessage }
}
