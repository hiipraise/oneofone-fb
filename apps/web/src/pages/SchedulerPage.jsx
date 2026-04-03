// src/pages/SchedulerPage.jsx
import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import PaginationControls from "../components/PaginationControls";
import { triggerResolution } from "../services/api";
import { formatWatDateTime } from "../utils/wat";

const SPORTS = ["soccer", "basketball"];
const SPORT_DOTS = {
  soccer: "bg-brand-green",
  basketball: "bg-yellow-500",
};
const SPORT_LABEL = {
  soccer: "Football / Soccer",
  basketball: "Basketball",
};

function timeAgo(ts) {
  if (!ts) return "—";
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatTime(iso) {
  if (!iso) return "—";
  try {
    return formatWatDateTime(iso);
  } catch {
    return iso;
  }
}

function outcomeTag(outcome) {
  if (outcome === "home_win")
    return <span className="tag-green text-xs">HOME WIN</span>;
  if (outcome === "away_win")
    return <span className="tag-red text-xs">AWAY WIN</span>;
  if (outcome === "draw") return <span className="tag-gray text-xs">DRAW</span>;
  return <span className="tag-gray text-xs">—</span>;
}

// ── Status card ───────────────────────────────────────────────────────────────
function StatusCard({ status, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="card p-4 animate-pulse">
            <div className="h-2 bg-brand-midgray rounded w-20 mb-3" />
            <div className="h-6 bg-brand-midgray rounded w-24" />
          </div>
        ))}
      </div>
    );
  }

  const isOnline = status?.scheduler_running;
  const totalToday = status?.today_predictions?.total ?? 0;
  const bySport = status?.today_predictions?.by_sport ?? {};

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {/* Scheduler state */}
      <div className="card p-4">
        <p className="label mb-2">SCHEDULER</p>
        <div className="flex flex-wrap items-center gap-2">
          <div
            className={`w-2.5 h-2.5 rounded-full shrink-0 ${isOnline ? "bg-brand-green animate-pulse" : "bg-brand-red"}`}
          />
          <span
            className={`font-display text-sm ${isOnline ? "text-brand-greenlight" : "text-brand-redlight"}`}
          >
            {isOnline ? "ONLINE" : "OFFLINE"}
          </span>
        </div>
      </div>

      {/* Next run */}
      <div className="card p-4">
        <p className="label mb-2">NEXT RUN</p>
        <p className="font-display text-xs text-white leading-tight">
          {formatTime(status?.next_run)}
        </p>
      </div>

      {/* Last run */}
      <div className="card p-4">
        <p className="label mb-2">LAST RUN</p>
        <p className="font-display text-xs text-white">
          {timeAgo(status?.last_run?.timestamp)}
        </p>
        {status?.last_run?.timestamp && (
          <p className="font-display text-xs text-gray-700 mt-0.5">
            {formatTime(status.last_run.timestamp)}
          </p>
        )}
      </div>

      {/* Today total */}
      <div className="card p-4">
        <p className="label mb-2">TODAY</p>
        <p className="font-display text-2xl text-white tabular-nums">
          {totalToday}
        </p>
        <p className="font-display text-xs text-gray-600 mt-0.5">
          predictions generated
        </p>
      </div>
    </div>
  );
}

