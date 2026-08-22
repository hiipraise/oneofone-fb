// src/hooks/useData.js
import { useQuery } from "../lib/reactQueryCompat.jsx";
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

const asMessage = (error) => error?.response?.data?.detail || error?.message || null;
const asArray = (res) => (Array.isArray(res?.data) ? res.data : []);
const asData = (res) => res?.data ?? null;

function compatQuery(query, fallback) {
  return {
    data: query.data ?? fallback,
    loading: query.isLoading,
    error: asMessage(query.error),
    refetch: query.refetch,
  };
}

export function usePredictions(
  sport = null,
  limit = 50,
  refreshMs = 0,
  matchDate,
) {
  const query = useQuery({
    queryKey: ["predictions", sport || "all", limit, matchDate || "all-dates"],
    queryFn: () => getPredictions(sport, limit, false, matchDate).then(asArray),
    refetchInterval: refreshMs && refreshMs >= 1000 ? refreshMs : false,
    refetchIntervalInBackground: false,
  });
  return compatQuery(query, []);
}

export function useMetricsSummary() {
  const query = useQuery({
    queryKey: ["metrics", "summary"],
    queryFn: () => getMetricsSummary().then(asData),
  });
  return compatQuery(query, null);
}

export function useMetricsHistory(limit = 30) {
  const query = useQuery({
    queryKey: ["metrics", "history", limit],
    queryFn: () => getMetrics(limit).then(asArray),
  });
  return compatQuery(query, []);
}

/**
 * Real-world performance trend — brier_score, log_loss, accuracy per day,
 * computed from actual predictions evaluated against actual_results.
 */
export function usePerformanceHistory(days = 90) {
  const query = useQuery({
    queryKey: ["metrics", "performance-history", days],
    queryFn: () => getPerformanceHistory(days).then(asArray),
  });
  return compatQuery(query, []);
}

export function useConfidenceHistory(days = 30) {
  const query = useQuery({
    queryKey: ["metrics", "confidence-history", days],
    queryFn: () => getConfidenceHistory(days).then(asArray),
  });
  return compatQuery(query, []);
}

export function useResults(limit = 50, refreshMs = 0) {
  const query = useQuery({
    queryKey: ["results", limit],
    queryFn: () => getResults(limit).then(asArray),
    refetchInterval: refreshMs && refreshMs >= 1000 ? refreshMs : false,
    refetchIntervalInBackground: false,
  });
  return compatQuery(query, []);
}

export function useQuota() {
  const query = useQuery({
    queryKey: ["metrics", "quota"],
    queryFn: () => getQuota().then(asData),
  });
  return compatQuery(query, null);
}

export function useTeamAccuracy(minResolved = 10, limit = 20, sport = "") {
  const query = useQuery({
    queryKey: ["metrics", "team-accuracy", minResolved, limit, sport || "all"],
    queryFn: () => getTeamAccuracy(minResolved, limit, sport).then(asData),
  });
  return {
    data: Array.isArray(query.data?.teams) ? query.data.teams : [],
    meta: query.data?.meta ?? null,
    loading: query.isLoading,
    error: asMessage(query.error),
    refetch: query.refetch,
  };
}
