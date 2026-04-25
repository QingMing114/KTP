import React, { useEffect } from 'react'

interface ShortcutsOverlayProps {
  onClose: () => void
}

const ShortcutsOverlay: React.FC<ShortcutsOverlayProps> = ({ onClose }) => {
  const shortcuts = [
    { keys: "Ctrl + N", desc: "新建对话" },
    { keys: "Ctrl + K", desc: "聚焦输入框" },
    { keys: "Enter", desc: "发送消息" },
    { keys: "Shift + Enter", desc: "换行" },
    { keys: "Esc", desc: "停止生成" },
    { keys: "Ctrl + Shift + P", desc: "快捷键面板" },
  ]

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/20 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        className="bg-white rounded-xl shadow-xl border border-stone-200/60 p-6 w-80"
        onClick={e => e.stopPropagation()}
      >
        <h3 id="shortcuts-title" className="text-sm font-semibold text-stone-700 mb-4">键盘快捷键</h3>
        <div className="space-y-2.5">
          {shortcuts.map(s => (
            <div key={s.keys} className="flex items-center justify-between">
              <span className="text-[13px] text-stone-500">{s.desc}</span>
              <kbd className="text-[11px] bg-stone-100 text-stone-500 px-2 py-0.5 rounded font-mono border border-stone-200/60">{s.keys}</kbd>
            </div>
          ))}
        </div>
        <button onClick={onClose} className="mt-5 w-full py-2 text-[13px] bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors text-stone-600">关闭</button>
      </div>
    </div>
  )
}

export default ShortcutsOverlay
