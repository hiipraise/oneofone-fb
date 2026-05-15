// src/components/PredictionCard.jsx
import React, { useState } from 'react'
import { formatWatDate } from '../utils/wat'

// ─── Probability bar ─────────────────────────────────────────────────────────
function ProbBar({ label, value, isWinner }) {
  const pct = Math.round((value ?? 0) * 100)
  const barColor = isWinner ? 'bg-brand-green' : 'bg-brand-midgray'
  const textColor = isWinner ? 'text-brand-greenlight' : 'text-gray-400'

  return (
    <div className="flex items-center gap-3">
      <span className="font-display text-xs text-gray-500 w-24 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-brand-darkgray rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`font-display text-xs w-10 text-right tabular-nums ${textColor}`}>
        {pct}%
      </span>
    </div>
  )
}

// ─── Confidence badge ────────────────────────────────────────────────────────
function ConfidenceBadge({ value }) {
  const pct = Math.round((value ?? 0) * 100)
  const color =
    pct >= 60 ? 'text-brand-greenlight bg-brand-greendark border-brand-green'
    : pct >= 35 ? 'text-yellow-400 bg-yellow-900/30 border-yellow-700'
    :             'text-brand-redlight bg-brand-reddark border-brand-red'
  return (
    <span className={`font-display text-xs px-2 py-0.5 rounded-sm border ${color}`}>
      {pct}% confidence
    </span>
  )
}

// ─── BTTS badge ──────────────────────────────────────────────────────────────
function BttsBadge({ btts }) {
  if (!btts) return null
  const isYes = btts.result === 'Yes'
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-display text-xs text-gray-600">GG</span>
      <span className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
        isYes
          ? 'text-brand-greenlight bg-brand-greendark border-brand-green'
          : 'text-brand-redlight bg-brand-reddark border-brand-red'
      }`}>
        {isYes ? `Yes ${btts.yes_pct}%` : `No ${btts.no_pct}%`}
      </span>
    </div>
  )
}


function getActualBtts(resolvedMatch) {
  if (resolvedMatch?.home_score == null || resolvedMatch?.away_score == null) return null
  const homeScore = Number(resolvedMatch.home_score)
  const awayScore = Number(resolvedMatch.away_score)
  if (!Number.isFinite(homeScore) || !Number.isFinite(awayScore)) return null
  return homeScore > 0 && awayScore > 0 ? 'Yes' : 'No'
}

function getPredictedBtts(btts) {
  if (!btts) return null
  if (['Yes', 'No'].includes(btts.result)) return btts.result

  const yes = Number(btts.yes)
  const no = Number(btts.no)
  if (Number.isFinite(yes) && Number.isFinite(no)) return yes >= no ? 'Yes' : 'No'
  if (Number.isFinite(yes)) return yes >= 0.5 ? 'Yes' : 'No'
  if (Number.isFinite(no)) return no >= 0.5 ? 'No' : 'Yes'
  return null
}

function BttsAccuracyBadge({ btts, resolvedMatch }) {
  const predicted = getPredictedBtts(btts)
  const actual = getActualBtts(resolvedMatch)
  if (!predicted || !actual) return null

  const correct = predicted === actual
  return (
    <span className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
      correct
        ? 'text-brand-greenlight bg-brand-greendark border-brand-green'
        : 'text-brand-redlight bg-brand-reddark border-brand-red'
    }`}>
      GG {correct ? '✔ Correct' : '✖ Miss'}
    </span>
  )
}

function getPredictedCorners(corners) {
  if (!corners) return null
  const line = Number.isFinite(Number(corners.line)) ? Number(corners.line) : 9.5
  if (['Over', 'Under'].includes(corners.result)) return { side: corners.result, line }

  const market = corners[`line_${String(line).replace('.', '_')}`] || corners.line_9_5
  const over = Number(market?.over)
  const under = Number(market?.under)
  if (Number.isFinite(over) && Number.isFinite(under)) {
    return { side: over >= under ? 'Over' : 'Under', line }
  }

  const expected = Number(corners.expected_total)
  if (Number.isFinite(expected)) return { side: expected > line ? 'Over' : 'Under', line }
  return null
}

