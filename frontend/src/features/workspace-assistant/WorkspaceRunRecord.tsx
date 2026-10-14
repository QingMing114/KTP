import { useId } from 'react'
import { ChevronRight } from 'lucide-react'
import type { CanonicalAssistantPart } from '../../services/canonical/workspaceClient'
import type { AnalysisWorkflow } from '../../services/spatialClient'
import AnalysisDetails from './AnalysisDetails'
import LaiSceneParameters from './LaiSceneParameters'
import { workflowTitle, workflowStatusLabel } from './workspaceFlow'
import { useRunRecordExpansion } from './useRunRecordExpansion'

const STEP_STATUS = { planned: '待执行', waiting: '等待依赖', running: '执行中', completed: '已完成', blocked: '待补充', failed: '失败', skipped: '已跳过' }

export default function WorkspaceRunRecord({ runId, round, automaticallyExpanded, parts, workflows, assistantSummary, automatic }: {
  runId: string; round: string; automaticallyExpanded: boolean; parts: CanonicalAssistantPart[]
  workflows: AnalysisWorkflow[]; assistantSummary: string; automatic: boolean
}) {
  const contentId = useId()
  const { expanded, toggle } = useRunRecordExpansion(round, automaticallyExpanded)
  if (!parts.length && !workflows.length) return null
  return <section data-run-record={runId} data-run-record-expanded={expanded ? 'true' : undefined} className="mt-2 text-[11px] leading-5 text-slate-300">
    <button type="button" aria-expanded={expanded} aria-controls={contentId} onClick={toggle} className="flex items-center gap-1 py-1 text-emerald-100">
      <ChevronRight size={12} className={expanded ? 'rotate-90' : ''} />本轮分析记录
    </button>
    <div id={contentId} hidden={!expanded} className="mt-2 space-y-3">
      {!!parts.length && <AnalysisDetails parts={parts} expanded demo={workflows.some((flow) => flow.data_mode === 'demo')} />}
      {workflows.map((flow) => <div key={flow.workflow_id} className="space-y-3 rounded-lg border border-white/10 bg-black/10 p-3">
        <h3 className="font-medium text-emerald-100">{workflowTitle(flow.requested_task_ids)} · {workflowStatusLabel(flow)}</h3>
        <div><h4 className="font-medium text-emerald-100">影像与选片依据</h4>
          <p className="mt-1">观测日期：{flow.imagery_snapshot.acquired_at.slice(0, 10)}</p>
          <p className="break-all">影像：{flow.imagery_item_id}</p>
          <p>云量：{flow.imagery_snapshot.cloud_cover != null ? `${flow.imagery_snapshot.cloud_cover}%` : '未记录'} · 覆盖率：{flow.imagery_snapshot.coverage_percent != null ? `${flow.imagery_snapshot.coverage_percent.toFixed(1)}%` : '未记录'}</p>
          {flow.imagery_snapshot.recommendation_reason && <p className="mt-1 whitespace-pre-wrap text-slate-400">候选推荐说明（系统）：{flow.imagery_snapshot.recommendation_reason}</p>}
          {automatic && assistantSummary.includes('已自动选择') && <p className="mt-1 whitespace-pre-wrap text-slate-400">选片与启动说明（保存的助手答复）：{assistantSummary}</p>}
        </div>
        <div><h4 className="font-medium text-emerald-100">任务执行过程</h4>
          <ol className="mt-2 space-y-2">{flow.steps.map((step, index) => <li key={step.step_id}>
            <p>{index + 1}. {step.step_id === 'imagery' ? '影像准备' : workflowTitle([step.step_id])}<span className="ml-2 text-emerald-200">{STEP_STATUS[step.status]}</span></p>
            {!!step.depends_on.length && <p className="text-slate-500">依赖：{step.depends_on.map((id) => id === 'imagery' ? '影像准备' : workflowTitle([id])).join('、')}</p>}
            <p className="whitespace-pre-wrap text-slate-400">{step.detail}</p>
          </li>)}</ol>
        </div>
        {flow.parameters && <div><h4 className="font-medium text-emerald-100">实际算法配置</h4><p className="mt-1">分辨率：{flow.parameters.target_resolution_m} m</p><p>共享波段：{flow.parameters.reflectance_bands.join(' / ')}</p></div>}
        {flow.steps.filter((step) => step.step_id === 'lai').map((step) => <LaiSceneParameters key={step.step_id} step={step} showRequested />)}
        {flow.requested_task_ids.includes('yield') && <div><h4 className="font-medium text-emerald-100">APSIM 输入记录</h4><p className="mt-1">地块资料：{flow.yield_inputs.field_dataset_id ?? '未提供'}</p><p>播种日期：{flow.yield_inputs.sowing_date ?? '未提供'}</p><p>品种：{flow.yield_inputs.cultivar ?? '未提供'}</p></div>}
      </div>)}
    </div>
  </section>
}
