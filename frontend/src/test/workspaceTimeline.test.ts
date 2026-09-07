// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { latestWorkspaceTimelineItem, workspaceTimelineReducer, type WorkspaceTimelineItem } from '../features/workspace-assistant/workspaceTimeline'

const aoi: WorkspaceTimelineItem = {
  eventId: 'aoi-1',
  kind: 'aoi_ready',
  areaLabel: '12.48 ha',
  timestamp: '2026-07-20T10:00:00Z',
}

describe('workspaceTimelineReducer', () => {
  it('appends independent cards in their original order', () => {
    const candidates: WorkspaceTimelineItem = {
      eventId: 'candidates-1',
      kind: 'imagery_candidates',
      candidates: [],
      timestamp: '2026-07-20T10:01:00Z',
    }

    const state = workspaceTimelineReducer(
      workspaceTimelineReducer([], { type: 'upsert', item: aoi }),
      { type: 'upsert', item: candidates },
    )

    expect(state.map((item) => item.eventId)).toEqual(['aoi-1', 'candidates-1'])
  })

  it('updates one analysis progress card rather than adding duplicate SSE cards', () => {
    const initial = workspaceTimelineReducer([], {
      type: 'upsert',
      item: {
        eventId: 'analysis-progress-1',
        kind: 'analysis_progress',
        analysisId: 'analysis-1',
        progress: 5,
        detail: '正在获取影像',
        timestamp: '2026-07-20T10:02:00Z',
      },
    })
    const updated = workspaceTimelineReducer(initial, {
      type: 'upsert',
      item: {
        eventId: 'analysis-progress-1',
        kind: 'analysis_progress',
        analysisId: 'analysis-1',
        progress: 72,
        detail: '正在进行 LAI 反演',
        timestamp: '2026-07-20T10:03:00Z',
      },
    })

    expect(updated).toHaveLength(1)
    expect(updated[0]).toMatchObject({ progress: 72, detail: '正在进行 LAI 反演' })
  })

  it('returns the latest card of a requested kind and removes obsolete error cards', () => {
    const withError = [
      aoi,
      { eventId: 'error-1', kind: 'error' as const, detail: '搜索失败', timestamp: '2026-07-20T10:02:00Z' },
      { eventId: 'error-2', kind: 'error' as const, detail: '反演失败', timestamp: '2026-07-20T10:03:00Z' },
    ]

    expect(latestWorkspaceTimelineItem(withError, 'error')?.detail).toBe('反演失败')
    expect(workspaceTimelineReducer(withError, { type: 'removeKinds', kinds: ['error'] })).toEqual([aoi])
  })
})
