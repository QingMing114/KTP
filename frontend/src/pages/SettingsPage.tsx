import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { User, Key, Trash2, Server, ArrowLeft, Loader2, CheckCircle2, AlertTriangle, RefreshCw, Save, Wifi, WifiOff } from 'lucide-react'
import * as api from '../services/api'
import { SystemManifest } from '../types'

const SettingsPage: React.FC = () => {
  const { state, refreshAll, logout } = useAppContext()
  const [manifest, setManifest] = useState<SystemManifest | null>(null)
  const [loadingManifest, setLoadingManifest] = useState(true)
  const [apiKeyValue, setApiKeyValue] = useState(api.getApiKey())
  const [apiBaseUrl, setApiBaseUrl] = useState(api.getApiBaseUrl())
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [cleanupDays, setCleanupDays] = useState(30)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<{ deleted_sessions: number; deleted_runs: number } | null>(null)
  const [cleanupError, setCleanupError] = useState<string | null>(null)
  const [showCleanupConfirm, setShowCleanupConfirm] = useState(false)

  const loadManifest = useCallback(async () => {
    setLoadingManifest(true)
    try {
      const data = await api.getSystemManifest()
      setManifest(data)
    } catch {
      setManifest(null)
    } finally {
      setLoadingManifest(false)
    }
  }, [])

  useEffect(() => {
    loadManifest()
  }, [loadManifest])

  async function handleSaveConfig() {
    setSaving(true)
    try {
      api.setApiKey(apiKeyValue)
      api.setApiBaseUrl(apiBaseUrl)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      refreshAll({})
    } finally {
      setSaving(false)
    }
  }

  async function handleCleanup() {
    setCleaning(true)
    setCleanupError(null)
    setCleanupResult(null)
    setShowCleanupConfirm(false)
    try {
      const result = await api.cleanupSystem(cleanupDays)
      setCleanupResult(result)
    } catch (err: unknown) {
      setCleanupError(err instanceof Error ? err.message : '清理失败')
    } finally {
      setCleaning(false)
    }
  }

  function requestCleanup() {
    setShowCleanupConfirm(true)
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="mb-6 sm:mb-8">
          <h1 className="text-xl sm:text-2xl font-semibold text-stone-700 mb-1">设置</h1>
          <p className="text-sm text-stone-400">管理应用配置、账户和系统状态</p>
        </div>

        <div className="space-y-6">
          <section className="bg-white rounded-xl border border-stone-200/60 overflow-hidden">
            <div className="px-5 py-3 border-b border-stone-100 flex items-center gap-2">
              <User size={14} className="text-stone-400" />
              <h2 className="text-sm font-semibold text-stone-700">账户</h2>
            </div>
            <div className="p-5">
              {state.auth.isAuthenticated ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-stone-200 flex items-center justify-center">
                      <User size={18} className="text-stone-500" />
                    </div>
                    <div>
                      <p className="text-[14px] font-medium text-stone-700">{state.auth.user?.user_id}</p>
                      <p className="text-[12px] text-stone-400">角色：{state.auth.user?.role || 'user'}</p>
                    </div>
                  </div>
                  <button
                    onClick={logout}
                    className="flex items-center gap-2 px-4 py-2 text-[13px] text-red-500 bg-red-50 hover:bg-red-100 rounded-lg transition-colors"
                  >
                    退出登录
                  </button>
                </div>
              ) : (
                <p className="text-[13px] text-stone-400">未登录。点击侧边栏底部的登录按钮进行登录。</p>
              )}
            </div>
          </section>

          <section className="bg-white rounded-xl border border-stone-200/60 overflow-hidden">
            <div className="px-5 py-3 border-b border-stone-100 flex items-center gap-2">
              <Key size={14} className="text-stone-400" />
              <h2 className="text-sm font-semibold text-stone-700">连接配置</h2>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label htmlFor="settings-api-base" className="block text-[12px] font-medium text-stone-500 mb-1.5">API 基础地址</label>
                <input
                  id="settings-api-base"
                  type="text"
                  value={apiBaseUrl}
                  onChange={(e) => setApiBaseUrl(e.target.value)}
                  placeholder="http://localhost:8000"
                  className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors font-mono"
                />
              </div>
              <div>
                <label htmlFor="settings-api-key" className="block text-[12px] font-medium text-stone-500 mb-1.5">API Key（可选）</label>
                <input
                  id="settings-api-key"
                  type="password"
                  value={apiKeyValue}
                  onChange={(e) => setApiKeyValue(e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors font-mono"
                />
              </div>
              <button
                onClick={handleSaveConfig}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 text-[13px] font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50"
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
                {saved ? '已保存' : '保存并刷新'}
              </button>
            </div>
          </section>

          <section className="bg-white rounded-xl border border-stone-200/60 overflow-hidden">
            <div className="px-5 py-3 border-b border-stone-100 flex items-center gap-2">
              <Server size={14} className="text-stone-400" />
              <h2 className="text-sm font-semibold text-stone-700">系统状态</h2>
            </div>
            <div className="p-5">
              <div className="flex items-center gap-2 mb-4">
                {state.backendOnline ? (
                  <span className="flex items-center gap-1.5 text-[13px] text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200/60">
                    <Wifi size={13} /> 后端在线
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-[13px] text-red-500 bg-red-50 px-3 py-1.5 rounded-lg border border-red-200/60">
                    <WifiOff size={13} /> 后端离线
                  </span>
                )}
              </div>
              {loadingManifest ? (
                <div className="flex items-center gap-2 text-stone-400">
                  <Loader2 size={14} className="animate-spin" />
                  <span className="text-[13px]">加载系统信息...</span>
                </div>
              ) : manifest ? (
                <div className="grid grid-cols-2 gap-3 text-[13px]">
                  {manifest.version && (
                    <div>
                      <p className="text-stone-400 text-[11px]">版本</p>
                      <p className="text-stone-700 font-mono">{manifest.version}</p>
                    </div>
                  )}
                  {manifest.tools_count !== undefined && (
                    <div>
                      <p className="text-stone-400 text-[11px]">工具数量</p>
                      <p className="text-stone-700">{manifest.tools_count}</p>
                    </div>
                  )}
                  {manifest.agents_count !== undefined && (
                    <div>
                      <p className="text-stone-400 text-[11px]">智能体数量</p>
                      <p className="text-stone-700">{manifest.agents_count}</p>
                    </div>
                  )}
                  {manifest.packs_count !== undefined && (
                    <div>
                      <p className="text-stone-400 text-[11px]">领域包数量</p>
                      <p className="text-stone-700">{manifest.packs_count}</p>
                    </div>
                  )}
                  {manifest.uptime_seconds !== undefined && (
                    <div className="col-span-2">
                      <p className="text-stone-400 text-[11px]">运行时间</p>
                      <p className="text-stone-700">
                        {manifest.uptime_seconds >= 86400
                          ? `${Math.floor(manifest.uptime_seconds / 86400)}天 ${Math.floor((manifest.uptime_seconds % 86400) / 3600)}小时`
                          : manifest.uptime_seconds >= 3600
                          ? `${Math.floor(manifest.uptime_seconds / 3600)}小时 ${Math.floor((manifest.uptime_seconds % 3600) / 60)}分钟`
                          : `${Math.floor(manifest.uptime_seconds / 60)}分钟`}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-[13px] text-stone-400">无法获取系统信息</p>
              )}
              <button
                onClick={loadManifest}
                className="mt-3 flex items-center gap-1.5 text-[12px] text-stone-400 hover:text-stone-600 transition-colors"
              >
                <RefreshCw size={11} /> 刷新状态
              </button>
            </div>
          </section>

          <section className="bg-white rounded-xl border border-stone-200/60 overflow-hidden">
            <div className="px-5 py-3 border-b border-stone-100 flex items-center gap-2">
              <Trash2 size={14} className="text-stone-400" />
              <h2 className="text-sm font-semibold text-stone-700">数据管理</h2>
            </div>
            <div className="p-5">
              <p className="text-[13px] text-stone-500 mb-4">清理过期的会话和运行数据以释放存储空间。此操作不可撤销。</p>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label htmlFor="cleanup-days" className="block text-[12px] font-medium text-stone-500 mb-1.5">保留天数</label>
                  <input
                    id="cleanup-days"
                    type="number"
                    min={1}
                    max={365}
                    value={cleanupDays}
                    onChange={(e) => setCleanupDays(parseInt(e.target.value) || 30)}
                    className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 focus:border-stone-400 focus:bg-white outline-none transition-colors"
                  />
                </div>
                <button
                  onClick={requestCleanup}
                  disabled={cleaning}
                  className="flex items-center gap-2 px-4 py-2 text-[13px] font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors disabled:opacity-50"
                >
                  {cleaning ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  清理
                </button>
              </div>
              {showCleanupConfirm && (
                <div className="mt-3 bg-amber-50 border border-amber-200/60 rounded-lg p-3">
                  <p className="text-[13px] text-amber-700 mb-2">确定要清理 {cleanupDays} 天前的数据吗？此操作不可撤销。</p>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCleanup}
                      className="px-3 py-1.5 text-[12px] font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                    >
                      确认清理
                    </button>
                    <button
                      onClick={() => setShowCleanupConfirm(false)}
                      className="px-3 py-1.5 text-[12px] font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors"
                    >
                      取消
                    </button>
                  </div>
                </div>
              )}
              {cleanupResult && (
                <div className="mt-3 flex items-center gap-2 text-[13px] text-emerald-600 bg-emerald-50 px-3 py-2 rounded-lg border border-emerald-200/60">
                  <CheckCircle2 size={14} />
                  已删除 {cleanupResult.deleted_sessions} 个会话，{cleanupResult.deleted_runs} 个运行记录
                </div>
              )}
              {cleanupError && (
                <div className="mt-3 flex items-center gap-2 text-[13px] text-red-500 bg-red-50 px-3 py-2 rounded-lg border border-red-100">
                  <AlertTriangle size={14} />
                  {cleanupError}
                </div>
              )}
            </div>
          </section>
        </div>

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

export default SettingsPage