// ── Today fixture table ───────────────────────────────────────────────────────
function TodayTable({ fixtures, sport, loading }) {
  const rows = fixtures?.by_sport?.[sport] ?? [];
  const PAGE_SIZE = 8;
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [sport, rows.length]);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginatedRows = rows.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  if (loading) {
    return (
      <div className="flex flex-col gap-1">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="h-10 bg-brand-midgray rounded animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="card p-6 text-center">
        <p className="font-display text-gray-600 text-xs">
          NO {sport.toUpperCase()} PREDICTIONS FOR TODAY
        </p>
        <p className="font-body text-xs text-gray-700 mt-1">
          Run the scheduler or add fixtures via the Odds API
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
              {[
                "MATCH",
                "LEAGUE",
                "PREDICTION",
                "HOME%",
                "DRAW%",
                "AWAY%",
                "CONF",
              ].map((h) => (
                <th key={h} className="text-left label px-4 py-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.map((row, i) => {
              const isHome = row.predicted_outcome === "home_win";
              const isAway = row.predicted_outcome === "away_win";
              return (
                <tr
                  key={row.match_id || i}
                  className="border-b border-brand-midgray hover:bg-brand-gray transition-colors"
                >
                  <td className="px-4 py-3">
                    <span className="font-display text-xs text-white">
                      <span className={isHome ? "text-brand-greenlight" : ""}>
                        {row.home_team}
                      </span>
                      <span className="text-gray-600 mx-1.5">vs</span>
                      <span className={isAway ? "text-brand-redlight" : ""}>
                        {row.away_team}
                      </span>
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-display text-xs text-gray-600 truncate max-w-[120px] block">
                      {row.league || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {outcomeTag(row.predicted_outcome)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`font-display text-xs tabular-nums ${isHome ? "text-brand-greenlight" : "text-gray-400"}`}
                    >
                      {Math.round((row.home_win_probability ?? 0) * 100)}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-display text-xs text-gray-500 tabular-nums">
                      {`${Math.round((row.draw_probability ?? 0) * 100)}%`}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`font-display text-xs tabular-nums ${isAway ? "text-brand-redlight" : "text-gray-400"}`}
                    >
                      {Math.round((row.away_win_probability ?? 0) * 100)}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-display text-xs text-gray-500 tabular-nums">
                      {Math.round((row.confidence_score ?? 0) * 100)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <PaginationControls
        currentPage={safePage}
        totalItems={rows.length}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        itemLabel="FIXTURES TODAY"
      />
    </div>
  );
}

// ── Schedule log ──────────────────────────────────────────────────────────────
function SchedulerLogs({ logs, loading }) {
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

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SchedulerPage() {
  const [status, setStatus] = useState(null);
  const [fixtures, setFixtures] = useState(null);
  const [logs, setLogs] = useState([]);
  const [statusLoading, setStatusLoading] = useState(true);
  const [fixturesLoading, setFixturesLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(true);
  const [sport, setSport] = useState("soccer");
  const [triggering, setTriggering] = useState(false);
  const [trigMsg, setTrigMsg] = useState(null);
  const [resolving, setResolving] = useState(false);
  const [resolveMsg, setResolveMsg] = useState(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await api.get("/scheduler/status");
      setStatus(res.data);
    } catch {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const loadFixtures = useCallback(async () => {
    setFixturesLoading(true);
    try {
      const res = await api.get("/scheduler/fixtures/today");
      setFixtures(res.data);
    } catch {
      setFixtures(null);
    } finally {
      setFixturesLoading(false);
    }
  }, []);

  const loadLogs = useCallback(async () => {
    try {
      const res = await api.get("/scheduler/logs", { params: { limit: 30 } });
      setLogs(Array.isArray(res.data) ? res.data : []);
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadFixtures();
    loadLogs();
    // Auto-refresh status every 60s
    const id = setInterval(() => {
      loadStatus();
      loadFixtures();
    }, 60_000);
    return () => clearInterval(id);
  }, [loadStatus, loadFixtures, loadLogs]);

  const handleTrigger = async () => {
    setTriggering(true);
    setTrigMsg(null);
    try {
      const res = await api.post("/scheduler/trigger");
      setTrigMsg({
        type: "success",
        text: res.data.message || "Scheduler triggered.",
      });
      // Refresh after a brief delay to pick up new predictions
      setTimeout(() => {
        loadStatus();
        loadFixtures();
        loadLogs();
      }, 4000);
    } catch (e) {
      setTrigMsg({
        type: "error",
        text: e.response?.data?.detail || "Trigger failed",
      });
    } finally {
      setTriggering(false);
    }
  };

  const handleResolve = async () => {
    setResolving(true);
    setResolveMsg(null);
    try {
      const res = await triggerResolution();
      setResolveMsg({
        type: "success",
        text: res.data.message || "Resolution triggered.",
      });
      setTimeout(() => {
        loadStatus();
        loadLogs();
      }, 5000);
    } catch (e) {
      setResolveMsg({
        type: "error",
        text: e.response?.data?.detail || "Resolution trigger failed",
      });
    } finally {
      setResolving(false);
    }
  };

  const bySport = status?.today_predictions?.by_sport ?? {};

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">
            DAILY SCHEDULER
          </h1>
          <p className="font-body text-xs text-gray-600 mt-1">
            Automated prediction generation · Runs daily at configured WAT time
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => {
              setStatusLoading(true);
              loadStatus();
              loadFixtures();
              loadLogs();
            }}
            className="btn-ghost text-xs"
          >
            ↺ REFRESH
          </button>
          <button
            onClick={handleResolve}
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
            onClick={handleTrigger}
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
      </div>

      {/* Trigger messages */}
      {trigMsg && (
        <div
          className={`font-display text-xs px-4 py-3 rounded-sm border ${
            trigMsg.type === "success"
              ? "text-brand-greenlight bg-brand-greendark border-brand-green"
              : "text-brand-redlight bg-brand-reddark border-brand-red"
          }`}
        >
          {trigMsg.text}
          {trigMsg.type === "success" && (
            <span className="text-gray-500 ml-2">
              Results will appear below in ~30s
            </span>
          )}
        </div>
      )}
      {resolveMsg && (
        <div
          className={`font-display text-xs px-4 py-3 rounded-sm border ${
            resolveMsg.type === "success"
              ? "text-brand-greenlight bg-brand-greendark border-brand-green"
              : "text-brand-redlight bg-brand-reddark border-brand-red"
          }`}
        >
          {resolveMsg.text}
          {resolveMsg.type === "success" && (
            <span className="text-gray-500 ml-2">
              Check logs below for resolved matches
            </span>
          )}
        </div>
      )}

      {/* Status cards */}
      {/* Status cards — now 5 cards */}
      <section>
        <p className="label mb-3">SCHEDULER STATUS</p>
        {statusLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="card p-4 animate-pulse">
                <div className="h-2 bg-brand-midgray rounded w-20 mb-3" />
                <div className="h-6 bg-brand-midgray rounded w-24" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {/* Scheduler state */}
            <div className="card p-4">
              <p className="label mb-2">SCHEDULER</p>
              <div className="flex flex-wrap items-center gap-2">
                <div
                  className={`w-2.5 h-2.5 rounded-full shrink-0 ${status?.scheduler_running ? "bg-brand-green animate-pulse" : "bg-brand-red"}`}
                />
                <span
                  className={`font-display text-sm ${status?.scheduler_running ? "text-brand-greenlight" : "text-brand-redlight"}`}
                >
                  {status?.scheduler_running ? "ONLINE" : "OFFLINE"}
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
        )}
      </section>

      {/* Per-sport breakdown */}
      {!statusLoading && (
        <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {SPORTS.map((s) => (
            <div
              key={s}
              onClick={() => setSport(s)}
              className={`card p-4 cursor-pointer transition-all duration-150 ${
                sport === s
                  ? "border-brand-red bg-brand-reddark"
                  : "hover:border-gray-500"
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className={`w-2 h-2 rounded-full ${SPORT_DOTS[s]}`} />
                <p className="label">{s.toUpperCase()}</p>
              </div>
              <p
                className={`font-display text-3xl tabular-nums ${sport === s ? "text-white" : "text-gray-400"}`}
              >
                {bySport[s] ?? 0}
              </p>
              <p className="font-display text-xs text-gray-600 mt-0.5">
                {SPORT_LABEL[s]}
              </p>
            </div>
          ))}
        </section>
      )}

      {/* Today's fixtures table */}
      <section>
        <div className="flex flex-col gap-3 mb-3 lg:flex-row lg:items-center lg:justify-between">
          <p className="label">
            TODAY'S PREDICTIONS — {SPORT_LABEL[sport]?.toUpperCase()}
          </p>
          <div className="flex flex-wrap gap-1">
            {SPORTS.map((s) => (
              <button
                key={s}
                onClick={() => setSport(s)}
                className={`font-display text-xs px-3 py-1 rounded-sm border transition-colors ${
                  sport === s
                    ? "bg-brand-red border-brand-red text-white"
                    : "border-brand-midgray text-gray-500 hover:text-white"
                }`}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <TodayTable
          fixtures={fixtures}
          sport={sport}
          loading={fixturesLoading}
        />
      </section>

      {/* Config info */}
      <section className="card p-5">
        <p className="label mb-4">CONFIGURATION</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <p className="label">SCHEDULE</p>
            <p className="font-display text-xs text-gray-300">
              Predictions — daily at configured WAT hour
            </p>
            <p className="font-display text-xs text-gray-600">
              Set via DAILY_PREDICTION_HOUR in .env
            </p>
            <p className="font-display text-xs text-gray-300 mt-2">
              Resolution — daily at 00:00 WAT
            </p>
            <p className="font-display text-xs text-gray-600">
              Set via RESULT_RESOLUTION_HOUR in .env
            </p>
          </div>
          <div className="space-y-2">
            <p className="label">SPORTS</p>
            <div className="flex flex-col gap-1">
              {SPORTS.map((s) => (
                <div key={s} className="flex items-center gap-2">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${SPORT_DOTS[s]}`}
                  />
                  <span className="font-display text-xs text-gray-400">
                    {SPORT_LABEL[s]}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <p className="label">DATA SOURCES</p>
            <p className="font-display text-xs text-gray-400">
              The Odds API — fixture discovery
            </p>
            <p className="font-display text-xs text-gray-400">
              ESPN API — team stats (free)
            </p>
            <p className="font-display text-xs text-gray-400">
              Serper.dev — search (2,400/mo)
            </p>
            <p className="font-display text-xs text-gray-400">
              RapidAPI — structured stats
            </p>
          </div>
        </div>
      </section>

      {/* Scheduler logs */}
      <section>
        <div className="flex flex-col gap-3 mb-3 lg:flex-row lg:items-center lg:justify-between">
          <p className="label">SCHEDULER LOGS</p>
          <span className="font-display text-xs text-gray-700">
            {logs.length} entries
          </span>
        </div>
        <SchedulerLogs logs={logs} loading={logsLoading} />
      </section>

      {/* Quick links */}
      <section className="flex gap-3">
        <Link to="/history" className="btn-ghost text-xs">
          VIEW ALL PREDICTIONS →
        </Link>
        <Link to="/metrics" className="btn-ghost text-xs">
          MODEL METRICS →
        </Link>
      </section>
    </div>
  );
}
