// src/components/Sidebar.jsx
import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { getMetricsSummary } from '../services/api'
import { useQuota } from '../hooks/useData'
import { getMlWeightState, ML_ACTIVATION_THRESHOLD } from './MlWeightLogic'

const NAV_ITEMS = [
  { path: '/',             label: 'Dashboard',      icon: '◈' },
  { path: '/predict',      label: 'New Prediction', icon: '⊕' },
  { path: '/history',      label: 'History',        icon: '≡' },
  { path: '/metrics',      label: 'Model Metrics',  icon: '◎' },
  { path: '/scheduler',    label: 'Scheduler',      icon: '⏱' },
  { path: '/chat',         label: 'AI Chat',        icon: '⌘' },
  { path: '/chat/history', label: 'Chat History',   icon: '◷' },
]

const SPORTS = [
  { key: 'soccer',     label: 'Football',   dot: 'bg-brand-green'  },
  { key: 'basketball', label: 'Basketball', dot: 'bg-yellow-500'   },
]

function NavItem({ path, label, icon, isActive }) {
  return (
    <Link
      to={path}
      className={`flex items-center gap-3 px-3 py-2 rounded-sm transition-all duration-150 group ${
        isActive
          ? 'bg-brand-midgray text-white'
          : 'text-gray-500 hover:text-white hover:bg-brand-gray'
      }`}
    >
      <span className={`text-sm shrink-0 transition-colors ${
        isActive ? 'text-brand-red' : 'text-gray-600 group-hover:text-brand-red'
      }`}>
        {icon}
      </span>
      <span className="font-body text-sm truncate">{label}</span>
      {isActive && (
        <span className="ml-auto w-1 h-4 bg-brand-red rounded-full shrink-0" />
      )}
    </Link>
  )
}

// ── Serper.dev / Search quota bar ─────────────────────────────────────────────
function QuotaBar({ quota, loading }) {
  if (loading) {
    return (
      <div className="px-3 py-2">
        <div className="h-2 bg-brand-midgray rounded-full animate-pulse" />
      </div>
    )
  }
  if (!quota) return null

  const pct       = Math.round((quota.used / quota.budget) * 100)
  const remaining = quota.remaining ?? (quota.budget - quota.used)
  const barColor  = pct >= 90 ? 'bg-brand-red'  : pct >= 70 ? 'bg-yellow-500' : 'bg-brand-green'
  const textColor = pct >= 90 ? 'text-brand-redlight' : pct >= 70 ? 'text-yellow-400' : 'text-brand-greenlight'

  return (
    <div className="p-3 border-b border-brand-midgray">
      <div className="flex items-center justify-between mb-1.5">
        {/* Updated label — reflects Serper.dev */}
        <p className="label">SERPER USAGE</p>
        <span className={`font-display text-xs tabular-nums ${textColor}`}>
          {quota.used}/{quota.budget}
        </span>
      </div>
      <div className="h-1.5 bg-brand-darkgray rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <div className="flex items-center justify-between mt-1">
        <span className="font-display text-xs text-gray-700">
          serper.dev · {quota.month || 'this month'}
        </span>
        <span className={`font-display text-xs ${textColor}`}>
          {remaining} left
        </span>
      </div>
      {pct >= 90 && (
        <div className="mt-2 bg-brand-reddark border border-brand-red rounded-sm px-2 py-1">
          <p className="font-display text-xs text-brand-redlight">⚠ BUDGET CRITICAL</p>
        </div>
      )}
    </div>
  )
}

// ── ML weight row ─────────────────────────────────────────────────────────────
function MlWeightRow({ sport, weight, nSamples, dot }) {
  const { n, wPct, active, progressPct, mlBarColor, mlTextColor, threshold } = getMlWeightState(weight, nSamples)

  return (
    <div className="flex items-center gap-2 py-1">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
      <span className="font-display text-xs text-gray-500 w-16 truncate capitalize">{sport}</span>
      <div className="relative flex-1 h-1 bg-brand-darkgray rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${active ? mlBarColor : 'bg-blue-500 opacity-40'}`}
          style={{ width: `${active ? Math.min(wPct, 100) : progressPct}%` }}
        />
        {!active && <div className="absolute right-0 top-0 w-px h-full bg-gray-600" />}
      </div>
      <span className={`font-display text-xs tabular-nums w-10 text-right ${active ? mlTextColor : 'text-blue-400'}`}>
        {active ? `${wPct}%` : `${n}/${threshold}`}
      </span>
    </div>
  )
}

