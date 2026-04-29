import React, { useState, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { Search, Bot, Activity, ArrowLeft, ArrowRight, Package, Users, ShieldAlert, ShieldOff } from 'lucide-react'
import { escapeHtml } from '../utils'
import { Tool, Agent } from '../types'

const AnalysisPage: React.FC = () => {
  const { state, handlePromptClick } = useAppContext()
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')

  if (state.loading.boot) {
    return (
      <div className="flex-1 overflow-auto bg-stone-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-stone-400">加载中...</p>
        </div>
      </div>
    )
  }

  const tools = state.tools || []
  const agents = state.agents || []
  const packs = state.packs || []

  const filteredTools = useMemo(() => {
    if (!searchQuery) return tools
    return tools.filter((tool: Tool) =>
      (tool.name || tool.tool_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (tool.description || '').toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [tools, searchQuery])

  const filteredAgents = useMemo(() => {
    if (!searchQuery) return agents
    return agents.filter((agent: Agent) =>
      (agent.display_name || agent.name || agent.agent_id || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (agent.description || '').toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [agents, searchQuery])

  const handleToolSelect = (tool: Tool) => {
    const toolName = tool.display_name || tool.name || tool.tool_name || ''
    handlePromptClick(`请使用 ${toolName} 工具帮我分析`)
    navigate('/')
  }

  const handleAgentSelect = (agent: Agent) => {
    handlePromptClick(`请使用 ${agent.display_name || agent.name || agent.agent_id} 帮我`)
    navigate('/')
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="mb-6 sm:mb-8">
          <h1 className="text-xl sm:text-2xl font-semibold text-stone-700 mb-1">分析工具</h1>
          <p className="text-sm text-stone-400">浏览并使用可用的分析工具和智能体</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6 sm:mb-8">
          <div className="bg-white p-4 rounded-xl border border-stone-200/60 flex items-center space-x-3">
            <div className="p-2 bg-stone-100 text-stone-500 rounded-lg">
              <Bot size={18} />
            </div>
            <div>
              <p className="text-[11px] text-stone-400 font-medium">工具</p>
              <p className="text-xl font-bold text-stone-700">{tools.length}</p>
            </div>
          </div>
          <div className="bg-white p-4 rounded-xl border border-stone-200/60 flex items-center space-x-3">
            <div className="p-2 bg-stone-100 text-stone-500 rounded-lg">
              <Users size={18} />
            </div>
            <div>
              <p className="text-[11px] text-stone-400 font-medium">智能体</p>
              <p className="text-xl font-bold text-stone-700">{agents.length}</p>
            </div>
          </div>
          <div className="bg-white p-4 rounded-xl border border-stone-200/60 flex items-center space-x-3">
            <div className="p-2 bg-stone-100 text-stone-500 rounded-lg">
              <Package size={18} />
            </div>
            <div>
              <p className="text-[11px] text-stone-400 font-medium">领域包</p>
              <p className="text-xl font-bold text-stone-700">{packs.length}</p>
            </div>
          </div>
        </div>

        <div className="relative mb-6">
          <Search className="absolute left-3.5 top-1/2 transform -translate-y-1/2 text-stone-300" size={16} />
          <input
            type="text"
            placeholder="搜索工具和智能体..."
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-stone-200/80 rounded-xl text-sm focus:border-stone-300 outline-none transition-all placeholder:text-stone-300"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {filteredTools.length === 0 && filteredAgents.length === 0 ? (
          <div className="bg-white border border-stone-200/60 rounded-xl p-12 text-center">
            <Bot size={32} className="text-stone-200 mx-auto mb-3" />
            <p className="text-stone-400 text-sm">
              {tools.length === 0 && agents.length === 0 ? '暂无可用工具，请确认后端服务已启动。' : '没有找到匹配的结果。'}
            </p>
          </div>
        ) : (
          <>
            {filteredTools.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {filteredTools.map((tool: Tool, index: number) => (
                  <div key={tool.tool_name || index} className="bg-white rounded-xl border border-stone-200/60 hover:border-stone-300 transition-all p-4 cursor-pointer group" onClick={() => handleToolSelect(tool)}>
                    <div className="flex items-center gap-2.5 mb-2">
                      <div className="p-1.5 rounded-md bg-stone-100 text-stone-400 group-hover:bg-stone-200 transition-colors">
                        <Activity size={14} />
                      </div>
                      <h3 className="font-medium text-stone-700 text-[14px]">{escapeHtml(tool.display_name || tool.name || tool.tool_name)}</h3>
                    </div>
                    {tool.description && (
                      <p className="text-[13px] text-stone-400 mb-3 line-clamp-2">{escapeHtml(tool.description)}</p>
                    )}
                    <div className="flex items-center justify-between pt-2 border-t border-stone-100">
                      <span className="text-[11px] text-stone-300 font-mono">{tool.tool_name || ''}</span>
                      <div className="flex items-center gap-1.5">
                        {tool.safety_level === 'dangerous' && (
                          <span className="flex items-center gap-0.5 text-[10px] text-red-500 bg-red-50 px-1.5 py-0.5 rounded-full border border-red-200/60"><ShieldOff size={9} />危险</span>
                        )}
                        {tool.safety_level === 'caution' && (
                          <span className="flex items-center gap-0.5 text-[10px] text-amber-500 bg-amber-50 px-1.5 py-0.5 rounded-full border border-amber-200/60"><ShieldAlert size={9} />注意</span>
                        )}
                        <span className="text-[13px] text-stone-400 group-hover:text-stone-600 transition-colors">使用 →</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {filteredAgents.length > 0 && (
              <>
                <h2 className="text-lg font-semibold text-stone-700 mt-8 sm:mt-10 mb-4">智能体</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {filteredAgents.map((agent: Agent, index: number) => (
                    <div key={agent.agent_id || index} className="bg-white rounded-xl border border-stone-200/60 hover:border-stone-300 transition-all p-4 cursor-pointer group" onClick={() => handleAgentSelect(agent)}>
                      <div className="flex items-center gap-2.5 mb-2">
                        <div className="p-1.5 rounded-md bg-stone-100 text-stone-400 group-hover:bg-stone-200 transition-colors">
                          <Users size={14} />
                        </div>
                        <h3 className="font-medium text-stone-700 text-[14px]">{escapeHtml(agent.display_name || agent.name || agent.agent_id)}</h3>
                      </div>
                      {agent.description && (
                        <p className="text-[13px] text-stone-400 mb-3 line-clamp-2">{escapeHtml(agent.description)}</p>
                      )}
                      <div className="flex items-center justify-between pt-2 border-t border-stone-100">
                        <span className="text-[11px] text-stone-300 font-mono">{agent.agent_id || ''}</span>
                        <span className="text-[13px] text-stone-400 group-hover:text-stone-600 transition-colors">开始 →</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        <div className="flex justify-between gap-4 mt-8 sm:mt-10">
          <Link
            to="/"
            className="flex items-center space-x-2 text-stone-400 hover:text-stone-600 rounded-lg text-[14px] font-medium transition-colors"
          >
            <ArrowLeft size={14} /> <span>返回对话</span>
          </Link>
          <Link
            to="/results"
            className="flex items-center space-x-2 bg-stone-700 text-white rounded-lg px-4 py-2 text-[14px] font-medium hover:bg-stone-800 transition-colors"
          >
            <span>查看结果</span> <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  )
}

export default AnalysisPage
