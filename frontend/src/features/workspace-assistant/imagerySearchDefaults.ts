import type { WorkspaceContext } from '../../services/canonical/workspaceClient'

export function defaultManualImageryDates(now = new Date()): { start: string; end: string } {
  const start = new Date(now)
  start.setDate(start.getDate() - 365)
  const format = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  return { start: format(start), end: format(now) }
}

export function assistantImagerySearch(autoExecute: boolean, start: string, end: string): WorkspaceContext['imagery_search'] {
  return autoExecute ? undefined : { start_date: start || undefined, end_date: end || undefined, max_cloud_cover: 20 }
}
