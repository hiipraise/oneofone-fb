// src/pages/SchedulerPage.jsx
//
// Sprint 5.3 — status grid, trigger/toggle controls, and the log viewer were
// extracted into src/components/scheduler/*. This page keeps data loading,
// the fixtures table, prediction groups, config panel, and the layout.
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import PaginationControls from "../components/PaginationControls";
import { disableScheduler, enableScheduler, triggerResolution, triggerScheduler } from "../services/api";
import { watTodayISO } from "../utils/wat";
import SchedulerStatusGrid from "../components/scheduler/StatusCards";
import SchedulerLogs from "../components/scheduler/SchedulerLogs";
import TriggerControls, { MessageBanner } from "../components/scheduler/TriggerControls";

const SPORTS = ["soccer"];
const SPORT_DOTS = {
  soccer: "bg-brand-green",
};
const SPORT_LABEL = {
  soccer: "Football / Soccer",
};

function rankedPredictionSort(a, b) {
  const rankA = Number.isFinite(Number(a?.overall_rank))
    ? Number(a.overall_rank)
    : Number.MAX_SAFE_INTEGER;
  const rankB = Number.isFinite(Number(b?.overall_rank))
    ? Number(b.overall_rank)
    : Number.MAX_SAFE_INTEGER;
  if (rankA !== rankB) return rankA - rankB;

  const playA = Number.isFinite(Number(a?.play_rank)) ? Number(a.play_rank) : 0;
  const playB = Number.isFinite(Number(b?.play_rank)) ? Number(b.play_rank) : 0;
  if (playA !== playB) return playB - playA;

  const confA = Number.isFinite(Number(a?.confidence_score))
    ? Number(a.confidence_score)
    : 0;
  const confB = Number.isFinite(Number(b?.confidence_score))
    ? Number(b.confidence_score)
    : 0;
  if (confA !== confB) return confB - confA;

  return String(a?.match_id || "").localeCompare(String(b?.match_id || ""));
}

function groupRankSort(a, b) {
  const groupA = Number.isFinite(Number(a?.group_index))
    ? Number(a.group_index)
    : Number.MAX_SAFE_INTEGER;
  const groupB = Number.isFinite(Number(b?.group_index))
    ? Number(b.group_index)
    : Number.MAX_SAFE_INTEGER;
  if (groupA !== groupB) return groupA - groupB;

  const playA = Number.isFinite(Number(a?.play_rank)) ? Number(a.play_rank) : 0;
  const playB = Number.isFinite(Number(b?.play_rank)) ? Number(b.play_rank) : 0;
  if (playA !== playB) return playB - playA;

  const confA = Number.isFinite(Number(a?.avg_confidence_score))
    ? Number(a.avg_confidence_score)
    : 0;
  const confB = Number.isFinite(Number(b?.avg_confidence_score))
    ? Number(b.avg_confidence_score)
    : 0;
  if (confA !== confB) return confB - confA;

  return String(a?.group_id || "").localeCompare(String(b?.group_id || ""));
}

function outcomeTag(outcome) {
  if (outcome === "home_win")
    return <span className="tag-green text-xs">HOME WIN</span>;
  if (outcome === "away_win")
    return <span className="tag-red text-xs">AWAY WIN</span>;
  if (outcome === "draw") return <span className="tag-gray text-xs">DRAW</span>;
  return <span className="tag-gray text-xs">—</span>;
}

