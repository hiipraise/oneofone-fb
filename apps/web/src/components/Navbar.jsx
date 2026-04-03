// src/components/Navbar.jsx
import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { healthCheck } from '../services/api'
import { useQuota } from '../hooks/useData'

const NAV_LINKS = [
  { path: '/',             label: 'DASHBOARD' },
  { path: '/predict',      label: 'PREDICT' },
  { path: '/history',      label: 'HISTORY' },
  { path: '/metrics',      label: 'METRICS' },
  { path: '/scheduler',    label: 'SCHEDULER' },
  { path: '/chat',         label: 'AI CHAT' },
]

export default function Navbar({ toggleSidebar }) {
  const location = useLocation()
  const [systemOnline, setSystemOnline] = useState(null)
  const [healthMeta, setHealthMeta] = useState(null)
  const { data: quota } = useQuota()

  useEffect(() => {
    healthCheck()
      .then((res) => {
        setSystemOnline(true)
        setHealthMeta(res.data ?? null)
      })
      .catch(() => setSystemOnline(false))
  }, [])

  const quotaPct      = quota ? Math.round((quota.used / quota.budget) * 100) : 0
  const quotaCritical = quotaPct >= 90
  const quotaWarning  = quotaPct >= 70 && quotaPct < 90

  return (
    <header className="border-b border-brand-midgray bg-brand-darkgray sticky top-0 z-50">
      <div className="flex items-center justify-between px-4 md:px-6 py-3 gap-3">

        {/* Left: hamburger + logo */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={toggleSidebar}
            className="md:hidden text-2xl leading-none text-gray-500 hover:text-white transition-colors"
            aria-label="Open menu"
          >
            ☰
          </button>

          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-brand-red flex items-center justify-center rounded-[3px] shrink-0">
              <span className="font-display text-xs font-medium text-white leading-none">1/1</span>
            </div>
            <div className="hidden sm:block">
              <span className="font-display text-xs text-white tracking-widest">ONEOFONE</span>
              <span className="font-body text-xs text-gray-600 ml-2">SPORTS PREDICTION</span>
            </div>
          </Link>
        </div>

        {/* Center: desktop nav */}
        <nav className="hidden md:flex items-center gap-0.5 flex-1 justify-center">
          {NAV_LINKS.map(({ path, label }) => {
            const active = path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(path)
            return (
              <Link
                key={path}
                to={path}
                className={`font-display text-xs tracking-widest px-4 py-2 transition-colors duration-150 border-b-2 ${
                  active
                    ? 'text-white border-brand-red'
                    : 'text-gray-500 border-transparent hover:text-white hover:border-brand-midgray'
                }`}
              >
                {label}
              </Link>
            )
          })}
        </nav>

        {/* Right: quota warning + system status */}
        <div className="flex items-center gap-3 shrink-0">

          {/* Search quota warning pill — only when ≥ 70% */}
          {quota && (quotaWarning || quotaCritical) && (
            <Link
              to="/metrics"
              className={`hidden sm:flex items-center gap-1.5 font-display text-xs px-2 py-1 rounded-sm border transition-colors ${
                quotaCritical
                  ? 'border-brand-red text-brand-redlight bg-brand-reddark hover:bg-red-900'
                  : 'border-yellow-700 text-yellow-400 bg-yellow-900/30 hover:bg-yellow-900/50'
              }`}
              title={`Serper usage: ${quota.used}/${quota.budget} used`}
            >
              <span>{quotaCritical ? '⚠' : '▲'}</span>
              <span>SERPER {quotaPct}%</span>
            </Link>
          )}

          {/* System status */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full shrink-0 ${
              systemOnline === null
                ? 'bg-gray-500 animate-pulse'
                : systemOnline
                  ? 'bg-brand-green animate-pulse-slow'
                  : 'bg-brand-red'
            }`} />
            <span className="font-display text-xs text-gray-500 hidden sm:block">
              {systemOnline === null ? 'CONNECTING' : systemOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
            {healthMeta && (
              <span
                className="font-display text-[10px] text-gray-700 hidden lg:block"
                title={`DB: ${healthMeta?.services?.database || 'unknown'} · Scheduler: ${healthMeta?.services?.scheduler || 'unknown'} · Uptime: ${Math.round(healthMeta?.uptime_seconds || 0)}s`}
              >
                {healthMeta?.services?.database || 'unknown'} / {healthMeta?.services?.scheduler || 'unknown'}
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
