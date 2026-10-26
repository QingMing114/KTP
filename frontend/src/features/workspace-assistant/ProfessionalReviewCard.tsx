import { useState } from 'react'
import type { CanonicalAssistantPart, ProfessionalReview, ProfessionalDecision, WorkspaceContext, LaiParameterRanges } from '../../services/canonical/workspaceClient'
import type { AnalysisWorkflow, WorkflowTaskId } from '../../services/spatialClient'
import { WORKSPACE_TASKS } from './workspaceTasks'
import ProfessionalReviewTrace from './ProfessionalReviewTrace'

const RANGES = [
  ['lai_range', 'LAI', 'm²/m²', 10], ['cab_range', '叶绿素 Cab', 'μg/cm²', 100],
  ['lidfa_range', '叶倾角', '°', 90], ['psoil_range', '土壤参数', '', 1],
] as const

const CROP_CLASSES = ['玉米', '棉花', '大豆', '春小麦', '冬小麦', '大麦']

export function isProfessionalReviewCurrent(review: ProfessionalReview, current: WorkspaceContext): boolean {
  const original = review.context
  if (!current.professional_mode || current.execution_mode !== 'live' || current.workspace_id !== review.workspace_id || current.farm_id !== original.farm_id || JSON.stringify(current.aoi?.geometry) !== JSON.stringify(original.aoi?.geometry)) return false
  if (review.phase === 'lai' || review.phase === 'crop') return current.imagery_item_id === review.selected_imagery_id && current.active_workflow_id === review.workflow_id
  return current.imagery_item_id === original.imagery_item_id && (current.apsim_mode ?? 'field') === (original.apsim_mode ?? 'field')
    && JSON.stringify(current.draft_task_ids) === JSON.stringify(original.draft_task_ids)
    && (current.imagery_search?.start_date ?? null) === (original.imagery_search?.start_date ?? null)
    && (current.imagery_search?.end_date ?? null) === (original.imagery_search?.end_date ?? null)
    && (current.imagery_search?.max_cloud_cover ?? 20) === (original.imagery_search?.max_cloud_cover ?? 20)
}

