import { useId } from 'react'
import { ChevronRight } from 'lucide-react'
import type { ProfessionalDecision, ProfessionalReview, WorkspaceContext } from '../../services/canonical/workspaceClient'
import type { WorkspaceTimelineItem } from './workspaceTimeline'
import ProfessionalReviewCard, { isProfessionalReviewCurrent } from './ProfessionalReviewCard'
import type { AnalysisWorkflow } from '../../services/spatialClient'
import { workflowTitle } from './workspaceFlow'
import { useRunRecordExpansion } from './useRunRecordExpansion'

export default function ProfessionalReviewList({ runId, reviews: allReviews, context, timeline, busy, onDecision, workflows, onOpenWorkflow, automaticallyExpanded = false }: {
  runId: string; reviews: ProfessionalReview[]; context: WorkspaceContext; timeline: WorkspaceTimelineItem[]; busy: boolean
  workflows?: ReadonlyMap<string, AnalysisWorkflow>; onOpenWorkflow?: (id: string) => void
  automaticallyExpanded?: boolean
  onDecision: (id: string, decision: ProfessionalDecision) => Promise<void>
}) {
  const listId = useId()
  const reviews = allReviews.filter((review) => review.source_run_id === runId && review.workspace_id === context.workspace_id)
  const latestMessage = timeline.filter((item) => item.kind === 'agent_user_message' || item.kind === 'agent_message').at(-1)
  const latestUser = timeline.filter((item) => item.kind === 'agent_user_message').at(-1)
  const round = latestUser?.eventId ?? latestMessage?.eventId ?? 'restored'
  // A refreshed workspace may recover confirmations before its conversation.
  const currentRun = latestMessage?.kind === 'agent_message' ? latestMessage.runId : latestMessage ? undefined : runId
  const activeIds = new Set(reviews.filter((review) => ['pending', 'processing'].includes(review.status)
    && isProfessionalReviewCurrent(review, context) && review.source_run_id === currentRun).map((review) => review.review_id))
  const historyCount = reviews.length - activeIds.size
  const { expanded, toggle } = useRunRecordExpansion(round, automaticallyExpanded)
  const replyIndex = timeline.findIndex((item) => item.kind === 'agent_message' && item.runId === runId)
  const request = timeline.slice(0, replyIndex < 0 ? 0 : replyIndex).reverse().find((item) => item.kind === 'agent_user_message')
  const parts = timeline.flatMap((item) => item.kind === 'agent_part' && item.runId === runId ? [item.part] : [])
  const firstHistoricalId = reviews.find((item) => !activeIds.has(item.review_id))?.review_id
  if (!reviews.length) return null
  return <div id={listId} data-professional-run={runId} data-run-record={runId} data-run-record-expanded={expanded ? 'true' : undefined} data-active-review={activeIds.size ? 'true' : undefined} className="mt-2 flex flex-col gap-2">
    {reviews.map((review) => {
      const historical = !activeIds.has(review.review_id)
      const workflow = review.workflow_id ? workflows?.get(review.workflow_id) : undefined
      const date = new Date(review.created_at)
      // Keep each editor mounted so collapsing a round preserves its draft.
      return <div key={review.review_id} hidden={historical && !expanded} style={{ order: historical ? 2 : 0 }}>
        {historical && firstHistoricalId === review.review_id && <div className="mb-2 mt-2 border-t border-white/10 pt-3" data-history-run={runId}>
          <p className="text-[10px] font-medium text-emerald-100">{Number.isNaN(date.getTime()) ? '历史任务' : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })} · {workflowTitle(reviews.find((item) => item.phase === 'workflow')?.intent.task_ids ?? review.intent.task_ids)}</p>
          {request?.kind === 'agent_user_message' && <p className="mt-1 whitespace-pre-wrap break-words text-[10px] text-slate-400">需求：{request.message}</p>}
        </div>}
        <ProfessionalReviewCard review={review} context={context} busy={busy} compact={historical} expandedHistory={expanded && automaticallyExpanded} onDecision={onDecision} parts={parts} workflow={workflow} onOpenWorkflow={onOpenWorkflow} />
      </div>
    })}
    {!!historyCount && <button type="button" aria-expanded={expanded} aria-controls={listId}
      onClick={toggle} style={{ order: 1 }}
      className="flex items-center gap-1.5 px-1 py-1 text-left text-[10px] text-slate-500 hover:text-slate-300">
      <ChevronRight size={12} className={expanded ? 'rotate-90' : ''} />本轮分析记录（{historyCount}）
    </button>}
  </div>
}
