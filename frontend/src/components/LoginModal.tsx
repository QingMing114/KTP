import React, { useState, useEffect, useRef, useCallback } from 'react'
import { X, LogIn, UserPlus, Loader2, Eye, EyeOff } from 'lucide-react'

interface LoginModalProps {
  isOpen: boolean
  onClose: () => void
  onLogin: (userId: string, password: string) => Promise<void>
  onRegister: (userId: string, password: string) => Promise<void>
}

const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose, onLogin, onRegister }) => {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement as HTMLElement
      const timer = setTimeout(() => {
        const firstInput = dialogRef.current?.querySelector<HTMLInputElement>('input')
        firstInput?.focus()
      }, 50)
      return () => clearTimeout(timer)
    } else {
      previousFocusRef.current?.focus()
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, input, [tabindex]:not([tabindex="-1"])'
        )
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!userId.trim() || !password.trim()) {
      setError('请输入用户名和密码')
      return
    }
    if (userId.trim().length < 2) {
      setError('用户名至少需要2个字符')
      return
    }
    if (!/^[a-zA-Z0-9_-]{2,32}$/.test(userId.trim())) {
      setError('用户名只能包含字母、数字、下划线和连字符')
      return
    }
    if (password.length < 4) {
      setError('密码至少需要4个字符')
      return
    }
    if (password.length > 128) {
      setError('密码不能超过128个字符')
      return
    }
    if (mode === 'register' && password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }
    setLoading(true)
    setError(null)
    try {
      if (mode === 'login') {
        await onLogin(userId.trim(), password)
      } else {
        await onRegister(userId.trim(), password)
      }
      setUserId('')
      setPassword('')
      setConfirmPassword('')
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setLoading(false)
    }
  }, [userId, password, confirmPassword, mode, onLogin, onRegister, onClose])

  const switchMode = useCallback(() => {
    setMode(mode === 'login' ? 'register' : 'login')
    setError(null)
    setConfirmPassword('')
  }, [mode])

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/20 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-modal-title"
        className="bg-white rounded-xl shadow-xl border border-stone-200 w-full max-w-sm mx-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
          <h2 id="login-modal-title" className="text-sm font-semibold text-stone-700">
            {mode === 'login' ? '登录' : '注册'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-stone-400 hover:text-stone-600 rounded-lg transition-colors"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label htmlFor="login-user-id" className="block text-[12px] font-medium text-stone-500 mb-1.5">
              用户名
            </label>
            <input
              id="login-user-id"
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="输入用户名"
              className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors"
              autoComplete="username"
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-[12px] font-medium text-stone-500 mb-1.5">
              密码
            </label>
            <div className="relative">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="输入密码"
                className="w-full px-3 py-2 pr-9 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-stone-300 hover:text-stone-500 transition-colors"
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
              >
                {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {mode === 'register' && (
            <div>
              <label htmlFor="login-confirm-password" className="block text-[12px] font-medium text-stone-500 mb-1.5">
                确认密码
              </label>
              <input
                id="login-confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="再次输入密码"
                className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors"
                autoComplete="new-password"
              />
            </div>
          )}

          {error && (
            <div className="text-[12px] text-red-500 bg-red-50 px-3 py-2 rounded-lg border border-red-100" role="alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 text-[13px] font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : mode === 'login' ? (
              <LogIn size={14} />
            ) : (
              <UserPlus size={14} />
            )}
            <span>{mode === 'login' ? '登录' : '注册'}</span>
          </button>

          <div className="text-center">
            <button
              type="button"
              onClick={switchMode}
              className="text-[12px] text-stone-400 hover:text-stone-600 transition-colors"
            >
              {mode === 'login' ? '没有账号？点击注册' : '已有账号？点击登录'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default LoginModal
