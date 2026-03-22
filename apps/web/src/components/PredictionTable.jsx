// src/components/PredictionTable.jsx
import React, { useState } from 'react'
import { deletePrediction } from '../services/api'

function outcomeTag(outcome) {
  if (outcome === 'home_win') return <span className="tag-green">HOME WIN</span>
  if (outcome === 'away_win') return <span className="tag-red">AWAY WIN</span>
  if (outcome === 'draw')    return <span className="tag-gray">DRAW</span>
  return <span className="tag-gray">—</span>
}


function resolutionStatus(pred, resolvedMatch) {
  if (!resolvedMatch?.actual_outcome) {
    return { icon: '➖', label: 'Pending', className: 'text-gray-600' }
  }

  if (resolvedMatch.actual_outcome === pred.predicted_outcome) {
    return { icon: '✔️', label: 'Correct', className: 'text-brand-greenlight' }
  }

  return { icon: '❌', label: 'Miss', className: 'text-brand-redlight' }
}

function pctCell(value, highlight = false) {
  const pct = Math.round((value || 0) * 100)
  const color = highlight
    ? 'text-white font-medium'
    : pct >= 60 ? 'text-brand-greenlight'
    : pct >= 45 ? 'text-yellow-500'
    : 'text-brand-redlight'
  return <span className={`font-display text-xs tabular-nums ${color}`}>{pct}%</span>
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = (e) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button
      onClick={handleCopy}
      className="ml-1 font-display text-xs text-gray-700 hover:text-gray-400 transition-colors"
      title="Copy match ID"
    >
      {copied ? '✓' : '⎘'}
    </button>
  )
}

function DeleteButton({ matchId, onDeleted }) {
  const [confirming, setConfirming] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleClick = (e) => {
    e.stopPropagation()
    if (!confirming) { setConfirming(true); return }
    setLoading(true)
    deletePrediction(matchId)
      .then(() => onDeleted(matchId))
      .catch(() => setConfirming(false))
      .finally(() => setLoading(false))
  }

  return (
    <button
      onClick={handleClick}
      onBlur={() => setTimeout(() => setConfirming(false), 200)}
      disabled={loading}
      className={`font-display text-xs px-2 py-0.5 rounded-sm border transition-colors duration-150 ${
        confirming
          ? 'border-brand-red text-brand-redlight bg-brand-reddark'
          : 'border-brand-midgray text-gray-600 hover:border-brand-red hover:text-brand-redlight'
      } disabled:opacity-40`}
      title={confirming ? 'Click again to confirm delete' : 'Delete prediction'}
    >
      {loading ? '...' : confirming ? 'CONFIRM?' : '✕'}
    </button>
  )
}

