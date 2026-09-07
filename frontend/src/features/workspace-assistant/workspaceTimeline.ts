export interface WorkspaceCandidateCardItem {
  id: string
  date: string
  cloud: string
  recommended: boolean
}

interface WorkspaceTimelineBase {
  eventId: string
  timestamp: string
}

export interface WorkspaceAoiTimelineItem extends WorkspaceTimelineBase {
  kind: 'aoi_ready'
  areaLabel: string
}

export interface WorkspaceCandidatesTimelineItem extends WorkspaceTimelineBase {
  kind: 'imagery_candidates'
  candidates: WorkspaceCandidateCardItem[]
}

export interface WorkspaceSelectionTimelineItem extends WorkspaceTimelineBase {
  kind: 'imagery_selected'
  candidateId: string
}

export interface WorkspaceAnalysisProgressTimelineItem extends WorkspaceTimelineBase {
  kind: 'analysis_progress'
  analysisId?: string
  progress: number
  detail: string
}

export interface WorkspaceAnalysisResultTimelineItem extends WorkspaceTimelineBase {
  kind: 'analysis_result'
  analysisId?: string
}

export interface WorkspaceErrorTimelineItem extends WorkspaceTimelineBase {
  kind: 'error'
  detail: string
}

export interface WorkspaceUserMessageTimelineItem extends WorkspaceTimelineBase {
  kind: 'agent_user_message'
  message: string
}

export interface WorkspaceAgentMessageTimelineItem extends WorkspaceTimelineBase {
  kind: 'agent_message'
  message: string
  submissionId: string
  runId?: string
  status: 'streaming' | 'completed' | 'failed'
}

export type WorkspaceTimelineItem =
  | WorkspaceAoiTimelineItem
  | WorkspaceCandidatesTimelineItem
  | WorkspaceSelectionTimelineItem
  | WorkspaceAnalysisProgressTimelineItem
  | WorkspaceAnalysisResultTimelineItem
  | WorkspaceErrorTimelineItem
  | WorkspaceUserMessageTimelineItem
  | WorkspaceAgentMessageTimelineItem

export type WorkspaceTimelineAction =
  | { type: 'upsert'; item: WorkspaceTimelineItem }
  | { type: 'removeKinds'; kinds: WorkspaceTimelineItem['kind'][] }
  | { type: 'reset' }

/**
 * Updates preserve the original card position.  This lets high-frequency LAI
 * progress events update one existing card instead of pushing a new card for
 * every SSE message.
 */
export function workspaceTimelineReducer(
  state: WorkspaceTimelineItem[],
  action: WorkspaceTimelineAction,
): WorkspaceTimelineItem[] {
  if (action.type === 'reset') return []
  if (action.type === 'removeKinds') {
    return state.filter((item) => !action.kinds.includes(item.kind))
  }

  const index = state.findIndex((item) => item.eventId === action.item.eventId)
  if (index < 0) return [...state, action.item]
  const next = [...state]
  next[index] = action.item
  return next
}

export function createWorkspaceTimelineEventId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function latestWorkspaceTimelineItem<TKind extends WorkspaceTimelineItem['kind']>(
  items: WorkspaceTimelineItem[],
  kind: TKind,
): Extract<WorkspaceTimelineItem, { kind: TKind }> | undefined {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index]
    if (item.kind === kind) return item as Extract<WorkspaceTimelineItem, { kind: TKind }>
  }
  return undefined
}
