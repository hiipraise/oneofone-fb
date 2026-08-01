// src/hooks/useData.js
import { useState, useEffect, useCallback, useRef } from "react";
import {
  getPredictions,
  getMetricsSummary,
  getMetrics,
  getResults,
  getQuota,
  getConfidenceHistory,
  getPerformanceHistory,
  getTeamAccuracy,
} from "../services/api";

export function usePredictions(sport = null, limit = 50, refreshMs = 0) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const inFlight = useRef(false);

  const fetch = useCallback(
    async (silent = false) => {
      if (inFlight.current) return;
      if (document.hidden) return;
      inFlight.current = true;
      if (!silent) {
        setLoading(true);
        setError(null);
      }
      try {
        const res = await getPredictions(sport, limit);
        setData(Array.isArray(res.data) ? res.data : []);
      } catch (e) {
        setError(e.response?.data?.detail || e.message);
        setData([]);
      } finally {
        if (!silent) setLoading(false);
        inFlight.current = false;
      }
    },
    [sport, limit],
  );

  useEffect(() => {
    fetch(false);
  }, [fetch]);

  useEffect(() => {
    if (!refreshMs || refreshMs < 1000) return;
    const timer = setInterval(() => fetch(true), refreshMs);
    return () => clearInterval(timer);
  }, [fetch, refreshMs]);

  return { data, loading, error, refetch: fetch };
}

export function useMetricsSummary() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getMetricsSummary();
      setData(res.data ?? null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);
  return { data, loading, error, refetch: fetch };
}

export function useMetricsHistory(limit = 30) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMetrics(limit)
      .then((r) => setData(Array.isArray(r.data) ? r.data : []))
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [limit]);

  return { data, loading };
}

/**
 * Real-world performance trend — brier_score, log_loss, accuracy per day,
 * computed from actual predictions evaluated against actual_results.
 * This is what PerformanceTrendChart should use instead of useMetricsHistory.
 */
export function usePerformanceHistory(days = 90) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getPerformanceHistory(days);
      setData(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

export function useConfidenceHistory(days = 30) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getConfidenceHistory(days);
      setData(Array.isArray(res.data) ? res.data : []);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetch();
  }, [fetch]);
  return { data, loading, refetch: fetch };
}

export function useResults(limit = 50, refreshMs = 0) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
        setError(null);
      }

      try {
        const r = await getResults(limit);
        setData(Array.isArray(r.data) ? r.data : []);
      } catch (e) {
        setError(e.message);
        setData([]);
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [limit],
  );

  useEffect(() => {
    fetch(false);
  }, [fetch]);

  useEffect(() => {
    if (!refreshMs || refreshMs < 1000) return undefined;
    const timer = setInterval(() => {
      fetch(true);
    }, refreshMs);
    return () => clearInterval(timer);
  }, [fetch, refreshMs]);

  return { data, loading, error, refetch: fetch };
}

/**
 * Serper monthly usage — calls GET /api/metrics/quota
 * Returns: { month, used, budget, remaining }
 */
export function useQuota() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getQuota();
      setData(res.data ?? null);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);
  return { data, loading, refetch: fetch };
}

export function useTeamAccuracy(minResolved = 10, limit = 20, sport = "") {
  const [data, setData] = useState([]);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getTeamAccuracy(minResolved, limit, sport);
      setData(Array.isArray(res.data?.teams) ? res.data.teams : []);
      setMeta(res.data?.meta ?? null);
    } catch {
      setData([]);
      setMeta(null);
    } finally {
      setLoading(false);
    }
  }, [minResolved, limit, sport]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, meta, loading, refetch: fetch };
}
