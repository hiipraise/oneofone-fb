// src/hooks/useData.js
import { useState, useEffect, useCallback } from 'react'
import {
  getPredictions,
  getMetricsSummary,
  getMetrics,
  getResults,
  getQuota,
  getConfidenceHistory,
} from '../services/api'

export function usePredictions(sport = null, limit = 50, refreshMs = 0) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetch = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    try {
      const res = await getPredictions(sport, limit)
      setData(Array.isArray(res.data) ? res.data : [])
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
      setData([])
    } finally {
      if (!silent) setLoading(false)
    }
  }, [sport, limit])

  useEffect(() => { fetch(false) }, [fetch])

  useEffect(() => {
    if (!refreshMs || refreshMs < 1000) return undefined
    const timer = setInterval(() => {
      fetch(true)
    }, refreshMs)
    return () => clearInterval(timer)
  }, [fetch, refreshMs])

  return { data, loading, error, refetch: fetch }
}

export function useMetricsSummary() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetch = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getMetricsSummary()
      setData(res.data ?? null)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])
  return { data, loading, error, refetch: fetch }
}

export function useMetricsHistory(limit = 30) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMetrics(limit)
      .then((r) => setData(Array.isArray(r.data) ? r.data : []))
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [limit])

  return { data, loading }
}

export function useConfidenceHistory(days = 30) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getConfidenceHistory(days)
      setData(Array.isArray(res.data) ? res.data : [])
    } catch {
      setData([])
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => { fetch() }, [fetch])
  return { data, loading, refetch: fetch }
}

export function useResults(limit = 50, refreshMs = 0) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetch = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true)
      setError(null)
    }

    try {
      const r = await getResults(limit)
      setData(Array.isArray(r.data) ? r.data : [])
    } catch (e) {
      setError(e.message)
      setData([])
    } finally {
      if (!silent) setLoading(false)
    }
  }, [limit])

  useEffect(() => { fetch(false) }, [fetch])

  useEffect(() => {
    if (!refreshMs || refreshMs < 1000) return undefined
    const timer = setInterval(() => {
      fetch(true)
    }, refreshMs)
    return () => clearInterval(timer)
  }, [fetch, refreshMs])

  return { data, loading, error, refetch: fetch }
}

/**
 * Serper monthly usage — calls GET /api/metrics/quota
 * Returns: { month, used, budget, remaining }
 */
export function useQuota() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getQuota()
      setData(res.data ?? null)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])
  return { data, loading, refetch: fetch }
}
