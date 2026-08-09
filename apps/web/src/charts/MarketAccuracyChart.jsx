// src/charts/MarketAccuracyChart.jsx
import React, { useEffect, useState } from "react";
import api from "../services/api";

/**
 * MarketAccuracyChart
 *
 * Displays prediction accuracy across different market types:
 *   - GG (Both Teams To Score)
 *   - Corners
 *   - Over/Under Goals
 */
export default function MarketAccuracyChart({ days = 90 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const response = await api.get("/metrics/market-accuracy", {
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
        <div className="h-4 bg-brand-midgray rounded w-32 mb-4" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-12 bg-brand-midgray rounded animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  const marketAccuracy = data?.market_accuracy || {};

  if (error) {
    return (
      <div className="card p-6 border border-brand-red">
        <p className="text-brand-redlight font-display text-sm mb-2">
          Error Loading Markets
        </p>
        <p className="text-gray-500 text-xs">{error}</p>
      </div>
    );
  }

  if (!marketAccuracy || Object.keys(marketAccuracy).length === 0) {
    return (
      <div className="card p-6">
        <p className="text-gray-500 text-sm">No market data available</p>
        {data?.error && (
          <p className="text-gray-600 text-xs mt-2">{data.error}</p>
        )}
        {typeof data?.total_predictions_analyzed === "number" && (
          <p className="text-gray-600 text-xs mt-2">
            Predictions analyzed: {data.total_predictions_analyzed}
          </p>
        )}
      </div>
    );
  }

  const marketData = [
    marketAccuracy.gg || {},
    marketAccuracy.ou || {},
    marketAccuracy.corners || {},
  ];

  return (
    <div className="card p-6">
      <h3 className="label mb-6">MARKET ACCURACY BY TYPE</h3>

      <div className="space-y-4">
        {marketData.map((market, idx) => {
          if (!market.market_type) return null;

          const isGG = market.market_type === "gg";
          const isOU = market.market_type === "ou";
          const isCorners = market.market_type === "corners";

          let icon = "📊";
          if (isGG) icon = "⚽";
          if (isOU) icon = "🎯";
          if (isCorners) icon = "🔄";

          // Sprint 7.20 — explicit insufficient-data contract: when the backend
          // reports available:false (no resolved samples for this market), render
          // a real "not enough data yet" state instead of a bare N/A/NaN.
          if (market.available === false) {
            return (
              <div
                key={market.market_type || idx}
                className="p-4 rounded border border-brand-midgray bg-gray-900/20"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">{icon}</span>
                  <span className="font-display text-sm font-medium">
                    {market.name}
                  </span>
                </div>
                <p className="text-brand-redlight font-display text-xs">
                  NOT ENOUGH DATA YET
                </p>
                <p className="text-gray-600 text-xs mt-1">
                  {market.reason ||
                    "No resolved predictions recorded for this market yet."}
                </p>
              </div>
            );
          }

          const accuracy = market.accuracy;
          const accuracyPct =
            accuracy != null ? (accuracy * 100).toFixed(1) : "N/A";

          let accuracyColor = "text-gray-600";
          if (accuracy !== null) {
            if (accuracy >= 0.65) accuracyColor = "text-brand-greenlight";
            else if (accuracy >= 0.55) accuracyColor = "text-yellow-400";
            else accuracyColor = "text-brand-redlight";
          }

          const bgColor =
            accuracy !== null
              ? accuracy >= 0.65
                ? "bg-green-900/10"
                : accuracy >= 0.55
                  ? "bg-yellow-900/10"
                  : "bg-red-900/10"
              : "bg-gray-900/20";

          return (
            <div
              key={market.market_type || idx}
              className={`p-4 rounded border border-brand-midgray ${bgColor}`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{icon}</span>
                    <span className="font-display text-sm font-medium">
                      {market.name}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600">
                    {market.samples || market.total_predictions} predictions
                  </p>
                </div>
                <div className="text-right">
                  <div
                    className={`font-display text-xl tabular-nums ${accuracyColor}`}
                  >
                    {accuracyPct}%
                  </div>
                  {market.correct_predictions !== null && (
                    <p className="text-xs text-gray-600">
                      {market.correct_predictions}/{market.total_predictions}{" "}
                      correct
                    </p>
                  )}
                </div>
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
                    style={{ width: `${Math.max(accuracy * 100, 5)}%` }}
                  />
                </div>
              )}

              {/* Confidence info */}
              {market.avg_confidence !== null && (
                <p className="text-xs text-gray-600 mt-2">
                  Avg confidence:{" "}
                  <span className="text-gray-400">
                    {(market.avg_confidence * 100).toFixed(1)}%
                  </span>
                </p>
              )}

              {/* Per-line accuracy for O/U */}
              {isOU &&
                market.accuracy_per_line &&
                Object.keys(market.accuracy_per_line).length > 0 && (
                  <div className="mt-3 pt-3 border-t border-brand-midgray">
                    <p className="text-xs text-gray-600 mb-2">By Line:</p>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(market.accuracy_per_line).map(
                        ([line, lineData]) => (
                          <div key={line} className="text-xs">
                            <span className="text-gray-600">{line}:</span>
                            <span className="text-gray-400 ml-1">
                              {(lineData.accuracy * 100).toFixed(0)}% (
                              {lineData.samples})
                            </span>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                )}

              {/* Note for corners */}
              {isCorners && market.note && (
                <p className="text-xs text-gray-600 mt-2 italic">
                  {market.note}
                </p>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-xs text-gray-600 mt-6">Last {days} days</p>
    </div>
  );
}
