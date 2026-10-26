import type { ReactNode } from 'react'

export interface CropDecision {
  final_class_id?: number
  final_name_zh?: string
  source?: 'llm' | 'model_fallback' | 'user_confirmed' | string
  confidence?: string
  rationale?: string
  phenology?: string
  location?: {
    label?: string | null; admin_hint?: string | null; lat?: number | null; lon?: number | null
    province?: string | null; city?: string | null; source?: string
    farm_label?: string | null; farm_name?: string | null; farm_mismatch?: boolean
  } | null
  observed_at?: string
  excluded_classes?: Array<{ class_id: number; reason: string }>
  model_prediction?: { class_id?: number; name_zh?: string; score?: number } | null
  fallback_reason?: string | null
  fallback_detail?: {
    stage?: string; error_type?: string; category?: string | null; status_code?: number | null
    provider?: string; message?: string; upstream_excerpt?: string | null; attempts?: number
  } | null
}
export interface CropScore { class_id?: number; name_zh?: string; name?: string; score?: number }

const SOURCE_LABEL: Record<string, string> = {
  llm: '大模型结合地点与时序判定',
  user_confirmed: '用户确认',
  model_fallback: '大模型不可用，回退模型最高分',
}

export function readCropDecision(result: Record<string, unknown> | undefined | null): CropDecision | null {
  const value = result?.crop_decision
  return value && typeof value === 'object' ? value as CropDecision : null
}

export function readCropScores(result: Record<string, unknown> | undefined | null): CropScore[] {
  const value = result?.class_scores
  return Array.isArray(value) ? (value as CropScore[]).filter((item) => item && typeof item.score === 'number') : []
}

function percent(value: number | undefined): string {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—'
}

const LOCATION_SOURCE_LABEL: Record<string, string> = {
  'farm_preset+admin_boundary': '农场范围 + 行政区反查',
  farm_preset: '农场范围',
  admin_boundary: 'AOI 行政区反查',
  coordinates_only: '仅经纬度',
}

/** One card shows the agronomic judgement and the raw model evidence it was built on. */
export default function CropDecisionCard({ result, modelReport, compact = false }: {
  result: Record<string, unknown>; modelReport?: ReactNode; compact?: boolean
}) {
  const decision = readCropDecision(result)
  if (!decision) return null
  const scores = [...readCropScores(result)].sort((first, second) => (second.score ?? 0) - (first.score ?? 0))
  const location = decision.location ?? {}
  const place = [location.label ?? location.province ?? location.admin_hint, decision.observed_at?.slice(0, 10)].filter(Boolean).join(' · ')
  const locationSource = LOCATION_SOURCE_LABEL[String(location.source ?? '')] ?? ''
  const source = SOURCE_LABEL[String(decision.source ?? '')] ?? '未记录'
  const confidence = { high: '高', medium: '中', low: '低' }[String(decision.confidence ?? '')] ?? ''
  return <section aria-label="农作物识别判定依据" className="mt-3 border-t border-white/10 pt-3 text-[10px] leading-5 text-slate-200">
    <div className="flex items-baseline justify-between gap-2">
      <p className="text-[10px] text-slate-400">农作物识别 · 判定依据</p>
      <span className="text-[9px] text-emerald-200/80">{source}{confidence && ` · 置信度 ${confidence}`}</span>
    </div>
    <p className="mt-1 text-sm font-semibold text-white">{decision.final_name_zh ?? '未判定'}</p>
    {place && <p className="mt-1 text-slate-400">地点与时间：{place}{locationSource && <span className="ml-1 text-slate-500">（{locationSource}）</span>}</p>}
    {location.farm_mismatch && <p className="mt-1 text-[9px] leading-4 text-amber-200/80">所选农场“{location.farm_label ?? '未记录'}”与 AOI 位置不一致，地点已按坐标反查为{location.province ?? '未知行政区'}。</p>}
    {decision.phenology && <p className="text-slate-400">物候判断：{decision.phenology}</p>}
    {decision.rationale && <p className="mt-1 whitespace-pre-wrap rounded-md bg-black/15 px-2 py-1.5 text-slate-300">{decision.rationale}</p>}
    {!!scores.length && <div className="mt-2 space-y-1">
      <p className="text-[9px] text-slate-500">模型原始分数（未经校准，仅作证据）</p>
      {scores.map((score) => <div key={score.class_id ?? score.name_zh} className="grid grid-cols-[3.5rem_1fr_2.3rem] items-center gap-2 text-[9px] text-slate-300">
        <span>{score.name_zh ?? score.name}</span>
        <div className="h-1 overflow-hidden rounded-full bg-slate-900"><div className="h-full bg-emerald-400" style={{ width: `${Math.max(0, Math.min(1, score.score ?? 0)) * 100}%` }} /></div>
        <span className="text-right">{percent(score.score)}</span>
      </div>)}
    </div>}
    {!!decision.excluded_classes?.length && <p className="mt-2 text-[9px] text-slate-400">排除说明：{decision.excluded_classes.slice(0, 4).map((item) => item.reason).filter(Boolean).join('；')}</p>}
    {decision.source === 'model_fallback' && <div className="mt-2 rounded-md border border-amber-300/25 bg-amber-300/5 px-2 py-1.5 text-[9px] leading-4 text-amber-100/90">
      <p>大模型判定不可用，当前展示模型最高分结果，判定口径与既有流程一致。</p>
      <p className="mt-1 break-words">原因：{decision.fallback_reason || decision.fallback_detail?.message || '未记录'}</p>
      {decision.fallback_detail && <details className="mt-1">
        <summary className="cursor-pointer text-amber-200">查看失败详情</summary>
        <div className="mt-1 space-y-0.5 text-amber-100/80">
          {decision.fallback_detail.stage && <p>阶段：{decision.fallback_detail.stage}</p>}
          {decision.fallback_detail.error_type && <p>错误类型：{decision.fallback_detail.error_type}{decision.fallback_detail.category ? `（${decision.fallback_detail.category}）` : ''}</p>}
          {decision.fallback_detail.status_code != null && <p>上游状态码：{decision.fallback_detail.status_code}</p>}
          {decision.fallback_detail.provider && <p>调用方：{decision.fallback_detail.provider}</p>}
          {decision.fallback_detail.attempts != null && <p>尝试次数：{decision.fallback_detail.attempts}</p>}
          {decision.fallback_detail.message && <p className="break-words">错误信息：{decision.fallback_detail.message}</p>}
          {decision.fallback_detail.upstream_excerpt && <p className="break-words">上游返回片段：{decision.fallback_detail.upstream_excerpt}</p>}
        </div>
      </details>}
    </div>}
    {!compact && <p className="mt-2 text-[9px] leading-4 text-amber-200/80">最终判定综合了区域物候先验与模型分数，未经实地验证，不代表识别精度。</p>}
    {modelReport}
  </section>
}
