// src/components/scheduler/SchedulerLogs.jsx
//
// Scheduler log viewer (extracted from SchedulerPage.jsx in the Sprint 5.3
// file-split pass). Renders timestamp / level / message rows with pagination.
import React, { useEffect, useState } from "react";
import PaginationControls from "../PaginationControls";
import { formatTime, timeAgo } from "./schedulerUtils";

export default function SchedulerLogs({ logs, loading }) {
  const PAGE_SIZE = 10;
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [logs.length]);

  const totalPages = Math.max(1, Math.ceil(logs.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginatedLogs = logs.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );
  if (loading) {
    return (
      <div className="flex flex-col gap-1">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-8 bg-brand-midgray rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (!logs.length) {
    return (
      <div className="card p-6 text-center">
        <p className="font-display text-gray-600 text-xs">
          NO SCHEDULER LOGS YET
        </p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-brand-midgray bg-brand-darkgray">
            <tr>
              {["TIMESTAMP", "LEVEL", "MESSAGE"].map((h) => (
                <th key={h} className="text-left label px-4 py-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedLogs.map((log, i) => (
              <tr
                key={i}
                className="border-b border-brand-midgray hover:bg-brand-gray transition-colors"
              >
                <td className="px-4 py-3 font-display text-xs text-gray-500 whitespace-nowrap">
                  {formatTime(log.timestamp)}
                  <span className="ml-2 text-gray-700">
                    {timeAgo(log.timestamp)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
                      log.level === "ERROR"
                        ? "text-brand-redlight bg-brand-reddark border-brand-red"
                        : log.level === "WARNING"
                          ? "text-yellow-400 bg-yellow-900/20 border-yellow-800"
                          : "text-brand-greenlight bg-brand-greendark border-brand-green"
                    }`}
                  >
                    {log.level}
                  </span>
                </td>
                <td className="px-4 py-3 font-display text-xs text-gray-400">
                  {log.message}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <PaginationControls
        currentPage={safePage}
        totalItems={logs.length}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        itemLabel="LOG ENTRIES"
      />
    </div>
  );
}
