import { useCallback, useEffect, useRef, useState } from 'react'
import { decideProfessionalReview, getProfessionalReviews, syncWorkspaceContext, type WorkspaceContext, type ProfessionalReview, type ProfessionalDecision } from '../../services/canonical/workspaceClient'
import type { WorkspaceTimelineItem } from './workspaceTimeline'

export function useProfessionalReviews(context: WorkspaceContext, isSending: boolean,
  onWorkflowLinked: (id: string, activate?: boolean) => Promise<void>, onTimelineItem: (item: WorkspaceTimelineItem) => void) {
  const [reviews, setReviews] = useState<ProfessionalReview[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pendingWorkflowId, setPendingWorkflowId] = useState<string | null>(null)
  const pendingContext = useRef<WorkspaceContext | null>(null)
  const locked = useRef(false)
  const current = useRef({ context, onWorkflowLinked, onTimelineItem })
  current.current = { context, onWorkflowLinked, onTimelineItem }
  const upsert = useCallback((review: ProfessionalReview) => setReviews((items) => {
    const previous = items.find((item) => item.review_id === review.review_id)
    return previous ? items.map((item) => item.review_id === review.review_id ? review : item) : [...items, review]
  }), [])
  useEffect(() => {
    let disposed = false, pending = false
    const refresh = async () => {
      if (pending || locked.current) return
      pending = true
      try {
        const items = await getProfessionalReviews(context.workspace_id)
        if (!disposed && !locked.current) setReviews(items)
      } catch { /* Retain proposals across temporary connection failures. */ }
      finally { pending = false }
    }
    void refresh()
    const timer = context.professional_mode ? window.setInterval(() => void refresh(), 2000) : null
    return () => { disposed = true; if (timer !== null) window.clearInterval(timer) }
  }, [context.workspace_id, context.professional_mode, isSending])
  const decide = useCallback(async (id: string, decision: ProfessionalDecision) => {
    if (locked.current) return
    locked.current = true
    setBusy(true)
    setError('')
    const captured = current.current.context
    try {
      await syncWorkspaceContext(captured)
      const result = await decideProfessionalReview(id, captured, decision)
      upsert(result.review)
      if (result.next_review) upsert(result.next_review)
      if (result.workflow) {
        current.current.onTimelineItem({ eventId: `workflow-${result.workflow.workflow_id}`, kind: 'workflow', workflow: result.workflow, timestamp: result.workflow.created_at })
        pendingContext.current = captured
        setPendingWorkflowId(result.workflow.workflow_id)
        try {
          await current.current.onWorkflowLinked(result.workflow.workflow_id, captured.revision === current.current.context.revision)
          setPendingWorkflowId(null)
        } catch { setError('任务已提交，但状态同步失败，请点击“恢复任务状态”。') }
      }
    } finally { locked.current = false; setBusy(false) }
  }, [upsert])
  const recover = useCallback(async () => {
    if (!pendingWorkflowId || locked.current) return
    locked.current = true; setBusy(true)
    try {
      await current.current.onWorkflowLinked(pendingWorkflowId, pendingContext.current?.revision === current.current.context.revision)
      setPendingWorkflowId(null); setError('')
    } catch { setError('任务仍在后台，请稍后再次恢复状态。') }
    finally { locked.current = false; setBusy(false) }
  }, [pendingWorkflowId])
  return { reviews, busy, decide, error, recover, isLaunching: busy || !!pendingWorkflowId }
}