function groupTag(row, groupStatusById) {
  const idx = row?.prediction_group_index;
  const groupId = row?.prediction_group_id;
  if (!idx || !groupId)
    return <span className="tag-gray text-xs">UNGROUPED</span>;

  const status = groupStatusById[groupId];
  if (!status) {
    return <span className="tag-gray text-xs">G{idx} · GROUP</span>;
  }

  if (status === "won") {
    return (
      <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-brand-greenlight bg-brand-greendark border-brand-green">
        G{idx} · GROUP WON
      </span>
    );
  }
  if (status === "lost") {
    return (
      <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-brand-redlight bg-brand-reddark border-brand-red">
        G{idx} · GROUP LOST
      </span>
    );
  }
  if (status === "miss") {
    return (
      <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-brand-redlight bg-brand-reddark border-brand-red">
        G{idx} · GROUP MISS
      </span>
    );
  }

  return (
    <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-brand-greenlight bg-brand-greendark border-brand-green">
      G{idx} · GROUP CORRECT
    </span>
  );
}

function buildPredictionGroups(fixtures) {
  const apiGroups = fixtures?.groups ?? [];
  if (apiGroups.length) return apiGroups;

  const rows = Object.values(fixtures?.by_sport || {}).flat();
  const groups = new Map();

  for (const row of rows) {
    const groupId = row?.prediction_group_id;
    if (!groupId) continue;

    const existing = groups.get(groupId) || {
      group_id: groupId,
      group_index: row?.prediction_group_index ?? null,
      is_high_risk_group: !!row?.prediction_group_is_high_risk,
      group_status: null,
      games: [],
    };

    if (existing.group_index == null && row?.prediction_group_index != null) {
      existing.group_index = row.prediction_group_index;
    }
    existing.is_high_risk_group =
      existing.is_high_risk_group || !!row?.prediction_group_is_high_risk;
    existing.games.push({
      match_id: row.match_id,
      sport: row.sport,
      home_team: row.home_team,
      away_team: row.away_team,
      league: row.league,
      predicted_outcome: row.predicted_outcome,
    });
    groups.set(groupId, existing);
  }

  return Array.from(groups.values()).sort((a, b) => {
    const aIdx = a.group_index ?? Number.POSITIVE_INFINITY;
    const bIdx = b.group_index ?? Number.POSITIVE_INFINITY;
    if (aIdx !== bIdx) return aIdx - bIdx;
    return String(a.group_id || "").localeCompare(String(b.group_id || ""));
  });
}

