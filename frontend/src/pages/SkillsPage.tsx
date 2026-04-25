import React, { useState, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { Search, Shield, ShieldAlert, ShieldCheck, ShieldOff, Zap, ArrowLeft, Sparkles, Wrench, Eye, EyeOff } from 'lucide-react'
import { escapeHtml } from '../utils'
import { Tool } from '../types'

const CATEGORY_LABELS: Record<string, string> = {
  analysis: '分析',
  knowledge: '知识',
  workspace: '工作区',
  conversation: '对话',
  training: '训练',
  report: '报告',
  visualization: '可视化',
  debug: '调试',
}

const SAFETY_CONFIG: Record<string, { label: string; color: string; icon: typeof Shield }> = {
  safe: { label: '安全', color: 'text-emerald-500 bg-emerald-50 border-emerald-200/60', icon: ShieldCheck },
  caution: { label: '注意', color: 'text-amber-500 bg-amber-50 border-amber-200/60', icon: ShieldAlert },
  dangerous: { label: '危险', color: 'text-red-500 bg-red-50 border-red-200/60', icon: ShieldOff },
}

const VISIBILITY_LABELS: Record<string, string> = {
  web: 'Web',
  bounded: '受限',
  internal: '内部',
  debug: '调试',
}

const SkillsPage: React.FC = () => {
  const { state, handlePromptClick } = useAppContext()
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [selectedSafety, setSelectedSafety] = useState<string | null>(null)
  const [expandedTool, setExpandedTool] = useState<string | null>(null)

  const tools = state.tools || []

  const categories = useMemo(() => {
    const cats = new Set<string>()
    tools.forEach((t: Tool) => { if (t.category) cats.add(t.category) })
    return Array.from(cats).sort()
  }, [tools])

  const filteredTools = useMemo(() => {
    let result = tools
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter((t: Tool) =>
        (t.tool_name || '').toLowerCase().includes(q) ||
        (t.display_name || t.name || '').toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q)
      )
    }
    if (selectedCategory) {
      result = result.filter((t: Tool) => t.category === selectedCategory)
    }
    if (selectedSafety) {
      result = result.filter((t: Tool) => t.safety_level === selectedSafety)
    }
    return result
  }, [tools, searchQuery, selectedCategory, selectedSafety])

  const groupedTools = useMemo(() => {
    const groups: Record<string, Tool[]> = {}
    filteredTools.forEach((t: Tool) => {
      const cat = t.category || 'other'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(t)
    })
    return groups
  }, [filteredTools])

  function handleToolUse(tool: Tool) {
    const toolName = tool.display_name || tool.name || tool.tool_name
    handlePromptClick(`请使用 ${toolName} 工具帮我分析`)
    navigate('/')
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="mb-6 sm:mb-8">
          <h1 className="text-xl sm:text-2xl font-semibold text-stone-700 mb-1">技能中心</h1>
          <p className="text-sm text-stone-400">浏览系统所有可用技能，按类别和安全级别筛选</p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <div className="bg-white p-3 rounded-xl border border-stone-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-stone-100 text-stone-500 rounded-lg">
              <Wrench size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">总技能</p>
              <p className="text-lg font-bold text-stone-700">{tools.length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-emerald-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-emerald-50 text-emerald-500 rounded-lg">
              <ShieldCheck size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">安全</p>
              <p className="text-lg font-bold text-stone-700">{tools.filter((t: Tool) => t.safety_level === 'safe').length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-amber-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-amber-50 text-amber-500 rounded-lg">
              <ShieldAlert size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">注意</p>
              <p className="text-lg font-bold text-stone-700">{tools.filter((t: Tool) => t.safety_level === 'caution').length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-red-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-red-50 text-red-500 rounded-lg">
              <ShieldOff size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">危险</p>
              <p className="text-lg font-bold text-stone-700">{tools.filter((t: Tool) => t.safety_level === 'dangerous').length}</p>
            </div>
          </div>
        </div>

        <div className="relative mb-4">
          <Search className="absolute left-3.5 top-1/2 transform -translate-y-1/2 text-stone-300" size={16} />
          <input
            type="text"
            placeholder="搜索技能名称或描述..."
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-stone-200/80 rounded-xl text-sm focus:border-stone-300 outline-none transition-all placeholder:text-stone-300"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="flex flex-wrap gap-2 mb-6">
          <button
            onClick={() => setSelectedCategory(null)}
            className={`px-3 py-1.5 text-[12px] rounded-lg border transition-colors ${!selectedCategory ? 'bg-stone-700 text-white border-stone-700' : 'bg-white text-stone-500 border-stone-200/60 hover:border-stone-300'}`}
          >
            全部类别
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
              className={`px-3 py-1.5 text-[12px] rounded-lg border transition-colors ${selectedCategory === cat ? 'bg-stone-700 text-white border-stone-700' : 'bg-white text-stone-500 border-stone-200/60 hover:border-stone-300'}`}
            >
              {CATEGORY_LABELS[cat] || cat}
            </button>
          ))}
          <div className="w-px h-6 bg-stone-200 self-center mx-1" />
          {(['safe', 'caution', 'dangerous'] as const).map((level) => {
            const cfg = SAFETY_CONFIG[level]
            const Icon = cfg.icon
            return (
              <button
                key={level}
                onClick={() => setSelectedSafety(selectedSafety === level ? null : level)}
                className={`px-3 py-1.5 text-[12px] rounded-lg border transition-colors flex items-center gap-1.5 ${selectedSafety === level ? `${cfg.color} border-current` : 'bg-white text-stone-500 border-stone-200/60 hover:border-stone-300'}`}
              >
                <Icon size={11} />
                {cfg.label}
              </button>
            )
          })}
        </div>

        {filteredTools.length === 0 ? (
          <div className="bg-white border border-stone-200/60 rounded-xl p-12 text-center">
            <Wrench size={32} className="text-stone-200 mx-auto mb-3" />
            <p className="text-stone-400 text-sm">
              {tools.length === 0 ? '暂无可用技能，请确认后端服务已启动。' : '没有找到匹配的技能。'}
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedTools).sort(([a], [b]) => a.localeCompare(b)).map(([category, catTools]) => (
              <div key={category}>
                <h2 className="text-sm font-semibold text-stone-500 mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-stone-300 rounded-full" />
                  {CATEGORY_LABELS[category] || category}
                  <span className="text-stone-300 font-normal">({catTools.length})</span>
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {catTools.map((tool: Tool) => {
                    const safety = tool.safety_level || 'safe'
                    const safetyCfg = SAFETY_CONFIG[safety] || SAFETY_CONFIG.safe
                    const SafetyIcon = safetyCfg.icon
                    const isExpanded = expandedTool === tool.tool_name
                    return (
                      <div
                        key={tool.tool_name}
                        className="bg-white rounded-xl border border-stone-200/60 hover:border-stone-300 transition-all overflow-hidden"
                      >
                        <div className="p-4 cursor-pointer" onClick={() => setExpandedTool(isExpanded ? null : tool.tool_name)}>
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <h3 className="font-medium text-stone-700 text-[14px] truncate">{escapeHtml(tool.display_name || tool.name || tool.tool_name)}</h3>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              {tool.produces_artifacts && (
                                <span className="flex items-center gap-0.5 text-[10px] text-stone-400 bg-stone-50 px-1.5 py-0.5 rounded-full border border-stone-200/60">
                                  <Sparkles size={9} /> 产物
                                </span>
                              )}
                              <span className={`flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full border ${safetyCfg.color}`}>
                                <SafetyIcon size={9} /> {safetyCfg.label}
                              </span>
                            </div>
                          </div>
                          {tool.description && (
                            <p className="text-[13px] text-stone-400 line-clamp-2 mb-2">{escapeHtml(tool.description)}</p>
                          )}
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] text-stone-300 font-mono">{tool.tool_name}</span>
                            <div className="flex items-center gap-1.5">
                              {tool.visibility && (
                                <span className="text-[10px] text-stone-400 bg-stone-50 px-1.5 py-0.5 rounded">
                                  <Eye size={9} className="inline mr-0.5" />{VISIBILITY_LABELS[tool.visibility] || tool.visibility}
                                </span>
                              )}
                              {isExpanded ? <EyeOff size={12} className="text-stone-300" /> : <Eye size={12} className="text-stone-300" />}
                            </div>
                          </div>
                        </div>
                        {isExpanded && (
                          <div className="px-4 pb-4 border-t border-stone-100 pt-3 space-y-3">
                            {tool.capabilities && tool.capabilities.length > 0 && (
                              <div>
                                <p className="text-[11px] text-stone-400 mb-1.5">能力标签</p>
                                <div className="flex flex-wrap gap-1.5">
                                  {tool.capabilities.map((cap, i) => (
                                    <span key={i} className="text-[11px] bg-stone-100 text-stone-500 px-2 py-0.5 rounded-full">{cap}</span>
                                  ))}
                                </div>
                              </div>
                            )}
                            <button
                              onClick={(e) => { e.stopPropagation(); handleToolUse(tool) }}
                              className="w-full flex items-center justify-center gap-2 py-2 text-[13px] font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors"
                            >
                              <Zap size={13} />
                              使用此技能
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-between gap-4 mt-8">
          <Link
            to="/"
            className="flex items-center space-x-2 text-stone-400 hover:text-stone-600 rounded-lg text-[14px] font-medium transition-colors"
          >
            <ArrowLeft size={14} /> <span>返回对话</span>
          </Link>
        </div>
      </div>
    </div>
  )
}

export default SkillsPage