export default function Sidebar({ isOpen = false, onClose }) {
  const location = useLocation()
  const [modelSummary, setModelSummary] = useState(null)
  const [summaryError, setSummaryError] = useState(false)
  const { data: quota, loading: quotaLoading } = useQuota()

  useEffect(() => {
    setSummaryError(false)
    getMetricsSummary()
      .then(r => setModelSummary(r.data ?? null))
      .catch(err => {
        console.error('[Sidebar] metrics/summary failed:', err)
        setSummaryError(true)
      })
  }, [])

  const isActive = (path) => {
    if (path === '/')     return location.pathname === '/'
    if (path === '/chat') return location.pathname === '/chat'
    return location.pathname.startsWith(path)
  }

  const searchSport = new URLSearchParams(location.search).get('sport') || ''

  const mlWeights = modelSummary?.ml_weights         ?? { soccer: 0, basketball: 0 }
  const nSamples  = modelSummary?.n_training_samples ?? { soccer: 0, basketball: 0 }
  const isTrained = modelSummary?.is_trained         ?? { soccer: false, basketball: false }

  return (
    <aside className={`
      fixed top-[53px] left-0 z-50 w-56 h-[calc(100vh-53px)] overflow-y-auto
      border-r border-brand-midgray bg-brand-darkgray flex flex-col
      transform transition-transform duration-300 ease-in-out
      ${isOpen ? 'translate-x-0' : '-translate-x-full'}
      md:translate-x-0 md:z-auto
    `}>

      {/* Mobile close */}
      <div className="md:hidden flex items-center justify-between p-3 border-b border-brand-midgray shrink-0">
        <span className="font-display text-xs text-white tracking-widest">MENU</span>
        <button
          onClick={onClose}
          className="text-2xl leading-none text-gray-500 hover:text-white transition-colors"
          aria-label="Close sidebar"
        >×</button>
      </div>

      {/* Navigation */}
      <div className="p-3 border-b border-brand-midgray shrink-0">
        <p className="label px-3 py-1.5 mb-1">NAVIGATION</p>
        <nav className="flex flex-col gap-0.5">
          {NAV_ITEMS.map(item => (
            <NavItem key={item.path} {...item} isActive={isActive(item.path)} />
          ))}
        </nav>
      </div>

      {/* Sports quick-links */}
      <div className="p-3 border-b border-brand-midgray shrink-0">
        <p className="label px-3 py-1.5 mb-1">SPORTS</p>
        <div className="flex flex-col gap-0.5">
          {SPORTS.map(sport => (
            <Link
              key={sport.key}
              to={`/history?sport=${sport.key}`}
              className={`flex items-center justify-between px-3 py-1.5 rounded-sm transition-colors group ${
                location.pathname === '/history' && searchSport === sport.key
                  ? 'bg-brand-gray text-white'
                  : 'text-gray-500 hover:text-white hover:bg-brand-gray'
              }`}
            >
              <span className="font-body text-xs">{sport.label}</span>
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${sport.dot} opacity-50 group-hover:opacity-100 transition-opacity`} />
            </Link>
          ))}
        </div>
      </div>

      {/* Serper.dev / Search quota */}
      <QuotaBar quota={quota} loading={quotaLoading} />

      {/* ML Weight per sport */}
      <div className="p-3 border-b border-brand-midgray shrink-0">
        <p className="label px-0 py-1 mb-2">ML WEIGHT / SPORT</p>
        {summaryError ? (
          <p className="font-display text-xs text-gray-700 px-1">Unavailable</p>
        ) : !modelSummary ? (
          <div className="flex flex-col gap-2 px-1">
            {SPORTS.map(s => (
              <div key={s.key} className="h-3 bg-brand-midgray rounded animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-0.5 px-1">
            {SPORTS.map(s => (
              <MlWeightRow
                key={s.key}
                sport={s.key}
                weight={mlWeights[s.key]}
                nSamples={nSamples[s.key]}
                dot={s.dot}
              />
            ))}
            <p className="font-display text-xs text-gray-700 mt-2">
              {SPORTS.some(s => (nSamples[s.key] ?? 0) >= ML_ACTIVATION_THRESHOLD)
                ? 'Higher = more ML, less prior model'
                : `Building toward ML activation (${ML_ACTIVATION_THRESHOLD} samples per sport)`}
            </p>
          </div>
        )}
      </div>

      {/* Model status */}
      <div className="p-3 mt-auto shrink-0">
        <div className="card p-3">
          <p className="label mb-2">MODEL STATUS</p>

          {modelSummary ? (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="font-display text-xs text-gray-600">ENGINE</span>
                <span className={`font-display text-xs ${
                  Object.values(isTrained).some(Boolean)
                    ? 'text-brand-greenlight' : 'text-yellow-500'
                }`}>
                  {Object.values(isTrained).some(Boolean) ? 'ML ACTIVE' : 'PRIOR MODE'}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="font-display text-xs text-gray-600">VERSION</span>
                <span className="font-display text-xs text-gray-400">
                  v{modelSummary.model_version || '3.0.0'}
                </span>
              </div>

              {modelSummary.performance_metrics?.accuracy != null && (
                <div className="flex items-center justify-between">
                  <span className="font-display text-xs text-gray-600">ACCURACY</span>
                  <span className={`font-display text-xs tabular-nums ${
                    modelSummary.performance_metrics.accuracy > 0.6
                      ? 'text-brand-greenlight'
                      : modelSummary.performance_metrics.accuracy > 0.5
                      ? 'text-yellow-500'
                      : 'text-brand-redlight'
                  }`}>
                    {(modelSummary.performance_metrics.accuracy * 100).toFixed(1)}%
                  </span>
                </div>
              )}

              <div className="flex items-center justify-between">
                <span className="font-display text-xs text-gray-600">PREDICTIONS</span>
                <span className="font-display text-xs text-gray-400 tabular-nums">
                  {(modelSummary.total_predictions || 0).toLocaleString()}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="font-display text-xs text-gray-600">RESOLVED</span>
                <span className="font-display text-xs text-gray-400 tabular-nums">
                  {(modelSummary.total_resolved || 0).toLocaleString()}
                </span>
              </div>

              {/* Per-sport sample counts */}
              <div className="pt-1.5 border-t border-brand-midgray">
                <p className="font-display text-xs text-gray-600 mb-1">TRAINING SAMPLES</p>
                {SPORTS.map(s => (
                  <div key={s.key} className="flex items-center justify-between py-0.5">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                      <span className="font-display text-xs text-gray-600 capitalize">{s.key}</span>
                    </div>
                    <span className={`font-display text-xs tabular-nums ${
                      (nSamples[s.key] ?? 0) >= 100
                        ? 'text-brand-greenlight'
                        : (nSamples[s.key] ?? 0) >= ML_ACTIVATION_THRESHOLD
                        ? 'text-yellow-400'
                        : 'text-gray-600'
                    }`}>
                      {(nSamples[s.key] ?? 0).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>

              {modelSummary.performance_metrics?.brier_score != null && (
                <div className="pt-1.5 border-t border-brand-midgray">
                  <div className="flex items-center justify-between">
                    <span className="font-display text-xs text-gray-600">BRIER</span>
                    <span className={`font-display text-xs tabular-nums ${
                      modelSummary.performance_metrics.brier_score < 0.20
                        ? 'text-brand-greenlight'
                        : modelSummary.performance_metrics.brier_score < 0.25
                        ? 'text-yellow-500'
                        : 'text-brand-redlight'
                    }`}>
                      {modelSummary.performance_metrics.brier_score.toFixed(4)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="font-display text-xs text-gray-600">ENGINE</span>
                <span className="font-display text-xs text-brand-greenlight">OPERATIONAL</span>
              </div>
              <div className="h-1.5 bg-brand-midgray rounded-full animate-pulse w-full mt-1" />
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}