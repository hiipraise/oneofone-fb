// src/components/scheduler/schedulerUtils.js
//
// Shared formatting helpers for the scheduler components (extracted from
// SchedulerPage.jsx in the Sprint 5.3 file-split pass).
import { formatWatDateTime } from "../../utils/wat";

export function timeAgo(ts) {
  if (!ts) return "—";
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function formatTime(iso) {
  if (!iso) return "—";
  try {
    return formatWatDateTime(iso);
  } catch {
    return iso;
  }
}
