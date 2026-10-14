import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import LaiSceneParameters from '../features/workspace-assistant/LaiSceneParameters'
import type { AnalysisWorkflowStep } from '../services/spatialClient'

afterEach(cleanup)
const step: AnalysisWorkflowStep = {
  step_id: 'lai', depends_on: ['imagery'], status: 'running', progress_percent: 5, detail: '', result: {},
}

it('shows pending configuration without claiming that parameters have taken effect', () => {
  const view = render(<LaiSceneParameters step={step} />)
  expect(screen.getByText(/正在自动配置/)).toBeInTheDocument()
  view.rerender(<LaiSceneParameters step={{ ...step, result: { scene_parameters: { source: 'llm', lai_range: [4, 5] } } }} />)
  expect(screen.getByText(/待反演核验/)).toBeInTheDocument()
  expect(screen.queryByText(/已生效/)).not.toBeInTheDocument()
})

it('shows effective ranges from inversion and identifies the model source', () => {
  render(<LaiSceneParameters step={{ ...step, status: 'completed', result: {
    scene_parameters: { source: 'llm', reasoning: '结合影像日期配置' },
    constraint_application: { status: 'applied', effective: { lai_range: [4, 5], cab_range: [40, 70] }, used_rows: 20 },
  } }} />)
  expect(screen.getByText(/LAI 自动参数 · 已生效/)).toBeInTheDocument()
  expect(screen.getByText('配置来源：大模型')).toBeInTheDocument()
  expect(screen.getByText('4–5 m²/m²')).toBeInTheDocument()
  expect(screen.getByText('40–70 μg/cm²')).toBeInTheDocument()
})

it('discloses rule and LUT fallbacks without displaying rejected ranges as effective', () => {
  render(<LaiSceneParameters step={{ ...step, status: 'completed', result: {
    scene_parameters: { source: 'rule_based', lai_range: [9, 10] },
    constraint_application: { status: 'fallback', effective: {}, reason: '场景范围匹配不足10条，已使用完整 LUT。', used_rows: 30 },
  } }} />)
  expect(screen.getByText(/规则回退/)).toBeInTheDocument()
  expect(screen.getByText(/匹配不足10条/)).toBeInTheDocument()
  expect(screen.queryByText('9–10 m²/m²')).not.toBeInTheDocument()
})
