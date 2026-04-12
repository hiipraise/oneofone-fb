import React, { useEffect, useState } from 'react'
import { getPlatformReport } from '../services/api'

const EMPTY_REPORT = {
  overview: 'No report data available yet.',
  working: [],
  needsImprovement: [],
  suggestions: [],
  generatedTasks: [],
  generatedAt: null,
  facts: {
    totalPredictions: 0,
    scoredResolved: 0,
    rawResolved: 0,
    accuracy: null,
    brier: null,
    resultsCount: 0,
    predictionsCount: 0,
  },
}

export default function ReportsPage() {
  const [report, setReport] = useState(EMPTY_REPORT)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [taskStatus, setTaskStatus] = useState({})

  useEffect(() => {
    let mounted = true
    const fetchReport = async () => {
      setLoading(true)
      setError('')
      try {
        const res = await getPlatformReport(100)
        if (!mounted) return
        setReport(res.data ?? EMPTY_REPORT)
      } catch (err) {
        if (!mounted) return
        setError(err?.response?.data?.detail || err.message || 'Failed to load report')
        setReport(EMPTY_REPORT)
      } finally {
        if (mounted) setLoading(false)
      }
    }

    fetchReport()
    return () => {
      mounted = false
    }
  }, [])

  const toggleTask = (taskId) => {
    setTaskStatus((prev) => ({ ...prev, [taskId]: !prev[taskId] }))
  }

  return (
    <div className="max-w-full animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6 gap-2">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">AI PLATFORM REPORT</h1>
          <p className="font-body text-xs text-gray-600 mt-1">Backend-generated analysis of what is working, what needs improvement, and recommended tasks.</p>
        </div>
        <span className="font-display text-xs text-gray-600">
          Generated: {report.generatedAt ? new Date(report.generatedAt).toLocaleString() : '—'}
        </span>
      </div>

      {loading ? (
        <div className="card p-6 animate-pulse">
          <div className="h-4 w-56 bg-brand-midgray rounded mb-3" />
          <div className="h-3 w-full bg-brand-midgray rounded mb-2" />
          <div className="h-3 w-5/6 bg-brand-midgray rounded" />
        </div>
      ) : (
        <>
          {error && (
            <div className="mb-4 border border-brand-red bg-brand-reddark rounded-sm p-3">
              <p className="font-display text-xs text-brand-redlight">Report error: {error}</p>
            </div>
          )}

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
              <p className="font-display text-xs text-gray-600">Mark done for this session (not persisted)</p>
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
              {!report.generatedTasks.length && (
                <p className="font-body text-sm text-gray-500">No tasks generated yet.</p>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
