import React, { useState, useMemo, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { Search, Shield, ShieldAlert, ShieldCheck, ShieldOff, Zap, ArrowLeft, Sparkles, Wrench, Eye, EyeOff, Plus, X, Trash2, FlaskConical, Tag } from 'lucide-react'
import { escapeHtml } from '../utils'
import { Tool, PluginToolSpec, PluginToolTestResult } from '../types'
import { registerPluginTool, unregisterPluginTool, testPluginTool, listPluginTools } from '../services/api'

const CATEGORY_LABELS: Record<string, string> = {
  analysis: '分析',
  knowledge: '知识',
  workspace: '工作区',
  conversation: '对话',
  training: '训练',
  report: '报告',
  visualization: '可视化',
  debug: '调试',
  remote_sensing: '遥感',
  crop_simulation: '作物模拟',
  web: '网络',
  plugin: '插件',
}

const SAFETY_CONFIG: Record<string, { label: string; color: string; icon: typeof Shield }> = {
  safe: { label: '安全', color: 'text-emerald-500 bg-emerald-50 border-emerald-200/60', icon: ShieldCheck },
  caution: { label: '注意', color: 'text-amber-500 bg-amber-50 border-amber-200/60', icon: ShieldAlert },
  dangerous: { label: '危险', color: 'text-red-500 bg-red-50 border-red-200/60', icon: ShieldOff },
}

const VISIBILITY_LABELS: Record<string, string> = {
  web: '网页端',
  bounded: '受限',
  internal: '内部',
  debug: '调试',
  all: '全部',
  api: 'API',
}

interface ParamRow {
  name: string
  type: string
}

const EMPTY_PARAM: ParamRow = { name: '', type: 'string' }

const SkillsPage: React.FC = () => {
  const { state, handlePromptClick, refreshAll } = useAppContext()
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [selectedSafety, setSelectedSafety] = useState<string | null>(null)
  const [expandedTool, setExpandedTool] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [pluginNames, setPluginNames] = useState<Set<string>>(new Set())
  const [deletingTool, setDeletingTool] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  useEffect(() => {
    listPluginTools().then(tools => {
      setPluginNames(new Set(tools.map(t => t.name)))
    }).catch(() => {})
  }, [])

  const [formName, setFormName] = useState('')
  const [formDisplayName, setFormDisplayName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formCategory, setFormCategory] = useState('plugin')
  const [formUsageHint, setFormUsageHint] = useState('')
  const [formUrl, setFormUrl] = useState('')
  const [formMethod, setFormMethod] = useState<'GET' | 'POST'>('POST')
  const [formHeaders, setFormHeaders] = useState('')
  const [formTimeout, setFormTimeout] = useState(30)
  const [formSafety, setFormSafety] = useState<'safe' | 'caution' | 'dangerous'>('safe')
  const [formParams, setFormParams] = useState<ParamRow[]>([{ ...EMPTY_PARAM }])
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccess, setFormSuccess] = useState<string | null>(null)

  const [testInput, setTestInput] = useState('')
  const [testResult, setTestResult] = useState<PluginToolTestResult | null>(null)
  const [testing, setTesting] = useState(false)

  const tools = state.tools || []

  const categories = useMemo(() => {
    const cats = new Set<string>()
    tools.forEach((t: Tool) => { if (t.category) cats.add(t.category) })
    return Array.from(cats).sort()
  }, [tools])

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

  async function handleDeleteTool(toolName: string) {
    setDeletingTool(toolName)
    try {
      await unregisterPluginTool(toolName)
      setPluginNames(prev => { const next = new Set(prev); next.delete(toolName); return next })
      setExpandedTool(null)
      refreshAll()
    } catch (err) {
      setFormError(`删除失败: ${err instanceof Error ? err.message : err}`)
    } finally {
      setDeletingTool(null)
      setConfirmDelete(null)
    }
  }

  function resetForm() {
    setFormName(''); setFormDisplayName(''); setFormDescription('')
    setFormCategory('plugin'); setFormUsageHint(''); setFormUrl('')
    setFormMethod('POST'); setFormHeaders(''); setFormTimeout(30)
    setFormSafety('safe'); setFormParams([{ ...EMPTY_PARAM }])
    setFormError(null); setFormSuccess(null); setTestInput(''); setTestResult(null)
  }

  function buildSpec(): PluginToolSpec {
    const inputSchema: Record<string, string> = {}
    for (const p of formParams) {
      if (p.name.trim()) inputSchema[p.name.trim()] = p.type
    }
    const headers: Record<string, string> = {}
    if (formHeaders.trim()) {
      for (const line of formHeaders.split('\n')) {
        const idx = line.indexOf(':')
        if (idx > 0) {
          const k = line.slice(0, idx).trim()
          const v = line.slice(idx + 1).trim()
          if (k) headers[k] = v
        }
      }
    }
    return {
      name: formName.trim(),
      display_name: formDisplayName.trim() || formName.trim(),
      description: formDescription.trim(),
      category: formCategory,
      pack_name: formName.split('.')[0] || 'plugin',
      usage_hint: formUsageHint.trim() || undefined,
      input_schema: inputSchema,
      safety_level: formSafety,
      endpoint: {
        adapter: 'http_api',
        url: formUrl.trim(),
        method: formMethod,
        headers: Object.keys(headers).length > 0 ? headers : undefined,
        timeout: formTimeout,
      },
      enabled: true,
    }
  }

  async function handleSubmit() {
    setFormError(null); setFormSuccess(null)
    if (!formName.trim() || !formUrl.trim() || !formDescription.trim()) {
      setFormError('工具名、描述和 API URL 为必填项')
      return
    }
    if (!/^[a-zA-Z][a-zA-Z0-9_.\-]{1,63}$/.test(formName.trim())) {
      setFormError('工具名格式不正确，需以字母开头，仅含字母数字下划线点号，2-64字符')
      return
    }
    setFormSubmitting(true)
    try {
      const spec = buildSpec()
      await registerPluginTool(spec)
      setFormSuccess(`工具 "${spec.name}" 注册成功！`)
      setPluginNames(prev => new Set(prev).add(spec.name))
      refreshAll()
      setTimeout(() => { setShowAddModal(false); resetForm() }, 1500)
    } catch (err) {
      setFormError(`注册失败: ${err instanceof Error ? err.message : err}`)
    } finally {
      setFormSubmitting(false)
    }
  }

  async function handleTest() {
    const toolName = formName.trim()
    if (!toolName) {
      setFormError('请先填写工具名称')
      return
    }
    setTesting(true); setTestResult(null); setFormError(null)
    try {
      let toolInput: Record<string, unknown> = {}
      if (testInput.trim()) {
        try { toolInput = JSON.parse(testInput) } catch { toolInput = { query: testInput } }
      }
      const result = await testPluginTool(toolName, toolInput)
      setTestResult({
        success: result.status === 'success',
        status: result.status,
        summary: result.summary,
        data: result.payload,
        message: result.status === 'success' ? '测试成功' : result.summary,
      })
    } catch (err) {
      setFormError(`测试失败: ${err instanceof Error ? err.message : err}`)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="mb-6 sm:mb-8 flex items-start justify-between">
          <div>
            <h1 className="text-xl sm:text-2xl font-semibold text-stone-700 mb-1">技能中心</h1>
            <p className="text-sm text-stone-400">浏览系统所有可用技能，按类别和安全级别筛选</p>
          </div>
          <button
            onClick={() => { resetForm(); setShowAddModal(true) }}
            className="flex items-center gap-1.5 px-3 py-2 text-[13px] font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors shrink-0"
          >
            <Plus size={14} /> 添加 API 工具
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <div className="bg-white p-3 rounded-xl border border-stone-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-stone-100 text-stone-500 rounded-lg"><Wrench size={16} /></div>
            <div>
              <p className="text-[10px] text-stone-400">总技能</p>
              <p className="text-lg font-bold text-stone-700">{tools.length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-emerald-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-emerald-50 text-emerald-500 rounded-lg"><ShieldCheck size={16} /></div>
            <div>
              <p className="text-[10px] text-stone-400">安全</p>
              <p className="text-lg font-bold text-stone-700">{tools.filter((t: Tool) => t.safety_level === 'safe').length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-amber-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-amber-50 text-amber-500 rounded-lg"><ShieldAlert size={16} /></div>
            <div>
              <p className="text-[10px] text-stone-400">注意</p>
              <p className="text-lg font-bold text-stone-700">{tools.filter((t: Tool) => t.safety_level === 'caution').length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-red-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-red-50 text-red-500 rounded-lg"><ShieldOff size={16} /></div>
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
          >全部类别</button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
              className={`px-3 py-1.5 text-[12px] rounded-lg border transition-colors ${selectedCategory === cat ? 'bg-stone-700 text-white border-stone-700' : 'bg-white text-stone-500 border-stone-200/60 hover:border-stone-300'}`}
            >{CATEGORY_LABELS[cat] || cat}</button>
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
                <Icon size={11} /> {cfg.label}
              </button>
            )
          })}
        </div>

        {filteredTools.length === 0 ? (
          <div className="bg-white border border-stone-200/60 rounded-xl p-12 text-center">
            <Wrench size={32} className="text-stone-200 mx-auto mb-3" />
            <p className="text-stone-400 text-sm">{tools.length === 0 ? '暂无可用技能，请确认后端服务已启动。' : '没有找到匹配的技能。'}</p>
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
                    const isPlugin = pluginNames.has(tool.tool_name) || tool.capabilities?.includes('plugin')
                    return (
                      <div key={tool.tool_name} className="bg-white rounded-xl border border-stone-200/60 hover:border-stone-300 transition-all overflow-hidden">
                        <div className="p-4 cursor-pointer" onClick={() => setExpandedTool(isExpanded ? null : tool.tool_name)}>
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <h3 className="font-medium text-stone-700 text-[14px] truncate">{escapeHtml(tool.display_name || tool.name || tool.tool_name)}</h3>
                              {isPlugin && <span className="text-[9px] px-1.5 py-0 rounded-full font-medium bg-blue-50 text-blue-600 border border-blue-200/60 flex items-center gap-0.5"><Tag size={8} />插件</span>}
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              {tool.produces_artifacts && (
                                <span className="flex items-center gap-0.5 text-[10px] text-stone-400 bg-stone-50 px-1.5 py-0.5 rounded-full border border-stone-200/60"><Sparkles size={9} /> 产物</span>
                              )}
                              <span className={`flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full border ${safetyCfg.color}`}><SafetyIcon size={9} /> {safetyCfg.label}</span>
                            </div>
                          </div>
                          {tool.description && <p className="text-[13px] text-stone-400 line-clamp-2 mb-2">{escapeHtml(tool.description)}</p>}
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] text-stone-300 font-mono">{tool.tool_name}</span>
                            <div className="flex items-center gap-1.5">
                              {tool.visibility && <span className="text-[10px] text-stone-400 bg-stone-50 px-1.5 py-0.5 rounded"><Eye size={9} className="inline mr-0.5" />{VISIBILITY_LABELS[tool.visibility] || tool.visibility}</span>}
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
                            <div className="flex gap-2">
                              <button onClick={(e) => { e.stopPropagation(); handleToolUse(tool) }} className="flex-1 flex items-center justify-center gap-2 py-2 text-[13px] font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors">
                                <Zap size={13} /> 使用此技能
                              </button>
                              {isPlugin && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); setConfirmDelete(tool.tool_name) }}
                                  disabled={deletingTool === tool.tool_name}
                                  className="flex items-center justify-center gap-1.5 px-3 py-2 text-[13px] font-medium text-red-500 bg-red-50 hover:bg-red-100 border border-red-200/60 rounded-lg transition-colors disabled:opacity-50"
                                >
                                  <Trash2 size={13} /> {deletingTool === tool.tool_name ? '删除中...' : '删除'}
                                </button>
                              )}
                            </div>
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
          <Link to="/" className="flex items-center space-x-2 text-stone-400 hover:text-stone-600 rounded-lg text-[14px] font-medium transition-colors">
            <ArrowLeft size={14} /> <span>返回对话</span>
          </Link>
        </div>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowAddModal(false)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-white border-b border-stone-100 px-6 py-4 flex items-center justify-between rounded-t-2xl">
              <h2 className="text-lg font-semibold text-stone-700">添加 API 工具</h2>
              <button onClick={() => setShowAddModal(false)} className="p-1 text-stone-400 hover:text-stone-600"><X size={18} /></button>
            </div>
            <div className="px-6 py-4 space-y-4">
              {formError && <div className="p-3 bg-red-50 border border-red-200/60 rounded-lg text-[13px] text-red-600">{formError}</div>}
              {formSuccess && <div className="p-3 bg-emerald-50 border border-emerald-200/60 rounded-lg text-[13px] text-emerald-600">{formSuccess}</div>}

              <div>
                <label className="block text-[12px] font-medium text-stone-500 mb-1">工具名 <span className="text-red-400">*</span></label>
                <input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="例: weather.query" className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none" />
                <p className="text-[10px] text-stone-300 mt-1">格式: 包名.动作，如 weather.query</p>
              </div>
              <div>
                <label className="block text-[12px] font-medium text-stone-500 mb-1">显示名</label>
                <input value={formDisplayName} onChange={(e) => setFormDisplayName(e.target.value)} placeholder="例: 天气查询" className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none" />
              </div>
              <div>
                <label className="block text-[12px] font-medium text-stone-500 mb-1">描述 <span className="text-red-400">*</span></label>
                <textarea value={formDescription} onChange={(e) => setFormDescription(e.target.value)} placeholder="例: 查询指定城市的天气信息" rows={2} className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none resize-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[12px] font-medium text-stone-500 mb-1">类别</label>
                  <select value={formCategory} onChange={(e) => setFormCategory(e.target.value)} className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none bg-white">
                    <option value="plugin">插件</option>
                    <option value="web">网络</option>
                    <option value="analysis">分析</option>
                    <option value="knowledge">知识</option>
                    <option value="remote_sensing">遥感</option>
                    <option value="crop_simulation">作物模拟</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-stone-500 mb-1">安全级别</label>
                  <select value={formSafety} onChange={(e) => setFormSafety(e.target.value as 'safe' | 'caution' | 'dangerous')} className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none bg-white">
                    <option value="safe">安全</option>
                    <option value="caution">注意</option>
                    <option value="dangerous">危险</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-[12px] font-medium text-stone-500 mb-1">使用提示</label>
                <input value={formUsageHint} onChange={(e) => setFormUsageHint(e.target.value)} placeholder="例: 当用户需要查询天气信息时使用" className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none" />
              </div>

              <div className="border-t border-stone-100 pt-4">
                <h3 className="text-[13px] font-semibold text-stone-600 mb-3">API 配置</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-[12px] font-medium text-stone-500 mb-1">API URL <span className="text-red-400">*</span></label>
                    <input value={formUrl} onChange={(e) => setFormUrl(e.target.value)} placeholder="https://api.example.com/v1/endpoint" className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[12px] font-medium text-stone-500 mb-1">HTTP 方法</label>
                      <select value={formMethod} onChange={(e) => setFormMethod(e.target.value as 'GET' | 'POST')} className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none bg-white">
                        <option value="POST">POST</option>
                        <option value="GET">GET</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[12px] font-medium text-stone-500 mb-1">超时 (秒)</label>
                      <input type="number" value={formTimeout} onChange={(e) => setFormTimeout(Number(e.target.value))} min={1} max={120} className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-[12px] font-medium text-stone-500 mb-1">请求头 (每行 Key: Value)</label>
                    <textarea value={formHeaders} onChange={(e) => setFormHeaders(e.target.value)} placeholder={"Authorization: Bearer xxx\nContent-Type: application/json"} rows={2} className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[13px] focus:border-stone-400 outline-none resize-none font-mono" />
                  </div>
                </div>
              </div>

              <div className="border-t border-stone-100 pt-4">
                <h3 className="text-[13px] font-semibold text-stone-600 mb-3">输入参数</h3>
                {formParams.map((p, i) => (
                  <div key={i} className="flex gap-2 mb-2">
                    <input value={p.name} onChange={(e) => { const next = [...formParams]; next[i] = { ...next[i], name: e.target.value }; setFormParams(next) }} placeholder="参数名" className="flex-1 px-3 py-1.5 border border-stone-200 rounded-lg text-[12px] focus:border-stone-400 outline-none" />
                    <select value={p.type} onChange={(e) => { const next = [...formParams]; next[i] = { ...next[i], type: e.target.value }; setFormParams(next) }} className="px-2 py-1.5 border border-stone-200 rounded-lg text-[12px] focus:border-stone-400 outline-none bg-white">
                      <option value="string">string</option>
                      <option value="integer">integer</option>
                      <option value="number">number</option>
                      <option value="boolean">boolean</option>
                    </select>
                    {formParams.length > 1 && (
                      <button onClick={() => setFormParams(formParams.filter((_, j) => j !== i))} className="p-1.5 text-stone-300 hover:text-red-400"><X size={14} /></button>
                    )}
                  </div>
                ))}
                <button onClick={() => setFormParams([...formParams, { ...EMPTY_PARAM }])} className="text-[12px] text-stone-400 hover:text-stone-600 flex items-center gap-1"><Plus size={12} /> 添加参数</button>
              </div>

              <div className="border-t border-stone-100 pt-4">
                <h3 className="text-[13px] font-semibold text-stone-600 mb-3">测试</h3>
                <textarea value={testInput} onChange={(e) => setTestInput(e.target.value)} placeholder='{"query": "测试内容"} 或直接输入文本' rows={2} className="w-full px-3 py-2 border border-stone-200 rounded-lg text-[12px] focus:border-stone-400 outline-none resize-none font-mono" />
                <button onClick={handleTest} disabled={testing} className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 border border-stone-200/60 rounded-lg transition-colors disabled:opacity-50">
                  <FlaskConical size={12} /> {testing ? '测试中...' : '测试 API'}
                </button>
                {testResult && (
                  <div className={`mt-2 p-3 rounded-lg text-[12px] ${testResult.status === 'success' ? 'bg-emerald-50 border border-emerald-200/60 text-emerald-700' : 'bg-red-50 border border-red-200/60 text-red-600'}`}>
                    <p className="font-medium mb-1">状态: {testResult.status}</p>
                    <p>{testResult.summary}</p>
                    {testResult.artifacts && testResult.artifacts.length > 0 && <p className="mt-1 text-stone-500">产物: {testResult.artifacts.map(a => a.title).join(', ')}</p>}
                  </div>
                )}
              </div>
            </div>

            <div className="sticky bottom-0 bg-white border-t border-stone-100 px-6 py-4 flex justify-end gap-3 rounded-b-2xl">
              <button onClick={() => setShowAddModal(false)} className="px-4 py-2 text-[13px] text-stone-500 hover:text-stone-700 transition-colors">取消</button>
              <button onClick={handleSubmit} disabled={formSubmitting} className="px-5 py-2 text-[13px] font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50">
                {formSubmitting ? '提交中...' : '注册工具'}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setConfirmDelete(null)}>
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4" onClick={e => e.stopPropagation()} role="alertdialog" aria-modal="true">
            <h3 className="text-lg font-semibold text-stone-800 mb-2">确认删除</h3>
            <p className="text-stone-600 mb-6">确定删除工具 &ldquo;{confirmDelete}&rdquo;？此操作不可撤销。</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmDelete(null)} className="px-4 py-2 text-sm font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors">取消</button>
              <button onClick={() => handleDeleteTool(confirmDelete)} disabled={deletingTool === confirmDelete} className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors disabled:opacity-50">{deletingTool === confirmDelete ? '删除中...' : '确认删除'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default SkillsPage
