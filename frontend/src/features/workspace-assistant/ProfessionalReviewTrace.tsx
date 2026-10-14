import type { CanonicalAssistantPart, LaiParameterRanges, ProfessionalDecision, ProfessionalReview } from '../../services/canonical/workspaceClient'
import type { AnalysisWorkflow, WorkflowTaskId } from '../../services/spatialClient'
import { workflowTitle } from './workspaceFlow'

const RANGES = [
  ['lai_range', 'LAI', 'm²/m²'], ['cab_range', '叶绿素 Cab', 'μg/cm²'],
  ['lidfa_range', '叶倾角', '°'], ['psoil_range', '土壤参数', ''],
] as const
const STEP_STATUS = { planned: '待执行', waiting: '等待依赖', running: '执行中', completed: '已完成', blocked: '待补充', failed: '失败', skipped: '已跳过' }
const sourceLabel = (source?: string) => source === 'llm' ? '大模型推荐' : source === 'rule_based' ? '规则推荐' : source === 'user_confirmed' ? '用户确认' : '未记录'
const rangeLabel = (value: unknown, unit: string) => value === null ? '不限制范围' : Array.isArray(value) && value.length === 2 ? `${value[0]}–${value[1]}${unit ? ` ${unit}` : ''}` : '未记录'
const stepTitle = (id: string) => id === 'imagery' ? '影像准备' : workflowTitle([id as WorkflowTaskId])

