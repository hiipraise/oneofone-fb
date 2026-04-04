import React, { useMemo, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { usePerformanceHistory } from '../hooks/useData'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

const GRANULARITY_OPTIONS = [
  { key: 'day',   label: 'DAY'   },
  { key: 'week',  label: 'WEEK'  },
  { key: 'month', label: 'MONTH' },
  { key: 'year',  label: 'YEAR'  },
]

const DAYS_FOR_GRANULARITY = {
  day:   30,
  week:  90,
  month: 180,
  year:  365,
}

function getPeriodKey(dateStr, granularity) {
  // dateStr is "YYYY-MM-DD" from the backend — parse as local date to avoid
  // UTC-midnight timezone shifts that would push dates back by one day.
  const [year, month, day] = dateStr.split('-').map(Number)
  if (!year || !month || !day) return null

  if (granularity === 'day') {
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  }

  if (granularity === 'month') {
    return `${year}-${String(month).padStart(2, '0')}`
  }

  if (granularity === 'year') {
    return `${year}`
  }

  // ISO week (Monday-based)
  const d = new Date(year, month - 1, day)
  const dayOfWeek = d.getDay() || 7
  const thursday = new Date(d)
  thursday.setDate(d.getDate() + (4 - dayOfWeek))
  const weekYear = thursday.getFullYear()
  const yearStart = new Date(weekYear, 0, 1)
  const weekNo = Math.ceil((((thursday - yearStart) / 86400000) + 1) / 7)
  return `${weekYear}-W${String(weekNo).padStart(2, '0')}`
}

function formatLabel(period, granularity) {
  if (granularity === 'week' || granularity === 'year') return period
  if (granularity === 'month') {
    const [year, month] = period.split('-').map(Number)
    return new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  }
  // day — parse as local date
  const [year, month, day] = period.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function PerformanceTrendChart() {
  const [granularity, setGranularity] = useState('week')

  // Fetch real performance metrics (predictions vs actual_results),
  // adjusting the lookback window to match the chosen granularity.
  const days = DAYS_FOR_GRANULARITY[granularity]
  const { data: performanceHistory, loading } = usePerformanceHistory(days)

  const { labels, brierData, logLossData, accuracyData } = useMemo(() => {
    const bucketMap = new Map()

    performanceHistory.forEach((row) => {
      if (!row.date) return
      const periodKey = getPeriodKey(row.date, granularity)
      if (!periodKey) return

      if (!bucketMap.has(periodKey)) {
        bucketMap.set(periodKey, {
          brierSum: 0, brierCount: 0,
          logLossSum: 0, logLossCount: 0,
          accuracySum: 0, accuracyCount: 0,
          totalMatches: 0,
        })
      }

      const bucket = bucketMap.get(periodKey)
      const n = row.count ?? 1  // weight by number of matches in that day

      if (typeof row.brier_score === 'number') {
        bucket.brierSum   += row.brier_score * n
        bucket.brierCount += n
      }
      if (typeof row.log_loss === 'number') {
        bucket.logLossSum   += row.log_loss * n
        bucket.logLossCount += n
      }
      if (typeof row.accuracy === 'number') {
        bucket.accuracySum   += row.accuracy * n
        bucket.accuracyCount += n
      }
      bucket.totalMatches += n
    })

    const sortedPeriods = Array.from(bucketMap.keys()).sort()

    return {
      labels: sortedPeriods.map((p) => formatLabel(p, granularity)),
      brierData: sortedPeriods.map((p) => {
        const b = bucketMap.get(p)
        return b.brierCount ? +(b.brierSum / b.brierCount).toFixed(4) : null
      }),
      logLossData: sortedPeriods.map((p) => {
        const b = bucketMap.get(p)
        return b.logLossCount ? +(b.logLossSum / b.logLossCount).toFixed(4) : null
      }),
      accuracyData: sortedPeriods.map((p) => {
        const b = bucketMap.get(p)
        return b.accuracyCount ? +(b.accuracySum / b.accuracyCount).toFixed(4) : null
      }),
    }
  }, [performanceHistory, granularity])

  if (loading) {
    return (
      <div className="card p-6 flex items-center justify-center" style={{ height: 260 }}>
        <p className="font-display text-gray-600 text-sm animate-pulse">LOADING TREND…</p>
      </div>
    )
  }

  if (!performanceHistory.length) {
    return (
      <div className="card p-6 flex items-center justify-center" style={{ height: 260 }}>
        <p className="font-display text-gray-600 text-sm">NO PERFORMANCE TREND DATA</p>
      </div>
    )
  }

  const data = {
    labels,
    datasets: [
      {
        label: 'Avg Brier Score',
        data: brierData,
        borderColor: '#dc2626',
        backgroundColor: 'rgba(220,38,38,0.08)',
        borderWidth: 1.5,
        pointRadius: 2,
        tension: 0.35,
        fill: true,
        yAxisID: 'y',
      },
      {
        label: 'Avg Log Loss',
        data: logLossData,
        borderColor: '#ef4444',
        backgroundColor: 'transparent',
        borderWidth: 1,
        pointRadius: 2,
        borderDash: [4, 4],
        tension: 0.35,
        yAxisID: 'y',
      },
      {
        label: 'Avg Accuracy',
        data: accuracyData,
        borderColor: '#16a34a',
        backgroundColor: 'rgba(22,163,74,0.08)',
        borderWidth: 1.5,
        pointRadius: 2,
        tension: 0.35,
        fill: false,
        yAxisID: 'y1',
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        labels: {
          color: '#6b7280',
          font: { family: '"DM Mono"', size: 10 },
          boxWidth: 12,
          padding: 16,
        },
      },
      tooltip: {
        backgroundColor: '#1a1a1a',
        borderColor: '#2a2a2a',
        borderWidth: 1,
        titleColor: '#9ca3af',
        bodyColor: '#ffffff',
        titleFont: { family: '"DM Mono"', size: 10 },
        bodyFont: { family: '"DM Mono"', size: 11 },
        callbacks: {
          afterBody: (items) => {
            // Show match count for the hovered period from the first dataset's index
            const idx = items[0]?.dataIndex
            if (idx == null) return
            return ''   // extend here if you want to surface count per tooltip
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#4b5563', font: { family: '"DM Mono"', size: 10 } },
        grid:  { color: '#1a1a1a' },
        border: { color: '#2a2a2a' },
      },
      y: {
        type: 'linear',
        position: 'left',
        ticks: { color: '#dc2626', font: { family: '"DM Mono"', size: 10 } },
        grid:  { color: '#1a1a1a' },
        border: { color: '#2a2a2a' },
        title: { display: true, text: 'Loss', color: '#6b7280', font: { family: '"DM Mono"', size: 10 } },
      },
      y1: {
        type: 'linear',
        position: 'right',
        min: 0,
        max: 1,
        ticks: { color: '#16a34a', font: { family: '"DM Mono"', size: 10 } },
        grid:  { drawOnChartArea: false },
        border: { color: '#2a2a2a' },
        title: { display: true, text: 'Accuracy', color: '#6b7280', font: { family: '"DM Mono"', size: 10 } },
      },
    },
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4 gap-3">
        <p className="label">PERFORMANCE TREND (GROUPED)</p>
        <div className="flex items-center gap-1">
          {GRANULARITY_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setGranularity(option.key)}
              className={`px-2 py-1 text-[10px] font-display rounded border transition-colors ${
                granularity === option.key
                  ? 'border-brand-red text-white bg-brand-red/20'
                  : 'border-brand-midgray text-gray-500 hover:text-gray-300'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div style={{ height: 220 }}>
        <Line data={data} options={options} />
      </div>
    </div>
  )
}