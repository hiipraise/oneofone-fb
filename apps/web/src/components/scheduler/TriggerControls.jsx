// src/components/scheduler/TriggerControls.jsx
//
// Scheduler trigger / toggle controls and message banners (extracted from
// SchedulerPage.jsx in the Sprint 5.3 file-split pass).
import React from "react";

export function MessageBanner({ msg }) {
  if (!msg) return null;
  return (
    <div
      className={`font-display text-xs px-4 py-3 rounded-sm border ${
        msg.type === "success"
          ? "text-brand-greenlight bg-brand-greendark border-brand-green"
          : "text-brand-redlight bg-brand-reddark border-brand-red"
      }`}
    >
      {msg.text}
      {msg.type === "success" && msg.hint && (
        <span className="text-gray-500 ml-2">{msg.hint}</span>
      )}
    </div>
  );
}

export default function TriggerControls({
  status,
  togglingEnabled,
  triggering,
  resolving,
  onRefresh,
  onToggleEnabled,
  onTrigger,
  onResolve,
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button onClick={onRefresh} className="btn-ghost text-xs">
        ↺ REFRESH
      </button>

      <button
        onClick={onToggleEnabled}
        disabled={togglingEnabled || !status?.scheduler_running}
        className={`text-xs px-3 py-2 rounded-sm border font-display ${
          status?.scheduler_enabled === false
            ? "border-brand-red text-brand-redlight bg-brand-reddark"
            : "border-brand-green text-brand-greenlight bg-brand-greendark"
        }`}
      >
        {togglingEnabled
          ? "UPDATING..."
          : status?.scheduler_enabled === false
            ? "ENABLE JOBS"
            : "DISABLE JOBS"}
      </button>
      <button
        onClick={onResolve}
        disabled={resolving || !status?.scheduler_running}
        className="btn-ghost text-xs"
      >
        {resolving ? (
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 border border-gray-400 border-t-transparent rounded-full animate-spin" />
            RESOLVING...
          </span>
        ) : (
          "⟳ RESOLVE RESULTS"
        )}
      </button>
      <button
        onClick={onTrigger}
        disabled={triggering || !status?.scheduler_running}
        className="btn-primary"
      >
        {triggering ? (
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />
            RUNNING...
          </span>
        ) : (
          "▶ RUN NOW"
        )}
      </button>
    </div>
  );
}
