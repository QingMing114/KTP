import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import WorkspaceRunRecord from '../features/workspace-assistant/WorkspaceRunRecord'
import type { AnalysisWorkflow } from '../services/spatialClient'
import type { CanonicalAssistantPart } from '../services/canonical/workspaceClient'

afterEach(cleanup)
const workflow: AnalysisWorkflow = { workflow_id: 'flow', run_id: 'run', status: 'completed', detail: '完成', aoi: { geometry: {}, source: 'drawn', area_hectares: 10 }, imagery_item_id: 'image', imagery_snapshot: { item_id: 'image', collection: 'sentinel-2-l2a', acquired_at: '2026-09-10T00:00:00Z', cloud_cover: 3, coverage_percent: 100, is_recommended: true }, requested_task_ids: ['lai'], effective_task_ids: ['lai'], parameters: { target_resolution_m: 20, reflectance_bands: ['B02', 'B03'], parameter_source: 'algorithm_fixed' }, yield_inputs: { confirmed_crop_class_id: null, field_dataset_id: null, sowing_date: null, cultivar: null }, steps: [{ step_id: 'lai', status: 'completed', progress_percent: 100, detail: '真实反演已完成', depends_on: ['imagery'], result: { scene_parameters: { source: 'llm', reasoning: '根据作物和影像月份配置范围。', lai_range: [0, 2], cab_range: null, lidfa_range: null, psoil_range: null }, constraint_application: { status: 'applied', effective: { lai_range: [0, 2] }, used_rows: 10 } } }], created_at: '', updated_at: '' }
const parts: CanonicalAssistantPart[] = [{ type: 'analysis_plan', data: { rationale: '本轮保存的任务规划依据' } }, { type: 'parameter_set', data: { state: 'effective', parameters: [{ name: '影像准备分辨率', value: 20, unit: 'm', source: 'algorithm_fixed', editable: false }] } }]
function record(expanded = true, round = 'user-1', flows = [workflow]) {
  return <WorkspaceRunRecord runId="run" round={round} automaticallyExpanded={expanded} parts={parts} workflows={flows} assistantSummary="已自动选择当前影像，启动反演。" automatic />
}
it('directly displays saved planning, selected imagery, task steps and actual parameter ranges', () => {
  render(record())
  expect(screen.getByRole('button', { name: '本轮分析记录' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByText('本轮保存的任务规划依据')).toBeVisible()
  expect(screen.getByText('影像准备分辨率')).toBeVisible()
  expect(screen.getByText('根据作物和影像月份配置范围。')).toBeVisible()
  expect(screen.getByText('真实反演已完成')).toBeVisible()
  const row = within(screen.getByRole('table', { name: 'LAI 配置与生效范围' })).getAllByRole('row')[1]
  expect(within(row).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['LAI', '0–2 m²/m²', '0–2 m²/m²'])
})
it('respects manual collapse and folds the previous record when the next turn begins', () => {
  const { rerender } = render(record())
  const toggle = screen.getByRole('button', { name: '本轮分析记录' })
  fireEvent.click(toggle)
  rerender(record())
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  fireEvent.click(toggle)
  rerender(record(false, 'user-2'))
  expect(screen.getByText('本轮保存的任务规划依据')).not.toBeVisible()
})
it('shows missing effective data explicitly rather than treating the configured range as applied', () => {
  const missing = { ...workflow, steps: workflow.steps.map((step) => ({ ...step, result: { scene_parameters: step.result.scene_parameters } })) }
  render(record(true, 'user-1', [missing]))
  const row = within(screen.getByRole('table', { name: 'LAI 配置与生效范围' })).getAllByRole('row')[1]
  expect(within(row).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['LAI', '0–2 m²/m²', '尚未记录'])
})
