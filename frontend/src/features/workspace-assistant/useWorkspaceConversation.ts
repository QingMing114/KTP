import { useCallback, useEffect, useRef, useState } from 'react'
import { getLastLoginUser } from '../../services/api'
import { createConversation } from '../../services/canonical/conversationClient'
import { getRun, type CanonicalRun } from '../../services/canonical/runClient'
import { cancelSubmission, createSubmission, subscribeSubmissionEvents } from '../../services/canonical/submissionClient'
import type { SubmissionSseEvent } from '../../services/canonical/request'
import { createWorkspaceTimelineEventId, type WorkspaceTimelineItem } from './workspaceTimeline'

interface ActiveSubmission {
  submissionId: string
  assistantEventId: string
  controller: AbortController
}

export interface WorkspaceConversationState {
  conversationId: string | null
  isSending: boolean
  error: string
  sendMessage: (message: string) => Promise<void>
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
): WorkspaceConversationState {
  const [conversationId, setConversationId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    return window.localStorage.getItem(conversationStorageKey())
  })
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState('')
  const activeSubmissionRef = useRef<ActiveSubmission | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => () => activeSubmissionRef.current?.controller.abort(), [])

  const sendMessage = useCallback(async (message: string) => {
    const trimmedMessage = message.trim()
    if (!trimmedMessage || activeSubmissionRef.current) return

    const timestamp = new Date().toISOString()
    onTimelineItem({
      eventId: createWorkspaceTimelineEventId('agent-user'),
      kind: 'agent_user_message',
      message: trimmedMessage,
      timestamp,
    })
    setError('')
    setIsSending(true)
    cancelledRef.current = false

    let activeConversationId = conversationId
    let active: ActiveSubmission | null = null
    let streamedText = ''
    let runId: string | undefined

    try {
      if (!activeConversationId) {
        const conversation = await createConversation('地图工作台助手')
        activeConversationId = conversation.conversation_id
        setConversationId(activeConversationId)
        if (typeof window !== 'undefined') window.localStorage.setItem(conversationStorageKey(), activeConversationId)
      }

      const submission = await createSubmission(activeConversationId, {
        message: trimmedMessage,
        mode: { interaction: 'chat', delivery: 'async' },
        context: { inherit: 'latest' },
        client: { name: 'workspace-assistant', version: '1' },
      })
      runId = submission.run_id
      active = {
        submissionId: submission.submission_id,
        assistantEventId: `agent-message-${submission.submission_id}`,
        controller: new AbortController(),
      }
      activeSubmissionRef.current = active
      onTimelineItem({
        eventId: active.assistantEventId,
        kind: 'agent_message',
        message: '正在思考…',
        submissionId: active.submissionId,
        runId,
        status: 'streaming',
        timestamp: new Date().toISOString(),
      })

      await new Promise<void>((resolve, reject) => {
        subscribeSubmissionEvents(
          active!.submissionId,
          (event) => {
            runId = event.run_id || runId
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
              resolve()
            } else if (event.event === 'run.failed' || event.event === 'submission.cancelled') {
              reject(new Error(event.detail || '遥感分析助手未能完成本次回答。'))
            }
          },
          (streamError) => reject(streamError),
          active!.controller.signal,
        )
      })

      let run: CanonicalRun | null = null
      if (runId) {
        try { run = await getRun(runId) } catch { /* retain streamed text when final retrieval is unavailable */ }
      }
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
      const detail = sendError instanceof Error ? sendError.message : '发送给遥感分析助手失败。'
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
      setIsSending(false)
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
    setIsSending(false)
  }, [onTimelineItem])

  return { conversationId, isSending, error, sendMessage, cancelMessage }
}
