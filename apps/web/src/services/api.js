// src/services/api.js
import axios from "axios";
import { DEFAULT_API_CONTRACT } from "../config/apiContract";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  timeout: 60000,
  headers: { "Content-Type": "application/json" },
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
  api.get(`/predictions/${matchId}`);

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
  api.delete(`/predictions/${matchId}`);
export const restorePrediction = (matchId) =>
  api.post(`/predictions/${matchId}/restore`);
export const repredictPrediction = (matchId) =>
  api.post(`/predictions/${matchId}/repredict`);

// ── Metrics ──────────────────────────────────────────────────────────────────
export const getMetrics = (limit = 30) =>
  api.get("/metrics/", { params: { limit } });
export const getLatestMetrics = () => api.get("/metrics/latest");
export const getMetricsSummary = () => api.get("/metrics/summary");
export const getQuota = () => api.get("/metrics/quota");
export const getConfidenceHistory = (days = 30) =>
  api.get("/metrics/confidence-history", { params: { days } });

// ── Results ──────────────────────────────────────────────────────────────────
export const getResults = (limit = 50) =>
  api.get("/results/", { params: { limit } });

// ── Search ───────────────────────────────────────────────────────────────────
export const webSearch = (q) => api.get("/search/", { params: { q } });
export const getTeamInfo = (team, sport) =>
  api.get("/search/team", { params: { team, sport } });

// ── API contract ─────────────────────────────────────────────────────────────
export const getFrontendContract = () => api.get("/meta/frontend");

// ── Chat ─────────────────────────────────────────────────────────────────────
export const sendChat = (data) => api.post("/chat/", data);

export const getSessionHistory = (sessionId, limit = 50) =>
  api.get(`/chat/session/${sessionId}/history`, { params: { limit } });

export const createSession = () => api.post("/chat/session/new");

export const getSessionSummary = (sessionId) =>
  api.get(`/chat/session/${sessionId}/summary`);

export const deleteSession = (sessionId) =>
  api.delete(`/chat/session/${sessionId}`);

export const restoreSession = (sessionId) =>
  api.post(`/chat/session/${sessionId}/restore`);

// ── Scheduler ────────────────────────────────────────────────────────────────
export const getSchedulerStatus = () => api.get("/scheduler/status");
export const triggerScheduler = () => api.post("/scheduler/trigger");
export const getSchedulerLogs = (limit = 50) =>
  api.get("/scheduler/logs", { params: { limit } });
export const getTodayFixtures = () => api.get("/scheduler/fixtures/today");
export const triggerResolution = () =>
  api.post("/scheduler/trigger-resolution");

// ── Health ───────────────────────────────────────────────────────────────────
export const healthCheck = () =>
  axios.get(
    `${import.meta.env.VITE_API_URL?.replace(/\/api$/, "") || ""}/health`,
  );

export default api;
