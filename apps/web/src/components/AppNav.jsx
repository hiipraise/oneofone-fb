// src/components/AppNav.jsx
//
// Sprint 6.14 — replaces the draggable FloatingBentoNav with a compact,
// reliable navigation: a slim vertical rail on desktop (lg+), a bottom tab
// bar on mobile/tablet. Keeps the DM Mono trading-terminal aesthetic.
import React, { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { healthCheck } from '../services/api'
import { useQuota } from '../hooks/useData'

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: '◈' },
  { path: '/predict', label: 'Predict', icon: '⊕' },
  { path: '/history', label: 'History', icon: '≡' },
  { path: '/metrics', label: 'Metrics', icon: '◎' },
  { path: '/scheduler', label: 'Scheduler', icon: '⏱' },
]

function isActive(pathname, item) {
  return item.path === '/' ? pathname === '/' : pathname.startsWith(item.path)
}

function RailLink({ item, active }) {
  return (
    <Link
      to={item.path}
      aria-label={item.label}
      aria-current={active ? 'page' : undefined}
      title={item.label}
      className={`group flex h-12 w-12 items-center justify-center rounded-xl border font-display text-base transition-all duration-150 ${
        active
          ? 'border-brand-red bg-brand-red/10 text-brand-redlight shadow-[0_0_18px_-4px_rgba(255,59,48,0.45)]'
          : 'border-transparent text-gray-500 hover:border-brand-midgray hover:bg-brand-gray/60 hover:text-white'
      }`}
    >
      {item.icon}
    </Link>
  )
}

function TabLink({ item, active }) {
  return (
    <Link
      to={item.path}
      aria-label={item.label}
      aria-current={active ? 'page' : undefined}
      className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 py-2 font-display text-[0.55rem] tracking-[0.18em] transition-colors duration-150 ${
        active ? 'text-brand-redlight' : 'text-gray-500 hover:text-white'
      }`}
    >
      <span className={`text-lg leading-none ${active ? 'drop-shadow-[0_0_10px_rgba(255,59,48,0.5)]' : ''}`}>{item.icon}</span>
      <span className="truncate">{item.label.toUpperCase()}</span>
    </Link>
  )
}

export default function AppNav() {
  const location = useLocation()
  const { data: quota } = useQuota()
  const [systemOnline, setSystemOnline] = useState(null)

  useEffect(() => {
    healthCheck()
      .then(() => setSystemOnline(true))
      .catch(() => setSystemOnline(false))
  }, [])

  const quotaPct = quota && quota.budget ? Math.round((quota.used / quota.budget) * 100) : 0
  const quotaTone = quotaPct >= 90 ? 'bg-brand-red' : quotaPct >= 70 ? 'bg-yellow-400' : 'bg-brand-green'

  return (
    <>
      {/* Desktop rail (lg+) */}
      <nav
        aria-label="Primary navigation"
        className="fixed inset-y-0 left-0 z-40 hidden w-16 flex-col items-center gap-1 border-r border-brand-midgray bg-brand-darkgray/95 py-4 backdrop-blur lg:flex print:hidden"
      >
        <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-xl border border-brand-midgray bg-brand-black">
          <span className="font-display text-[0.6rem] font-bold leading-tight text-white">
            1<sub className="text-brand-redlight">:1</sub>
          </span>
        </div>

        <div className="mt-2 flex flex-col gap-1.5">
          {NAV_ITEMS.map((item) => (
            <RailLink key={item.path} item={item} active={isActive(location.pathname, item)} />
          ))}
        </div>

        <div className="mt-auto flex flex-col items-center gap-2.5">
          <span
            title={systemOnline === null ? 'Checking backend…' : systemOnline ? 'Backend online' : 'Backend unreachable'}
            className={`h-2 w-2 rounded-full ${systemOnline === false ? 'bg-brand-red' : 'bg-brand-green'} ${systemOnline === null ? 'animate-pulse' : ''}`}
          />
          {quota && (
            <div className="flex w-9 flex-col items-center gap-1" title={`Serper usage ${quota.used}/${quota.budget}`}>
              <div className="h-10 w-1 overflow-hidden rounded-full bg-brand-black">
                <div className={`w-full rounded-full ${quotaTone} transition-all`} style={{ height: `${Math.min(quotaPct, 100)}%` }} />
              </div>
            </div>
          )}
        </div>
      </nav>

      {/* Mobile / tablet bottom tab bar (< lg) — pb-[env(safe-area-inset-bottom)]
          keeps the tabs clear of the iPhone home indicator (Sprint 6.16). */}
      <nav
        aria-label="Primary navigation"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-brand-midgray bg-brand-darkgray/95 backdrop-blur lg:hidden print:hidden pb-[env(safe-area-inset-bottom)]"
      >
        {NAV_ITEMS.map((item) => (
          <TabLink key={item.path} item={item} active={isActive(location.pathname, item)} />
        ))}
      </nav>
    </>
  )
}
