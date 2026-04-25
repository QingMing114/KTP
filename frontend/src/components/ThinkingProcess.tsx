import React, { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Brain, Lightbulb, Users, Cog, ExternalLink, Sparkles } from 'lucide-react'
import { escapeHtml, buildArtifactOpenHref, isMockArtifact, getArtifactLabel } from '../utils'
import { ThinkingStep, Artifact } from '../types'

interface ThinkingProcessProps {
  steps: ThinkingStep[]
  isActive: boolean
  onArtifactClick?: (href: string) => void
}

const ThinkingProcess: React.FC<ThinkingProcessProps> = ({ steps, isActive, onArtifactClick }) => {
  const [expanded, setExpanded] = useState(true)
  const [manuallyToggled, setManuallyToggled] = useState(false)
  const [expandedTools, setExpandedTools] = useState<Set<number>>(() => {
    const initial = new Set<number>()
    steps.forEach((step, i) => {
      if (step.type === 'tool_calling') initial.add(i)
    })
    return initial
  })

  useEffect(() => {
    if (!manuallyToggled && isActive) {
      setExpanded(true)
    }
  }, [isActive, manuallyToggled])

  useEffect(() => {
    setExpandedTools(prev => {
      const next = new Set(prev)
      steps.forEach((step, i) => {
        if (step.type === 'tool_calling' && !prev.has(i)) next.add(i)
      })
      return next
    })
  }, [steps.length])

  if (steps.length === 0) return null

  const lastStep = steps[steps.length - 1]
  const summaryLabel = isActive
    ? lastStep.label
    : `思考过程（${steps.length} 步）`

  function getStepIcon(step: ThinkingStep) {
    switch (step.type) {
      case 'planning': return <Brain size={12} className="text-stone-400" />
      case 'reasoning': return <Lightbulb size={12} className="text-stone-400" />
      case 'delegating': return <Users size={12} className="text-stone-400" />
      case 'delegated_back': return <Users size={12} className="text-stone-400" />
      case 'tool_calling': return step.toolStatus === 'running' ? <Cog size={12} className="text-stone-400 animate-spin" style={{animationDuration: '3s'}} /> : <Cog size={12} className="text-stone-400" />
      case 'error': return <Brain size={12} className="text-red-400" />
      default: return <Brain size={12} className="text-stone-400" />
    }
  }

  function toggleToolDetail(index: number) {
    setExpandedTools(prev => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  return (
    <div className={`border rounded-lg overflow-hidden transition-colors ${isActive ? 'border-stone-300/80 bg-stone-50/80' : 'border-stone-200/60 bg-stone-50/40'}`}>
      <button
        type="button"
        onClick={() => { setExpanded(!expanded); setManuallyToggled(true) }}
        className="w-full flex items-center gap-2 px-3 py-2 text-[13px] text-stone-400 hover:bg-stone-100/40 transition-colors"
      >
        {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {isActive ? (
          <>
            <div className="w-1.5 h-1.5 bg-stone-500 rounded-full animate-pulse" />
            <span className="text-stone-600 font-medium">{escapeHtml(summaryLabel)}</span>
          </>
        ) : (
          <>
            <Brain size={13} className="text-stone-400" />
            <span>{escapeHtml(summaryLabel)}</span>
          </>
        )}
      </button>
      {expanded && (
        <div className="px-3 pb-2.5 space-y-1.5 border-t border-stone-200/40">
          {steps.map((step, index) => (
            <div key={index}>
              <div className="flex items-start gap-2 pt-1.5">
                <div className="mt-0.5 shrink-0">{getStepIcon(step)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[12px] text-stone-500 font-medium">{escapeHtml(step.label)}</span>
                    {step.type === 'tool_calling' && step.toolStatus && (
                      <span className={`text-[9px] px-1.5 py-0 rounded-full font-medium ${
                        step.toolStatus === 'running' ? 'bg-blue-50 text-blue-500' :
                        step.toolStatus === 'completed' || step.toolStatus === 'success' ? 'bg-green-50 text-green-600' :
                        step.toolStatus === 'error' ? 'bg-red-50 text-red-500' :
                        'bg-stone-100 text-stone-500'
                      }`}>
                        {step.toolStatus === 'running' ? '运行中' : step.toolStatus === 'completed' || step.toolStatus === 'success' ? '完成' : step.toolStatus === 'error' ? '失败' : step.toolStatus}
                      </span>
                    )}
                    {step.type === 'tool_calling' && step.toolStatus === 'running' && (
                      <span className="text-[9px] text-stone-400 animate-pulse">处理中...</span>
                    )}
                    {step.type === 'tool_calling' && (step.toolInput || step.toolOutput || (step.artifacts && step.artifacts.length > 0)) && (
                      <button
                        type="button"
                        onClick={() => toggleToolDetail(index)}
                        className="text-[10px] text-stone-400 hover:text-stone-600 flex items-center gap-0.5 transition-colors"
                      >
                        {expandedTools.has(index) ? <ChevronDown size={9} /> : <ChevronRight size={9} />}
                        详情
                      </button>
                    )}
                  </div>
                  {step.detail && (
                    <p className="text-[11px] text-stone-400 mt-0.5 leading-relaxed">{escapeHtml(step.detail)}</p>
                  )}
                </div>
                {index === steps.length - 1 && isActive && (
                  <div className="w-1 h-1 bg-stone-500 rounded-full animate-pulse mt-1.5 shrink-0" />
                )}
              </div>
              {step.type === 'tool_calling' && expandedTools.has(index) && (
                <div className="ml-5 mt-1 mb-1 border-l-2 border-stone-200/60 pl-2.5 space-y-1.5">
                  {step.toolInput && (
                    <div>
                      <span className="text-[10px] text-stone-400 font-medium">输入</span>
                      <pre className="text-[10px] text-stone-500 mt-0.5 whitespace-pre-wrap break-all font-mono leading-relaxed bg-white/60 rounded px-2 py-1 border border-stone-100/60 max-h-32 overflow-y-auto">
                        {escapeHtml(step.toolInput)}
                      </pre>
                    </div>
                  )}
                  {step.toolOutput && (
                    <div>
                      <span className="text-[10px] text-stone-400 font-medium">输出</span>
                      <pre className="text-[10px] text-stone-500 mt-0.5 whitespace-pre-wrap break-all font-mono leading-relaxed bg-white/60 rounded px-2 py-1 border border-stone-100/60 max-h-32 overflow-y-auto">
                        {escapeHtml(step.toolOutput)}
                      </pre>
                    </div>
                  )}
                  {step.artifacts && step.artifacts.map((artifact: Artifact, ai: number) => (
                    <div key={ai} className="rounded-md p-2 bg-white/60 border border-stone-100/60">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Sparkles size={11} className="text-stone-400" />
                        <span className="font-medium text-[11px] text-stone-600">{escapeHtml(artifact.title)}</span>
                        {isMockArtifact(artifact) && <span className="text-[9px] bg-amber-100/60 text-amber-600 px-1 py-0 rounded-full font-medium">Mock</span>}
                      </div>
                      {artifact.content && <div className="text-[10px] text-stone-400 whitespace-pre-wrap mb-1">{escapeHtml(artifact.content)}</div>}
                      {artifact.uri && onArtifactClick && buildArtifactOpenHref(artifact) && (
                        <button
                          onClick={() => { const href = buildArtifactOpenHref(artifact); if (href) onArtifactClick(href) }}
                          className="inline-flex items-center gap-1 text-[10px] font-medium text-stone-400 hover:text-stone-600 transition-colors"
                        >
                          <ExternalLink size={10} /> {getArtifactLabel(artifact)}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ThinkingProcess
