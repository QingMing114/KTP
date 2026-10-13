// @vitest-environment node
import { describe, expect, it } from 'vitest'
import type { WorkspaceContext } from '../services/canonical/workspaceClient'
import { buildWorkspaceUiState, canApplyAssistantDraft } from '../features/workspace-assistant/workspaceUiContext'

const context: WorkspaceContext = {
  workspace_id: 'workspace-1', revision: 1, execution_mode: 'live', farm_id: 'farm-1',
  aoi: { geometry: { type: 'Polygon', coordinates: [[[100, 38], [100.01, 38], [100.01, 38.01], [100, 38]]] }, source: 'drawn', area_hectares: 8.25 },
  imagery_item_id: null, imagery_snapshot: null, active_workflow_id: null, draft_task_ids: [],
}

describe('original workbench cards as assistant context', () => {
  it('sends explicit image selection and the shared task card without treating a recommendation as selection', () => {
    const selected = { ...context, imagery_item_id: 'image-2', draft_task_ids: ['lai'] as const }
    const ui = buildWorkspaceUiState({ ...selected, draft_task_ids: [...selected.draft_task_ids] }, 'ready', { name: '农场', locationLabel: '甘肃', areaLabel: '1286 ha' }, [
      { id: 'image-1', date: '2026-09-10', cloud: '0%', recommended: true },
      { id: 'image-2', date: '2026-10-07', cloud: '0%', recommended: false },
    ], [])
    expect(ui.imagery_candidates.map((item) => item.selected)).toEqual([false, true])
    expect(ui.cards.find((card) => card.kind === 'task_selection')?.task_ids).toEqual(['lai'])
    expect(ui.cards.find((card) => card.kind === 'imagery_selected')?.selected_candidate_id).toBe('image-2')
  })

  it('labels an old missing-image plan as historical after the user selects imagery', () => {
    const ui = buildWorkspaceUiState({ ...context, imagery_item_id: 'image-2' }, 'ready', { name: '农场', locationLabel: '', areaLabel: '' }, [], [{
      eventId: 'old-plan', timestamp: '2026-10-12T00:00:00Z', kind: 'agent_part', part: { type: 'analysis_plan', data: { workspace_id: context.workspace_id, execution_mode: 'live', farm_id: context.farm_id, input_aoi: context.aoi!.geometry, imagery_item_id: null, missing_inputs: ['请先选择影像'], requested_task_ids: ['lai'] } },
    }])
    expect(ui.cards.find((card) => card.card_id === 'old-plan')?.state).toBe('historical')
  })

  it('keeps a pending LAI configuration when only the imagery selection changes', () => {
    expect(canApplyAssistantDraft(context, { ...context, revision: 2, imagery_item_id: 'selected' })).toBe(true)
  })

  it('does not override manually changed tasks or a different AOI', () => {
    expect(canApplyAssistantDraft(context, { ...context, revision: 2, draft_task_ids: ['crop'] })).toBe(false)
    expect(canApplyAssistantDraft(context, { ...context, revision: 2, aoi: null })).toBe(false)
  })
})
