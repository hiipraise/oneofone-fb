// src/charts/ConfidenceHistoryChart.jsx
import React, { useMemo, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { useConfidenceHistory } from '../hooks/useData'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

const SPORTS = ['soccer']

const SPORT_COLORS = {
  soccer:     { line: '#16a34a', fill: 'rgba(22,163,74,0.08)',   point: '#16a34a' },
}

const RANGE_OPTIONS = [
  { label: '7D',  value: 7  },
  { label: '30D', value: 30 },
  { label: '90D', value: 90 },
]

function buildDatasets(rows, activeSports) {
  // Collect all unique dates across all sports
  const dateSet = new Set(rows.map(r => r.date))
  const labels  = [...dateSet].sort()

  const datasets = []

  for (const sport of SPORTS) {
    if (!activeSports.includes(sport)) continue

    const byDate = {}
    for (const row of rows) {
      if (row.sport === sport) byDate[row.date] = row
    }

    const avgData = labels.map(d => byDate[d] ? round2(byDate[d].avg * 100) : null)
    const maxData = labels.map(d => byDate[d] ? round2(byDate[d].max * 100) : null)
    const minData = labels.map(d => byDate[d] ? round2(byDate[d].min * 100) : null)
    const counts  = labels.map(d => byDate[d]?.count ?? 0)

    const c = SPORT_COLORS[sport]

    // Shaded band — max line (invisible, just for fill reference)
    datasets.push({
      label:           `${sport}_max`,
      data:            maxData,
      borderColor:     'transparent',
      backgroundColor: c.fill,
      pointRadius:     0,
      fill:            '+1',   // fill down to the min line below it
      tension:         0.4,
      _sport:          sport,
      _type:           'band',
    })

    // Min line (invisible)
    datasets.push({
      label:           `${sport}_min`,
      data:            minData,
      borderColor:     'transparent',
      backgroundColor: 'transparent',
      pointRadius:     0,
      fill:            false,
      tension:         0.4,
      _sport:          sport,
      _type:           'band',
    })

    // Avg line — the one users see in the legend
    datasets.push({
      label:           sport.charAt(0).toUpperCase() + sport.slice(1),
      data:            avgData,
      borderColor:     c.line,
      backgroundColor: 'transparent',
      borderWidth:     2,
      pointRadius:     avgData.map(v => v !== null ? 3 : 0),
      pointBackgroundColor: c.point,
      tension:         0.4,
      fill:            false,
      _sport:          sport,
      _type:           'avg',
      _counts:         counts,
    })
  }

  return { labels, datasets }
}

function round2(n) {
  return Math.round(n * 100) / 100
}

export default function ConfidenceHistoryChart() {
  const [days, setDays]           = useState(30)
  const [activeSports, setActive] = useState([...SPORTS])
  const { data: rows, loading }   = useConfidenceHistory(days)

  const toggleSport = (sport) =>
    setActive(prev =>
      prev.includes(sport)
        ? prev.length > 1 ? prev.filter(s => s !== sport) : prev  // always keep ≥1
        : [...prev, sport]
    )

  const { labels, datasets } = useMemo(
    () => buildDatasets(rows, activeSports),
    [rows, activeSports]
  )

  // Only show avg datasets in the legend
  const legendDatasets = datasets.filter(d => d._type === 'avg')

  const chartData = { labels, datasets }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },  // we draw our own legend below
      tooltip: {
        backgroundColor: '#1a1a1a',
        borderColor:     '#2a2a2a',
        borderWidth:     1,
        titleColor:      '#9ca3af',
        bodyColor:       '#ffffff',
        titleFont:       { family: '"DM Mono"', size: 10 },
        bodyFont:        { family: '"DM Mono"', size: 11 },
        filter: (item) => item.dataset._type === 'avg',
        callbacks: {
          title: (items) => items[0]?.label ?? '',
          label: (ctx) => {
            const sport  = ctx.dataset._sport
            const date   = labels[ctx.dataIndex]
            const row    = rows.find(r => r.sport === sport && r.date === date)
            if (!row) return ''
            return [
              ` ${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%`,
              ` Range: ${round2(row.min * 100)}% – ${round2(row.max * 100)}%`,
              ` Predictions: ${row.count}`,
            ]
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#4b5563',
          font:  { family: '"DM Mono"', size: 10 },
          maxTicksLimit: 10,
          maxRotation: 0,
        },
        grid:   { color: '#1a1a1a' },
        border: { color: '#2a2a2a' },
      },
      y: {
        min:  0,
        max:  100,
        ticks: {
          color:    '#6b7280',
          font:     { family: '"DM Mono"', size: 10 },
          callback: v => `${v}%`,
          stepSize: 20,
        },
        grid:   { color: '#1a1a1a' },
        border: { color: '#2a2a2a' },
        title: {
          display: true,
          text:    'Confidence Score',
          color:   '#6b7280',
          font:    { family: '"DM Mono"', size: 10 },
        },
      },
    },
  }

  // Empty state — no data at all
  if (!loading && !rows.length) {
    return (
      <div className="card p-4">
        <p className="label mb-4">CONFIDENCE SCORE — HISTORY BY SPORT</p>
        <div className="flex items-center justify-center" style={{ height: 220 }}>
          <p className="font-display text-gray-600 text-sm">NO PREDICTIONS YET</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card p-4">
      {/* Header row */}
      <div className="flex flex-col gap-3 mb-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="label">CONFIDENCE SCORE — HISTORY BY SPORT</p>
          <p className="font-display text-xs text-gray-700 mt-0.5">
            Daily avg ± range · shaded band = min/max
          </p>
        </div>

        {/* Time range pills */}
        <div className="flex flex-wrap gap-1">
          {RANGE_OPTIONS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setDays(value)}
              className={`font-display text-xs px-2.5 py-1 rounded-sm border transition-colors ${
                days === value
                  ? 'bg-brand-red border-brand-red text-white'
                  : 'border-brand-midgray text-gray-500 hover:text-white'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Sport toggle chips */}
      <div className="flex flex-wrap gap-2 mb-3">
        {SPORTS.map(sport => {
          const c      = SPORT_COLORS[sport]
          const active = activeSports.includes(sport)
          return (
            <button
              key={sport}
              onClick={() => toggleSport(sport)}
              className={`flex items-center gap-1.5 font-display text-xs px-2.5 py-1 rounded-sm border transition-all ${
                active
                  ? 'border-current text-white bg-brand-gray'
                  : 'border-brand-midgray text-gray-600 hover:text-gray-400'
              }`}
              style={active ? { borderColor: c.line, color: c.line } : {}}
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: active ? c.line : '#374151' }}
              />
              {sport.charAt(0).toUpperCase() + sport.slice(1)}
            </button>
          )
        })}
      </div>

      {/* Chart */}
      {loading ? (
        <div className="animate-pulse bg-brand-midgray rounded" style={{ height: 220 }} />
      ) : (
        <div style={{ height: 220 }}>
          <Line data={chartData} options={options} />
        </div>
      )}

      {/* Summary stats row */}
      {!loading && rows.length > 0 && (
        <div className="grid grid-cols-1 gap-3 mt-4 pt-3 border-t border-brand-midgray sm:grid-cols-2 xl:grid-cols-3">
          {SPORTS.filter(s => activeSports.includes(s)).map(sport => {
            const sportRows = rows.filter(r => r.sport === sport)
            if (!sportRows.length) return null
            const avg    = sportRows.reduce((s, r) => s + r.avg, 0) / sportRows.length
            const latest = sportRows[sportRows.length - 1]
            const trend  = sportRows.length >= 2
              ? latest.avg - sportRows[sportRows.length - 2].avg
              : 0
            const c = SPORT_COLORS[sport]
            return (
              <div key={sport} className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: c.line }} />
                  <p className="label" style={{ color: c.line }}>{sport.toUpperCase()}</p>
                </div>
                <p className="font-display text-xl tabular-nums text-white">
                  {(avg * 100).toFixed(1)}%
                </p>
                <p className="font-display text-xs text-gray-600 mt-0.5">period avg</p>
                {trend !== 0 && (
                  <p className={`font-display text-xs tabular-nums mt-1 ${
                    trend > 0 ? 'text-brand-greenlight' : 'text-brand-redlight'
                  }`}>
                    {trend > 0 ? '▲' : '▼'} {Math.abs(trend * 100).toFixed(1)}% last day
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
