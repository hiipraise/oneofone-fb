// src/components/ModelStatsPanel.jsx
import React from "react";
import { usePerformanceHistory } from "../hooks/useData";
import TrendSparkline from "../charts/TrendSparkline";
import { getMlWeightState, ML_ACTIVATION_THRESHOLD } from "./MlWeightLogic";
import {
  getCalibrationMethod,
  getCalibrationColor,
  SAMPLE_THRESHOLD_MID,
  SAMPLE_THRESHOLD_CALIBRATION,
} from "./MlWeightLogic";

function StatBlock({ label, value, sub, colorClass = "text-white", spark }) {
  return (
    <div className="p-4 border border-brand-midgray bg-brand-gray rounded-sm">
      <p className="label mb-1">{label}</p>
      <p className={`font-display text-xl tabular-nums ${colorClass}`}>
        {value ?? <span className="text-gray-700">—</span>}
      </p>
      {spark && <div className="mt-2">{spark}</div>}
      {sub && <p className="font-display text-xs text-gray-600 mt-1">{sub}</p>}
    </div>
  );
}

/**
 * WeightBar — dual-mode:
 *  • untrained → shows progress toward activation threshold (blue fill)
 *  • trained   → shows actual ML weight (green/yellow fill)
 */
function WeightBar({ sport, weight, nSamples, isTrained, dot, threshold }) {
  const {
    n,
    wPct,
    active,
    readyToTrain,
    progressPct,
    mlBarColor,
    mlTextColor,
    threshold: computedThreshold,
  } = getMlWeightState(weight, nSamples, isTrained, threshold);
  const progressColor = "bg-blue-500";

  const calLabel = getCalibrationMethod(n);
  const calColor = getCalibrationColor(n);

  return (
    <div>
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
        <span className="font-display text-xs text-gray-500 w-20 capitalize">
          {sport}
        </span>

        {/* Track */}
        <div className="relative flex-1 h-2 bg-brand-darkgray rounded-full overflow-hidden border border-brand-midgray">
          {active ? (
            /* ML weight fill */
            <div
              className={`h-full rounded-full transition-all duration-700 ${mlBarColor}`}
              style={{ width: `${wPct}%` }}
            />
          ) : (
            /* Progress-to-threshold fill */
            <>
              <div
                className={`h-full rounded-full transition-all duration-700 ${progressColor} opacity-40`}
                style={{ width: `${progressPct}%` }}
              />
              {/* Threshold marker at 100% */}
              <div className="absolute right-0 top-0 w-px h-full bg-gray-600" />
            </>
          )}
        </div>

        {active ? (
          <span
            className={`font-display text-xs tabular-nums w-10 text-right ${mlTextColor}`}
          >
            {wPct}%
          </span>
        ) : (
          <span className="font-display text-xs tabular-nums w-10 text-right text-blue-400">
            {readyToTrain
              ? `${computedThreshold}+`
              : `${n}/${computedThreshold}`}
          </span>
        )}
      </div>

      {/* Sub-label row */}
      <div className="flex justify-between mt-1 pl-5">
        <span className="font-display text-xs text-gray-700">
          {active
            ? `${n} samples`
            : readyToTrain
              ? `${n} samples · ready to retrain`
              : `${n} samples · ${Math.max(threshold - n, 0)} to activate`}
        </span>
        <span className={`font-display text-xs ${calColor}`}>{calLabel}</span>
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-3">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="card p-4 animate-pulse">
          <div className="h-2 bg-brand-midgray rounded w-16 mb-3" />
          <div className="h-6 bg-brand-midgray rounded w-20" />
        </div>
      ))}
    </div>
  );
}

function fmt4dp(v) {
  return v != null ? v.toFixed(4) : null;
}
function fmtPct(v) {
  return v != null ? `${(v * 100).toFixed(1)}%` : null;
}

const SPORT_DOTS = {
  soccer: "bg-brand-green",
};

const DEFAULT_SPORTS = ["soccer"];

