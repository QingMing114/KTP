import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import CropDecisionCard from '../features/workspace-assistant/CropDecisionCard'
import WorkspaceRunRecord from '../features/workspace-assistant/WorkspaceRunRecord'
import type { AnalysisWorkflow } from '../services/spatialClient'

afterEach(cleanup)

const SCORES = [
  { class_id: 0, name_zh: '玉米', score: 0.29 },
  { class_id: 4, name_zh: '冬小麦', score: 0.23 },
  { class_id: 3, name_zh: '春小麦', score: 0.22 },
]
const DECISION = {
  final_class_id: 0,
  final_name_zh: '玉米',
  source: 'llm',
  confidence: 'medium',
  rationale: '7月山东邹平，冬小麦已收、夏玉米苗期；模型最高为玉米29%，与物候一致。',
  phenology: '冬小麦收获期(6月)后 · 夏玉米苗期',
  observed_at: '2026-07-12T03:20:00Z',
  location: { label: '山东 · 邹平', province: '山东省', lat: 36.95, lon: 117.8, source: 'farm_preset+admin_boundary', farm_label: '山东 · 邹平', farm_mismatch: false },
  model_prediction: { class_id: 3, name_zh: '春小麦', score: 0.22 },
  excluded_classes: [{ class_id: 4, reason: '7月冬小麦已收获' }],
  fallback_reason: null,
}

it('shows the judgement rationale next to the raw model scores', () => {
  render(<CropDecisionCard result={{ crop_decision: DECISION, class_scores: SCORES, predicted_class: { name_zh: '春小麦', score: 0.22 } }} />)
  expect(screen.getByText('农作物识别 · 判定依据')).toBeVisible()
  expect(screen.getAllByText('玉米').length).toBeGreaterThan(0)
  expect(screen.getByText(/7月山东邹平/)).toBeVisible()
  expect(screen.getByText(/地点与时间：山东 · 邹平 · 2026-07-12/)).toBeVisible()
  expect(screen.getByText(/物候判断：冬小麦收获期/)).toBeVisible()
  expect(screen.getByText(/大模型结合地点与时序判定/)).toBeVisible()
  expect(screen.getByText(/29.0%/)).toBeVisible()
  expect(screen.getByText(/排除说明：7月冬小麦已收获/)).toBeVisible()
})

it('labels the fallback path and exposes the actionable failure detail', () => {
  render(<CropDecisionCard result={{
    crop_decision: {
      ...DECISION, source: 'model_fallback',
      fallback_reason: '大模型判定失败：Upstream LLM returned a structured response that did not match the planner contract',
      fallback_detail: {
        stage: 'llm_call', error_type: 'AgentLLMError', category: 'schema_mismatch', status_code: 200,
        provider: 'OpenAICompatibleProvider', attempts: 1,
        message: 'Upstream LLM returned a structured response that did not match the planner contract: excluded_classes.0.reason Field required',
        upstream_excerpt: '{"confidence":"low","excluded_classes":[{"class_id":1,"name_zh":"棉花"}]}',
      },
    },
    class_scores: SCORES,
  }} />)
  expect(screen.getByText(/大模型不可用，回退模型最高分/)).toBeVisible()
  expect(screen.getByText(/查看失败详情/)).toBeVisible()
  expect(screen.getByText(/错误类型：AgentLLMError（schema_mismatch）/)).toBeInTheDocument()
  expect(screen.getByText(/上游状态码：200/)).toBeInTheDocument()
  expect(screen.getByText(/excluded_classes.0.reason Field required/)).toBeInTheDocument()
  expect(screen.getByText(/判定口径与既有流程一致/)).toBeVisible()
})

it('shows where the location came from and flags a farm/AOI mismatch', () => {
  const { rerender } = render(<CropDecisionCard result={{ crop_decision: DECISION, class_scores: SCORES }} />)
  expect(screen.getByText(/（农场范围 \+ 行政区反查）/)).toBeVisible()
  rerender(<CropDecisionCard result={{
    crop_decision: { ...DECISION, location: { label: '甘肃省', province: '甘肃省', farm_label: '山东 · 邹平', farm_mismatch: true, source: 'admin_boundary' } },
    class_scores: SCORES,
  }} />)
  expect(screen.getByText(/（AOI 行政区反查）/)).toBeVisible()
  expect(screen.getByText(/所选农场“山东 · 邹平”与 AOI 位置不一致，地点已按坐标反查为甘肃省/)).toBeVisible()
})

it('renders nothing for workflows stored before the decision existed', () => {
  const { container } = render(<CropDecisionCard result={{ predicted_class: { name_zh: '春小麦', score: 0.22 }, class_scores: SCORES }} />)
  expect(container).toBeEmptyDOMElement()
})

it('keeps the judgement visible in the per-turn history record', () => {
  const workflow = {
    workflow_id: 'flow', conversation_id: 'conv', run_id: 'run', status: 'blocked',
    detail: '专业模式：请确认农作物识别结果后继续', requested_task_ids: ['crop', 'lai'], effective_task_ids: ['imagery', 'crop', 'lai'],
    aoi: { geometry: {}, source: 'drawn', area_hectares: 8 }, farm_id: 'farm', imagery_item_id: 'scene',
    imagery_snapshot: { item_id: 'scene', acquired_at: '2026-07-12T03:20:00Z', cloud_cover: 3 },
    parameters: { target_resolution_m: 20, reflectance_bands: ['B02', 'B03', 'B04', 'B07', 'B08'], parameter_source: 'algorithm_fixed' },
    yield_inputs: { confirmed_crop_class_id: null }, created_at: '', updated_at: '',
    steps: [
      { step_id: 'imagery', depends_on: [], status: 'completed', progress_percent: 100, analysis_id: null, detail: '已准备', result: {} },
      { step_id: 'crop', depends_on: ['imagery'], status: 'completed', progress_percent: 100, analysis_id: 'crop-1', detail: '判定为玉米', result: { crop_decision: DECISION, class_scores: SCORES } },
    ],
  } as unknown as AnalysisWorkflow
  render(<WorkspaceRunRecord runId="run" round="run" automaticallyExpanded parts={[]} workflows={[workflow]} assistantSummary="" automatic={false} />)
  expect(screen.getByText(/本轮分析记录/)).toBeVisible()
  expect(screen.getByText('农作物识别 · 判定依据')).toBeVisible()
  expect(screen.getByText(/7月山东邹平/)).toBeVisible()
})
