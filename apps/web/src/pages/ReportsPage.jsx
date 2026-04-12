import React, { useEffect, useMemo, useState } from 'react'
import { useMetricsSummary, usePredictions, useResults } from '../hooks/useData'

const STORAGE_KEY = 'platform-report-task-status-v1'

function getNumeric(value, fallback = null) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function buildReport(summary, predictions, results) {
  const accuracy = getNumeric(summary?.performance_metrics_all_sports?.accuracy)
  const brier = getNumeric(summary?.performance_metrics_all_sports?.brier_score)
  const totalPredictions = getNumeric(summary?.total_predictions, 0)
  const scoredResolved = getNumeric(summary?.total_resolved_scored, getNumeric(summary?.total_resolved, 0))
  const rawResolved = getNumeric(summary?.total_resolved_raw, 0)

  const highConfidence = predictions.filter((p) => (p?.confidence_score ?? 0) >= 0.75).length
  const lowConfidence = predictions.filter((p) => (p?.confidence_score ?? 0) < 0.55).length
  const resolutionRate = totalPredictions > 0 ? scoredResolved / totalPredictions : 0

  const working = []
  if (accuracy !== null && accuracy >= 0.58) {
    working.push(`Model accuracy is ${(accuracy * 100).toFixed(1)}%, indicating healthy baseline decision quality.`)
  }
  if (brier !== null && brier <= 0.42) {
    working.push(`Calibration quality is acceptable (Brier ${brier.toFixed(4)}).`)
  }
  if (highConfidence > 0) {
    working.push(`${highConfidence} recent predictions were made with high confidence (≥ 75%).`)
  }

  const needsImprovement = []
  if (accuracy === null || accuracy < 0.55) {
    needsImprovement.push('Accuracy is below target and should be improved with more validated training examples.')
  }
  if (brier === null || brier > 0.5) {
    needsImprovement.push('Probability calibration appears weak; confidence likely needs recalibration.')
  }
  if (resolutionRate < 0.5) {
    needsImprovement.push(`Only ${(resolutionRate * 100).toFixed(1)}% of predictions are scored in metrics; result submission coverage is low.`)
  }
  if (lowConfidence > highConfidence) {
    needsImprovement.push('Low-confidence predictions are dominating recent output.')
  }

  const suggestions = [
    'Automate post-match result ingestion to increase resolved + scored volume.',
    'Prioritize per-sport model retraining when sample counts cross activation thresholds.',
    'Add a weekly calibration review to compare confidence buckets vs actual win rates.',
  ]

  const generatedTasks = [
    {
      id: 'task-improve-resolution',
      title: 'Increase scored resolution coverage to 70%',
      detail: `Current scored coverage: ${(resolutionRate * 100).toFixed(1)}% (${scoredResolved}/${totalPredictions || 0}).`,
    },
    {
      id: 'task-calibration-audit',
      title: 'Run calibration audit on latest 100 predictions',
      detail: brier !== null ? `Latest Brier score is ${brier.toFixed(4)}.` : 'Brier score unavailable; investigate metrics collection.',
    },
    {
      id: 'task-data-quality',
      title: 'Review unresolved submitted results',
      detail: `${rawResolved} results submitted, ${scoredResolved} currently scored in model metrics.`,
    },
  ]

  return {
    overview: `This AI report analyzes platform performance using live model metrics and recent platform activity. It highlights what is working, where to improve, and the next actions for your team.`,
    working,
    needsImprovement,
    suggestions,
    generatedTasks,
    generatedAt: new Date().toISOString(),
    facts: {
      totalPredictions,
      scoredResolved,
      rawResolved,
      accuracy,
      brier,
      resultsCount: results.length,
      predictionsCount: predictions.length,
    },
  }
}

