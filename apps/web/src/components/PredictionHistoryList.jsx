// src/components/PredictionHistoryList.jsx
import React from "react";
import { formatWatDate } from "../utils/wat";

export default function PredictionHistoryList({ predictions = [], loading }) {
  if (loading) {
    return (
      <div className="flex flex-col gap-2">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card p-3 animate-pulse">
            <div className="h-3 bg-brand-midgray rounded w-48 mb-2" />
            <div className="h-2 bg-brand-midgray rounded w-32" />
          </div>
        ))}
      </div>
    );
  }

  if (!predictions.length) {
    return (
      <div className="card p-6 text-center">
        <p className="font-display text-gray-600 text-sm">NO HISTORY FOUND</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {predictions.map((pred, i) => {
        const homePct = Math.round((pred.home_win_probability || 0) * 100);
        const awayPct = Math.round((pred.away_win_probability || 0) * 100);
        const isHome = pred.predicted_outcome === "home_win";
        const isAway = pred.predicted_outcome === "away_win";

        return (
          <div
            key={pred.match_id || i}
            className="card p-3 hover:border-gray-600 transition-colors duration-150 cursor-default"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    isHome
                      ? "bg-brand-green"
                      : isAway
                        ? "bg-brand-red"
                        : "bg-yellow-600"
                  }`}
                />
                <span className="font-display text-xs text-white">
                  {pred.home_team} vs {pred.away_team}
                </span>
                <span className="tag-gray">{pred.sport}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-display text-xs text-gray-500">
                  H: {homePct}% / A: {awayPct}%
                </span>
                <span className="font-display text-xs text-gray-600">
                  {pred.match_date ||
                    (pred.timestamp &&
                      formatWatDate(pred.timestamp))}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
