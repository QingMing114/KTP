import type { CanonicalAssistantPart } from '../../services/canonical/workspaceClient'

export default function AnalysisDetails({ parts, demo = false, expanded = true }: { parts: CanonicalAssistantPart[]; demo?: boolean; expanded?: boolean }) {
  return <div className="space-y-2 text-[10px] leading-5 text-slate-300">
    {demo && <span className="rounded bg-amber-300/10 px-2 py-1 text-amber-200">演示数据</span>}
    {parts.map((part, index) => part.type === 'analysis_plan'
      ? <details key={part.part_id ?? index} open={expanded} className="rounded-lg border border-white/10 bg-black/10 p-3">
          <summary className="cursor-pointer font-medium text-emerald-100">分析过程</summary>
          {part.data?.rationale && <p className="mt-2">{part.data.rationale}</p>}
          <ol className="mt-2 space-y-1">{part.data?.steps?.map((step, i) => <li key={step.step_id}>{i + 1}. {step.label}{step.depends_on.length > 0 && <span className="ml-1 text-slate-500">（依赖上游步骤）</span>}</li>)}</ol>
          {part.data?.missing_inputs?.map((missing) => <p key={missing} className="mt-1 text-amber-200">{missing}</p>)}
        </details>
      : part.type === 'parameter_set'
        ? <details key={part.part_id ?? index} className="rounded-lg border border-white/10 bg-black/10 p-3">
            <summary className="cursor-pointer font-medium text-emerald-100">参数配置 · {part.data?.state === 'effective' ? '实际生效' : '待提交'}</summary>
            <dl className="mt-2 space-y-2">{part.data?.parameters?.map((parameter) => <div key={parameter.name} className="flex justify-between gap-3"><dt className="shrink-0 text-slate-500">{parameter.name}</dt><dd className="break-all text-right">{parameter.value} {parameter.unit}{parameter.source === 'algorithm_fixed' && <span className="ml-1 text-slate-500">固定</span>}</dd></div>)}</dl>
          </details>
        : null)}
  </div>
}