function CornersBadge({ corners, resolvedMatch }) {
  if (!corners) return null
  const expected = Number(corners.expected_total)
  const predicted = getPredictedCorners(corners)
  const hasExpected = Number.isFinite(expected)
  if (!hasExpected && !predicted) return null

  const actualTotal = Number(resolvedMatch?.actual_corner_total ?? resolvedMatch?.corner_total)
  const hasActual = Number.isFinite(actualTotal) && predicted
  const actualSide = hasActual ? (actualTotal > predicted.line ? 'Over' : 'Under') : null
  const correct = hasActual ? actualSide === predicted.side : false

  return (
    <div className="flex items-center gap-1.5">
      <span className="font-display text-xs text-gray-600">CORNERS</span>
      <span className="font-display text-xs px-2 py-0.5 rounded-sm border text-gray-300 bg-brand-darkgray border-brand-midgray">
        {predicted ? `${predicted.side} ${predicted.line.toFixed(1)}` : (hasExpected ? `Exp ${expected.toFixed(1)}` : 'Exp —')}
      </span>
      {hasActual && (
        <span className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
          correct
            ? 'text-brand-greenlight bg-brand-greendark border-brand-green'
            : 'text-brand-redlight bg-brand-reddark border-brand-red'
        }`}>
          {correct ? '✔ Correct' : '✖ Miss'}
        </span>
      )}
    </div>
  )
}

// ─── Main card ───────────────────────────────────────────────────────────────

function ResolutionBadge({ prediction, resolvedMatch }) {
  if (!prediction?.match_id) return null

  if (!resolvedMatch?.actual_outcome) {
    return (
      <span className="font-display text-xs px-2 py-0.5 rounded-sm border border-brand-midgray text-gray-500">
        ➖ Pending
      </span>
    )
  }

  const correct = resolvedMatch.actual_outcome === prediction.predicted_outcome

  return (
    <span className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
      correct
        ? 'text-brand-greenlight bg-brand-greendark border-brand-green'
        : 'text-brand-redlight bg-brand-reddark border-brand-red'
    }`}>
      {correct ? '✔️ Correct' : '❌ Miss'}
    </span>
  )
}

