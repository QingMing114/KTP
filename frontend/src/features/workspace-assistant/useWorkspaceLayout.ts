import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'

const WIDTH_KEY = 'ktp_workspace_analysis_width'
export function useWorkspaceLayout() {
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)
  const [preferredWidth, setPreferredWidth] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(WIDTH_KEY) ?? 360)
      return Number.isFinite(saved) ? Math.min(520, Math.max(280, saved)) : 360
    } catch { return 360 }
  })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [resizing, setResizing] = useState(false)
  const origin = useRef<{ x: number; width: number } | null>(null)
  const opener = useRef<HTMLElement | null>(null)
  const docked = viewportWidth >= 1040
  const chatWidth = viewportWidth <= 1100 ? 320 : 360
  const maximum = Math.min(520, Math.max(280, viewportWidth - chatWidth - 320))
  const width = docked ? Math.min(preferredWidth, maximum) : Math.min(preferredWidth, viewportWidth - 24)
  useEffect(() => {
    const resize = () => setViewportWidth(window.innerWidth)
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
  useEffect(() => { try { localStorage.setItem(WIDTH_KEY, String(preferredWidth)) } catch { /* Keep the in-memory width. */ } }, [preferredWidth])
  const closeDrawer = () => { setDrawerOpen(false); opener.current?.focus({ preventScroll: true }) }
  useEffect(() => {
    if (!drawerOpen || docked) return
    const escape = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape') { setDrawerOpen(false); opener.current?.focus({ preventScroll: true }) } }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [drawerOpen, docked])
  const adjust = (next: number) => setPreferredWidth(Math.max(280, Math.min(maximum, next)))
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    origin.current = { x: event.clientX, width }
    setResizing(true)
  }
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => { if (origin.current) adjust(origin.current.width + event.clientX - origin.current.x) }
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    origin.current = null
    setResizing(false)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    adjust(event.key === 'Home' ? 280 : event.key === 'End' ? maximum : width + (event.key === 'ArrowRight' ? 24 : -24))
  }
  return { docked, chatWidth, width, maximum, drawerOpen, resizing, closeDrawer, openDrawer: () => { opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setDrawerOpen(true) }, resizeHandlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp, onKeyDown } }
}