export default function PredictionTable({ predictions = [], resolvedMatches = {}, showSport = true, onRefetch }) {
  const [sortKey, setSortKey] = useState('timestamp')
  const [sortDir, setSortDir] = useState('desc')
  const [localPreds, setLocalPreds] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [currentPage, setCurrentPage] = useState(1)
  const pageSize = 10

  const items = localPreds ?? predictions

  const handleDeleted = (matchId) => {
    setLocalPreds((localPreds ?? predictions).filter(p => p.match_id !== matchId))
    if (onRefetch) onRefetch()
  }

  const sorted = [...items].sort((a, b) => {
    const av = a[sortKey] ?? '', bv = b[sortKey] ?? ''
    return sortDir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
  })

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize))
  const safePage = Math.min(currentPage, totalPages)
  const startIndex = (safePage - 1) * pageSize
  const paginated = sorted.slice(startIndex, startIndex + pageSize)

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
    setCurrentPage(1)
    setExpandedId(null)
  }

  const goToPage = (nextPage) => {
    setCurrentPage(Math.max(1, Math.min(totalPages, nextPage)))
    setExpandedId(null)
  }

  const Col = ({ label, k, className = '' }) => (
    <th
      onClick={() => k && toggleSort(k)}
      className={`text-left label px-4 py-3 ${k ? 'cursor-pointer hover:text-white transition-colors select-none' : ''} ${className}`}
    >
      {label} {k && sortKey === k ? (sortDir === 'asc' ? '↑' : '↓') : ''}
    </th>
  )

  if (!items.length) {
    return (
      <div className="card p-10 text-center">
        <p className="font-display text-gray-600 text-sm">NO PREDICTIONS RECORDED</p>
        <p className="font-body text-xs text-gray-700 mt-2">Generate predictions from the Predict page</p>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-brand-midgray bg-brand-darkgray">
            <tr>
              <Col label="MATCH ID" k="match_id" />
              <Col label="MATCH" k="home_team" />
              {showSport && <Col label="SPORT" k="sport" />}
              <Col label="PREDICTION" k="predicted_outcome" />
              <Col label="HOME%" k="home_win_probability" />
              {showSport && <Col label="DRAW%" k="draw_probability" />}
              <Col label="AWAY%" k="away_win_probability" />
              <Col label="CONF" k="confidence_score" />
              <Col label="STATUS" k={null} />
              <Col label="DATE" k="timestamp" />
              <Col label="" k={null} className="w-16" />
            </tr>
          </thead>
          <tbody>
            {paginated.map((pred, i) => {
              const isExpanded = expandedId === pred.match_id
              const shortId = pred.match_id
                ? pred.match_id.split('-').slice(0, 2).join('-').toUpperCase()
                : '—'
              const isHome = pred.predicted_outcome === 'home_win'
              const isAway = pred.predicted_outcome === 'away_win'
              const resolvedMatch = resolvedMatches[pred.match_id]
              const status = resolutionStatus(pred, resolvedMatch)

              return (
                <React.Fragment key={pred.match_id || `${startIndex + i}`}>
                  <tr
                    onClick={() => setExpandedId(isExpanded ? null : pred.match_id)}
                    className="border-b border-brand-midgray hover:bg-brand-gray transition-colors duration-100 cursor-pointer"
                  >
                    {/* Match ID */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <span
                          className="font-display text-xs text-gray-600 font-mono tracking-tight"
                          title={pred.match_id}
                        >
                          {shortId}
                        </span>
                        {pred.match_id && <CopyButton text={pred.match_id} />}
                      </div>
                    </td>

                    {/* Match */}
                    <td className="px-4 py-3">
                      <div className="font-display text-xs text-white whitespace-nowrap">
                        <span className={isHome ? 'text-brand-greenlight' : ''}>
                          {pred.home_team}
                        </span>
                        <span className="text-gray-600 mx-1.5">vs</span>
                        <span className={isAway ? 'text-brand-redlight' : ''}>
                          {pred.away_team}
                        </span>
                      </div>
                      {pred.league && (
                        <div className="font-display text-xs text-gray-700 mt-0.5 truncate max-w-[180px]">
                          {pred.league}
                        </div>
                      )}
                    </td>

                    {showSport && (
                      <td className="px-4 py-3">
                        <span className="tag-gray">{pred.sport?.toUpperCase()}</span>
                      </td>
                    )}

                    <td className="px-4 py-3">{outcomeTag(pred.predicted_outcome)}</td>
                    <td className="px-4 py-3">{pctCell(pred.home_win_probability, isHome)}</td>
                    {showSport && (
                      <td className="px-4 py-3">
                        {pctCell(pred.draw_probability)}
                      </td>
                    )}
                    <td className="px-4 py-3">{pctCell(pred.away_win_probability, isAway)}</td>
                    <td className="px-4 py-3">{pctCell(pred.confidence_score)}</td>
                    <td className="px-4 py-3">
                      <div className={`font-display text-xs flex items-center gap-1.5 whitespace-nowrap ${status.className}`}>
                        <span>{status.icon}</span>
                        <span>{status.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-display text-xs text-gray-600 whitespace-nowrap">
                        {pred.timestamp
                          ? new Date(pred.timestamp).toLocaleDateString()
                          : pred.match_date || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      <DeleteButton matchId={pred.match_id} onDeleted={handleDeleted} />
                    </td>
                  </tr>

                  {/* Expanded match ID row */}
                  {isExpanded && pred.match_id && (
                    <tr className="border-b border-brand-midgray bg-brand-darkgray">
                      <td colSpan={showSport ? 11 : 9} className="px-4 py-3">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="label">FULL MATCH ID</span>
                          <code className="font-display text-xs text-gray-400 bg-brand-gray px-2 py-1 rounded-sm break-all">
                            {pred.match_id}
                          </code>
                          <CopyButton text={pred.match_id} />
                          {pred.model_version && (
                            <span className="font-display text-xs text-gray-600">
                              Model v{pred.model_version}
                              {pred.is_trained_model === false && (
                                <span className="ml-2 text-yellow-600">PRIOR</span>
                              )}
                            </span>
                          )}
                          {(pred.confidence_interval_low != null) && (
                            <span className="font-display text-xs text-gray-600">
                              CI: {Math.round(pred.confidence_interval_low * 100)}%–{Math.round(pred.confidence_interval_high * 100)}%
                            </span>
                          )}
                          {resolvedMatch?.actual_outcome && (
                            <span className={`font-display text-xs ${status.className}`}>
                              {status.icon} Actual: {resolvedMatch.actual_outcome.replace('_', ' ').toUpperCase()}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="px-4 py-2 border-t border-brand-midgray flex items-center justify-between">
        <div className="font-display text-xs text-gray-700">
          {startIndex + 1}–{Math.min(startIndex + pageSize, sorted.length)} of {sorted.length} PREDICTIONS
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => goToPage(safePage - 1)}
            disabled={safePage === 1}
            className="font-display text-xs px-2 py-1 rounded-sm border border-brand-midgray text-gray-600 disabled:opacity-40"
          >
            PREV
          </button>
          <span className="font-display text-xs text-gray-700">PAGE {safePage}/{totalPages}</span>
          <button
            onClick={() => goToPage(safePage + 1)}
            disabled={safePage === totalPages}
            className="font-display text-xs px-2 py-1 rounded-sm border border-brand-midgray text-gray-600 disabled:opacity-40"
          >
            NEXT
          </button>
          <span className="font-display text-xs text-gray-700 hidden sm:inline">CLICK ROW TO EXPAND · ✕ TO DELETE</span>
        </div>
      </div>
    </div>
  )
}
