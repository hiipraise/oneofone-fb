import React, { useMemo } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const SPORTS = ['soccer']
const COLORS = {
  soccer: '#16a34a',
}

function labelForSport(sport) {
  return sport.charAt(0).toUpperCase() + sport.slice(1)
}

export default function SportPerformanceChart({ summary, loading }) {
  const sportBreakdown = summary?.sport_breakdown || {}

  const chartData = useMemo(() => {
    const labels = SPORTS.map(labelForSport)
    return {
      labels,
      datasets: [
        {
          label: 'Accuracy',
          data: SPORTS.map((sport) => {
            const value = sportBreakdown[sport]?.accuracy
            return value == null ? 0 : Math.round(value * 1000) / 10
          }),
          backgroundColor: SPORTS.map((sport) => COLORS[sport]),
          borderRadius: 6,
          maxBarThickness: 38,
        },
      ],
    }
  }, [sportBreakdown])

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#111827',
        borderColor: '#374151',
        borderWidth: 1,
        callbacks: {
          label: (ctx) => {
            const sport = SPORTS[ctx.dataIndex]
            const resolved = sportBreakdown[sport]?.resolved ?? 0
            const confidence = sportBreakdown[sport]?.avg_confidence
            const parts = [`Accuracy: ${ctx.parsed.y.toFixed(1)}%`, `Resolved: ${resolved}`]
            if (confidence != null) parts.push(`Avg confidence: ${(confidence * 100).toFixed(1)}%`)
            return parts
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#9ca3af', font: { family: '"DM Mono"', size: 10 } },
        grid: { display: false },
        border: { color: '#2a2a2a' },
      },
      y: {
        beginAtZero: true,
        max: 100,
        ticks: {
          color: '#6b7280',
          callback: (value) => `${value}%`,
          font: { family: '"DM Mono"', size: 10 },
        },
        grid: { color: '#1a1a1a' },
        border: { color: '#2a2a2a' },
      },
    },
  }

  if (loading) {
    return <div className="animate-pulse bg-brand-midgray rounded" style={{ height: 260 }} />
  }

  const hasResolvedData = SPORTS.some((sport) => (sportBreakdown[sport]?.resolved ?? 0) > 0)
  if (!hasResolvedData) {
    return (
      <div className="card p-4">
        <p className="label mb-2">MODEL PERFORMANCE BY SPORT</p>
        <div className="flex items-center justify-center" style={{ height: 220 }}>
          <p className="font-display text-gray-600 text-sm">RESOLVED MATCHES WILL APPEAR HERE</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card p-4">
      <div className="flex flex-col gap-1 mb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="label">MODEL PERFORMANCE BY SPORT</p>
          <p className="font-display text-xs text-gray-700 mt-0.5">
            Accuracy across resolved predictions for each sport
          </p>
        </div>
      </div>

      <div style={{ height: 240 }}>
        <Bar data={chartData} options={options} />
      </div>

      <div className="grid grid-cols-1 gap-3 mt-4 pt-3 border-t border-brand-midgray sm:grid-cols-3">
        {SPORTS.map((sport) => {
          const item = sportBreakdown[sport] || {}
          return (
            <div key={sport} className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[sport] }} />
                <p className="label">{labelForSport(sport).toUpperCase()}</p>
              </div>
              <p className="font-display text-lg text-white tabular-nums">
                {item.accuracy == null ? '—' : `${(item.accuracy * 100).toFixed(1)}%`}
              </p>
              <p className="font-display text-xs text-gray-600 mt-1">
                {item.resolved ?? 0} resolved · avg conf {item.avg_confidence == null ? '—' : `${(item.avg_confidence * 100).toFixed(1)}%`}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
