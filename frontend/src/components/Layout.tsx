import React, { useState, useEffect } from 'react'
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import SessionList from './SessionList'
import LoginModal from './LoginModal'
import { useAppContext } from '../context/AppContext'
import { Bot, MessageSquare, Activity, FileText, Plus, Loader2, WifiOff, Key, PanelLeftClose, PanelLeft, LogOut, User, Wrench, Database, History, Settings, Menu, X } from 'lucide-react'
import { getApiKey, setApiKey as saveApiKey } from '../services/api'

const Layout: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const { selectSession, createSession, state, refreshAll, login, register, logout } = useAppContext()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [creatingSession, setCreatingSession] = useState(false)
  const [showApiKeyInput, setShowApiKeyInput] = useState(false)
  const [apiKeyValue, setApiKeyValue] = useState(getApiKey())
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null
    const handleResize = () => {
      if (timeoutId) clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        const mobile = window.innerWidth < 768
        setIsMobile(mobile)
        if (mobile) {
          setCollapsed(true)
          setMobileMenuOpen(false)
        }
      }, 150)
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [])

  useEffect(() => {
    if (isMobile) setMobileMenuOpen(false)
  }, [location.pathname, isMobile])

  const handleNewChat = async () => {
    if (creatingSession) return
    setCreatingSession(true)
    try {
      const session = await createSession("新对话")
      await selectSession(session.session_id)
      navigate('/')
    } catch (error) {
      console.error("Failed to create session:", error)
    } finally {
      setCreatingSession(false)
    }
  }

  const navItems = [
    { path: '/', icon: MessageSquare, label: '对话' },
    { path: '/skills', icon: Wrench, label: '技能中心' },
    { path: '/analysis', icon: Activity, label: '分析工具' },
    { path: '/results', icon: FileText, label: '分析结果' },
    { path: '/datasets', icon: Database, label: '数据集' },
    { path: '/history', icon: History, label: '运行历史' },
    { path: '/settings', icon: Settings, label: '设置' },
  ]

  const sidebarContent = (
    <>
      <div className={`${collapsed && !isMobile ? 'p-2 justify-center' : 'p-3'} flex items-center ${collapsed && !isMobile ? '' : 'space-x-2.5'}`}>
        {isMobile ? (
          <div className="flex items-center justify-between w-full">
            <span className="text-sm font-semibold text-stone-700 tracking-wide">KTP</span>
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="p-1.5 text-stone-400 hover:text-stone-600 hover:bg-stone-200/60 rounded-lg transition-colors"
              aria-label="关闭菜单"
            >
              <X size={18} />
            </button>
          </div>
        ) : (
          <>
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="p-1.5 text-stone-400 hover:text-stone-600 hover:bg-stone-200/60 rounded-lg transition-colors shrink-0"
              title={collapsed ? "展开侧边栏" : "收起侧边栏"}
              aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
            >
              {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
            </button>
            {!collapsed && <span className="text-sm font-semibold text-stone-700 tracking-wide">KTP</span>}
          </>
        )}
      </div>

      {(!collapsed || isMobile) && (
        <div className="px-2 mb-1">
          <button
            onClick={handleNewChat}
            disabled={creatingSession}
            className="w-full flex items-center justify-center gap-2 py-2 text-[13px] font-medium text-stone-600 bg-white hover:bg-stone-50 border border-stone-200 rounded-lg transition-colors disabled:opacity-50"
          >
            {creatingSession ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            <span>新建对话</span>
          </button>
        </div>
      )}

      {collapsed && !isMobile && (
        <div className="px-2 mb-1 flex justify-center">
          <button
            onClick={handleNewChat}
            disabled={creatingSession}
            className="p-1.5 text-stone-400 hover:text-stone-600 hover:bg-stone-200/60 rounded-lg transition-colors disabled:opacity-50"
            title="新建对话"
            aria-label="新建对话"
          >
            {creatingSession ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          </button>
        </div>
      )}

      {(!collapsed || isMobile) && !state.backendOnline && (
        <div className="mx-2 mt-1 bg-amber-50 text-amber-600 px-2.5 py-1.5 rounded-lg text-[11px] flex items-center gap-1.5 border border-amber-200/60">
          <WifiOff size={11} />
          <span>后端离线</span>
        </div>
      )}

      {collapsed && !isMobile && !state.backendOnline && (
        <div className="px-2 mb-1 flex justify-center" title="后端离线">
          <WifiOff size={12} className="text-amber-500" />
        </div>
      )}

      {(!collapsed || isMobile) && (
        <div className="flex-1 px-2 mt-2 overflow-y-auto">
          <SessionList />
        </div>
      )}

      <div className={`${collapsed && !isMobile ? 'px-2 py-2 flex flex-col items-center gap-1' : 'px-2 py-2 space-y-0.5'}`}>
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = location.pathname === item.path
          if (collapsed && !isMobile) {
            return (
              <Link
                key={item.path}
                to={item.path}
                className="p-2 rounded-lg transition-colors flex items-center justify-center"
                style={{ minWidth: 44, minHeight: 44 }}
                title={item.label}
                aria-label={item.label}
              >
                <span className={`p-1 rounded-lg transition-colors ${isActive ? 'bg-stone-200/80 text-stone-700' : 'text-stone-400 hover:bg-stone-200/40 hover:text-stone-500'}`}>
                  <Icon size={15} />
                </span>
              </Link>
            )
          }
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`w-full flex items-center space-x-2.5 px-2.5 py-2.5 rounded-lg transition-colors text-[13px] ${isActive ? 'bg-stone-200/80 text-stone-700' : 'text-stone-400 hover:bg-stone-200/40 hover:text-stone-500'}`}
              aria-label={item.label}
            >
              <Icon size={15} />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </div>

      {(!collapsed || isMobile) && (
        <div className="px-2 py-2 border-t border-stone-200/60">
          <div className="flex items-center space-x-2.5 px-2.5">
            <div className="w-6 h-6 rounded-full bg-stone-200 flex items-center justify-center shrink-0">
              {state.auth.isAuthenticated ? (
                <User size={12} className="text-stone-500" />
              ) : (
                <Bot size={12} className="text-stone-500" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              {state.auth.isAuthenticated ? (
                <p className="text-[13px] font-medium truncate text-stone-600">
                  {state.auth.user?.user_id || 'User'}
                </p>
              ) : (
                <button
                  onClick={() => setShowLoginModal(true)}
                  className="text-[13px] font-medium text-stone-400 hover:text-stone-600 transition-colors"
                >
                  点击登录
                </button>
              )}
            </div>
            {state.auth.isAuthenticated ? (
              <button
                onClick={logout}
                className="p-1 rounded transition-colors text-stone-300 hover:text-stone-500"
                title="退出登录"
                aria-label="退出登录"
              >
                <LogOut size={12} />
              </button>
            ) : (
              <button
                onClick={() => setShowApiKeyInput(!showApiKeyInput)}
                className={`p-1 rounded transition-colors ${apiKeyValue ? 'text-emerald-500' : 'text-stone-300 hover:text-stone-400'}`}
                title="API Key"
                aria-label="API Key 设置"
              >
                <Key size={12} />
              </button>
            )}
          </div>
          {showApiKeyInput && !state.auth.isAuthenticated && (
            <div className="mt-2 space-y-1.5 px-1">
              <input
                type="password"
                value={apiKeyValue}
                onChange={(e) => setApiKeyValue(e.target.value)}
                placeholder="API Key（可选）"
                className="w-full px-2.5 py-1.5 text-[12px] bg-white border border-stone-200 rounded-lg text-stone-600 placeholder:text-stone-300 focus:border-stone-300 outline-none"
              />
              <button
                onClick={() => { saveApiKey(apiKeyValue); setShowApiKeyInput(false); refreshAll() }}
                className="w-full py-1.5 text-[12px] bg-stone-200 text-stone-600 rounded-lg hover:bg-stone-300 transition-colors"
              >
                保存并刷新
              </button>
            </div>
          )}
        </div>
      )}

      {collapsed && !isMobile && (
        <div className="px-2 py-2 flex justify-center border-t border-stone-200/60">
          {state.auth.isAuthenticated ? (
            <button
              onClick={logout}
              className="p-2 rounded-lg transition-colors text-stone-300 hover:text-stone-500"
              title={`退出 ${state.auth.user?.user_id}`}
              aria-label={`退出 ${state.auth.user?.user_id}`}
              style={{ minWidth: 44, minHeight: 44 }}
            >
              <LogOut size={12} />
            </button>
          ) : (
            <button
              onClick={() => setShowLoginModal(true)}
              className="p-2 rounded-lg transition-colors text-stone-300 hover:text-stone-500"
              title="登录"
              aria-label="登录"
              style={{ minWidth: 44, minHeight: 44 }}
            >
              <User size={12} />
            </button>
          )}
        </div>
      )}
    </>
  )

  return (
    <div className="flex h-screen w-full bg-stone-50 font-sans overflow-hidden">
      {state.loading.boot && (
        <div className="fixed inset-0 bg-stone-50/80 z-50 flex items-center justify-center pointer-events-none">
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={28} className="text-stone-400 animate-spin" />
            <span className="text-sm text-stone-400">加载中...</span>
          </div>
        </div>
      )}

      {isMobile ? (
        <>
          {mobileMenuOpen && (
            <div
              className="fixed inset-0 z-40 bg-stone-900/20 backdrop-blur-sm"
              onClick={() => setMobileMenuOpen(false)}
            />
          )}
          <div
            className={`fixed top-0 left-0 bottom-0 z-50 w-72 bg-stone-100 border-r border-stone-200/60 flex flex-col h-full transition-transform duration-300 ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}
          >
            {sidebarContent}
          </div>
        </>
      ) : (
        <div className={`${collapsed ? 'w-12' : 'w-64'} bg-stone-100 border-r border-stone-200/60 flex flex-col h-full transition-all duration-300 shrink-0 relative z-10`}>
          {sidebarContent}
        </div>
      )}

      <LoginModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onLogin={login}
        onRegister={register}
      />

      <main className="flex-1 flex flex-col min-w-0">
        {isMobile && (
          <div className="flex items-center gap-3 px-4 py-2.5 bg-white border-b border-stone-200/60 shrink-0">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="p-2 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded-lg transition-colors"
              aria-label="打开菜单"
            >
              <Menu size={18} />
            </button>
            <span className="text-sm font-semibold text-stone-700">KTP</span>
            <span className="text-[12px] text-stone-400">
              {navItems.find(n => n.path === location.pathname)?.label || ''}
            </span>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}

export default Layout