export default function ProfessionalReviewCard({ review, context, busy = false, compact = false, expandedHistory = false, onDecision, parts, workflow, onOpenWorkflow }: {
  review: ProfessionalReview; context: WorkspaceContext; busy?: boolean; compact?: boolean
  expandedHistory?: boolean
  parts?: CanonicalAssistantPart[]; workflow?: AnalysisWorkflow; onOpenWorkflow?: (id: string) => void
  onDecision: (id: string, decision: ProfessionalDecision) => Promise<void>
}) {
  const [start, setStart] = useState(review.search?.start_date ?? '')
  const [end, setEnd] = useState(review.search?.end_date ?? '')
  const [cloud, setCloud] = useState(String(review.search?.max_cloud_cover ?? 20))
  const [image, setImage] = useState(review.selected_imagery_id ?? '')
  const [tasks, setTasks] = useState<WorkflowTaskId[]>(review.intent.task_ids.length ? review.intent.task_ids : review.context.draft_task_ids)
  const [mode, setMode] = useState<'field' | 'example'>(review.intent.apsim_mode ?? review.context.apsim_mode ?? 'field')
  const [ranges, setRanges] = useState<LaiParameterRanges>(() => Object.fromEntries(RANGES.map(([key]) => [key, review.proposed_scene?.[key] ?? null])) as LaiParameterRanges)
  const [cropClass, setCropClass] = useState(review.proposed_crop?.final_class_id == null ? '' : String(review.proposed_crop.final_class_id))
  const [error, setError] = useState('')
  const current = isProfessionalReviewCurrent(review, context)
  const disabled = busy || !current || review.status !== 'pending'
  const changeRange = (key: keyof LaiParameterRanges, index: 0 | 1, value: string) => setRanges((previous) => ({ ...previous, [key]: index === 0 ? [value === '' ? NaN : Number(value), previous[key]?.[1] ?? 0] : [previous[key]?.[0] ?? 0, value === '' ? NaN : Number(value)] }))
  const decide = async (decision: 'confirm' | 'cancel') => {
    setError('')
    let params: ProfessionalDecision = { decision }
    if (decision === 'confirm') {
      if (review.phase === 'search') {
        if (!start || !end || start > end || !cloud.trim() || !Number.isFinite(Number(cloud)) || Number(cloud) < 0 || Number(cloud) > 100) { setError('请填写有效日期范围及 0–100 的云量上限'); return }
        params = { decision, search: { start_date: start, end_date: end, max_cloud_cover: Number(cloud) } }
      } else if (review.phase === 'workflow') {
        if (!image || !tasks.length) { setError('请至少选择一景影像和一项任务'); return }
        params = { decision, imagery_item_id: image, task_ids: tasks, apsim_mode: mode }
      } else if (review.phase === 'crop') {
        if (cropClass === '') { setError('请选择地块作物类别'); return }
        params = { decision, crop_class_id: Number(cropClass) }
      } else {
        if (RANGES.some(([key, , , upper]) => ranges[key] && (!ranges[key]!.every(Number.isFinite) || ranges[key]![0] < 0 || ranges[key]![0] > ranges[key]![1] || ranges[key]![1] > upper))) { setError('参数范围需要从小到大，且在标注的允许范围内'); return }
        params = { decision, scene: ranges }
      }
    }
    try { await onDecision(review.review_id, params) } catch (cause) { setError(cause instanceof Error ? cause.message : '确认未完成，请重试') }
  }
  if (review.status !== 'pending' && review.status !== 'processing') {
    return <details open={expandedHistory} className="rounded-lg border border-white/10 p-2 text-[10px] text-slate-400"><summary>{review.title} · {review.status === 'confirmed' ? '已确认' : review.status === 'cancelled' ? '已取消' : '未完成'}</summary><p className="mt-2">{review.detail}</p>
      <ProfessionalReviewTrace review={review} parts={parts} workflow={workflow} onOpenWorkflow={onOpenWorkflow} />
    </details>
  }
  return <details open={!compact} className={compact ? 'rounded-lg border border-white/10 p-2 text-[10px] text-slate-400' : ''}>
    <summary className={compact ? 'cursor-pointer' : 'hidden'}>{review.title} · {review.status === 'processing' ? '处理中' : current ? '待确认' : '已失效'}</summary>
    <section aria-label={review.title} className="rounded-xl border border-cyan-300/30 bg-cyan-400/[0.04] p-3 text-[11px] leading-5 text-slate-200">
    <h3 className="font-semibold text-cyan-100">{review.title}</h3><p className="mt-1 text-[10px] text-slate-400">专业模式 · 工具尚未继续执行</p>
    {compact && <ProfessionalReviewTrace review={review} parts={parts} workflow={workflow} onOpenWorkflow={onOpenWorkflow} />}
    {review.rationale && <p className="mt-2 text-[10px] text-slate-300">推荐依据：{review.rationale}</p>}
    {review.phase === 'search' && <div className="mt-3 grid grid-cols-2 gap-2">
      <label>开始日期<input aria-label="确认搜索开始日期" type="date" value={start} onChange={(event) => setStart(event.target.value)} disabled={disabled} className="workspace-review-input" /></label>
      <label>结束日期<input aria-label="确认搜索结束日期" type="date" value={end} onChange={(event) => setEnd(event.target.value)} disabled={disabled} className="workspace-review-input" /></label>
      <label className="col-span-2">云量上限（%）<input aria-label="确认搜索云量上限" type="number" min={0} max={100} step="any" value={cloud} onChange={(event) => setCloud(event.target.value)} disabled={disabled} className="workspace-review-input" /></label>
      <p className="col-span-2 text-[10px] text-slate-400">数值为推荐配置，可修改；确认后执行影像搜索。</p>
    </div>}
    {review.phase === 'workflow' && <div className="mt-3 space-y-3">
      <label className="block">分析影像<select aria-label="确认分析影像" value={image} onChange={(event) => setImage(event.target.value)} disabled={disabled} className="workspace-review-input">{review.candidates.map((item) => <option key={item.item_id} value={item.item_id}>{item.acquired_at.slice(0, 10)} · 云量 {item.cloud_cover ?? '未知'}%{item.is_recommended ? ' · 推荐' : ''} · {item.item_id}</option>)}</select></label>
      <fieldset disabled={disabled}><legend>分析任务</legend><div className="mt-1 grid grid-cols-2 gap-2">{WORKSPACE_TASKS.filter((task) => task.id !== 'forecast' && task.available).map((task) => <label key={task.id} className="flex items-start gap-1"><input type="checkbox" checked={tasks.includes(task.id as WorkflowTaskId)} onChange={(event) => setTasks((values) => event.target.checked ? [...values, task.id as WorkflowTaskId] : values.filter((id) => id !== task.id))} />{task.title}</label>)}</div></fieldset>
      {tasks.includes('yield') && <label className="block">APSIM 方式<select aria-label="确认 APSIM 方式" value={mode} onChange={(event) => setMode(event.target.value as 'field' | 'example')} disabled={disabled} className="workspace-review-input"><option value="field">地块估产 · 需核验资料</option><option value="example">真实示例模拟 · 非当前地块产量</option></select></label>}
      <p className="text-[10px] text-slate-400">固定配置：20 m · B02/B03/B04/B07/B08。依赖步骤自动加入；LAI 场景参数在影像准备后另行确认。</p>
    </div>}
    {review.phase === 'crop' && <div className="mt-3 space-y-3">
      <div className="rounded-md bg-black/15 px-2 py-1.5 text-[10px] leading-4 text-slate-300">
        <p>判定结果：<span className="font-medium text-white">{review.proposed_crop?.final_name_zh ?? '未判定'}</span><span className="ml-2 text-slate-400">{review.proposed_crop?.source === 'model_fallback' ? '（大模型不可用，回退模型最高分）' : '（大模型结合地点与时序判定）'}</span></p>
        {(review.proposed_crop?.location?.label || review.proposed_crop?.observed_at) && <p className="mt-1 text-slate-400">地点与时间：{review.proposed_crop?.location?.label ?? '未记录'}{review.proposed_crop?.observed_at ? ` · ${review.proposed_crop.observed_at.slice(0, 10)}` : ''}</p>}
        {review.proposed_crop?.phenology && <p className="text-slate-400">物候判断：{review.proposed_crop.phenology}</p>}
        {review.proposed_crop?.rationale && <p className="mt-1 whitespace-pre-wrap">{review.proposed_crop.rationale}</p>}
        {review.proposed_crop?.fallback_reason && <p className="mt-1 text-amber-200/80">回退原因：{review.proposed_crop.fallback_reason}</p>}
        {review.proposed_crop?.fallback_detail?.message && <p className="mt-1 break-words text-amber-200/70">错误信息：{review.proposed_crop.fallback_detail.message}</p>}
      </div>
      <label className="block">地块作物<select aria-label="确认地块作物类别" value={cropClass} onChange={(event) => setCropClass(event.target.value)} disabled={disabled} className="workspace-review-input">{CROP_CLASSES.map((name, id) => <option key={id} value={id}>{name}</option>)}</select></label>
      <p className="text-[10px] text-slate-400">卡片已填入最终判定结果，可改选后继续；后续估产按此作物执行。</p>
    </div>}
    {review.phase === 'lai' && <div className="mt-3 space-y-3">
      <p className="text-[10px] text-slate-400">推荐来源：{review.proposed_scene?.source === 'llm' ? '大模型' : '规则回退（模型不可用或置信度不足）'}。可编辑的范围将直接用于反演。</p>
      {RANGES.map(([key, label, unit, upper]) => <fieldset key={key} disabled={disabled}><legend>{label}（0–{upper}{unit && ` ${unit}`}）</legend><label className="text-[10px] text-slate-400"><input type="checkbox" checked={ranges[key] === null} onChange={(event) => setRanges((values) => ({ ...values, [key]: event.target.checked ? null : review.proposed_scene?.[key] ?? [0, upper] }))} /> 不限制范围</label>{ranges[key] !== null && <div className="mt-1 grid grid-cols-2 gap-2">{([0, 1] as const).map((index) => <label key={index}>{index === 0 ? '最小值' : '最大值'}<input aria-label={`${label}${index === 0 ? '最小值' : '最大值'}`} type="number" min={0} max={upper} step="any" value={Number.isNaN(ranges[key]![index]) ? '' : ranges[key]![index]} onChange={(event) => changeRange(key, index, event.target.value)} className="workspace-review-input" /></label>)}</div>}</fieldset>)}
      <p className="text-[10px] text-slate-400">固定配置：20 m 分辨率、五波段、Top-1% 匹配。确认后保留模型推荐值和用户实际执行值。</p>
    </div>}
    {!current && <p className="mt-3 text-amber-200">{!context.professional_mode ? '请开启专业模式后查看并确认。' : '区域、影像或配置已变化，请重新生成确认卡片。'}</p>}
    {error && <p role="alert" className="mt-2 text-rose-300">{error}</p>}
    <div className="mt-3 flex gap-2"><button type="button" disabled={disabled} onClick={() => void decide('confirm')} className="flex-1 rounded-lg bg-cyan-300 px-3 py-2 font-medium text-[#06261b] disabled:opacity-35">{busy || review.status === 'processing' ? '正在处理…' : '确认并执行'}</button><button type="button" disabled={busy || review.status !== 'pending'} onClick={() => void decide('cancel')} className="rounded-lg border border-white/15 px-3 py-2 text-slate-300 disabled:opacity-35">取消</button></div>
    </section>
  </details>
}