export default function ProfessionalReviewTrace({ review, parts = [], workflow, onOpenWorkflow }: {
  review: ProfessionalReview; parts?: CanonicalAssistantPart[]; workflow?: AnalysisWorkflow
  onOpenWorkflow?: (id: string) => void
}) {
  const confirmed = review.status === 'confirmed' ? review.confirmed_parameters : null
  const search = confirmed?.search as ProfessionalDecision['search'] | undefined
  const scene = confirmed?.scene as LaiParameterRanges | undefined
  const plan = parts.find((part) => part.type === 'analysis_plan')?.data
  const planningReason = plan?.rationale || review.intent.rationale || (review.phase !== 'lai' ? review.rationale : '')
  const selectedId = typeof confirmed?.imagery_item_id === 'string' ? confirmed.imagery_item_id : null
  const confirmedTasks = Array.isArray(confirmed?.task_ids) ? confirmed.task_ids as WorkflowTaskId[] : null
  const steps = workflow?.steps ?? plan?.steps
  const lai = workflow?.steps.find((step) => step.step_id === 'lai')
  const application = lai?.result.constraint_application as { status?: string; effective?: Partial<LaiParameterRanges>; reason?: string; matched_rows?: number; used_rows?: number } | undefined
  const recommended = review.proposed_scene
  return <div className="mt-3 space-y-3 text-[11px] leading-5 text-slate-300">
    {review.intent.summary && <div><h4 className="font-medium text-emerald-100">任务理解</h4><p className="mt-1 whitespace-pre-wrap">{review.intent.summary}</p></div>}
    {review.phase !== 'lai' && <div><h4 className="font-medium text-emerald-100">{review.phase === 'search' ? '搜索条件依据' : '任务规划依据'}</h4><p className="mt-1 whitespace-pre-wrap">{planningReason || '该轮未保存决策说明。'}</p></div>}
    {review.phase === 'search' && <Comparison label="影像搜索条件" headers={['条件', '推荐值', '确认值']} rows={[
      ['开始日期', review.search?.start_date ?? '未记录', search?.start_date ?? '未确认'],
      ['结束日期', review.search?.end_date ?? '未记录', search?.end_date ?? '未确认'],
      ['云量上限', review.search ? `${review.search.max_cloud_cover}%` : '未记录', search?.max_cloud_cover != null ? `${search.max_cloud_cover}%` : '未确认'],
    ]} />}
    {review.phase === 'workflow' && <>
      <div><h4 className="font-medium text-emerald-100">影像选择依据</h4>
        <p className="mt-1">推荐影像：<span className="break-all">{review.selected_imagery_id ?? '未记录'}</span></p>
        <p>确认影像：<span className="break-all">{selectedId ?? '未确认'}</span></p>
        <p className="mt-1 text-slate-400">候选推荐说明（系统）：{review.candidates.find((item) => item.is_recommended)?.recommendation_reason || '该轮未保存排序说明；以下为搜索返回的候选指标。'}</p>
        {!!review.candidates.length && <Comparison label="候选影像对比" headers={['日期 / 影像', '云量', '覆盖率', '选择记录']} rows={review.candidates.map((item) => [
          `${item.acquired_at.slice(0, 10)} · ${item.item_id}`, item.cloud_cover != null ? `${item.cloud_cover}%` : '未记录',
          item.coverage_percent != null ? `${item.coverage_percent.toFixed(1)}%` : '未记录',
          [item.is_recommended ? '系统推荐' : '', item.item_id === selectedId ? '用户确认' : ''].filter(Boolean).join(' · ') || '候选',
        ])} />}
      </div>
      <div><h4 className="font-medium text-emerald-100">专业任务与执行顺序</h4>
        <p className="mt-1">推荐任务：{workflowTitle(review.intent.task_ids)}</p>
        <p>确认任务：{confirmedTasks ? workflowTitle(confirmedTasks) : '未确认'}</p>
        {steps?.length ? <ol className="mt-2 space-y-2">{steps.map((step, i) => <li key={step.step_id}>
          <p>{i + 1}. {stepTitle(step.step_id)}{'status' in step && <span className="ml-2 text-emerald-200">{STEP_STATUS[step.status]}</span>}</p>
          {!!step.depends_on.length && <p className="text-slate-500">依赖：{step.depends_on.map(stepTitle).join('、')}</p>}
          {'detail' in step && <p className="whitespace-pre-wrap text-slate-400">{step.detail}</p>}
        </li>)}</ol> : <p className="text-slate-500">该轮尚未保存执行步骤。</p>}
        {confirmedTasks?.includes('yield') && <p className="mt-2">确认 APSIM 方式：{confirmed?.apsim_mode === 'example' ? '真实示例模拟' : confirmed?.apsim_mode === 'field' ? '地块情景估产' : '未记录'}</p>}
        {workflow?.requested_task_ids.includes('yield') && <div className="mt-2 text-slate-400"><p>地块资料：{workflow.yield_inputs.field_dataset_id ?? '未提供'}</p><p>播种日期：{workflow.yield_inputs.sowing_date ?? '未提供'}</p><p>品种：{workflow.yield_inputs.cultivar ?? '未提供'}</p></div>}
      </div>
      {workflow?.parameters && <div><h4 className="font-medium text-emerald-100">固定算法配置</h4><p className="mt-1">分辨率：{workflow.parameters.target_resolution_m} m</p><p>共享波段：{workflow.parameters.reflectance_bands.join(' / ')}</p><p className="text-slate-500">来自工作流实际配置。</p></div>}
      {parts.some((part) => part.type === 'parameter_set' && part.data?.parameters?.length) && <div><h4 className="font-medium text-emerald-100">规划参数记录</h4>{parts.filter((part) => part.type === 'parameter_set').map((part, i) => <dl key={part.part_id ?? i}>{part.data?.parameters?.map((parameter) => <div key={parameter.name}><dt className="text-slate-500">{parameter.name} · {part.data?.state === 'effective' ? '已生效' : '草案'}</dt><dd className="break-all">{parameter.value} {parameter.unit}</dd></div>)}</dl>)}</div>}
    </>}
    {review.phase === 'lai' && <>
      <div><h4 className="font-medium text-emerald-100">参数配置依据</h4><p className="mt-1">推荐来源：{sourceLabel(recommended?.source)}</p><p className="mt-1 whitespace-pre-wrap">{recommended?.reasoning || review.rationale || '该轮未保存参数配置说明。'}</p>
        {(recommended?.crop_type || recommended?.region || recommended?.growth_stage) && <p className="mt-2 text-slate-400">推荐场景：{[recommended.crop_type, recommended.region, recommended.month ? `${recommended.month}月` : '', recommended.growth_stage].filter(Boolean).join(' · ')}</p>}
        {recommended?.context?.acquired_at && <p className="text-slate-400">依据影像日期：{recommended.context.acquired_at.slice(0, 10)}</p>}
        {recommended?.context?.crop_prediction && <p className="text-slate-400">上游作物识别：{recommended.context.crop_prediction.name_zh || recommended.context.crop_prediction.name || '未记录'}</p>}
      </div>
      <Comparison label="LAI 参数对比" headers={['参数', '推荐值', '用户确认', '实际生效']} rows={RANGES.map(([key, label, unit]) => [label, rangeLabel(recommended?.[key], unit), scene ? rangeLabel(scene[key], unit) : '未确认',
        application?.status === 'applied' ? application.effective ? rangeLabel(application.effective[key] ?? null, unit) : '未记录'
          : application?.status === 'unconstrained' ? '不限制范围' : application?.status === 'fallback' ? '完整 LUT（回退）' : '尚未记录',
      ])} />
      <p className="text-slate-500">用户确认与实际生效分别记录；生效范围以反演结果为准。</p>
      {application?.reason && <p className="text-amber-200">范围核验：{application.reason}</p>}
      {application?.matched_rows != null && <p>匹配参数组合：{application.matched_rows.toLocaleString()} 条</p>}
      {application?.used_rows != null && <p>实际使用参数组合：{application.used_rows.toLocaleString()} 条</p>}
      {lai && <p>LAI 状态：{STEP_STATUS[lai.status]} · {lai.detail}</p>}
    </>}
    {workflow && onOpenWorkflow && <button type="button" onClick={() => onOpenWorkflow(workflow.workflow_id)} className="text-emerald-200 underline underline-offset-2">查看本轮任务进度与结果</button>}
  </div>
}

function Comparison({ label, headers, rows }: { label: string; headers: string[]; rows: string[][] }) {
  return <div className="mt-2 overflow-x-auto"><table aria-label={label} className="w-full text-left text-[10px] leading-4">
    <thead><tr>{headers.map((header) => <th key={header} scope="col" className="border-b border-white/10 px-1 py-2 font-medium text-slate-400">{header}</th>)}</tr></thead>
    <tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j} className="break-all border-b border-white/5 px-1 py-2 align-top">{cell}</td>)}</tr>)}</tbody>
  </table></div>
}
