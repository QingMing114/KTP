import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ProfessionalTaskCard, WorkflowCard } from '../features/workspace-assistant/WorkspaceAnalysisCards'
import type { AnalysisWorkflow } from '../services/spatialClient'

vi.mock('../services/spatialClient', async (original) => ({ ...await original<typeof import('../services/spatialClient')>(), loadHtmlReportObjectUrl: vi.fn(async () => 'blob:demo-report') }))

afterEach(cleanup)
it('starts a crop-specific demo without calling the real execution button', () => {
  const start = vi.fn(), demo = vi.fn()
  render(<ProfessionalTaskCard initialTaskIds={['yield_simple']} executionMode="live" onDraftTasks={vi.fn()} onStartTasks={start} onStartYieldDemo={demo} />)
  fireEvent.change(screen.getByLabelText('演示作物'), { target: { value: 'maize' } })
  fireEvent.click(screen.getByRole('button', { name: '演示估产与报告' }))
  expect(demo).toHaveBeenCalledWith('maize')
  expect(start).not.toHaveBeenCalled()
  expect(screen.getByText(/数值不代表实际产量/)).toBeInTheDocument()
})
it('locks demo launch during submission and for mixed real-task selection', () => {
  const props = { executionMode: 'live' as const, onDraftTasks: vi.fn(), onStartTasks: vi.fn(), onStartYieldDemo: vi.fn() }
  const { rerender } = render(<ProfessionalTaskCard {...props} initialTaskIds={['yield_simple']} disabled />)
  expect(screen.getByRole('button', { name: '演示估产与报告' })).toBeDisabled()
  rerender(<ProfessionalTaskCard {...props} initialTaskIds={['lai', 'yield_simple']} />)
  expect(screen.getByRole('button', { name: '演示估产与报告' })).toBeDisabled()
})
it('labels completed simulated results and opens the APSIM template report', async () => {
  const flow: AnalysisWorkflow = { data_mode: 'demo', demo_crop: 'maize', workflow_id: 'demo-flow', status: 'completed', detail: '模拟演示已完成',
    aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, imagery_item_id: 'scene', imagery_snapshot: { item_id: 'scene', collection: 'sentinel-2-l2a', acquired_at: '2026-09-10', is_recommended: false },
    requested_task_ids: ['yield_simple'], effective_task_ids: ['crop', 'yield_simple'], created_at: '', updated_at: '',
    yield_inputs: { confirmed_crop_class_id: null, cultivar: null, sowing_date: null, field_dataset_id: null },
    steps: [{ step_id: 'yield_simple', depends_on: ['crop'], status: 'completed', progress_percent: 100, detail: '模拟结果', result: { estimated_yield_t_ha: 9.1, estimated_total_t: 72.8, parameter_scenario_range_t_ha: [8, 10.2], season: { start: '2025-05-10', end: '2025-09-20', observations: 134 }, report_uri: '/api/product/v1/artifacts/demo-report/render' } }] }
  render(<WorkflowCard workflow={flow} onRetry={vi.fn()} onUpdateYieldInputs={vi.fn()} onReset={vi.fn()} />)
  expect(screen.getByText(/模拟单产.*9.10/)).toBeInTheDocument()
  expect(screen.getByText(/示例总产量 72.80/)).toBeInTheDocument()
  expect(screen.getByText(/134 条模拟记录/)).toBeInTheDocument()
  expect(await screen.findByRole('link', { name: /查看估产演示报告/ })).toHaveAttribute('href', 'blob:demo-report')
  expect(screen.queryByText(/次清晰观测/)).not.toBeInTheDocument()
})
