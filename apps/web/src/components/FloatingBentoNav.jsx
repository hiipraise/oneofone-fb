// src/components/FloatingBentoNav.jsx
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { healthCheck } from '../services/api'
import { useQuota } from '../hooks/useData'

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', description: 'Live platform overview', icon: '◈' },
  { path: '/predict', label: 'Predict', description: 'Create a football prediction', icon: '⊕' },
  { path: '/history', label: 'History', description: 'Resolved and pending picks', icon: '≡' },
  { path: '/metrics', label: 'Metrics', description: 'Calibration and model quality', icon: '◎' },
  { path: '/scheduler', label: 'Scheduler', description: 'Fixtures, jobs, and logs', icon: '⏱' },
]

const DEFAULT_POSITION = { x: 24, y: 24 }

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export default function FloatingBentoNav() {
  const location = useLocation()
  const { data: quota } = useQuota()
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState(DEFAULT_POSITION)
  const [dragging, setDragging] = useState(false)
  const [systemOnline, setSystemOnline] = useState(null)
  const dragRef = useRef(null)

  useEffect(() => {
    healthCheck()
      .then(() => setSystemOnline(true))
      .catch(() => setSystemOnline(false))
  }, [])

  useEffect(() => {
    setOpen(false)
  }, [location.pathname, location.search])

  const activeItem = useMemo(
    () => NAV_ITEMS.find((item) => (item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path))) || NAV_ITEMS[0],
    [location.pathname],
  )

  const quotaPct = quota ? Math.round((quota.used / quota.budget) * 100) : 0
  const quotaTone = quotaPct >= 90 ? 'text-brand-redlight' : quotaPct >= 70 ? 'text-yellow-400' : 'text-brand-greenlight'

  const startDrag = (event) => {
    const pointer = event.touches?.[0] || event
    dragRef.current = {
      startX: pointer.clientX,
      startY: pointer.clientY,
      originX: position.x,
      originY: position.y,
      moved: false,
    }
    setDragging(true)
  }

  useEffect(() => {
    if (!dragging) return undefined

    const move = (event) => {
      const pointer = event.touches?.[0] || event
      if (!dragRef.current) return
      const dx = dragRef.current.startX - pointer.clientX
      const dy = dragRef.current.startY - pointer.clientY
      if (Math.abs(dx) + Math.abs(dy) > 4) dragRef.current.moved = true
      setPosition({
        x: clamp(dragRef.current.originX + dx, 12, Math.max(window.innerWidth - 88, 12)),
        y: clamp(dragRef.current.originY + dy, 12, Math.max(window.innerHeight - 88, 12)),
      })
    }

    const stop = () => setDragging(false)
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', stop)
    window.addEventListener('touchmove', move, { passive: true })
    window.addEventListener('touchend', stop)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', stop)
      window.removeEventListener('touchmove', move)
      window.removeEventListener('touchend', stop)
    }
  }, [dragging])

  const toggleOpen = () => {
    if (dragRef.current?.moved) return
    setOpen((value) => !value)
  }

  return (
    <div
      className="fixed z-50 print:hidden"
      style={{ right: position.x, bottom: position.y }}
    >
      {open && (
        <div className="mb-3 w-[min(22rem,calc(100vw-2rem))] max-h-[min(32rem,calc(100vh-7rem))] overflow-y-auto rounded-2xl border border-brand-midgray bg-brand-darkgray/95 shadow-2xl shadow-black/50 backdrop-blur animate-fade-in">
          <div className="sticky top-0 z-10 border-b border-brand-midgray bg-brand-darkgray/95 p-4 backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-display text-xs tracking-[0.28em] text-white">ONEOFONE</p>
                <p className="font-body text-xs text-gray-600">Football prediction workspace</p>
              </div>
              <span className={`h-2 w-2 rounded-full ${systemOnline === false ? 'bg-brand-red' : 'bg-brand-green'} ${systemOnline === null ? 'animate-pulse' : ''}`} />
            </div>
          </div>

          <nav className="grid grid-cols-1 gap-2 p-3" aria-label="Primary navigation">
            {NAV_ITEMS.map((item) => {
              const active = item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path)
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`group rounded-xl border p-3 transition-all duration-150 ${
                    active
                      ? 'border-brand-red bg-brand-red/10 text-white'
                      : 'border-brand-midgray bg-brand-gray/70 text-gray-400 hover:border-gray-600 hover:text-white'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border font-display text-sm ${active ? 'border-brand-red text-brand-redlight' : 'border-brand-midgray text-gray-600 group-hover:text-brand-redlight'}`}>
                      {item.icon}
                    </span>
                    <span className="min-w-0">
                      <span className="block font-display text-xs tracking-widest">{item.label.toUpperCase()}</span>
                      <span className="mt-1 block font-body text-xs text-gray-600">{item.description}</span>
                    </span>
                  </div>
                </Link>
              )
            })}
          </nav>

          {quota && (
            <div className="border-t border-brand-midgray p-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="label">SERPER USAGE</p>
                <p className={`font-display text-xs ${quotaTone}`}>{quota.used}/{quota.budget}</p>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-brand-black">
                <div className="h-full rounded-full bg-brand-red transition-all" style={{ width: `${Math.min(quotaPct, 100)}%` }} />
              </div>
            </div>
          )}
        </div>
      )}

      <button
        type="button"
        onMouseDown={startDrag}
        onTouchStart={startDrag}
        onClick={toggleOpen}
        aria-expanded={open}
        aria-label="Open navigation"
        className="flex h-14 min-w-14 items-center gap-2 rounded-2xl border border-brand-midgray bg-brand-red px-4 font-display text-xs tracking-widest text-white shadow-2xl shadow-black/50 transition-transform hover:scale-105 active:scale-95"
      >
        <span className="text-lg">{open ? '×' : activeItem.icon}</span>
        <span className="hidden sm:inline">{open ? 'CLOSE' : activeItem.label.toUpperCase()}</span>
      </button>
    </div>
  )
}
