// src/components/PredictionTable.jsx
import React, { useState } from "react";
import { deletePrediction, repredictPrediction } from "../services/api";
import { formatWatDate } from "../utils/wat";

function predictionDateValue(pred) {
  const rawDate = pred?.match_date || pred?.timestamp || "";
  const time = rawDate ? Date.parse(rawDate) : NaN;
  return Number.isFinite(time) ? time : 0;
}

function sortValue(pred, key) {
  if (key === "prediction_date") return predictionDateValue(pred);
  return pred?.[key] ?? "";
}

function outcomeTag(outcome) {
  if (outcome === "home_win")
    return <span className="tag-green">HOME WIN</span>;
  if (outcome === "away_win") return <span className="tag-red">AWAY WIN</span>;
  if (outcome === "draw") return <span className="tag-gray">DRAW</span>;
  return <span className="tag-gray">—</span>;
}

function resolutionStatus(pred, resolvedMatch) {
  if (!resolvedMatch?.actual_outcome) {
    return { icon: "➖", label: "Pending", className: "text-gray-600" };
  }

  if (resolvedMatch.actual_outcome === pred.predicted_outcome) {
    return { icon: "✔️", label: "Correct", className: "text-brand-greenlight" };
  }

  return { icon: "❌", label: "Miss", className: "text-brand-redlight" };
}

// Inline mini bar + % cell (Sprint 2) — scanning the table feels like a board
// of tickers rather than a spreadsheet of colored numbers.
function pctCell(value, highlight = false) {
  const pct = Math.round((value || 0) * 100);
  const color = highlight
    ? "#ffffff"
    : pct >= 60
      ? "#22c55e"
      : pct >= 45
        ? "#eab308"
        : "#ef4444";
  return (
    <div className="flex items-center gap-1.5 min-w-[72px]">
      <div className="flex-1 h-1 bg-brand-darkgray rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span
        className="font-display text-xs tabular-nums w-8 text-right"
        style={{ color }}
      >
        {pct}%
      </span>
    </div>
  );
}

// Mobile-only sort options (Sprint 6.16) — keys match the desktop table's
// sortValue() keys; subset omits sport/draw which aren't shown on mobile cards.
const MOBILE_SORT_OPTIONS = [
  { key: "prediction_date", label: "DATE" },
  { key: "match_id", label: "MATCH ID" },
  { key: "home_team", label: "TEAM" },
  { key: "predicted_outcome", label: "PICK" },
  { key: "home_win_probability", label: "HOME%" },
  { key: "away_win_probability", label: "AWAY%" },
  { key: "confidence_score", label: "CONF" },
];

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={handleCopy}
      className="ml-1 font-display text-xs text-gray-700 hover:text-gray-400 transition-colors"
      title="Copy match ID"
    >
      {copied ? "✓" : "⎘"}
    </button>
  );
}

function DeleteButton({ matchId, onDeleted }) {
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleClick = (e) => {
    e.stopPropagation();
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setLoading(true);
    deletePrediction(matchId)
      .then(() => onDeleted(matchId))
      .catch(() => setConfirming(false))
      .finally(() => setLoading(false));
  };

  return (
    <button
      onClick={handleClick}
      onBlur={() => setTimeout(() => setConfirming(false), 200)}
      disabled={loading}
      className={`font-display text-xs px-2 py-0.5 rounded-sm border transition-colors duration-150 ${
        confirming
          ? "border-brand-red text-brand-redlight bg-brand-reddark"
          : "border-brand-midgray text-gray-600 hover:border-brand-red hover:text-brand-redlight"
      } disabled:opacity-40`}
      title={confirming ? "Click again to confirm delete" : "Delete prediction"}
    >
      {loading ? "..." : confirming ? "CONFIRM?" : "✕"}
    </button>
  );
}

