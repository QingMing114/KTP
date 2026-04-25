import React, { useState } from 'react'
import { ChevronDown, ChevronRight, CheckCircle2 } from 'lucide-react'
import { escapeHtml } from '../utils'
import { RunPart } from '../types'

interface ToolResultBlockProps {
  part: RunPart
  isHistory?: boolean
}

const ToolResultBlock: React.FC<ToolResultBlockProps> = ({ part }) => {
  const [expanded, setExpanded] = useState(false)
  const toolName = part.tool_invocation?.display_name || part.tool_invocation?.tool_name || "工具"
  const resultPreview = part.text || part.tool_invocation?.output_summary || ""

  return (
    <div className="border border-stone-200/60 rounded-lg overflow-hidden bg-stone-50/40">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[13px] text-stone-400 hover:bg-stone-100/40 transition-colors"
      >
        {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <CheckCircle2 size={13} className="text-stone-400" />
        <span><span className="font-medium text-stone-600">{escapeHtml(toolName)}</span> 完成</span>
      </button>
      {expanded && resultPreview && (
        <div className="px-3 pb-2.5 border-t border-stone-200/40">
          <pre className="text-[11px] text-stone-400 mt-2 whitespace-pre-wrap break-all font-mono leading-relaxed max-h-48 overflow-y-auto">
            {typeof resultPreview === 'string' ? escapeHtml(resultPreview) : escapeHtml(JSON.stringify(resultPreview, null, 2))}
          </pre>
        </div>
      )}
    </div>
  )
}

export default ToolResultBlock