export default function ModelStatsPanel({ summary, loading }) {
  // Real performance-history trend, used for sparklines under key metric cards.
  const { data: perfHistory = [] } = usePerformanceHistory(30);

  if (loading) return <Skeleton />;

  if (!summary) {
    return (
      <div className="card p-6 text-center">
        <p className="font-display text-gray-600 text-sm">
          NO METRICS AVAILABLE YET
        </p>
        <p className="font-body text-xs text-gray-700 mt-2">
          Submit actual results to begin model evaluation
        </p>
      </div>
    );
  }

  const m = summary.performance_metrics_all_sports || {};
  const mlWeights = summary.ml_weights || {};
  const nSamples = summary.n_training_samples || {};
  const mlThreshold =
    summary.ml_activation_threshold ?? ML_ACTIVATION_THRESHOLD;
  const sports = (
    summary.supported_sports?.length
      ? summary.supported_sports
      : Object.keys(nSamples).length
        ? Object.keys(nSamples)
        : DEFAULT_SPORTS
  ).filter((sport) => sport === "soccer");
  const displaySports = sports.length ? sports : DEFAULT_SPORTS;
  const totalSamples = Object.values(nSamples).reduce(
    (s, v) => s + (v || 0),
    0,
  );

  const brierColor =
    m.brier_score == null
      ? "text-gray-500"
      : m.brier_score < 0.4
        ? "text-brand-greenlight"
        : m.brier_score < 0.55
          ? "text-yellow-500"
          : "text-brand-redlight";

  const llColor =
    m.log_loss == null
      ? "text-gray-500"
      : m.log_loss < 0.9
        ? "text-brand-greenlight"
        : m.log_loss < 1.1
          ? "text-yellow-500"
          : "text-brand-redlight";

  const accColor =
    m.accuracy == null
      ? "text-gray-500"
      : m.accuracy > 0.6
        ? "text-brand-greenlight"
        : m.accuracy > 0.5
          ? "text-yellow-500"
          : "text-brand-redlight";

  const trainedSports = Object.entries(summary.is_trained || {})
    .filter(([k, v]) => v && displaySports.includes(k))
    .map(([k]) => k);
  const engineLabel =
    trainedSports.length > 0
      ? `ML: ${trainedSports.join(", ")}`
      : "Prior model";

  const avgMlWeight =
    displaySports.length > 0
      ? displaySports.reduce((s, sp) => s + (mlWeights[sp] || 0), 0) /
        displaySports.length
      : null;
  const avgConfidence = summary.sport_breakdown?.soccer?.avg_confidence ?? null;

  // How many sports are still below threshold?
  const sportsBelowThreshold = displaySports.filter(
    (s) => (nSamples[s] ?? 0) < mlThreshold,
  );
  const anyActive = trainedSports.length > 0;
  const anyReadyToTrain = displaySports.some(
    (sport) =>
      (nSamples[sport] ?? 0) >= mlThreshold && !summary.is_trained?.[sport],
  );

  return (
    <div className="space-y-3">
      {/* Primary metrics row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-3">
        <StatBlock
          label="BRIER SCORE"
          value={fmt4dp(m.brier_score)}
          sub="↓ Better (0=perfect)"
          colorClass={brierColor}
          spark={
            <TrendSparkline
              rows={perfHistory}
              seriesKey="brier_score"
              color="#dc2626"
            />
          }
        />
        <StatBlock
          label="LOG LOSS"
          value={fmt4dp(m.log_loss)}
          sub="↓ Better"
          colorClass={llColor}
        />
        <StatBlock
          label="CALIB. ERROR"
          value={fmtPct(m.calibration_error)}
          sub="Expected calib."
          colorClass={
            m.calibration_error != null && m.calibration_error < 0.05
              ? "text-brand-greenlight"
              : "text-gray-400"
          }
        />
        <StatBlock
          label="ACCURACY"
          value={fmtPct(m.accuracy)}
          sub="Binary classification"
          colorClass={accColor}
          spark={
            <TrendSparkline
              rows={perfHistory}
              seriesKey="accuracy"
              color="#16a34a"
            />
          }
        />
        <StatBlock
          label="PREDICTIONS"
          value={(summary.total_predictions ?? 0).toLocaleString()}
          sub="Football only"
        />
        <StatBlock
          label="AVG CONFIDENCE"
          value={fmtPct(avgConfidence)}
          sub={avgConfidence == null ? "Resolve predictions to score confidence" : "Resolved football picks"}
          colorClass={
            avgConfidence == null
              ? "text-gray-500"
              : avgConfidence >= 0.65
                ? "text-brand-greenlight"
                : "text-yellow-500"
          }
        />
        <StatBlock
          label="RESOLVED (SCORED)"
          value={(
            summary.total_resolved_scored ??
            summary.total_resolved ??
            0
          ).toLocaleString()}
          sub={`Scored in metrics · v${summary.model_version || "3.0.0"}`}
          colorClass={anyActive ? "text-brand-greenlight" : "text-yellow-500"}
        />
        <StatBlock
          label="ML WEIGHT"
          value={avgMlWeight != null ? fmtPct(avgMlWeight) : "—"}
          sub="Avg ML vs prior trust"
          colorClass={
            !avgMlWeight
              ? "text-gray-500"
              : avgMlWeight > 0.5
                ? "text-brand-greenlight"
                : avgMlWeight > 0.2
                  ? "text-yellow-500"
                  : "text-gray-500"
          }
        />
        <StatBlock
          label="TRAINING DATA"
          value={totalSamples > 0 ? totalSamples.toLocaleString() : "—"}
          sub={engineLabel}
          colorClass={
            totalSamples >= mlThreshold
              ? "text-brand-greenlight"
              : "text-yellow-500"
          }
        />
      </div>

      {/* Soccer ML weight / progress breakdown */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="label">ML ENSEMBLE WEIGHT (FOOTBALL / SOCCER)</p>
          <p className="font-display text-xs text-gray-600">
            {anyActive
              ? "higher = more ML, less prior"
              : anyReadyToTrain
                ? "activation threshold reached · retrain pending"
                : "building toward activation"}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {displaySports.map((sport) => (
            <WeightBar
              key={sport}
              sport={sport}
              weight={mlWeights[sport] ?? 0}
              nSamples={nSamples[sport] ?? 0}
              isTrained={Boolean(summary.is_trained?.[sport])}
              threshold={mlThreshold}
              dot={SPORT_DOTS[sport]}
            />
          ))}
        </div>

        {sportsBelowThreshold.length > 0 && (
          <div className="mt-3 pt-3 border-t border-brand-midgray flex items-start gap-2">
            <span className="text-yellow-500 text-xs shrink-0 mt-0.5">⚠</span>
            <p className="font-display text-xs text-yellow-500">
              {sportsBelowThreshold.length === displaySports.length
                ? `ML needs ${mlThreshold} resolved predictions to activate. Blue bars show progress.`
                : `${sportsBelowThreshold.map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(", ")} still building toward ${mlThreshold}-sample threshold.`}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
