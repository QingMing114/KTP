import { cloneElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WorkspaceAnalysisPanel from '../features/workspace-assistant/WorkspaceAnalysisPanel'
import WorkspaceAssistantPanel from '../features/workspace-assistant/WorkspaceAssistantPanel'
import type { WorkspaceContext } from '../services/canonical/workspaceClient'

afterEach(cleanup)
const context: WorkspaceContext = { workspace_id: 'ws', revision: 2, execution_mode: 'live', aoi: { geometry: {}, source: 'drawn', area_hectares: 8.25 }, imagery_item_id: 'image', imagery_snapshot: null, active_workflow_id: null, draft_task_ids: ['growth'] }

describe('the current analysis card', () => {
  it('keeps one launch control while old conversation actions remain read-only', () => {
    const panel = <WorkspaceAssistantPanel
      farm={{ name: '农场', locationLabel: '甘肃', areaLabel: '1286 ha' }} aoiReady aoiAreaLabel="8.25 ha" imagerySearchEndDate="2026-10-12"
      stage="ready" selectedImage="image" selectedCandidate={{ id: 'image', date: '2026-10-07', cloud: '0%', recommended: true }}
      timeline={[
        { eventId: 'old-message', kind: 'agent_message', runId: 'run', submissionId: 'sub', message: '曾请求长势分析', status: 'completed', timestamp: '2026-10-12T00:00:00Z' },
        { eventId: 'old-plan', kind: 'agent_part', runId: 'run', part: { type: 'analysis_plan', data: { imagery_item_id: null, missing_inputs: ['旧计划缺少影像'], requested_task_ids: ['growth'] } }, timestamp: '2026-10-12T00:00:00Z' },
        { eventId: 'old-action', kind: 'agent_part', runId: 'run', part: { type: 'action_card', data: { action: 'search_imagery' } }, timestamp: '2026-10-12T00:00:00Z' },
      ]}
      analysisError="" progress={0} detail="" elapsedSeconds={0} lastUpdateSeconds={null} delayed={false} connectionIssue={false} pixelProgress={null}
      reportUrl="" rasterUrl="" cropAnalysis={null} workflow={null} executionMode="live" workspaceContext={context} draftTaskIds={['growth']}
      assistantIsSending={false} assistantIsLaunching={false} imageryIsSearching={false} assistantError=""
      onFindImagery={vi.fn()} onSelectCandidate={vi.fn()} onStartAnalysis={vi.fn()} onDraftTaskIds={vi.fn()} onRetryWorkflowStep={vi.fn()} onReset={vi.fn()}
      onUpdateYieldInputs={vi.fn()} onSendAssistantMessage={vi.fn()} onCancelAssistantMessage={vi.fn()} onRecoverTask={vi.fn()}
    />
    const panels = (chat: typeof panel) => <><WorkspaceAnalysisPanel {...chat.props} />{chat}</>
    const { rerender } = render(panels(panel))
    expect(screen.getByRole('tab', { name: '分析配置' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('tabpanel', { name: '分析配置' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: '开始执行 1 项任务' })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: '搜索影像' })).toBeNull()
    expect(screen.getByText('旧计划缺少影像')).not.toBeVisible()
    expect(screen.getByText('长势评估会自动包含 LAI 反演。')).toBeVisible()
    expect(screen.getByText(/2. LAI 反演/)).toBeInTheDocument()
    expect(screen.getByText(/3. 作物长势评估/)).toBeInTheDocument()
    expect(screen.getByRole('log')).not.toContainElement(screen.getByRole('tabpanel', { name: '分析配置' }))
    expect(screen.getByRole('log')).toContainElement(screen.getByText('曾请求长势分析'))
    rerender(panels(cloneElement(panel, { timeline: [...panel.props.timeline, { eventId: 'new-message', kind: 'agent_message', runId: 'new-run', submissionId: 'new-sub', message: '最新回答', status: 'completed', timestamp: '2026-10-12T00:00:01Z' }] })))
    expect(screen.getByRole('tab', { name: '分析配置' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('最新回答')).toBeVisible()
  })
})
