import React, { useState, useEffect, useCallback } from 'react'

interface Toast {
  id: number
  message: string
  type: 'error' | 'success' | 'info'
}

let _toastId = 0
let _addToast: ((toast: Toast) => void) | null = null

/** Show a toast notification from anywhere (even outside React) */
export function showToast(message: string, type: Toast['type'] = 'error') {
  if (_addToast) {
    _addToast({ id: ++_toastId, message, type })
  }
}

const TOAST_DURATION = 4000

export const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((toast: Toast) => {
    setToasts(prev => [...prev, toast])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toast.id))
    }, TOAST_DURATION)
  }, [])

  useEffect(() => {
    _addToast = addToast
    return () => { _addToast = null }
  }, [addToast])

  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all ${
            toast.type === 'error'
              ? 'bg-red-600 text-white'
              : toast.type === 'success'
              ? 'bg-green-600 text-white'
              : 'bg-gray-700 text-white'
          }`}
          role="alert"
        >
          {toast.message}
        </div>
      ))}
    </div>
  )
}
