import { useEffect, useState } from 'react'
import { getRunTrace } from '../services/canonical'
import type { DebugTrace } from '../services/canonical'

interface DebugDrawerProps {
  run_id: string | null
  isLoading?: boolean
}

function parseTraceStep(t: DebugTrace): { label: string; detail?: string; node: string } {
  const node = t.node ?? 'runtime'
  const event = t.event
  const detail = t.detail

  if (node === 'planner' && event.includes('plan_completed') && detail?.includes('tool=')) {
    const toolName = detail.slice(detail.indexOf('tool=') + 5).split(/\s|,/)[0] || detail
    return { node, label: `规划决策: ${toolName}`, detail }
  }
  if (node === 'runtime' && event.includes('tool_dispatched')) {
    const toolName = detail ?? event
    return { node, label: `开始执行: ${toolName}`, detail }
  }
  if (node === 'runtime' && event.includes('tool_completed')) {
    return { node, label: `执行完成: ${detail ?? event}`, detail }
  }
  if (node === 'llm' && event.includes('llm_call_start')) {
    return { node, label: 'LLM 调用中', detail }
  }
  if (node === 'llm' && event.includes('llm_call_end')) {
    return { node, label: 'LLM 调用完成', detail }
  }
  return { node, label: event, detail }
}

export default function DebugDrawer({ run_id, isLoading }: DebugDrawerProps) {
  const [traces, setTraces] = useState<DebugTrace[]>([])
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!run_id) return
    let cancelled = false

    const fetch = async () => {
      try {
        const data = await getRunTrace(run_id)
        if (!cancelled) setTraces(data)
      } catch { /* silent */ }
    }

    fetch()
    if (isLoading) {
      const interval = setInterval(fetch, 2000)
      return () => { cancelled = true; clearInterval(interval) }
    }
    return () => { cancelled = true }
  }, [run_id, isLoading])

  if (!run_id && !isLoading) return null

  return (
    <div className="mt-2 border border-stone-200 rounded-lg overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-stone-500 hover:bg-stone-50 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <span>
          查看执行过程 ({traces.length} 步)
          {isLoading && traces.length === 0 && <span className="ml-1 text-stone-300">⏳</span>}
        </span>
        <span className="text-[10px]">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="px-3 py-2 space-y-1.5 max-h-64 overflow-y-auto border-t border-stone-100">
          {traces.length > 0 ? (
            traces.map((t, i) => {
              const step = parseTraceStep(t)
              return (
                <div key={i} className="text-xs">
                  <span className="text-stone-400 font-medium">[{step.node}]</span>{' '}
                  <span className="text-stone-600">{step.label}</span>
                  {step.detail && (
                    <div className="text-[11px] text-stone-400 ml-4 mt-0.5 truncate">{step.detail}</div>
                  )}
                </div>
              )
            })
          ) : isLoading ? (
            <div className="text-xs text-stone-400 py-1">等待执行...</div>
          ) : (
            <div className="text-xs text-stone-400 py-1">暂无 trace 数据</div>
          )}
        </div>
      )}
    </div>
  )
}
