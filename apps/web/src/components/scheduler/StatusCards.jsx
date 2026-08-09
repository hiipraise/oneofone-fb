// src/components/scheduler/StatusCards.jsx
//
// Scheduler status grid (extracted from SchedulerPage.jsx in the Sprint 5.3
// file-split pass). Shows scheduler state, next runs, and today's totals.
import React from "react";
import { formatTime } from "./schedulerUtils";

export default function SchedulerStatusGrid({ status, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card p-4 animate-pulse">
            <div className="h-2 bg-brand-midgray rounded w-20 mb-3" />
            <div className="h-6 bg-brand-midgray rounded w-24" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {/* Scheduler state */}
      <div className="card p-4">
        <p className="label mb-2">SCHEDULER</p>
        <div className="flex flex-wrap items-center gap-2">
          <div
            className={`w-2.5 h-2.5 rounded-full shrink-0 ${
              status?.scheduler_running ? "bg-brand-green animate-pulse" : "bg-brand-red"
            }`}
          />
          <span
            className={`font-display text-sm ${
              status?.scheduler_running ? "text-brand-greenlight" : "text-brand-redlight"
            }`}
          >
            {status?.scheduler_running
              ? status?.scheduler_enabled === false
                ? "PAUSED"
                : "ONLINE"
              : "OFFLINE"}
          </span>
        </div>
      </div>

      {/* Next prediction run */}
      <div className="card p-4">
        <p className="label mb-2">NEXT PREDICTIONS</p>
        <p className="font-display text-xs text-white leading-tight">
          {formatTime(status?.next_run)}
        </p>
      </div>

      {/* Next resolution run */}
      <div className="card p-4">
        <p className="label mb-2">NEXT RESOLUTION</p>
        <p className="font-display text-xs text-white leading-tight">
          {formatTime(status?.next_resolution)}
        </p>
      </div>

      {/* Today predictions */}
      <div className="card p-4">
        <p className="label mb-2">TODAY</p>
        <p className="font-display text-2xl text-white tabular-nums">
          {status?.today_predictions?.total ?? 0}
        </p>
        <p className="font-display text-xs text-gray-600 mt-0.5">
          predictions generated
        </p>
      </div>

      {/* Resolved today */}
      <div className="card p-4">
        <p className="label mb-2">RESOLVED</p>
        <p className="font-display text-2xl tabular-nums text-brand-greenlight">
          {status?.resolved_today ?? 0}
        </p>
        <p className="font-display text-xs text-gray-600 mt-0.5">
          results auto-resolved
        </p>
      </div>
    </div>
  );
}