export default function ReportsPage() {
  const { data: summary, loading: summaryLoading } = useMetricsSummary()
  const { data: predictions, loading: predictionsLoading } = usePredictions(null, 100)
  const { data: results, loading: resultsLoading } = useResults(100)

  const report = useMemo(() => buildReport(summary, predictions, results), [summary, predictions, results])

  const [taskStatus, setTaskStatus] = useState({})

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object') setTaskStatus(parsed)
    } catch {
      setTaskStatus({})
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(taskStatus))
  }, [taskStatus])

  const toggleTask = (taskId) => {
    setTaskStatus((prev) => ({ ...prev, [taskId]: !prev[taskId] }))
  }

  const loading = summaryLoading || predictionsLoading || resultsLoading

  return (
    <div className="max-w-full animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6 gap-2">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">AI PLATFORM REPORT</h1>
          <p className="font-body text-xs text-gray-600 mt-1">Auto-generated analysis of what is working, what needs improvement, and recommended tasks.</p>
        </div>
        <span className="font-display text-xs text-gray-600">Generated: {new Date(report.generatedAt).toLocaleString()}</span>
      </div>

      {loading ? (
        <div className="card p-6 animate-pulse">
          <div className="h-4 w-56 bg-brand-midgray rounded mb-3" />
          <div className="h-3 w-full bg-brand-midgray rounded mb-2" />
          <div className="h-3 w-5/6 bg-brand-midgray rounded" />
        </div>
      ) : (
        <>
          <section className="card p-5 mb-4">
            <p className="label mb-2">PLATFORM OVERVIEW</p>
            <p className="font-body text-sm text-gray-300 leading-6">{report.overview}</p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mt-4">
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">PREDICTIONS</p>
                <p className="font-display text-sm text-white">{report.facts.totalPredictions}</p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">SCORED</p>
                <p className="font-display text-sm text-white">{report.facts.scoredResolved}</p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">SUBMITTED RESULTS</p>
                <p className="font-display text-sm text-white">{report.facts.rawResolved}</p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">ACCURACY</p>
                <p className="font-display text-sm text-white">{report.facts.accuracy != null ? `${(report.facts.accuracy * 100).toFixed(1)}%` : 'N/A'}</p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">BRIER</p>
                <p className="font-display text-sm text-white">{report.facts.brier != null ? report.facts.brier.toFixed(4) : 'N/A'}</p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">LIVE WINDOW</p>
                <p className="font-display text-sm text-white">{report.facts.predictionsCount} preds</p>
              </div>
            </div>
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <div className="card p-5">
              <p className="label mb-3">WHAT IS WORKING</p>
              <ul className="space-y-2">
                {report.working.length ? report.working.map((item, idx) => (
                  <li key={idx} className="font-body text-sm text-gray-300">✅ {item}</li>
                )) : <li className="font-body text-sm text-gray-500">No strong positives detected yet.</li>}
              </ul>
            </div>

            <div className="card p-5">
              <p className="label mb-3">NEEDS IMPROVEMENT</p>
              <ul className="space-y-2">
                {report.needsImprovement.length ? report.needsImprovement.map((item, idx) => (
                  <li key={idx} className="font-body text-sm text-gray-300">⚠ {item}</li>
                )) : <li className="font-body text-sm text-gray-500">No immediate performance risks detected.</li>}
              </ul>
            </div>
          </section>

          <section className="card p-5 mb-4">
            <p className="label mb-3">AI SUGGESTIONS</p>
            <ul className="space-y-2">
              {report.suggestions.map((item, idx) => (
                <li key={idx} className="font-body text-sm text-gray-300">• {item}</li>
              ))}
            </ul>
          </section>

          <section className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="label">ACTION TASKS</p>
              <p className="font-display text-xs text-gray-600">Mark done as you execute platform improvements</p>
            </div>

            <div className="space-y-2">
              {report.generatedTasks.map((task) => (
                <label key={task.id} className="flex items-start gap-3 p-3 border border-brand-midgray rounded-sm hover:border-gray-600 transition-colors cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(taskStatus[task.id])}
                    onChange={() => toggleTask(task.id)}
                    className="mt-1"
                  />
                  <div>
                    <p className={`font-display text-sm ${taskStatus[task.id] ? 'text-brand-greenlight line-through' : 'text-white'}`}>{task.title}</p>
                    <p className="font-body text-xs text-gray-600 mt-1">{task.detail}</p>
                  </div>
                </label>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
