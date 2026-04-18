// src/charts/PerformanceChart.jsx
import React, { useMemo } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { usePerformanceHistory } from '../hooks/useData'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

function parseDateLabel(dateStr) {
  const [year, month, day] = String(dateStr).split('-').map(Number)
  if (!year || !month || !day) return dateStr
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function safeNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export default function PerformanceChart() {
  const { data: performanceHistory, loading } = usePerformanceHistory(30)

  const { labels, brierData, logLossData, accuracyData } = useMemo(() => {
    const sorted = [...performanceHistory]
      .filter((m) => m?.date)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))

    return {
      labels: sorted.map((m) => parseDateLabel(m.date)),
      brierData: sorted.map((m) => safeNumber(m.brier_score)),
      logLossData: sorted.map((m) => safeNumber(m.log_loss)),
      accuracyData: sorted.map((m) => safeNumber(m.accuracy)),
    }
  }, [performanceHistory])

  if (loading) {
    return (
      <div className="card p-6 flex items-center justify-center" style={{ height: 260 }}>
        <p className="font-display text-gray-600 text-sm animate-pulse">LOADING PERFORMANCE DATA…</p>
      </div>
    )
  }

  if (!performanceHistory.length) {
    return (
      <div className="card p-6 flex items-center justify-center" style={{ height: 260 }}>
        <p className="font-display text-gray-600 text-sm">NO PERFORMANCE DATA YET</p>
      </div>
    )
  }

  const data = {
    labels,
    datasets: [
      {
        label: 'Brier Score',
        data: brierData,
        borderColor: '#dc2626',
        backgroundColor: 'rgba(220,38,38,0.08)',
        borderWidth: 1.5,
        pointRadius: 3,
        pointBackgroundColor: '#dc2626',
        tension: 0.4,
        fill: true,
        yAxisID: 'y',
      },
      {
        label: 'Log Loss',
        data: logLossData,
        borderColor: '#ef4444',
        backgroundColor: 'transparent',
        borderWidth: 1,
        pointRadius: 2,
        pointBackgroundColor: '#ef4444',
        borderDash: [4, 4],
        tension: 0.4,
        yAxisID: 'y',
      },
      {
        label: 'Accuracy',
        data: accuracyData,
        borderColor: '#16a34a',
        backgroundColor: 'rgba(22,163,74,0.08)',
        borderWidth: 1.5,
        pointRadius: 3,
        pointBackgroundColor: '#16a34a',
        tension: 0.4,
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
      },
    },
    scales: {
      x: {
        ticks: { color: '#4b5563', font: { family: '"DM Mono"', size: 10 } },
        grid: { color: '#1a1a1a' },
        border: { color: '#2a2a2a' },
      },
      y: {
        type: 'linear',
        position: 'left',
        ticks: { color: '#dc2626', font: { family: '"DM Mono"', size: 10 } },
        grid: { color: '#1a1a1a' },
        border: { color: '#2a2a2a' },
        title: { display: true, text: 'Loss', color: '#6b7280', font: { family: '"DM Mono"', size: 10 } },
      },
      y1: {
        type: 'linear',
        position: 'right',
        min: 0,
        max: 1,
        ticks: { color: '#16a34a', font: { family: '"DM Mono"', size: 10 } },
        grid: { drawOnChartArea: false },
        border: { color: '#2a2a2a' },
        title: { display: true, text: 'Accuracy', color: '#6b7280', font: { family: '"DM Mono"', size: 10 } },
      },
    },
  }

  return (
    <div className="card p-4">
      <p className="label mb-4">MODEL PERFORMANCE OVER TIME</p>
      <div style={{ height: 220 }}>
        <Line data={data} options={options} />
      </div>
    </div>
  )
}