// ── Today fixture table ───────────────────────────────────────────────────────
function TodayTable({ fixtures, sport, loading }) {
  const rawRows = fixtures?.by_sport?.[sport] ?? [];
  const rows = useMemo(
    () => [...rawRows].sort(rankedPredictionSort),
    [rawRows],
  );
  const groups = useMemo(() => buildPredictionGroups(fixtures), [fixtures]);
  const groupStatusById = useMemo(() => {
    const map = {};
    for (const group of groups) {
      if (!group?.group_id) continue;
      map[group.group_id] =
        group.group_status || (group.is_high_risk_group ? "miss" : "correct");
    }
    return map;
  }, [groups]);
  const orderedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const aRank = a.overall_rank ?? Number.POSITIVE_INFINITY;
      const bRank = b.overall_rank ?? Number.POSITIVE_INFINITY;
      if (aRank !== bRank) return aRank - bRank;

      const aPlay = a.play_rank ?? 0;
      const bPlay = b.play_rank ?? 0;
      if (aPlay !== bPlay) return bPlay - aPlay;

      const aConf = a.confidence_score ?? 0;
      const bConf = b.confidence_score ?? 0;
      if (aConf !== bConf) return bConf - aConf;

      return String(a.match_id || "").localeCompare(String(b.match_id || ""));
    });
  }, [rows]);
  const PAGE_SIZE = 8;
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [sport, rows.length]);

  const totalPages = Math.max(1, Math.ceil(orderedRows.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginatedRows = orderedRows.slice(
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
      <div className="px-4 py-3 border-b border-brand-midgray bg-brand-darkgray/60 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
        <p className="font-display text-xs text-white">RANKED PREDICTIONS</p>
        <p className="font-body text-xs text-gray-600">
          Sorted by TOP rank first, then play rank and confidence.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-brand-midgray bg-brand-darkgray">
            <tr>
              {[
                "MATCH",
                "RANK",
                "LEAGUE",
                "PREDICTION",
                "GROUP",
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
                    <div className="flex flex-col gap-1">
                      <span className="font-display text-[10px] text-gray-400">
                        TOP #{row.overall_rank ?? "—"}
                      </span>
                      <span className="font-display text-[10px] text-yellow-300">
                        PLAY {row.play_rank ?? 0}/5
                      </span>
                    </div>
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
                    {groupTag(row, groupStatusById)}
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
        totalItems={orderedRows.length}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        itemLabel="FIXTURES TODAY"
      />
    </div>
  );
}

function PredictionGroupsPanel({ fixtures, loading }) {
  const groups = useMemo(
    () => [...buildPredictionGroups(fixtures)].sort(groupRankSort),
    [fixtures],
  );

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {[...Array(2)].map((_, i) => (
          <div key={i} className="card p-4 animate-pulse">
            <div className="h-3 w-24 bg-brand-midgray rounded mb-3" />
            <div className="h-2 w-full bg-brand-midgray rounded mb-1.5" />
            <div className="h-2 w-4/5 bg-brand-midgray rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (!groups.length) {
    return (
      <div className="card p-4">
        <p className="font-display text-xs text-gray-600">
          NO GROUPED SLATE AVAILABLE YET.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {groups.map((group) => (
        <div
          key={group.group_id}
          className={`card p-4 border ${
            group.is_high_risk_group
              ? "border-brand-red bg-brand-reddark"
              : "border-brand-midgray"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <p className="font-display text-sm text-white">{group.group_id}</p>
            <div className="flex items-center gap-2">
              <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-yellow-300 border-yellow-800 bg-yellow-900/20">
                RANK {group.group_index ?? "—"} · PLAY {group.play_rank ?? 0}/5
              </span>
              <span
                className={`font-display text-[10px] px-2 py-0.5 rounded-sm border ${
                  group.is_high_risk_group
                    ? "text-brand-redlight border-brand-red bg-brand-reddark"
                    : "text-yellow-300 border-yellow-800 bg-yellow-900/20"
                }`}
              >
                {group.is_high_risk_group ? "MOST LIKELY MISSES" : "LOWER RISK"}
              </span>
              {group.group_status === "won" && (
                <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-brand-greenlight bg-brand-greendark border-brand-green">
                  GROUP WON
                </span>
              )}
              {group.group_status === "lost" && (
                <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-brand-redlight bg-brand-reddark border-brand-red">
                  GROUP LOST
                </span>
              )}
              {!group.group_status && (
                <span className="font-display text-[10px] px-2 py-0.5 rounded-sm border text-gray-400 border-brand-midgray bg-brand-darkgray">
                  GROUP
                </span>
              )}
            </div>
          </div>
          <div className="space-y-1">
            {(group.games || []).map((g) => (
              <p
                key={g.match_id}
                className="font-display text-xs text-gray-300"
              >
                {g.home_team} <span className="text-gray-600">vs</span>{" "}
                {g.away_team}
              </p>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SchedulerPage() {
  const defaultDate = watTodayISO();
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
  const [selectedDate, setSelectedDate] = useState(defaultDate);
  const [togglingEnabled, setTogglingEnabled] = useState(false);

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
      const res = await api.get("/scheduler/fixtures/today", {
        params: { match_date: selectedDate, sport },
      });
      setFixtures(res.data);
    } catch {
      setFixtures(null);
    } finally {
      setFixturesLoading(false);
    }
  }, [selectedDate, sport]);

  const loadLogs = useCallback(async () => {
    try {
      const res = await api.get("/scheduler/logs", {
        params: { limit: 30, sport },
      });
      setLogs(Array.isArray(res.data) ? res.data : []);
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  }, [sport]);

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

  const handleRefresh = () => {
    setStatusLoading(true);
    loadStatus();
    loadFixtures();
    loadLogs();
  };

  const handleToggleEnabled = async () => {
    setTogglingEnabled(true);
    setTrigMsg(null);
    try {
      const currentlyEnabled = status?.scheduler_enabled !== false;
      await (currentlyEnabled ? disableScheduler() : enableScheduler());
      await loadStatus();
      setTrigMsg({
        type: "success",
        text: currentlyEnabled ? "Scheduler disabled and jobs paused." : "Scheduler enabled and jobs resumed.",
      });
    } catch (e) {
      setTrigMsg({
        type: "error",
        text: e.response?.data?.detail || "Scheduler toggle failed",
      });
    } finally {
      setTogglingEnabled(false);
    }
  };

  const handleTrigger = async () => {
    setTriggering(true);
    setTrigMsg(null);
    try {
      const res = await triggerScheduler();
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
  const todayPredictionCount = status?.today_predictions?.total ?? 0;
  const resolvedTodayCount = status?.resolved_today ?? 0;
  const pendingLogsCount = logs.filter(
    (log) => log.level === "ERROR" || log.level === "WARNING",
  ).length;

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
        <TriggerControls
          status={status}
          togglingEnabled={togglingEnabled}
          triggering={triggering}
          resolving={resolving}
          onRefresh={handleRefresh}
          onToggleEnabled={handleToggleEnabled}
          onTrigger={handleTrigger}
          onResolve={handleResolve}
        />
      </div>

      {/* Trigger messages — hint only applies to success banners */}
      <MessageBanner
        msg={
          trigMsg &&
          (trigMsg.type === "success"
            ? { ...trigMsg, hint: "Results will appear below in ~30s" }
            : trigMsg)
        }
      />
      <MessageBanner
        msg={
          resolveMsg &&
          (resolveMsg.type === "success"
            ? { ...resolveMsg, hint: "Check logs below for resolved matches" }
            : resolveMsg)
        }
      />

      {/* Status cards */}
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="label">SCHEDULER STATUS</p>
          <span className="font-display text-xs text-gray-700 tabular-nums">
            {todayPredictionCount} predictions · {resolvedTodayCount} resolved ·{" "}
            {pendingLogsCount} alerts
          </span>
        </div>
        <SchedulerStatusGrid status={status} loading={statusLoading} />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-8 space-y-6">
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
              <div>
                <p className="label">
                  PREDICTIONS — {SPORT_LABEL[sport]?.toUpperCase()}
                </p>
                <p className="font-display text-xs text-gray-600 mt-1">
                  Viewing {fixtures?.date || selectedDate} (group history is
                  preserved by date)
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="bg-brand-darkgray border border-brand-midgray focus:border-brand-red outline-none text-white font-display text-xs px-3 py-1.5 rounded-sm"
                />
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
            </div>
            <TodayTable
              fixtures={fixtures}
              sport={sport}
              loading={fixturesLoading}
            />
          </section>

          <section>
            <div className="flex items-center justify-between mb-3">
              <p className="label">PREDICTION GROUPS (ALL SPORTS)</p>
              <span className="font-display text-xs text-gray-700">
                {buildPredictionGroups(fixtures).length} groups
              </span>
            </div>
            <PredictionGroupsPanel
              fixtures={fixtures}
              loading={fixturesLoading}
            />
          </section>
        </div>

        <div className="xl:col-span-4 space-y-6">
          {/* Config info */}
          <section className="card p-5">
            <p className="label mb-4">CONFIGURATION</p>
            <div className="space-y-4">
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
                  ESPN/free sources — structured stats
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
          <section className="flex flex-col gap-3">
            <Link to="/history" className="btn-ghost text-xs">
              VIEW ALL PREDICTIONS →
            </Link>
            <Link to="/metrics" className="btn-ghost text-xs">
              MODEL METRICS →
            </Link>
          </section>
        </div>
      </div>
    </div>
  );
}
