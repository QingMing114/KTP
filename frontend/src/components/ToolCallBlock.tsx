import React, { useState } from 'react'
import { ChevronDown, ChevronRight, Wrench } from 'lucide-react'
import { escapeHtml } from '../utils'
import { RunPart } from '../types'

interface ToolCallBlockProps {
  part: RunPart
  isHistory: boolean
}

const ToolCallBlock: React.FC<ToolCallBlockProps> = ({ part, isHistory }) => {
  const [expanded, setExpanded] = useState(false)
  const toolName = part.tool_invocation?.display_name || part.tool_invocation?.tool_name || "工具"
  const toolInput = part.tool_invocation?.input_summary || part.tool_invocation?.raw_input || ""

  return (
    <div className="border border-stone-200/60 rounded-lg overflow-hidden bg-stone-50/40">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[13px] text-stone-400 hover:bg-stone-100/40 transition-colors"
      >
        {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Wrench size={13} className="text-stone-300" />
        <span>调用 <span className="font-medium text-stone-600">{escapeHtml(toolName)}</span></span>
        {!isHistory && <div className="w-1 h-1 bg-stone-300 rounded-full animate-pulse ml-1" />}
      </button>
      {expanded && toolInput && (
        <div className="px-3 pb-2.5 border-t border-stone-200/40">
          <pre className="text-[11px] text-stone-400 mt-2 whitespace-pre-wrap break-all font-mono leading-relaxed">
            {typeof toolInput === 'string' ? escapeHtml(toolInput) : escapeHtml(JSON.stringify(toolInput, null, 2))}
          </pre>
        </div>
      )}
    </div>
  )
}

export default ToolCallBlock