function RePredictButton({ matchId, onDone }) {
  const [loading, setLoading] = useState(false);

  const handleClick = (e) => {
    e.stopPropagation();
    setLoading(true);
    repredictPrediction(matchId)
      .then(() => onDone?.())
      .finally(() => setLoading(false));
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className="font-display text-xs px-2 py-0.5 rounded-sm border border-brand-midgray text-gray-500 hover:border-brand-green hover:text-brand-greenlight transition-colors duration-150 disabled:opacity-40"
      title="Force regenerate this prediction and regroup its date"
    >
      {loading ? "..." : "↻"}
    </button>
  );
}

function ResolveButton({ prediction, onResolveRequest, isResolving = false }) {
  if (!prediction?.match_id) return null;

  const handleClick = (e) => {
    e.stopPropagation();
    onResolveRequest?.(prediction);
  };

  return (
    <button
      onClick={handleClick}
      disabled={isResolving}
      className="font-display text-xs px-2 py-0.5 rounded-sm border border-brand-green text-brand-greenlight hover:bg-brand-greendark transition-colors duration-150"
      title="Trigger result resolution for this prediction"
    >
      {isResolving ? "RESOLVING..." : "RESOLVE"}
    </button>
  );
}

export default function PredictionTable({
  predictions = [],
  resolvedMatches = {},
  showSport = true,
  onRefetch,
  engineStatusBySport = null,
  onResolveRequest = null,
  resolvingMatchId = null,
}) {
  const [sortKey, setSortKey] = useState("prediction_date");
  const [sortDir, setSortDir] = useState("desc");
  const [localPreds, setLocalPreds] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const items = localPreds ?? predictions;

  const handleDeleted = (matchId) => {
    setLocalPreds(
      (localPreds ?? predictions).filter((p) => p.match_id !== matchId),
    );
    if (onRefetch) onRefetch();
  };

  const sorted = [...items].sort((a, b) => {
    const av = sortValue(a, sortKey);
    const bv = sortValue(b, sortKey);
    return sortDir === "asc" ? (av > bv ? 1 : -1) : av < bv ? 1 : -1;
  });

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const paginated = sorted.slice(startIndex, startIndex + pageSize);

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
    setCurrentPage(1);
    setExpandedId(null);
  };

  const goToPage = (nextPage) => {
    setCurrentPage(Math.max(1, Math.min(totalPages, nextPage)));
    setExpandedId(null);
  };

  const Col = ({ label, k, className = "" }) => (
    <th
      onClick={() => k && toggleSort(k)}
      className={`text-left label px-4 py-3 ${k ? "cursor-pointer hover:text-white transition-colors select-none" : ""} ${className}`}
    >
      {label} {k && sortKey === k ? (sortDir === "asc" ? "↑" : "↓") : ""}
    </th>
  );

  // Sprint 6.16 — shared row metadata used by both the md+ table and the
  // deliberate mobile card-list fallback (below the md breakpoint).
  const rowMeta = (pred) => {
    const shortId = pred.match_id
      ? pred.match_id.split("-").slice(0, 2).join("-").toUpperCase()
      : "—";
    const isHome = pred.predicted_outcome === "home_win";
    const isAway = pred.predicted_outcome === "away_win";
    const resolvedMatch = resolvedMatches[pred.match_id];
    const status = resolutionStatus(pred, resolvedMatch);
    const normalizedSport = (pred.sport || "").toLowerCase();
    const engineStatusForSport =
      engineStatusBySport && normalizedSport
        ? engineStatusBySport[normalizedSport]
        : null;
    const isEngineActive =
      typeof engineStatusForSport === "boolean"
        ? engineStatusForSport
        : pred.is_trained_model !== false;
    return {
      shortId,
      isHome,
      isAway,
      resolvedMatch,
      status,
      isEngineActive,
    };
  };

  // Mobile-only sort control (Sprint 6.16): the desktop sortable headers are
  // hidden below md, so give the card list its own compact sort picker rather
  // than silently dropping the capability.
  const renderMobileSort = () => (
    <div className="md:hidden flex items-center gap-2 px-4 py-2 border-b border-brand-midgray bg-brand-darkgray/60">
      <span className="label">SORT</span>
      <select
        value={sortKey}
        onChange={(e) => {
          const key = e.target.value;
          if (key !== sortKey) {
            setSortKey(key);
            setSortDir("desc");
            setCurrentPage(1);
            setExpandedId(null);
          }
        }}
        className="flex-1 bg-brand-darkgray border border-brand-midgray text-white font-display text-xs px-2 py-1 rounded-sm outline-none"
        aria-label="Sort predictions"
      >
        {MOBILE_SORT_OPTIONS.map((opt) => (
          <option key={opt.key} value={opt.key}>
            {opt.label}
          </option>
        ))}
      </select>
      <button
        onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
        className="font-display text-xs px-2 py-1 rounded-sm border border-brand-midgray text-gray-400 hover:text-white transition-colors"
        title="Toggle sort direction"
      >
        {sortDir === "asc" ? "↑" : "↓"}
      </button>
    </div>
  );

  // Mobile-only card list (Sprint 6.16): below md the wide table is replaced
  // by compact cards so scanning picks on a phone doesn't require horizontal
  // scrolling. Table stays for md+. Rendered via a plain function call (not a
  // JSX element) so it never creates an unstable component identity that would
  // remount cards (and reset DeleteButton confirm state) on every re-render.
  const renderMobileCards = () => (
    <div className="md:hidden divide-y divide-brand-midgray">
      {paginated.map((pred, i) => {
        const meta = rowMeta(pred);
        const isExpandedMobile = expandedId === pred.match_id;
        return (
          <div
            key={pred.match_id || `card-${startIndex + i}`}
            className="px-4 py-3 space-y-2.5"
            onClick={() =>
              setExpandedId(isExpandedMobile ? null : pred.match_id)
            }
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-display text-xs text-white whitespace-nowrap overflow-hidden text-ellipsis">
                  <span className={meta.isHome ? "text-brand-greenlight" : ""}>
                    {pred.home_team}
                  </span>
                  <span className="text-gray-600 mx-1">vs</span>
                  <span className={meta.isAway ? "text-brand-redlight" : ""}>
                    {pred.away_team}
                  </span>
                </p>
                <p className="font-display text-xs text-gray-700 mt-0.5 truncate">
                  {pred.league || pred.match_id}
                </p>
              </div>
              {outcomeTag(pred.predicted_outcome)}
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="label">HOME</span>
                {pctCell(pred.home_win_probability, meta.isHome)}
              </div>
              {showSport && (
                <div className="flex items-center justify-between gap-2">
                  <span className="label">DRAW</span>
                  {pctCell(pred.draw_probability)}
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <span className="label">AWAY</span>
                {pctCell(pred.away_win_probability, meta.isAway)}
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="label">CONF</span>
                {pctCell(pred.confidence_score)}
              </div>
            </div>

            <div className="flex items-center justify-between gap-2">
              <div
                className={`font-display text-xs flex items-center gap-1.5 ${meta.status.className}`}
              >
                <span>{meta.status.icon}</span>
                <span>{meta.status.label}</span>
                <span className="text-gray-700 ml-2">
                  {pred.timestamp ? formatWatDate(pred.timestamp) : pred.match_date || "—"}
                </span>
              </div>
              <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                <ResolveButton
                  prediction={pred}
                  onResolveRequest={onResolveRequest}
                  isResolving={resolvingMatchId === pred.match_id}
                />
                <RePredictButton matchId={pred.match_id} onDone={onRefetch} />
                <DeleteButton matchId={pred.match_id} onDeleted={handleDeleted} />
              </div>
            </div>

            {isExpandedMobile && pred.match_id && (
              <div
                className="flex flex-col gap-1.5 border-t border-brand-midgray pt-2.5"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center gap-2">
                  <span className="label">FULL MATCH ID</span>
                  <code className="font-display text-xs text-gray-400 bg-brand-gray px-2 py-1 rounded-sm break-all flex-1 min-w-0">
                    {pred.match_id}
                  </code>
                  <CopyButton text={pred.match_id} />
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                  {pred.model_version && (
                    <span className="font-display text-xs text-gray-600">
                      Model v{pred.model_version}
                      <span
                        className={`ml-2 ${meta.isEngineActive ? "text-brand-greenlight" : "text-yellow-600"}`}
                      >
                        {meta.isEngineActive ? "ML ACTIVE" : "PRIOR MODE"}
                      </span>
                    </span>
                  )}
                  {pred.confidence_interval_low != null && (
                    <span className="font-display text-xs text-gray-600">
                      CI: {Math.round(pred.confidence_interval_low * 100)}%–
                      {Math.round(pred.confidence_interval_high * 100)}%
                    </span>
                  )}
                  {meta.resolvedMatch?.actual_outcome && (
                    <span className={`font-display text-xs ${meta.status.className}`}>
                      {meta.status.icon} Actual:{" "}
                      {meta.resolvedMatch.actual_outcome.replace("_", " ").toUpperCase()}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );

  if (!items.length) {
    return (
      <div className="card p-10 text-center">
        <p className="font-display text-gray-600 text-sm">
          NO PREDICTIONS RECORDED
        </p>
        <p className="font-body text-xs text-gray-700 mt-2">
          Generate predictions from the Predict page
        </p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      {renderMobileSort()}
      <div className="md:hidden">{renderMobileCards()}</div>
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-brand-midgray bg-brand-darkgray">
            <tr>
              <Col label="MATCH ID" k="match_id" />
              <Col label="MATCH" k="home_team" />
              {showSport && <Col label="SPORT" k="sport" />}
              <Col label="PREDICTION" k="predicted_outcome" />
              <Col label="HOME%" k="home_win_probability" />
              {showSport && <Col label="DRAW%" k="draw_probability" />}
              <Col label="AWAY%" k="away_win_probability" />
              <Col label="CONF" k="confidence_score" />
              <Col label="STATUS" k={null} />
              <Col label="DATE" k="prediction_date" />
              <Col label="" k={null} className="w-16" />
            </tr>
          </thead>
          <tbody>
            {paginated.map((pred, i) => {
              const isExpanded = expandedId === pred.match_id;
              const shortId = pred.match_id
                ? pred.match_id.split("-").slice(0, 2).join("-").toUpperCase()
                : "—";
              const isHome = pred.predicted_outcome === "home_win";
              const isAway = pred.predicted_outcome === "away_win";
              const resolvedMatch = resolvedMatches[pred.match_id];
              const status = resolutionStatus(pred, resolvedMatch);
              const normalizedSport = (pred.sport || "").toLowerCase();
              const engineStatusForSport =
                engineStatusBySport && normalizedSport
                  ? engineStatusBySport[normalizedSport]
                  : null;
              const isEngineActive =
                typeof engineStatusForSport === "boolean"
                  ? engineStatusForSport
                  : pred.is_trained_model !== false;

              return (
                <React.Fragment key={pred.match_id || `${startIndex + i}`}>
                  <tr
                    onClick={() =>
                      setExpandedId(isExpanded ? null : pred.match_id)
                    }
                    className="border-b border-brand-midgray hover:bg-brand-gray transition-colors duration-100 cursor-pointer"
                  >
                    {/* Match ID */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <span
                          className="text-xs text-gray-600 font-mono tracking-tight"
                          title={pred.match_id}
                        >
                          {shortId}
                        </span>
                        {pred.match_id && <CopyButton text={pred.match_id} />}
                      </div>
                    </td>

                    {/* Match */}
                    <td className="px-4 py-3">
                      <div className="font-display text-xs text-white whitespace-nowrap">
                        <span className={isHome ? "text-brand-greenlight" : ""}>
                          {pred.home_team}
                        </span>
                        <span className="text-gray-600 mx-1.5">vs</span>
                        <span className={isAway ? "text-brand-redlight" : ""}>
                          {pred.away_team}
                        </span>
                      </div>
                      {pred.league && (
                        <div className="font-display text-xs text-gray-700 mt-0.5 truncate max-w-[180px]">
                          {pred.league}
                        </div>
                      )}
                    </td>

                    {showSport && (
                      <td className="px-4 py-3">
                        <span className="tag-gray">
                          {pred.sport?.toUpperCase()}
                        </span>
                      </td>
                    )}

                    <td className="px-4 py-3">
                      {outcomeTag(pred.predicted_outcome)}
                    </td>
                    <td className="px-4 py-3">
                      {pctCell(pred.home_win_probability, isHome)}
                    </td>
                    {showSport && (
                      <td className="px-4 py-3">
                        {pctCell(pred.draw_probability)}
                      </td>
                    )}
                    <td className="px-4 py-3">
                      {pctCell(pred.away_win_probability, isAway)}
                    </td>
                    <td className="px-4 py-3">
                      {pctCell(pred.confidence_score)}
                    </td>
                    <td className="px-4 py-3">
                      <div
                        className={`font-display text-xs flex items-center gap-1.5 whitespace-nowrap ${status.className}`}
                      >
                        <span>{status.icon}</span>
                        <span>{status.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-display text-xs text-gray-600 whitespace-nowrap">
                        {pred.timestamp
                          ? formatWatDate(pred.timestamp)
                          : pred.match_date || "—"}
                      </span>
                    </td>
                    <td
                      className="px-4 py-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-end gap-1.5">
                        <ResolveButton
                          prediction={pred}
                          onResolveRequest={onResolveRequest}
                          isResolving={resolvingMatchId === pred.match_id}
                        />
                        <RePredictButton
                          matchId={pred.match_id}
                          onDone={onRefetch}
                        />
                        <DeleteButton
                          matchId={pred.match_id}
                          onDeleted={handleDeleted}
                        />
                      </div>
                    </td>
                  </tr>

                  {/* Expanded match ID row */}
                  {isExpanded && pred.match_id && (
                    <tr className="border-b border-brand-midgray bg-brand-darkgray">
                      <td colSpan={showSport ? 11 : 9} className="px-4 py-3">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="label">FULL MATCH ID</span>
                          <code className="font-display text-xs text-gray-400 bg-brand-gray px-2 py-1 rounded-sm break-all">
                            {pred.match_id}
                          </code>
                          <CopyButton text={pred.match_id} />
                          {pred.model_version && (
                            <span className="font-display text-xs text-gray-600">
                              Model v{pred.model_version}
                              <span
                                className={`ml-2 ${isEngineActive ? "text-brand-greenlight" : "text-yellow-600"}`}
                              >
                                {isEngineActive ? "ML ACTIVE" : "PRIOR MODE"}
                              </span>
                            </span>
                          )}
                          {pred.confidence_interval_low != null && (
                            <span className="font-display text-xs text-gray-600">
                              CI:{" "}
                              {Math.round(pred.confidence_interval_low * 100)}%–
                              {Math.round(pred.confidence_interval_high * 100)}%
                            </span>
                          )}
                          {resolvedMatch?.actual_outcome && (
                            <span
                              className={`font-display text-xs ${status.className}`}
                            >
                              {status.icon} Actual:{" "}
                              {resolvedMatch.actual_outcome
                                .replace("_", " ")
                                .toUpperCase()}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="px-4 py-2 border-t border-brand-midgray flex items-center justify-between">
        <div className="font-display text-xs text-gray-700">
          {startIndex + 1}–{Math.min(startIndex + pageSize, sorted.length)} of{" "}
          {sorted.length} PREDICTIONS
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => goToPage(safePage - 1)}
            disabled={safePage === 1}
            className="font-display text-xs px-2 py-1 rounded-sm border border-brand-midgray text-gray-600 disabled:opacity-40"
          >
            PREV
          </button>
          <span className="font-display text-xs text-gray-700">
            PAGE {safePage}/{totalPages}
          </span>
          <button
            onClick={() => goToPage(safePage + 1)}
            disabled={safePage === totalPages}
            className="font-display text-xs px-2 py-1 rounded-sm border border-brand-midgray text-gray-600 disabled:opacity-40"
          >
            NEXT
          </button>
          <span className="font-display text-xs text-gray-700 hidden sm:inline">
            CLICK ROW TO EXPAND · ✕ TO DELETE
          </span>
        </div>
      </div>
    </div>
  );
}
