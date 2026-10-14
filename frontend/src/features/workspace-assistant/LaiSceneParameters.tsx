import type { AnalysisWorkflowStep } from '../../services/spatialClient'

const RANGES = [
  ['lai_range', 'LAI', 'm²/m²'],
  ['cab_range', '叶绿素 Cab', 'μg/cm²'],
  ['lidfa_range', '叶倾角', '°'],
  ['psoil_range', '土壤参数', ''],
] as const

export default function LaiSceneParameters({ step, showRequested = false }: { step: AnalysisWorkflowStep; showRequested?: boolean }) {
  const scene = step.result.scene_parameters as ({ source?: string; reasoning?: string } & Partial<Record<typeof RANGES[number][0], number[] | null>>) | undefined
  const application = step.result.constraint_application as {
    status?: string; effective?: Record<string, number[]>; reason?: string; used_rows?: number
  } | undefined
  if (!scene) return <p className="mt-2 text-[10px] text-slate-400">LAI 场景参数：{step.status === 'running' ? '正在自动配置…' : step.status === 'completed' ? '该历史任务未记录自动配置参数' : '启动后由大模型自动配置'}</p>
  const applied = application?.status === 'applied'
  return <details className="mt-2 rounded-lg border border-white/10 bg-black/10 p-3 text-[10px] leading-5 text-slate-300" open>
    <summary className="cursor-pointer font-medium text-emerald-100">LAI {scene.source === 'user_confirmed' ? '确认' : '自动'}参数 · {applied ? '已生效' : application ? '使用完整 LUT' : '待反演核验'}</summary>
    <p className="mt-2">配置来源：{scene.source === 'user_confirmed' ? '用户编辑并确认' : scene.source === 'llm' ? '大模型' : '规则回退（模型不可用或置信度不足）'}</p>
    {scene.reasoning && <p className="mt-1 text-slate-400">{scene.reasoning}</p>}
    {showRequested && <table aria-label="LAI 配置与生效范围" className="mt-2 w-full text-left text-[10px] leading-4"><thead><tr><th scope="col" className="py-2">参数</th><th scope="col">配置范围</th><th scope="col">实际生效</th></tr></thead><tbody>{RANGES.map(([key, label, unit]) => {
      const configured = scene[key]
      const effective = application?.effective?.[key]
      const actual = applied ? application?.effective ? effective?.length === 2 ? `${effective[0]}–${effective[1]} ${unit}` : '完整 LUT 范围' : '未记录' : ['fallback', 'unconstrained'].includes(application?.status ?? '') ? '完整 LUT 范围' : '尚未记录'
      return <tr key={key}><td className="border-t border-white/10 py-2 pr-1 align-top">{label}</td><td className="break-all border-t border-white/10 py-2 pr-1 align-top">{configured?.length === 2 ? `${configured[0]}–${configured[1]} ${unit}` : configured === null ? '不限制范围' : '未记录'}</td><td className="break-all border-t border-white/10 py-2 align-top">{actual}</td></tr>
    })}</tbody></table>}
    {!showRequested && applied && <dl className="mt-2 space-y-1">{RANGES.map(([key, label, unit]) => {
      const range = application.effective?.[key]
      return <div key={key} className="flex justify-between gap-3"><dt>{label}</dt><dd>{range?.length === 2 ? `${range[0]}–${range[1]} ${unit}` : '完整 LUT 范围'}</dd></div>
    })}</dl>}
    {application?.reason && <p className="mt-2 text-amber-200">{application.reason}</p>}
    {application?.used_rows != null && <p className="mt-1 text-slate-500">实际使用 {application.used_rows.toLocaleString()} 条参数组合</p>}
  </details>
}
