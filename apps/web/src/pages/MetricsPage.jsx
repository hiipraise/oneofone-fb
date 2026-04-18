// src/pages/MetricsPage.jsx
import React, { useState, useEffect } from "react";
import {
  useMetricsSummary,
  useMetricsHistory,
  useQuota,
} from "../hooks/useData";
import ModelStatsPanel from "../components/ModelStatsPanel";
import PaginationControls from "../components/PaginationControls";
import { triggerLearning } from "../services/api";
import ConfidenceHistoryChart from "../charts/ConfidenceHistoryChart";
import SportPerformanceChart from "../charts/SportPerformanceChart";
import { formatWatDate } from "../utils/wat";

const SPORT_DOTS = {
  soccer: "bg-brand-green",
};

// ── Quota panel ───────────────────────────────────────────────────────────────

function QuotaPanel({ quota, loading }) {
  if (loading) {
    return (
      <div className="card p-5 animate-pulse">
        <div className="h-2 bg-brand-midgray rounded w-24 mb-4" />
        <div className="h-3 bg-brand-midgray rounded w-full mb-2" />
        <div className="h-3 bg-brand-midgray rounded w-3/4" />
      </div>
    );
  }

  if (!quota) {
    return (
      <div className="card p-5">
        <p className="label mb-2">SERPER SEARCH USAGE</p>
        <p className="font-display text-xs text-gray-600">
          Serper usage data unavailable
        </p>
      </div>
    );
  }

  const pct = Math.round((quota.used / quota.budget) * 100);
  const remaining = quota.remaining ?? quota.budget - quota.used;
  const barColor =
    pct >= 90 ? "bg-brand-red" : pct >= 70 ? "bg-yellow-500" : "bg-brand-green";
  const statusColor =
    pct >= 90
      ? "text-brand-redlight"
      : pct >= 70
        ? "text-yellow-400"
        : "text-brand-greenlight";
  const statusLabel =
    pct >= 90 ? "⚠ CRITICAL" : pct >= 70 ? "▲ MODERATE" : "✓ HEALTHY";

  // 3 search calls per prediction (combined queries)
  const predsRemaining = Math.floor(remaining / 3);

  return (
    <div className="card p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-4">
        <div>
          {/* Updated: Serper.dev branding */}
          <p className="label mb-0.5">SERPER SEARCH USAGE</p>
          <p className="font-body text-xs text-gray-600">
            2,400 searches/month (free plan) · resets{" "}
            {quota.month ? `end of ${quota.month}` : "monthly"}
          </p>
        </div>
        <span
          className={`font-display text-xs px-2 py-1 rounded-sm border ${
            pct >= 90
              ? "border-brand-red text-brand-redlight bg-brand-reddark"
              : pct >= 70
                ? "border-yellow-700 text-yellow-400 bg-yellow-900/30"
                : "border-brand-green text-brand-greenlight bg-brand-greendark"
          }`}
        >
          {statusLabel}
        </span>
      </div>

      {/* Main bar */}
      <div className="mb-4">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between mb-2">
          <span className="font-display text-xs text-gray-500">Usage</span>
          <span className={`font-display text-2xl tabular-nums ${statusColor}`}>
            {quota.used}
            <span className="text-sm text-gray-600">/{quota.budget}</span>
          </span>
        </div>
        <div className="h-3 bg-brand-darkgray rounded-full overflow-hidden border border-brand-midgray">
          <div
            className={`h-full rounded-full transition-all duration-700 ${barColor}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-1.5 gap-2">
          <span className="font-display text-xs text-gray-700">0</span>
          <span className="font-display text-xs text-gray-700">
            {quota.budget.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3 text-center">
          <p className="label mb-1">USED</p>
          <p className={`font-display text-lg tabular-nums ${statusColor}`}>
            {quota.used}
          </p>
          <p className="font-display text-xs text-gray-700 mt-0.5">
            {pct}% of budget
          </p>
        </div>
        <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3 text-center">
          <p className="label mb-1">REMAINING</p>
          <p className={`font-display text-lg tabular-nums ${statusColor}`}>
            {remaining.toLocaleString()}
          </p>
          <p className="font-display text-xs text-gray-700 mt-0.5">
            searches left
          </p>
        </div>
        <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3 text-center">
          <p className="label mb-1">PREDICTIONS</p>
          <p
            className={`font-display text-lg tabular-nums ${
              predsRemaining > 200
                ? "text-brand-greenlight"
                : predsRemaining > 50
                  ? "text-yellow-400"
                  : "text-brand-redlight"
            }`}
          >
            ~{predsRemaining.toLocaleString()}
          </p>
          <p className="font-display text-xs text-gray-700 mt-0.5">
            remaining (3 calls ea)
          </p>
        </div>
      </div>

      {/* Fallback info */}
      <div className="mt-4 rounded-sm p-3 border border-brand-midgray bg-brand-darkgray">
        <p className="font-display text-xs text-gray-600">
          DuckDuckGo fallback activates automatically when budget is exhausted —
          predictions continue with slightly reduced context quality.
        </p>
      </div>

      {pct >= 70 && (
        <div
          className={`mt-3 rounded-sm p-3 border ${
            pct >= 90
              ? "bg-brand-reddark border-brand-red"
              : "bg-yellow-900/20 border-yellow-800"
          }`}
        >
          <p
            className={`font-display text-xs ${pct >= 90 ? "text-brand-redlight" : "text-yellow-400"}`}
          >
            {pct >= 90
              ? "Serper.dev budget nearly exhausted. DuckDuckGo fallback is now active for all searches."
              : "Budget running low. RapidAPI structured data will reduce search consumption automatically."}
          </p>
        </div>
      )}
    </div>
  );
}

function SportModelTable({ summary }) {
  if (!summary) return null;
  const mlWeights = summary.ml_weights || {};
  const nSamples = summary.n_training_samples || {};
  const isTrained = summary.is_trained || {};
  const sports = ["soccer"];

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-brand-midgray">
        <p className="label">PER-SPORT MODEL BREAKDOWN</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-brand-darkgray border-b border-brand-midgray">
            <tr>
              {[
                "SPORT",
                "STATUS",
                "ML WEIGHT",
                "TRAINING SAMPLES",
                "CALIBRATION",
                "PROGRESS TO ML",
              ].map((h) => (
                <th key={h} className="text-left label px-4 py-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sports.map((sport) => {
              const weight = mlWeights[sport] ?? 0;
              const n = nSamples[sport] ?? 0;
              const trained = isTrained[sport] ?? false;

              // Calibration: only meaningful once ML is active
              const calLabel =
                n >= 100 ? "isotonic" : n >= 30 ? "sigmoid" : "prior";
              const calColor =
                n >= 100
                  ? "text-brand-greenlight"
                  : n >= 30
                    ? "text-yellow-400"
                    : "text-gray-600";

              // ML weight bar (only non-zero once n≥30)
              const wPct = Math.round(weight * 100);
              const barColor =
                wPct >= 60
                  ? "bg-brand-green"
                  : wPct >= 30
                    ? "bg-yellow-500"
                    : "bg-brand-midgray";
              const wColor =
                wPct >= 60
                  ? "text-brand-greenlight"
                  : wPct >= 30
                    ? "text-yellow-400"
                    : "text-gray-600";

              // Progress toward next threshold (30 → ML active, 100 → isotonic)
              const nextThreshold = n < 30 ? 30 : n < 100 ? 100 : null;
              const progressPct = nextThreshold
                ? Math.round((n / nextThreshold) * 100)
                : 100;
              const progressColor =
                n >= 100
                  ? "bg-brand-green"
                  : n >= 30
                    ? "bg-yellow-500"
                    : "bg-blue-500";
              const progressLabel = nextThreshold
                ? `${nextThreshold - n} more → ${nextThreshold >= 100 ? "isotonic" : "ML active"}`
                : "Max calibration";

              return (
                <tr
                  key={sport}
                  className="border-b border-brand-midgray hover:bg-brand-gray transition-colors"
                >
                  {/* Sport */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${SPORT_DOTS[sport]}`}
                      />
                      <span className="font-display text-xs text-white capitalize">
                        {sport}
                      </span>
                    </div>
                  </td>

                  {/* Status badge */}
                  <td className="px-4 py-3">
                    <span
                      className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
                        trained
                          ? "text-brand-greenlight bg-brand-greendark border-brand-green"
                          : "text-yellow-400 bg-yellow-900/20 border-yellow-800"
                      }`}
                    >
                      {trained ? "ML ACTIVE" : "PRIOR MODE"}
                    </span>
                  </td>

                  {/* ML weight bar */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 min-w-[100px]">
                      <div className="flex-1 h-1.5 bg-brand-darkgray rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${barColor}`}
                          style={{ width: wPct > 0 ? `${wPct}%` : "0%" }}
                        />
                      </div>
                      <span
                        className={`font-display text-xs tabular-nums w-8 ${wColor}`}
                      >
                        {wPct}%
                      </span>
                    </div>
                  </td>

                  {/* Training samples */}
                  <td className="px-4 py-3">
                    <span
                      className={`font-display text-xs tabular-nums ${
                        n >= 100
                          ? "text-brand-greenlight"
                          : n >= 30
                            ? "text-yellow-400"
                            : "text-gray-400"
                      }`}
                    >
                      {n.toLocaleString()}
                    </span>
                  </td>

                  {/* Calibration — shows method name or "prior" with clear colour */}
                  <td className="px-4 py-3">
                    <span
                      className={`font-display text-xs uppercase ${calColor}`}
                    >
                      {calLabel}
                    </span>
                  </td>

                  {/* Progress bar toward next threshold */}
                  <td className="px-4 py-3 min-w-[180px]">
                    {nextThreshold ? (
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <div className="flex-1 h-1.5 bg-brand-darkgray rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-700 ${progressColor}`}
                              style={{
                                width: `${Math.min(progressPct, 100)}%`,
                              }}
                            />
                          </div>
                          <span className="font-display text-xs text-gray-600 tabular-nums w-8 text-right">
                            {progressPct}%
                          </span>
                        </div>
                        <span className="font-display text-xs text-gray-600">
                          {progressLabel}
                        </span>
                      </div>
                    ) : (
                      <span className="font-display text-xs text-brand-greenlight">
                        Max calibration
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function MetricsPage() {
  const {
    data: summary,
    loading: summaryLoading,
    refetch,
  } = useMetricsSummary();
  const { data: history } = useMetricsHistory(60);
  const { data: quota, loading: quotaLoading } = useQuota();
  const [triggering, setTriggering] = useState(false);
  const [trigMsg, setTrigMsg] = useState(null);
  const HISTORY_PAGE_SIZE = 12;
  const [historyPage, setHistoryPage] = useState(1);

  useEffect(() => {
    setHistoryPage(1);
  }, [history.length]);

  const historyTotalPages = Math.max(
    1,
    Math.ceil(history.length / HISTORY_PAGE_SIZE),
  );
  const safeHistoryPage = Math.min(historyPage, historyTotalPages);
  const paginatedHistory = history.slice(
    (safeHistoryPage - 1) * HISTORY_PAGE_SIZE,
    safeHistoryPage * HISTORY_PAGE_SIZE,
  );
  const aggregateMetrics = summary?.performance_metrics_all_sports ?? {};
  const metricsBySport = summary?.performance_metrics_by_sport ?? {};

  const handleTriggerLearning = async () => {
    setTriggering(true);
    setTrigMsg(null);
    try {
      await triggerLearning();
      setTrigMsg({
        type: "success",
        text: "Learning update triggered — model will retrain with latest scored resolved predictions.",
      });
      refetch();
    } catch (e) {
      setTrigMsg({
        type: "error",
        text: e.response?.data?.detail || "Failed to trigger learning",
      });
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">
            MODEL METRICS
          </h1>
          <p className="font-body text-xs text-gray-600 mt-1">
            Brier Score · Log Loss · Calibration · Accuracy · Serper Usage · ML
            Ensemble Weights
          </p>
        </div>
        <button
          onClick={handleTriggerLearning}
          disabled={triggering}
          className="btn-ghost"
        >
          {triggering ? (
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 border border-gray-400 border-t-transparent rounded-full animate-spin" />
              UPDATING...
            </span>
          ) : (
            "TRIGGER LEARNING"
          )}
        </button>
      </div>

      {trigMsg && (
        <div
          className={`font-display text-xs px-4 py-3 rounded-sm border ${
            trigMsg.type === "success"
              ? "text-brand-greenlight bg-brand-greendark border-brand-green"
              : "text-brand-redlight bg-brand-reddark border-brand-red"
          }`}
        >
          {trigMsg.text}
        </div>
      )}

      {/* Current performance */}
      <section>
        <div className="flex items-center justify-between mb-3 gap-2">
          <p className="label">CURRENT PERFORMANCE</p>
          {!!Object.keys(metricsBySport).length && (
            <p className="font-display text-xs text-gray-600">
              Aggregate shown across {Object.keys(metricsBySport).length} sports
              {aggregateMetrics.accuracy != null
                ? ` · ${(aggregateMetrics.accuracy * 100).toFixed(1)}% acc`
                : ""}
            </p>
          )}
        </div>
        <ModelStatsPanel summary={summary} loading={summaryLoading} />
      </section>

      {/* Quota + per-sport breakdown */}
      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <QuotaPanel quota={quota} loading={quotaLoading} />
        <div className="card p-5">
          <p className="label mb-3">MODEL ENGINE INFO</p>
          {summary ? (
            <div className="space-y-2">
              <div className="flex justify-between items-center py-2 border-b border-brand-midgray">
                <span className="font-display text-xs text-gray-500">
                  MODEL VERSION
                </span>
                <span className="font-display text-xs text-white">
                  v{summary.model_version || "3.0.0"}
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-brand-midgray">
                <span className="font-display text-xs text-gray-500">
                  ALGORITHM
                </span>
                <span className="font-display text-xs text-gray-300">
                  HistGradientBoosting
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-brand-midgray">
                <span className="font-display text-xs text-gray-500">
                  ENSEMBLE STRATEGY
                </span>
                <span className="font-display text-xs text-gray-300">
                  ML × weight + Prior × (1−weight)
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-brand-midgray">
                <span className="font-display text-xs text-gray-500">
                  CI METHOD
                </span>
                <span className="font-display text-xs text-gray-300">
                  Beta distribution (analytical)
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-brand-midgray">
                <span className="font-display text-xs text-gray-500">
                  RECENCY WEIGHTING
                </span>
                <span className="font-display text-xs text-gray-300">
                  ≤30d: 2× · ≤90d: 1.5× · older: 1×
                </span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="font-display text-xs text-gray-500">
                  FEATURES
                </span>
                <span className="font-display text-xs text-gray-300">
                  17–23 per sport
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-t border-brand-midgray">
                <span className="font-display text-xs text-gray-500">
                  RESOLVED (SCORED)
                </span>
                <span className="font-display text-xs text-gray-300 tabular-nums">
                  {(summary.total_resolved_scored ?? summary.total_resolved ?? 0).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="font-display text-xs text-gray-500">
                  SUBMITTED RESULTS (RAW)
                </span>
                <span className="font-display text-xs text-gray-500 tabular-nums">
                  {(summary.total_resolved_raw ?? 0).toLocaleString()}
                </span>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="h-6 bg-brand-midgray rounded animate-pulse"
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Per-sport breakdown table */}
      <section>
        <p className="label mb-3">PER-SPORT STATUS</p>
        <SportModelTable summary={summary} />
      </section>

      {/* Charts */}
      <section className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
        <ConfidenceHistoryChart />
        <SportPerformanceChart summary={summary} loading={summaryLoading} />
      </section>

      {/* Metrics history */}
      <section>
        <p className="label mb-3">METRICS HISTORY</p>
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-brand-midgray bg-brand-darkgray">
                <tr>
                  {[
                    "DATE",
                    "VERSION",
                    "BRIER",
                    "LOG LOSS",
                    "CALIB ERR",
                    "ACCURACY",
                    "ML WEIGHT",
                    "SAMPLES",
                  ].map((col) => (
                    <th key={col} className="text-left label px-4 py-3">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!history.length ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-8 text-center font-display text-gray-600 text-xs"
                    >
                      NO METRICS RECORDED YET — SUBMIT ACTUAL RESULTS TO BEGIN
                      EVALUATION
                    </td>
                  </tr>
                ) : (
                  paginatedHistory.map((m, i) => {
                    const bColor =
                      m.brier_score < 0.2
                        ? "text-brand-greenlight"
                        : m.brier_score < 0.25
                          ? "text-yellow-500"
                          : "text-brand-redlight";
                    const aColor =
                      m.accuracy > 0.6
                        ? "text-brand-greenlight"
                        : m.accuracy > 0.5
                          ? "text-yellow-500"
                          : "text-brand-redlight";
                    const mlW = m.retrain_result?.ml_weight ?? m.ml_weight;
                    const mlWPct =
                      mlW != null ? `${Math.round(mlW * 100)}%` : "—";
                    const mColor =
                      mlW != null && mlW > 0.5
                        ? "text-brand-greenlight"
                        : mlW != null && mlW > 0.2
                          ? "text-yellow-400"
                          : "text-gray-600";
                    return (
                      <tr
                        key={`${m.date}-${m.model_version}-${i}`}
                        className="border-b border-brand-midgray hover:bg-brand-gray transition-colors"
                      >
                        <td className="px-4 py-3 font-display text-xs text-gray-500 whitespace-nowrap">
                          {formatWatDate(m.date)}
                        </td>
                        <td className="px-4 py-3 font-display text-xs text-gray-400">
                          v{m.model_version}
                          {m.sport && (
                            <span
                              className={`ml-2 w-1.5 h-1.5 inline-block rounded-full ${SPORT_DOTS[m.sport] || "bg-gray-500"}`}
                            />
                          )}
                        </td>
                        <td
                          className={`px-4 py-3 font-display text-xs tabular-nums ${bColor}`}
                        >
                          {m.brier_score?.toFixed(4) ?? "—"}
                        </td>
                        <td className="px-4 py-3 font-display text-xs text-gray-400 tabular-nums">
                          {m.log_loss?.toFixed(4) ?? "—"}
                        </td>
                        <td className="px-4 py-3 font-display text-xs text-gray-400 tabular-nums">
                          {m.calibration_error != null
                            ? `${(m.calibration_error * 100).toFixed(2)}%`
                            : "—"}
                        </td>
                        <td
                          className={`px-4 py-3 font-display text-xs tabular-nums ${aColor}`}
                        >
                          {m.accuracy != null
                            ? `${(m.accuracy * 100).toFixed(1)}%`
                            : "—"}
                        </td>
                        <td
                          className={`px-4 py-3 font-display text-xs tabular-nums ${mColor}`}
                        >
                          {mlWPct}
                        </td>
                        <td className="px-4 py-3 font-display text-xs text-gray-600 tabular-nums">
                          {m.n_training_samples ?? m.total_predictions ?? "—"}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <PaginationControls
            currentPage={safeHistoryPage}
            totalItems={history.length}
            pageSize={HISTORY_PAGE_SIZE}
            onPageChange={setHistoryPage}
            itemLabel="METRIC SNAPSHOTS"
          />
        </div>
      </section>
    </div>
  );
}