export default function PredictionCard({ prediction, resolvedMatch, engineStatusBySport = null }) {
  const [expanded, setExpanded] = useState(false)

  if (!prediction) return null

  const {
    match_id,
    home_team, away_team, sport, league, match_date,
    home_win_probability, away_win_probability, draw_probability,
    predicted_outcome, confidence_score,
    confidence_interval_low, confidence_interval_high,
    model_version, timestamp, data_sources,
    extended_markets,
    is_trained_model,
  } = prediction

  const normalizedSport = (sport || '').toLowerCase()
  const engineStatusForSport =
    engineStatusBySport && normalizedSport
      ? engineStatusBySport[normalizedSport]
      : null
  const isEngineActive =
    typeof engineStatusForSport === 'boolean'
      ? engineStatusForSport
      : (is_trained_model !== false)

  const bttsData = extended_markets?.btts ?? null
  const normalizedDataSources = (data_sources || []).filter(Boolean).map((src) => {
    if (typeof src === 'string') {
      return { title: src, link: src, source: null }
    }
    return {
      title: src.title || src.link || src.source || 'Source',
      link: src.link || '',
      source: src.source || null,
    }
  })

  // Which bar is the predicted winner?
  const winnerIs = predicted_outcome   // "home_win" | "away_win" | "draw"

  // Outcome label (short)
  const outcomeLabel =
    predicted_outcome === 'home_win' ? `${home_team} to Win`
    : predicted_outcome === 'away_win' ? `${away_team} to Win`
    : 'Draw'

  const outcomeColor =
    predicted_outcome === 'home_win' ? 'text-brand-greenlight'
    : predicted_outcome === 'away_win' ? 'text-brand-redlight'
    : 'text-yellow-400'

  const cornersData = extended_markets?.corners ?? null

  const ciLow  = Math.round((confidence_interval_low  ?? 0) * 100)
  const ciHigh = Math.round((confidence_interval_high ?? 0) * 100)

  const dateLabel =
    match_date
    || (timestamp && formatWatDate(timestamp))
    || '—'

  return (
    <div className="card p-4 animate-slide-up hover:border-gray-600 transition-colors duration-200">

      {/* Header */}
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            {sport && <span className="tag-gray">{sport.toUpperCase()}</span>}
            {league && <span className="tag-gray truncate max-w-[120px]">{league}</span>}
            <ResolutionBadge prediction={prediction} resolvedMatch={resolvedMatch} />
            <span className={`tag-gray ${isEngineActive ? 'text-brand-greenlight' : 'text-yellow-600'}`}>
              {isEngineActive ? 'ML ACTIVE' : 'PRIOR MODE'}
            </span>
          </div>
          <p className="font-display text-sm text-white leading-snug">
            {home_team}
            <span className="text-gray-600 mx-1.5 text-xs">vs</span>
            {away_team}
          </p>
          <p className="font-display text-xs text-gray-600 mt-0.5">{dateLabel}</p>
        </div>

        <div className="text-right shrink-0">
          <p className={`font-display text-sm font-medium ${outcomeColor}`}>{outcomeLabel}</p>
          <ConfidenceBadge value={confidence_score} />
        </div>
      </div>

      {/* Probability bars */}
      <div className="flex flex-col gap-2 my-3">
        <ProbBar
          label={home_team}
          value={home_win_probability}
          isWinner={winnerIs === 'home_win'}
        />
        <ProbBar
          label="Draw"
          value={draw_probability}
          isWinner={winnerIs === 'draw'}
        />
        <ProbBar
          label={away_team}
          value={away_win_probability}
          isWinner={winnerIs === 'away_win'}
        />
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between pt-2 border-t border-brand-midgray gap-2 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <div>
            <span className="label">CI</span>
            <p className="font-display text-xs text-gray-500 mt-0.5 tabular-nums">
              {ciLow}%–{ciHigh}%
            </p>
          </div>
          <div>
            <span className="label">MODEL</span>
            <p className="font-display text-xs text-gray-500 mt-0.5">v{model_version}</p>
          </div>
          <BttsBadge btts={bttsData} />
          <BttsAccuracyBadge btts={bttsData} resolvedMatch={resolvedMatch} />
          <CornersBadge corners={cornersData} resolvedMatch={resolvedMatch} />
        </div>
        <button
          onClick={() => setExpanded(p => !p)}
          className="font-display text-xs text-gray-600 hover:text-white transition-colors shrink-0"
        >
          {expanded ? 'LESS ↑' : 'MORE ↓'}
        </button>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-brand-midgray animate-fade-in space-y-3">

          {/* Match ID */}
          {match_id && (
            <div>
              <p className="label mb-1">MATCH ID</p>
              <p className="font-display text-xs text-gray-600 break-all">{match_id}</p>
            </div>
          )}

          {resolvedMatch?.actual_outcome && (
            <div>
              <p className="label mb-1">RESOLUTION</p>
              <p className="font-display text-xs text-gray-400">
                Actual outcome: {resolvedMatch.actual_outcome.replace('_', ' ').toUpperCase()}
              </p>
              {(resolvedMatch.home_score != null && resolvedMatch.away_score != null) && (
                <>
                  <p className="font-display text-xs text-gray-600 mt-1">
                    Final score: {resolvedMatch.home_score} - {resolvedMatch.away_score}
                  </p>
                  {bttsData && (
                    <p className="font-display text-xs text-gray-600 mt-1">
                      GG actual: {getActualBtts(resolvedMatch) || '—'} · Predicted: {getPredictedBtts(bttsData) || '—'}
                    </p>
                  )}
                </>
              )}
            </div>
          )}

          {/* Goals O/U summary */}
          {extended_markets?.goals_over_under && (
            <div>
              <p className="label mb-2">GOALS O/U</p>
              <div className="grid grid-cols-3 gap-1.5">
                {['1_5', '2_5', '3_5'].map(key => {
                  const market = extended_markets.goals_over_under[`over_${key}`]
                  if (!market) return null
                  const label = key.replace('_', '.')
                  return (
                    <div key={key} className="bg-brand-darkgray border border-brand-midgray p-2 rounded-sm text-center">
                      <p className="font-display text-xs text-gray-600">O{label}</p>
                      <p className="font-display text-xs text-white mt-0.5">
                        {Math.round(market.over * 100)}%
                      </p>
                    </div>
                  )
                })}
              </div>
              <p className="font-display text-xs text-gray-600 mt-1.5">
                xG: {extended_markets.goals_over_under.home_xg} – {extended_markets.goals_over_under.away_xg}
                &nbsp;(total {extended_markets.goals_over_under.expected_goals})
              </p>
            </div>
          )}

          {/* Correct score top 3 */}
          {extended_markets?.correct_score?.length > 0 && (
            <div>
              <p className="label mb-2">TOP CORRECT SCORES</p>
              <div className="flex flex-wrap gap-1.5">
                {extended_markets.correct_score.slice(0, 5).map(cs => (
                  <div key={cs.score} className="bg-brand-darkgray border border-brand-midgray px-2 py-1 rounded-sm">
                    <span className="font-display text-xs text-white">{cs.score}</span>
                    <span className="font-display text-xs text-gray-600 ml-1.5">
                      {Math.round(cs.probability * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Data sources */}
          {normalizedDataSources.length > 0 && (
            <div>
              <p className="label mb-1">DATA SOURCES</p>
              <div className="flex flex-wrap gap-2">
                {normalizedDataSources.map((src, i) => {
                  const hasLink = Boolean(src.link)
                  const safeLink = hasLink
                    ? (src.link.startsWith('http') ? src.link : `https://${src.link}`)
                    : null

                  return (
                    <div key={`${src.title}-${i}`} className="inline-flex items-center gap-1">
                      {hasLink ? (
                        <a
                          href={safeLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="tag-gray hover:text-brand-red transition-colors"
                          title={src.title}
                        >
                          {src.title}
                        </a>
                      ) : (
                        <span className="tag-gray">{src.title}</span>
                      )}
                      {src.source && (
                        <span className="font-display text-[10px] uppercase tracking-wide text-gray-600 border border-brand-midgray px-1 py-0.5 rounded-sm">
                          Source: {src.source}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
