// src/pages/HistoryPage.jsx
import React, { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { usePredictions, useResults, useMetricsSummary } from '../hooks/useData'
import PredictionTable from '../components/PredictionTable'
import PredictionCard from '../components/PredictionCard'
import { submitResult } from '../services/api'
import { watTodayISO } from '../utils/wat'

// Aligned with backend SportType enum
const SPORTS = ['all', 'soccer', 'basketball']

const todayISO = () => watTodayISO()

export default function HistoryPage() {
  const [searchParams] = useSearchParams()
  const defaultSport = searchParams.get('sport') || 'all'
  const validSport = SPORTS.includes(defaultSport) ? defaultSport : 'all'

  const [sport, setSport]       = useState(validSport)
  const [view, setView]         = useState('table')
  const [expandedGroupId, setExpandedGroupId] = useState(null)
  const [search, setSearch]     = useState('')
  const [resultForm, setResultForm] = useState({
    matchId: '', homeScore: '', awayScore: '', date: todayISO(),
  })
  const [submitting, setSubmitting] = useState(false)
  const [submitMsg, setSubmitMsg]   = useState(null)

  const { data, loading, error, refetch } = usePredictions(
    sport === 'all' ? null : sport,
    200,
    15000,
  )
  const { data: results = [] } = useResults(200, 10000)
  const { data: summary } = useMetricsSummary()
  const engineStatusBySport = summary?.is_trained || null

  const resolvedMatches = results.reduce((map, result) => {
    if (result?.match_id) map[result.match_id] = result
    return map
  }, {})

  const groupHistory = useMemo(() => {
    const groups = new Map()

    for (const pred of data) {
      const groupId = pred?.prediction_group_id
      if (!groupId) continue

      const existing = groups.get(groupId) || {
        groupId,
        matchDate: pred.match_date || pred.timestamp || '',
        games: 0,
        resolved: 0,
        hits: 0,
        highRisk: false,
        sports: new Set(),
        groupIndex: pred.prediction_group_index || null,
        gameItems: [],
      }

      existing.games += 1
      existing.highRisk = existing.highRisk || !!pred.prediction_group_is_high_risk
      if (pred.sport) existing.sports.add(pred.sport)

      const resolved = resolvedMatches[pred.match_id]
      const isResolved = !!resolved?.actual_outcome
      const isCorrect = isResolved && resolved.actual_outcome === pred.predicted_outcome

      if (isResolved) {
        existing.resolved += 1
        if (isCorrect) existing.hits += 1
      }

      existing.gameItems.push({
        matchId: pred.match_id,
        homeTeam: pred.home_team,
        awayTeam: pred.away_team,
        league: pred.league,
        predictedOutcome: pred.predicted_outcome,
        actualOutcome: resolved?.actual_outcome || null,
        isResolved,
        isCorrect,
      })

      groups.set(groupId, existing)
    }

    return Array.from(groups.values())
      .map((g) => {
        const isResolved = g.resolved === g.games && g.games > 0
        const hitRate = g.games > 0 ? g.hits / g.games : 0
        return {
          ...g,
          isResolved,
          status: isResolved ? (g.hits === g.games ? 'won' : 'lost') : 'pending',
          hitRate,
          sportsLabel: Array.from(g.sports).join(', ').toUpperCase() || '—',
          groupLabel: g.groupIndex ? `G${g.groupIndex}` : 'GROUP',
        }
      })
      .sort((a, b) => String(b.matchDate).localeCompare(String(a.matchDate)))
  }, [data, resolvedMatches])

  // Client-side search filter
  const filtered = search.trim().length > 1
    ? data.filter(p => {
        const q = search.toLowerCase()
        return (
          p.home_team?.toLowerCase().includes(q) ||
          p.away_team?.toLowerCase().includes(q) ||
          p.match_id?.toLowerCase().includes(q) ||
          p.league?.toLowerCase().includes(q)
        )
      })
    : data

  const handleResultSubmit = async (e) => {
    e.preventDefault()
    const { matchId, homeScore, awayScore, date } = resultForm

    if (!matchId.trim()) {
      setSubmitMsg({ type: 'error', text: 'Match ID is required — click a row to copy it.' })
      return
    }
    if (homeScore === '' || awayScore === '') {
      setSubmitMsg({ type: 'error', text: 'Both scores are required.' })
      return
    }

    const hs  = parseInt(homeScore, 10)
    const as_ = parseInt(awayScore, 10)

    if (isNaN(hs) || isNaN(as_) || hs < 0 || as_ < 0) {
      setSubmitMsg({ type: 'error', text: 'Scores must be non-negative integers.' })
      return
    }

    setSubmitting(true)
    setSubmitMsg(null)
    try {
      const outcome = hs > as_ ? 'home_win' : as_ > hs ? 'away_win' : 'draw'
      await submitResult({
        match_id:       matchId.trim(),
        home_score:     hs,
        away_score:     as_,
        actual_outcome: outcome,
        match_date:     date || todayISO(),   // never send empty string
      })
      setSubmitMsg({ type: 'success', text: `Result recorded: ${outcome.replace('_', ' ').toUpperCase()}` })
      setResultForm({ matchId: '', homeScore: '', awayScore: '', date: todayISO() })
      refetch()
    } catch (err) {
      setSubmitMsg({ type: 'error', text: err.response?.data?.detail || 'Submission failed' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">PREDICTION HISTORY</h1>
          <p className="font-body text-xs text-gray-600 mt-1">
            {filtered.length} of {data.length} predictions · click row for match ID
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setView('table')}
            className={view === 'table' ? 'btn-primary' : 'btn-ghost'}
          >TABLE</button>
          <button
            onClick={() => setView('cards')}
            className={view === 'cards' ? 'btn-primary' : 'btn-ghost'}
          >CARDS</button>
          <button
            onClick={() => setView('groups')}
            className={view === 'groups' ? 'btn-primary' : 'btn-ghost'}
          >GROUPS</button>
        </div>
      </div>

      {/* Filters row */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <div className="flex gap-1">
          {SPORTS.map(s => (
            <button
              key={s}
              onClick={() => setSport(s)}
              className={`font-display text-xs px-3 py-1 rounded-sm border transition-colors duration-150 ${
                sport === s
                  ? 'bg-brand-red border-brand-red text-white'
                  : 'border-brand-midgray text-gray-500 hover:text-white hover:border-gray-500'
              }`}
            >
              {s.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex-1 min-w-[180px] max-w-xs">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search team, match ID, league..."
            className="w-full bg-brand-gray border border-brand-midgray focus:border-brand-red outline-none text-white font-body text-xs px-3 py-1.5 rounded-sm placeholder-gray-700 transition-colors"
          />
        </div>

        {loading && (
          <div className="w-4 h-4 border-2 border-brand-red border-t-transparent rounded-full animate-spin" />
        )}
      </div>

      {error && (
        <div className="bg-brand-reddark border border-brand-red text-brand-redlight font-display text-xs px-4 py-3 rounded-sm mb-4">
          {error}
        </div>
      )}

      {/* Predictions */}
      {view === 'table' ? (
        <PredictionTable
          predictions={filtered}
          resolvedMatches={resolvedMatches}
          onRefetch={refetch}
          engineStatusBySport={engineStatusBySport}
        />
      ) : view === 'cards' ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
          {loading
            ? [...Array(6)].map((_, i) => (
                <div key={i} className="card p-4 animate-pulse h-40" />
              ))
            : filtered.map((pred, i) => (
                <PredictionCard
                  key={pred.match_id || i}
                  prediction={pred}
                  resolvedMatch={resolvedMatches[pred.match_id]}
                  engineStatusBySport={engineStatusBySport}
                />
              ))}
          {!loading && !filtered.length && (
            <div className="col-span-3 card p-8 text-center">
              <p className="font-display text-gray-600 text-sm">NO PREDICTIONS MATCH YOUR FILTER</p>
            </div>
          )}
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-brand-midgray bg-brand-darkgray">
                <tr>
                  {['GROUP', 'DATE', 'SPORTS', 'GAMES', 'HIT RATE', 'STATUS'].map((h) => (
                    <th key={h} className="text-left label px-4 py-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groupHistory.map((g) => (
                  <React.Fragment key={g.groupId}>
                  <tr
                    className="border-b border-brand-midgray hover:bg-brand-gray transition-colors cursor-pointer"
                    onClick={() => setExpandedGroupId(prev => (prev === g.groupId ? null : g.groupId))}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-display text-xs text-white">{g.groupLabel} · {g.groupId}</span>
                        {g.highRisk && (
                          <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-brand-redlight bg-brand-reddark border-brand-red">
                            HIGH RISK
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-display text-xs text-gray-500">{g.matchDate || '—'}</td>
                    <td className="px-4 py-3 font-display text-xs text-gray-400">{g.sportsLabel}</td>
                    <td className="px-4 py-3 font-display text-xs text-white tabular-nums">
                      {g.resolved}/{g.games}
                    </td>
                    <td className="px-4 py-3 font-display text-xs tabular-nums text-gray-400">
                      {Math.round(g.hitRate * 100)}%
                    </td>
                    <td className="px-4 py-3">
                      <span className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
                        g.status === 'won'
                          ? 'text-brand-greenlight bg-brand-greendark border-brand-green'
                          : g.status === 'lost'
                            ? 'text-brand-redlight bg-brand-reddark border-brand-red'
                            : 'text-gray-400 border-brand-midgray'
                      }`}>
                        {g.status.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                  {expandedGroupId === g.groupId && (
                    <tr className="border-b border-brand-midgray bg-brand-darkgray/30">
                      <td colSpan={6} className="px-4 py-3">
                        <div className="space-y-2">
                          {g.gameItems.map((item) => (
                            <div key={item.matchId} className="flex flex-wrap items-center justify-between gap-2 bg-brand-gray/40 border border-brand-midgray rounded-sm px-3 py-2">
                              <div>
                                <p className="font-display text-xs text-white">
                                  {item.homeTeam} <span className="text-gray-600">vs</span> {item.awayTeam}
                                </p>
                                <p className="font-display text-[10px] text-gray-600">
                                  {item.league || '—'} · {item.matchId}
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-gray-300 border-brand-midgray">
                                  PRED: {item.predictedOutcome ? item.predictedOutcome.replace('_', ' ').toUpperCase() : '—'}
                                </span>
                                <span className={`font-display text-[10px] px-2 py-0.5 rounded-sm border ${
                                  item.isResolved
                                    ? item.isCorrect
                                      ? 'text-brand-greenlight bg-brand-greendark border-brand-green'
                                      : 'text-brand-redlight bg-brand-reddark border-brand-red'
                                    : 'text-gray-400 border-brand-midgray'
                                }`}>
                                  {item.isResolved ? (item.isCorrect ? 'CORRECT' : 'MISS') : 'PENDING'}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {!groupHistory.length && (
            <div className="p-8 text-center">
              <p className="font-display text-gray-600 text-sm">NO GROUP HISTORY FOUND</p>
            </div>
          )}
        </div>
      )}

      {/* Submit actual result */}
      <div className="mt-8 card p-5">
        <p className="label mb-4">SUBMIT ACTUAL RESULT — TRIGGERS LEARNING UPDATE</p>
        <form
          onSubmit={handleResultSubmit}
          className="grid grid-cols-1 md:grid-cols-6 gap-3 items-end"
        >
          {/* Match ID — spans 2 cols */}
          <div className="md:col-span-2">
            <label className="label block mb-1">MATCH ID</label>
            <input
              value={resultForm.matchId}
              onChange={e => setResultForm(p => ({ ...p, matchId: e.target.value }))}
              placeholder="Paste match ID (click row to copy)"
              className="w-full bg-brand-darkgray border border-brand-midgray focus:border-brand-red outline-none text-white font-display text-xs px-3 py-2 rounded-sm placeholder-gray-700 transition-colors"
            />
          </div>

          {/* Home score */}
          <div>
            <label className="label block mb-1">HOME SCORE</label>
            <input
              type="number" min="0"
              value={resultForm.homeScore}
              onChange={e => setResultForm(p => ({ ...p, homeScore: e.target.value }))}
              className="w-full bg-brand-darkgray border border-brand-midgray focus:border-brand-red outline-none text-white font-display text-xs px-3 py-2 rounded-sm"
            />
          </div>

          {/* Away score */}
          <div>
            <label className="label block mb-1">AWAY SCORE</label>
            <input
              type="number" min="0"
              value={resultForm.awayScore}
              onChange={e => setResultForm(p => ({ ...p, awayScore: e.target.value }))}
              className="w-full bg-brand-darkgray border border-brand-midgray focus:border-brand-red outline-none text-white font-display text-xs px-3 py-2 rounded-sm"
            />
          </div>

          {/* Match date — was missing entirely */}
          <div>
            <label className="label block mb-1">MATCH DATE</label>
            <input
              type="date"
              value={resultForm.date}
              onChange={e => setResultForm(p => ({ ...p, date: e.target.value }))}
              className="w-full bg-brand-darkgray border border-brand-midgray focus:border-brand-red outline-none text-white font-display text-xs px-3 py-2 rounded-sm"
            />
          </div>

          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? 'SAVING...' : 'RECORD RESULT'}
          </button>
        </form>

        {submitMsg && (
          <div className={`mt-3 font-display text-xs px-3 py-2 rounded-sm ${
            submitMsg.type === 'success'
              ? 'text-brand-greenlight bg-brand-greendark'
              : 'text-brand-redlight bg-brand-reddark'
          }`}>
            {submitMsg.text}
          </div>
        )}
      </div>
    </div>
  )
}
