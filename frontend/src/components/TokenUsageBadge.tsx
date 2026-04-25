import React from 'react'
import { TokenUsage } from '../types'

function formatTokenCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

interface TokenUsageBadgeProps {
  usage?: TokenUsage | null
}

const TokenUsageBadge: React.FC<TokenUsageBadgeProps> = ({ usage }) => {
  if (!usage || (!usage.input_tokens && !usage.output_tokens)) return null
  const costStr = usage.estimated_cost_usd > 0
    ? usage.estimated_cost_usd < 0.001
      ? `<$0.001`
      : `$${usage.estimated_cost_usd.toFixed(4)}`
    : null
  return (
    <div className="inline-flex items-center gap-2 text-[11px] text-stone-400 bg-stone-100/60 rounded px-2 py-0.5 mt-1">
      <span>↑{formatTokenCount(usage.input_tokens)}</span>
      <span>↓{formatTokenCount(usage.output_tokens)}</span>
      {usage.model_name && <span className="text-stone-300">|</span>}
      {usage.model_name && <span>{usage.model_name}</span>}
      {costStr && <span className="text-stone-300">|</span>}
      {costStr && <span className="text-stone-500">{costStr}</span>}
    </div>
  )
}

export default TokenUsageBadge
