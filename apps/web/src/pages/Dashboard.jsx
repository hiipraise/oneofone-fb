// src/pages/Dashboard.jsx
import React from "react";
import { Link } from "react-router-dom";
import {
  usePredictions,
  useMetricsSummary,
  useResults,
} from "../hooks/useData";
import ModelStatsPanel from "../components/ModelStatsPanel";
import PredictionCard from "../components/PredictionCard";
import PerformanceChart from "../charts/PerformanceChart";
import ProbabilityDistributionChart from "../charts/ProbabilityDistributionChart";
import PerformanceTrendChart from "../charts/PerformanceTrendChart";
import CalibrationChart from "../charts/CalibrationChart";
import MarketAccuracyChart from "../charts/MarketAccuracyChart";
import ConfidenceThresholdChart from "../charts/ConfidenceThresholdChart";
import { formatWatDate } from "../utils/wat";

export default function Dashboard() {
  const { data: predictions, loading: predsLoading } = usePredictions(
    "soccer",
    20,
    60_000,
  );
  const { data: summary, loading: summaryLoading } = useMetricsSummary();
  const { data: results } = useResults(100, 60_000);

  const resolvedMatches = results.reduce((map, result) => {
    if (result?.match_id) map[result.match_id] = result;
    return map;
  }, {});

  const recentPredictions = predictions
    .filter((pred) => (pred?.sport || "").toLowerCase() === "soccer")
    .slice(0, 3);

  return (
    <div className="max-w-full animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">
            SYSTEM DASHBOARD
          </h1>
          <p className="font-body text-xs text-gray-600 mt-1">
            Real-time probabilistic sports prediction —{" "}
            {formatWatDate(new Date(), "en-US")} (WAT)
          </p>
        </div>
        <Link to="/predict" className="btn-primary">
          NEW PREDICTION
        </Link>
      </div>

      {/* Model Stats */}
      <section className="mb-6">
        <p className="label mb-3">MODEL PERFORMANCE</p>
        <ModelStatsPanel summary={summary} loading={summaryLoading} />
      </section>

      {/* Charts row */}
      <section className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-6">
        <PerformanceChart />
        <ProbabilityDistributionChart predictions={predictions} />
      </section>

      <section className="mb-6">
        <PerformanceTrendChart />
      </section>

      <section className="mb-6">
        <CalibrationChart
          predictions={predictions}
          resolvedPredictions={results}
        />
      </section>

      {/* Market Accuracy Section */}
      <section className="mb-6">
        <p className="label mb-3">MARKET PERFORMANCE</p>
        <MarketAccuracyChart days={90} />
      </section>

      {/* Confidence Threshold Analysis */}
      <section className="mb-6">
        <p className="label mb-3">CONFIDENCE THRESHOLD ANALYSIS</p>
        <ConfidenceThresholdChart days={90} />
      </section>

      {/* Recent Predictions */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <p className="label">RECENT PREDICTIONS</p>
          <Link
            to="/history"
            className="font-display text-xs text-gray-600 hover:text-white transition-colors"
          >
            VIEW ALL
          </Link>
        </div>
        {predsLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="card p-4 animate-pulse">
                <div className="h-3 bg-brand-midgray rounded w-32 mb-3" />
                <div className="h-2 bg-brand-midgray rounded w-full mb-2" />
                <div className="h-2 bg-brand-midgray rounded w-3/4" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {recentPredictions.map((pred, i) => (
              <PredictionCard
                key={pred.match_id || i}
                prediction={pred}
                resolvedMatch={resolvedMatches[pred.match_id]}
                engineStatusBySport={summary?.is_trained || null}
              />
            ))}
            {!recentPredictions.length && (
              <div className="col-span-3 card p-8 text-center">
                <p className="font-display text-gray-600 text-sm">
                  NO PREDICTIONS YET
                </p>
                <p className="font-body text-xs text-gray-700 mt-2">
                  Generate your first prediction from the Predict page
                </p>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
