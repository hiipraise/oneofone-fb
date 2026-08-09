// src/services/api.js
import axios from "axios";
import { DEFAULT_API_CONTRACT } from "../config/apiContract";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";
const APP_ORIGIN = typeof window !== "undefined" ? window.location.origin : "";
const SCHEDULER_ADMIN_KEY = import.meta.env.VITE_SCHEDULER_ADMIN_KEY || "";
const schedulerAuth = () => SCHEDULER_ADMIN_KEY ? { headers: { "X-Scheduler-Key": SCHEDULER_ADMIN_KEY } } : undefined;

const toSafePathSegment = (value) => encodeURIComponent(String(value ?? "").trim());

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  if (config.params) {
    config.params = Object.fromEntries(
      Object.entries(config.params)
        .filter(([, value]) => value !== undefined && value !== null && value !== "")
        .map(([key, value]) => [key, typeof value === "string" ? value.trim() : value]),
    );
  }
  if (config.data && typeof config.data === "object" && !(config.data instanceof FormData)) {
    config.data = Object.fromEntries(
      Object.entries(config.data).map(([key, value]) => [
        key,
        typeof value === "string" ? value.trim() : value,
      ]),
    );
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error("[API Error]", err.response?.data || err.message);
    return Promise.reject(err);
  },
);

// ── Predictions ──────────────────────────────────────────────────────────────
export const generatePrediction = (data) => api.post("/predictions/", data);

export const getPredictions = (
  sport,
  limit = DEFAULT_API_CONTRACT.field_limits.predictions_page_limit.default,
  includeDeleted = false,
) =>
  api.get("/predictions/", {
    params: { sport, limit, include_deleted: includeDeleted },
  });

export const getPredictionById = (matchId) =>
  api.get(`/predictions/${toSafePathSegment(matchId)}`);

export const validateMatch = (homeTeam, awayTeam, sport, date) =>
  api.get("/predictions/validate", {
    params: { home_team: homeTeam, away_team: awayTeam, sport, date },
  });

export const getLiveLeagues = (sport) =>
  api.get("/predictions/leagues", { params: { sport } });

export const submitResult = (data) =>
  api.post("/predictions/results/submit", data);
export const triggerLearning = () => api.post("/predictions/learn/trigger");

export const deletePrediction = (matchId) =>
  api.delete(`/predictions/${toSafePathSegment(matchId)}`);
export const restorePrediction = (matchId) =>
  api.post(`/predictions/${toSafePathSegment(matchId)}/restore`);
export const repredictPrediction = (matchId) =>
  api.post(`/predictions/${toSafePathSegment(matchId)}/repredict`);
export const resolvePrediction = (matchId) =>
  api.post(`/predictions/${toSafePathSegment(matchId)}/resolve`);

// ── Metrics ──────────────────────────────────────────────────────────────────
export const getMetrics = (limit = 30) =>
  api.get("/metrics/", { params: { limit } });
export const getLatestMetrics = () => api.get("/metrics/latest");
export const getMetricsSummary = () => api.get("/metrics/summary");
export const getQuota = () => api.get("/metrics/quota");
export const getConfidenceHistory = (days = 30) =>
  api.get("/metrics/confidence-history", { params: { days } });
export const getPerformanceHistory = (days = 90) =>
  api.get("/metrics/performance-history", { params: { days } });
export const getTeamAccuracy = (minResolved = 10, limit = 20, sport = "") =>
  api.get("/metrics/team-accuracy", {
    params: { min_resolved: minResolved, limit, sport: sport || undefined },
  });

// ── Results ──────────────────────────────────────────────────────────────────
export const getResults = (limit = 50) =>
  api.get("/results/", { params: { limit } });

// ── Search ───────────────────────────────────────────────────────────────────
export const webSearch = (q) => api.get("/search/", { params: { q } });
export const getTeamInfo = (team, sport) =>
  api.get("/search/team", { params: { team, sport } });

// ── API contract ─────────────────────────────────────────────────────────────
export const getFrontendContract = () => api.get("/meta/frontend");

// ── Scheduler ────────────────────────────────────────────────────────────────
export const getSchedulerStatus = () => api.get("/scheduler/status");
export const triggerScheduler = () => api.post("/scheduler/trigger", undefined, schedulerAuth());
export const enableScheduler = () => api.post("/scheduler/enable", undefined, schedulerAuth());
export const disableScheduler = () => api.post("/scheduler/disable", undefined, schedulerAuth());
export const getSchedulerLogs = (limit = 50) =>
  api.get("/scheduler/logs", { params: { limit } });
export const getTodayFixtures = () => api.get("/scheduler/fixtures/today");
export const triggerResolution = () =>
  api.post("/scheduler/trigger-resolution", undefined, schedulerAuth());

// ── Health ───────────────────────────────────────────────────────────────────
export const healthCheck = () =>
  axios.get(
    `${API_BASE_URL?.replace(/\/api$/, "") || APP_ORIGIN}/health`,
  );

export default api;
