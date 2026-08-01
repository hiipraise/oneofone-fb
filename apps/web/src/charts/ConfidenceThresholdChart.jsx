// src/charts/ConfidenceThresholdChart.jsx
import React, { useEffect, useState } from "react";
import api from "../services/api";

/**
 * ConfidenceThresholdChart
 *
 * Shows prediction accuracy at different confidence thresholds,
 * helping identify the confidence level at which the model makes
 * the most reliable predictions.
 *
 * Displays:
 *   - Accuracy % at each threshold (50%, 60%, 70%, etc.)
 *   - Number of predictions at each threshold
 *   - Optimal threshold recommendation
 */
export default function ConfidenceThresholdChart({ days = 90 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const response = await api.get("/metrics/confidence-thresholds", {
          params: { days },
        });
        setData(response.data);
        setError(null);
      } catch (err) {
        setError(err.message);
        setData(null);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [days]);

  if (loading) {
    return (
      <div className="card p-6">
        <div className="h-4 bg-brand-midgray rounded w-48 mb-4" />
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-8 bg-brand-midgray rounded animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-6 border border-brand-red">
        <p className="text-brand-redlight font-display text-sm mb-2">
          Error Loading Thresholds
        </p>
        <p className="text-gray-500 text-xs">{error}</p>
      </div>
    );
  }

  if (!data?.threshold_breakdown) {
    return (
      <div className="card p-6">
        <p className="text-gray-500 text-sm">No threshold data available</p>
      </div>
    );
  }

  const thresholds = Object.entries(data.threshold_breakdown).sort(
    ([a], [b]) => parseFloat(a) - parseFloat(b),
  );

  const optimal = data.optimal_threshold;

  return (
    <div className="card p-6">
      <h3 className="label mb-2">CONFIDENCE THRESHOLD ANALYSIS</h3>
      <p className="text-xs text-gray-600 mb-6">
        Model accuracy at different confidence levels
      </p>

      {/* Optimal threshold highlight */}
      {optimal && (
        <div className="mb-6 p-4 rounded border border-brand-green bg-green-900/10">
          <p className="text-xs text-gray-600 mb-1">OPTIMAL THRESHOLD</p>
          <div className="flex items-end justify-between">
            <div>
              <div className="font-display text-2xl text-brand-greenlight tabular-nums">
                {(optimal.threshold * 100).toFixed(0)}%
              </div>
              <p className="text-xs text-gray-600 mt-1">
                {optimal.samples} predictions · {optimal.accuracy_pct}% accuracy
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-600">Highest accuracy</p>
              <p className="text-xs text-gray-600">with minimum samples</p>
            </div>
          </div>
        </div>
      )}

      {/* Threshold breakdown */}
      <div className="space-y-3">
        {thresholds.map(([threshold, item]) => {
          const thresholdNum = parseFloat(threshold);
          const accuracy = item.accuracy;
          const scored = item.scored || 0;
          const count = item.count || 0;
          const accuracyPct = item.accuracy_pct;

          const isOptimal =
            optimal && Math.abs(thresholdNum - optimal.threshold) < 0.01;

          let acctColor = "text-gray-600";
          if (accuracy !== null) {
            if (accuracy >= 0.65) acctColor = "text-brand-greenlight";
            else if (accuracy >= 0.55) acctColor = "text-yellow-400";
            else acctColor = "text-brand-redlight";
          }

          const bgClass = isOptimal
            ? "bg-green-900/10 border-brand-green"
            : "bg-gray-900/5 border-brand-midgray";

          return (
            <div
              key={threshold}
              className={`p-4 rounded border ${bgClass} transition-colors`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className="font-display font-bold text-sm w-12">
                    ≥{(thresholdNum * 100).toFixed(0)}%
                  </span>
                  <div className="text-xs text-gray-600">
                    {count} predictions
                    {scored > 0 && (
                      <span>
                        {" "}
                        ·{" "}
                        <span className="text-gray-500">{scored} resolved</span>
                      </span>
                    )}
                  </div>
                </div>

                {accuracy !== null ? (
                  <div className="text-right">
                    <div
                      className={`font-display text-lg tabular-nums ${acctColor}`}
                    >
                      {accuracyPct}%
                    </div>
                    <p className="text-xs text-gray-600">
                      {item.correct}/{scored}
                    </p>
                  </div>
                ) : (
                  <div className="text-gray-600 text-sm">No data</div>
                )}
              </div>

              {/* Accuracy bar */}
              {accuracy !== null && (
                <div className="h-2 bg-brand-darkgray rounded-full overflow-hidden border border-brand-midgray">
                  <div
                    className={`h-full ${
                      accuracy >= 0.65
                        ? "bg-brand-greenlight"
                        : accuracy >= 0.55
                          ? "bg-yellow-500"
                          : "bg-brand-redlight"
                    }`}
                    style={{
                      width: `${Math.max(accuracy * 100, 3)}%`,
                    }}
                  />
                </div>
              )}

              {/* Optimal badge */}
              {isOptimal && (
                <p className="text-xs text-brand-greenlight mt-2 font-medium">
                  ✓ Most Reliable
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Distribution histogram */}
      {data.confidence_distribution && (
        <div className="mt-8 pt-6 border-t border-brand-midgray">
          <p className="text-xs text-gray-600 mb-4">CONFIDENCE DISTRIBUTION</p>
          <div className="grid grid-cols-5 gap-2">
            {Object.entries(data.confidence_distribution.bins || {})
              .sort(([a], [b]) => {
                const aStart = parseInt(a.split("-")[0]);
                const bStart = parseInt(b.split("-")[0]);
                return aStart - bStart;
              })
              .map(([bin, count]) => {
                const maxCount = Math.max(
                  ...Object.values(data.confidence_distribution.bins || {}),
                );
                const height = maxCount > 0 ? (count / maxCount) * 100 : 0;

                return (
                  <div key={bin} className="flex flex-col items-center gap-1">
                    <div
                      className="w-full bg-brand-green rounded-sm transition-all"
                      style={{
                        height: `${Math.max(height, 3)}px`,
                        opacity: 0.6 + (height / 100) * 0.4,
                      }}
                      title={`${count} predictions`}
                    />
                    <p className="text-xs text-gray-600">{bin}</p>
                  </div>
                );
              })}
          </div>

          {data.confidence_distribution.mean_confidence && (
            <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-brand-midgray">
              <div>
                <p className="text-xs text-gray-600 mb-1">MEAN</p>
                <p className="font-display text-sm text-gray-400">
                  {(data.confidence_distribution.mean_confidence * 100).toFixed(
                    1,
                  )}
                  %
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-600 mb-1">MEDIAN</p>
                <p className="font-display text-sm text-gray-400">
                  {(
                    data.confidence_distribution.median_confidence * 100
                  ).toFixed(1)}
                  %
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-600 mb-1">STD DEV</p>
                <p className="font-display text-sm text-gray-400">
                  {(data.confidence_distribution.std_confidence * 100).toFixed(
                    1,
                  )}
                  %
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-gray-600 mt-6">Last {days} days</p>
    </div>
  );
}
