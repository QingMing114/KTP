import { useEffect, useState } from 'react'
import { getLastLoginUser } from '../../services/api'
import type { ProfessionalReview, WorkspaceContext } from '../../services/canonical/workspaceClient'
import type { AnalysisWorkflow } from '../../services/spatialClient'
import type { WorkspaceTimelineItem } from './workspaceTimeline'
import { isProfessionalReviewCurrent } from './ProfessionalReviewCard'

type Message = Extract<WorkspaceTimelineItem, { kind: 'agent_user_message' | 'agent_message' }>

function readKeys(scope: string): string[] {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(scope) ?? '[]')
    return Array.isArray(value) ? value.filter((key): key is string => typeof key === 'string') : []
  } catch { return [] }
}

/** Visibility preferences only; the timeline, conversation and tasks stay intact. */
export function useWorkspaceHistoryVisibility(timeline: WorkspaceTimelineItem[], context: WorkspaceContext,
  reviews: ProfessionalReview[], workflows: ReadonlyMap<string, AnalysisWorkflow>, unattached: AnalysisWorkflow[]) {
  const scope = `ktp_workspace_hidden_history:${JSON.stringify([getLastLoginUser(), context.workspace_id])}`
  const [stored, setStored] = useState(() => ({ scope, keys: readKeys(scope) }))
  const [error, setError] = useState('')
  const hiddenKeys = new Set(stored.scope === scope ? stored.keys : readKeys(scope))
  useEffect(() => {
    setStored({ scope, keys: readKeys(scope) }); setError('')
    const sync = (event: StorageEvent) => {
      if (event.key === scope || event.key === null) setStored({ scope, keys: readKeys(scope) })
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [scope])

  const messages = timeline.filter((item): item is Message => item.kind === 'agent_user_message' || item.kind === 'agent_message')
  const messageKeys = new Map<string, string>()
  messages.forEach((item, index) => {
    let runId = item.kind === 'agent_message' ? item.runId : undefined
    if (item.kind === 'agent_user_message') {
      for (const following of messages.slice(index + 1)) {
        if (following.kind === 'agent_user_message') break
        if (following.runId) { runId = following.runId; break }
      }
    }
    messageKeys.set(item.eventId, runId ? `run:${runId}` : `event:${item.eventId}`)
  })
  const protectedKeys = new Set<string>()
  const protectRun = (runId?: string | null) => { if (runId) protectedKeys.add(`run:${runId}`) }
  for (const item of messages) {
    if (item.kind === 'agent_message' && item.status === 'streaming') {
      protectedKeys.add(messageKeys.get(item.eventId)!); protectRun(item.runId)
    }
  }
  for (const flow of workflows.values()) {
    if (['planned', 'running'].includes(flow.status) || (flow.status === 'blocked' && flow.workflow_id === context.active_workflow_id)) {
      protectedKeys.add(`workflow:${flow.workflow_id}`); protectRun(flow.run_id)
    }
  }
  const latest = messages.at(-1)
  const latestRun = latest?.kind === 'agent_message' ? latest.runId : undefined
  for (const review of reviews) {
    if (['pending', 'processing'].includes(review.status)
      && (review.source_run_id === latestRun || (review.phase === 'lai' && review.workflow_id === context.active_workflow_id))
      && isProfessionalReviewCurrent(review, { ...context, professional_mode: true })) protectRun(review.source_run_id)
  }
  const isHiddenKey = (key: string) => hiddenKeys.has(key) && !protectedKeys.has(key)
  const isHiddenMessage = (item: Message) => isHiddenKey(messageKeys.get(item.eventId)!)
  const isHiddenWorkflow = (flow: AnalysisWorkflow) => isHiddenKey(`workflow:${flow.workflow_id}`) || (!!flow.run_id && isHiddenKey(`run:${flow.run_id}`))
  const clearableKeys = messages.filter((item) => !isHiddenMessage(item) && !protectedKeys.has(messageKeys.get(item.eventId)!)).map((item) => messageKeys.get(item.eventId)!)
  for (const flow of unattached) {
    if (!isHiddenWorkflow(flow) && !protectedKeys.has(`workflow:${flow.workflow_id}`)) clearableKeys.push(`workflow:${flow.workflow_id}`)
  }
  const hasHidden = messages.some(isHiddenMessage) || unattached.some(isHiddenWorkflow)
  const clear = () => {
    if (!clearableKeys.length) return
    const keys = [...new Set([...readKeys(scope), ...clearableKeys])]
    try {
      window.localStorage.setItem(scope, JSON.stringify(keys))
      setStored({ scope, keys }); setError('')
    } catch { setError('未能保存列表显示设置，请稍后重试。') }
  }
  const restore = () => {
    const currentKeys = new Set([...messageKeys.values(), ...unattached.flatMap((flow) => [`workflow:${flow.workflow_id}`, ...(flow.run_id ? [`run:${flow.run_id}`] : [])])])
    const keys = readKeys(scope).filter((key) => !currentKeys.has(key))
    try {
      if (keys.length) window.localStorage.setItem(scope, JSON.stringify(keys))
      else window.localStorage.removeItem(scope)
      setStored({ scope, keys }); setError('')
    } catch { setError('未能恢复列表显示设置，请稍后重试。') }
  }
  return { messages, isHiddenMessage, isHiddenWorkflow, hasHidden, canClear: !!clearableKeys.length, clear, restore, error }
}
