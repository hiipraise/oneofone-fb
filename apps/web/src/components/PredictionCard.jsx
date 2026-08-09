// src/components/PredictionCard.jsx
import React, { useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  RadialBarChart,
  RadialBar,
  PolarAngleAxis,
  ResponsiveContainer,
} from "recharts";
import { formatWatDate } from "../utils/wat";

// ─── Probability donut + legend (Sprint 2) ───────────────────────────────────
// Compact recharts donut showing home/draw/away split at a glance; the winner
// slice is saturated, the rest dimmed, with a thin track + % legend alongside.
function ProbabilityDonut({ home = 0, draw = 0, away = 0, winnerIs }) {
  const sides = [
    { key: "home_win", label: "HOME", pct: home, color: "#22c55e" },
    { key: "draw", label: "DRAW", pct: draw, color: "#eab308" },
    { key: "away_win", label: "AWAY", pct: away, color: "#ef4444" },
  ];

  const hasAnyProb = sides.some((s) => Number(s.pct) > 0);
  if (!hasAnyProb) {
    return (
      <div className="flex items-center justify-center py-4">
        <p className="font-display text-xs text-gray-600">
          NO PROBABILITY DATA
        </p>
      </div>
    );
  }

  // Default the highlighted slice to the most likely outcome when the pick
  // isn't recorded (legacy docs) so the donut always reads at a glance.
  const effectiveWinner =
    winnerIs || sides.reduce((best, s) =>
      Number(s.pct) > Number(best.pct) ? s : best, sides[0]
    ).key;

  const data = sides.map((s) => ({
    ...s,
    value: Math.max((s.pct ?? 0) * 100, 0.5), // keep a tiny visible slice
  }));

  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="w-20 h-20 shrink-0 mx-auto sm:mx-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius="62%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="none"
              startAngle={90}
              endAngle={-270}
            >
              {data.map((d) => (
                <Cell
                  key={d.key}
                  fill={d.color}
                  fillOpacity={d.key === effectiveWinner ? 1 : 0.3}
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex-1 min-w-[200px] flex flex-col gap-1.5">
        {sides.map((s) => {
          const pct = Math.round((s.pct ?? 0) * 100);
          const isWin = s.key === effectiveWinner;
          return (
            <div key={s.key} className="flex items-center gap-2">
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ backgroundColor: s.color, opacity: isWin ? 1 : 0.4 }}
              />
              <span
                className={`font-display text-xs truncate ${isWin ? "text-white" : "text-gray-500"}`}
              >
                {s.label}
              </span>
              <span className="flex-1 h-1 bg-brand-darkgray rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: s.color,
                    opacity: isWin ? 1 : 0.35,
                  }}
                />
              </span>
              <span
                className={`font-display text-xs tabular-nums w-10 text-right ${isWin ? "text-white" : "text-gray-500"}`}
              >
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Confidence gauge (Sprint 2) ─────────────────────────────────────────────
// Radial gauge color-banded like the old badge: green >=60%, yellow 35-59%,
// red <35%. Reads as a meter instead of a label.
function ConfidenceGauge({ value }) {
  const pct = Math.round((value ?? 0) * 100);
  const color = pct >= 60 ? "#22c55e" : pct >= 35 ? "#eab308" : "#ef4444";
  const data = [{ name: "confidence", value: pct }];
  return (
    <div
      className="relative w-14 h-14 shrink-0"
      title={`${pct}% confidence`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="68%"
          outerRadius="100%"
          barSize={5}
          data={data}
          startAngle={225}
          endAngle={-45}
        >
          <PolarAngleAxis
            type="number"
            domain={[0, 100]}
            angleAxisId={0}
            tick={false}
          />
          <RadialBar
            background={{ fill: "#2a2a2a" }}
            dataKey="value"
            cornerRadius={4}
            angleAxisId={0}
            fill={color}
          />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex items-center justify-center">
        <span
          className="font-display text-xs tabular-nums"
          style={{ color }}
        >
          {pct}%
        </span>
      </div>
    </div>
  );
}

// Confidence is now rendered as a radial gauge in the card header.

// ─── BTTS badge ──────────────────────────────────────────────────────────────
function BttsBadge({ btts }) {
  if (!btts) return null;
  const isYes = btts.result === "Yes";
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-display text-xs text-gray-600">GG</span>
      <span
        className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
          isYes
            ? "text-brand-greenlight bg-brand-greendark border-brand-green"
            : "text-brand-redlight bg-brand-reddark border-brand-red"
        }`}
      >
        {isYes ? `Yes ${btts.yes_pct}%` : `No ${btts.no_pct}%`}
      </span>
    </div>
  );
}

function getActualBtts(resolvedMatch) {
  if (resolvedMatch?.home_score == null || resolvedMatch?.away_score == null)
    return null;
  const homeScore = Number(resolvedMatch.home_score);
  const awayScore = Number(resolvedMatch.away_score);
  if (!Number.isFinite(homeScore) || !Number.isFinite(awayScore)) return null;
  return homeScore > 0 && awayScore > 0 ? "Yes" : "No";
}

function getPredictedBtts(btts) {
  if (!btts) return null;
  if (["Yes", "No"].includes(btts.result)) return btts.result;

  const yes = Number(btts.yes);
  const no = Number(btts.no);
  if (Number.isFinite(yes) && Number.isFinite(no))
    return yes >= no ? "Yes" : "No";
  if (Number.isFinite(yes)) return yes >= 0.5 ? "Yes" : "No";
  if (Number.isFinite(no)) return no >= 0.5 ? "No" : "Yes";
  return null;
}

function BttsAccuracyBadge({ btts, resolvedMatch }) {
  const predicted = getPredictedBtts(btts);
  const actual = getActualBtts(resolvedMatch);
  if (!predicted || !actual) return null;

  const correct = predicted === actual;
  return (
    <span
      className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
        correct
          ? "text-brand-greenlight bg-brand-greendark border-brand-green"
          : "text-brand-redlight bg-brand-reddark border-brand-red"
      }`}
    >
      GG {correct ? "✔ Correct" : "✖ Miss"}
    </span>
  );
}

function CornersBadge({ corners }) {
  if (!corners) return null;
  const expected = Number(corners.expected_total);
  const line = Number(corners.line);
  const hasExpected = Number.isFinite(expected);
  const hasLine = Number.isFinite(line);
  if (!hasExpected && !hasLine) return null;

  return (
    <div className="flex items-center gap-1.5">
      <span className="font-display text-xs text-gray-600">CORNERS</span>
      <span className="font-display text-xs px-2 py-0.5 rounded-sm border text-gray-300 bg-brand-darkgray border-brand-midgray">
        {hasExpected ? `Exp ${expected.toFixed(1)}` : "Exp —"}
        {hasLine ? ` · Line ${line.toFixed(1)}` : ""}
      </span>
    </div>
  );
}

function CornerResolutionBadge({ corners, resolvedMatch }) {
  if (!corners || !resolvedMatch) return null;

  const actualCorners =
    Number(resolvedMatch.total_corners) ||
    (Number.isFinite(Number(resolvedMatch.home_corners)) &&
    Number.isFinite(Number(resolvedMatch.away_corners))
      ? Number(resolvedMatch.home_corners) + Number(resolvedMatch.away_corners)
      : null);

  if (!Number.isFinite(actualCorners)) return null;

  let bestLine = null;
  let bestSide = null;
  let bestConfidence = -1;

  Object.entries(corners).forEach(([lineKey, lineData]) => {
    if (!lineKey.startsWith("line_")) return;
    const lineValue = Number(lineKey.replace("line_", "").replace("_", "."));
    if (!Number.isFinite(lineValue)) return;
    const overProb = Number(lineData?.over ?? 0.5);
    const underProb = Number(lineData?.under ?? 0.5);
    const side = overProb >= underProb ? "over" : "under";
    const confidence = Math.max(overProb, underProb);
    if (confidence > bestConfidence) {
      bestConfidence = confidence;
      bestLine = lineValue;
      bestSide = side;
    }
  });

  if (bestLine == null || !bestSide) return null;

  const actualSide = actualCorners > bestLine ? "over" : "under";
  const correct = actualSide === bestSide;

  return (
    <span
      className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
        correct
          ? "text-brand-greenlight bg-brand-greendark border-brand-green"
          : "text-brand-redlight bg-brand-reddark border-brand-red"
      }`}
    >
      {correct ? "✔ Corners Correct" : "✖ Corners Miss"}
    </span>
  );
}

// ─── Market picks strip (Sprint 8) ──────────────────────────────────────────
// Shows the best selection per extended market (1X2, Double Chance, DNB,
// Goals O/U, BTTS, 1st Half, 10-Min, Either Half) so a card reads like a
// board of picks, not just a match-winner guess. Only renders when the
// prediction carries extended_markets.market_picks (computed by the API).
function MarketPicks({ picks }) {
  if (!Array.isArray(picks) || !picks.length) return null;

  return (
    <div className="mt-3 pt-3 border-t border-brand-midgray">
      <p className="label mb-2">MARKET PICKS</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-1.5">
        {picks.map((pick, i) => {
          const pct = Math.round((pick?.probability || 0) * 100);
          const strong = pct >= 60;
          const decent = pct >= 45;
          return (
            <div
              key={`${pick?.market}-${i}`}
              className="bg-brand-darkgray border border-brand-midgray rounded-sm px-2 py-1.5 min-w-0"
              title={`${pick?.market}: ${pick?.selection} (${pct}%)`}
            >
              <p className="font-display text-[10px] tracking-widest text-gray-600 truncate">
                {pick?.market}
              </p>
              <p className="font-display text-xs text-white truncate mt-0.5">
                {pick?.selection}
              </p>
              <p
                className={`font-display text-xs tabular-nums mt-0.5 ${
                  strong
                    ? "text-brand-greenlight"
                    : decent
                      ? "text-yellow-500"
                      : "text-gray-500"
                }`}
              >
                {pct}%
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main card ───────────────────────────────────────────────────────────────

function ResolutionBadge({ prediction, resolvedMatch }) {
  if (!prediction?.match_id) return null;

  if (!resolvedMatch?.actual_outcome) {
    return (
      <span className="font-display text-xs px-2 py-0.5 rounded-sm border border-brand-midgray text-gray-500">
        ➖ Pending
      </span>
    );
  }

  const correct = resolvedMatch.actual_outcome === prediction.predicted_outcome;

  return (
    <span
      className={`font-display text-xs px-2 py-0.5 rounded-sm border ${
        correct
          ? "text-brand-greenlight bg-brand-greendark border-brand-green"
          : "text-brand-redlight bg-brand-reddark border-brand-red"
      }`}
    >
      {correct ? "✔️ Correct" : "❌ Miss"}
    </span>
  );
}

export default function PredictionCard({
  prediction,
  resolvedMatch,
  engineStatusBySport = null,
  onResolveRequest = null,
  resolvingMatchId = null,
}) {
  const [expanded, setExpanded] = useState(false);

  if (!prediction) return null;

  const {
    match_id,
    home_team,
    away_team,
    sport,
    league,
    match_date,
    home_win_probability,
    away_win_probability,
    draw_probability,
    predicted_outcome,
    confidence_score,
    confidence_interval_low,
    confidence_interval_high,
    model_version,
    timestamp,
    data_sources,
    extended_markets,
    is_trained_model,
  } = prediction;

  const normalizedSport = (sport || "").toLowerCase();
  const engineStatusForSport =
    engineStatusBySport && normalizedSport
      ? engineStatusBySport[normalizedSport]
      : null;
  const isEngineActive =
    typeof engineStatusForSport === "boolean"
      ? engineStatusForSport
      : is_trained_model !== false;

  const bttsData = extended_markets?.btts ?? null;
  const normalizedDataSources = (data_sources || [])
    .filter(Boolean)
    .map((src) => {
      if (typeof src === "string") {
        return { title: src, link: src, source: null };
      }
      return {
        title: src.title || src.link || src.source || "Source",
        link: src.link || "",
        source: src.source || null,
      };
    });

  // Which bar is the predicted winner?
  const winnerIs = predicted_outcome; // "home_win" | "away_win" | "draw"

  // Outcome label (short)
  const outcomeLabel =
    predicted_outcome === "home_win"
      ? `${home_team} to Win`
      : predicted_outcome === "away_win"
        ? `${away_team} to Win`
        : "Draw";

  const outcomeColor =
    predicted_outcome === "home_win"
      ? "text-brand-greenlight"
      : predicted_outcome === "away_win"
        ? "text-brand-redlight"
        : "text-yellow-400";

  const cornersData = extended_markets?.corners ?? null;

  const ciLow = Math.round((confidence_interval_low ?? 0) * 100);
  const ciHigh = Math.round((confidence_interval_high ?? 0) * 100);

  const dateLabel =
    match_date || (timestamp && formatWatDate(timestamp)) || "—";

  return (
    <div className="card p-4 animate-slide-up hover:border-gray-600 transition-colors duration-200">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div className="min-w-0 flex-1 basis-52">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            {sport && <span className="tag-gray">{sport.toUpperCase()}</span>}
            {league && (
              <span className="tag-gray truncate max-w-[140px]">{league}</span>
            )}
            <ResolutionBadge
              prediction={prediction}
              resolvedMatch={resolvedMatch}
            />
            <span
              className={`tag-gray ${isEngineActive ? "text-brand-greenlight" : "text-yellow-600"}`}
            >
              {isEngineActive ? "ML ACTIVE" : "PRIOR MODE"}
            </span>
          </div>
          <p className="font-display text-sm text-white leading-snug break-words">
            {home_team}
            <span className="text-gray-600 mx-1.5 text-xs">vs</span>
            {away_team}
          </p>
          <p className="font-display text-xs text-gray-600 mt-0.5">
            {dateLabel}
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="text-right min-w-0">
            <p className={`font-display text-sm font-medium ${outcomeColor} break-words`}>
              {outcomeLabel}
            </p>
            <p className="font-display text-[10px] tracking-widest text-gray-600 mt-0.5">
              CONFIDENCE
            </p>
          </div>
          <ConfidenceGauge value={confidence_score} />
        </div>
      </div>

      {/* Probability split */}
      <div className="my-3">
        <ProbabilityDonut
          home={home_win_probability}
          draw={draw_probability}
          away={away_win_probability}
          winnerIs={winnerIs}
        />
      </div>

      {/* Best pick per extended market (Sprint 8) */}
      <MarketPicks picks={extended_markets?.market_picks} />

      {/* Footer row */}
      <div className="flex items-center justify-between pt-2 border-t border-brand-midgray gap-2 flex-wrap">
        <div className="flex items-center gap-x-3 gap-y-1.5 flex-wrap min-w-0">
          <div>
            <span className="label">CI</span>
            <p className="font-display text-xs text-gray-500 mt-0.5 tabular-nums">
              {ciLow}%–{ciHigh}%
            </p>
          </div>
          <div>
            <span className="label">MODEL</span>
            <p className="font-display text-xs text-gray-500 mt-0.5">
              v{model_version}
            </p>
          </div>
          <BttsBadge btts={bttsData} />
          <BttsAccuracyBadge btts={bttsData} resolvedMatch={resolvedMatch} />
          <CornersBadge corners={cornersData} />
          <CornerResolutionBadge
            corners={cornersData}
            resolvedMatch={resolvedMatch}
          />
        </div>
        <div className="flex items-center gap-2 ml-auto flex-wrap justify-end">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onResolveRequest?.(prediction);
            }}
            disabled={resolvingMatchId === prediction.match_id}
            className="font-display text-xs px-2 py-0.5 rounded-sm border border-brand-green text-brand-greenlight hover:bg-brand-greendark transition-colors shrink-0 disabled:opacity-50"
            title="Trigger result resolution for this prediction"
          >
            {resolvingMatchId === prediction.match_id
              ? "RESOLVING..."
              : "RESOLVE"}
          </button>
          <button
            onClick={() => setExpanded((p) => !p)}
            className="font-display text-xs text-gray-600 hover:text-white transition-colors shrink-0"
          >
            {expanded ? "LESS ↑" : "MORE ↓"}
          </button>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-brand-midgray animate-fade-in space-y-3">
          {/* Match ID */}
          {match_id && (
            <div>
              <p className="label mb-1">MATCH ID</p>
              <p className="font-display text-xs text-gray-600 break-all">
                {match_id}
              </p>
            </div>
          )}

          {resolvedMatch?.actual_outcome && (
            <div>
              <p className="label mb-1">RESOLUTION</p>
              <p className="font-display text-xs text-gray-400">
                Actual outcome:{" "}
                {resolvedMatch.actual_outcome.replace("_", " ").toUpperCase()}
              </p>
              {resolvedMatch.home_score != null &&
                resolvedMatch.away_score != null && (
                  <>
                    <p className="font-display text-xs text-gray-600 mt-1">
                      Final score: {resolvedMatch.home_score} -{" "}
                      {resolvedMatch.away_score}
                    </p>
                    {bttsData && (
                      <p className="font-display text-xs text-gray-600 mt-1">
                        GG actual: {getActualBtts(resolvedMatch) || "—"} ·
                        Predicted: {getPredictedBtts(bttsData) || "—"}
                      </p>
                    )}
                  </>
                )}
            </div>
          )}

          {/* Goals O/U summary */}
          {extended_markets?.goals_over_under && (
            <div>
              <p className="label mb-2">GOALS O/U</p>
              <div className="grid grid-cols-3 gap-1.5">
                {["1_5", "2_5", "3_5"].map((key) => {
                  const market =
                    extended_markets.goals_over_under[`over_${key}`];
                  if (!market) return null;
                  const label = key.replace("_", ".");
                  return (
                    <div
                      key={key}
                      className="bg-brand-darkgray border border-brand-midgray p-2 rounded-sm text-center"
                    >
                      <p className="font-display text-xs text-gray-600">
                        O{label}
                      </p>
                      <p className="font-display text-xs text-white mt-0.5">
                        {Math.round(market.over * 100)}%
                      </p>
                    </div>
                  );
                })}
              </div>
              <p className="font-display text-xs text-gray-600 mt-1.5">
                xG: {extended_markets.goals_over_under.home_xg} –{" "}
                {extended_markets.goals_over_under.away_xg}
                &nbsp;(total {extended_markets.goals_over_under.expected_goals})
              </p>
            </div>
          )}

          {/* Correct score top 3 */}
          {extended_markets?.correct_score?.length > 0 && (
            <div>
              <p className="label mb-2">TOP CORRECT SCORES</p>
              <div className="flex flex-wrap gap-1.5">
                {extended_markets.correct_score.slice(0, 5).map((cs) => (
                  <div
                    key={cs.score}
                    className="bg-brand-darkgray border border-brand-midgray px-2 py-1 rounded-sm"
                  >
                    <span className="font-display text-xs text-white">
                      {cs.score}
                    </span>
                    <span className="font-display text-xs text-gray-600 ml-1.5">
                      {Math.round(cs.probability * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Data sources */}
          {normalizedDataSources.length > 0 && (
            <div>
              <p className="label mb-1">DATA SOURCES</p>
              <div className="flex flex-wrap gap-2">
                {normalizedDataSources.map((src, i) => {
                  const hasLink = Boolean(src.link);
                  const safeLink = hasLink
                    ? src.link.startsWith("http")
                      ? src.link
                      : `https://${src.link}`
                    : null;

                  return (
                    <div
                      key={`${src.title}-${i}`}
                      className="inline-flex items-center gap-1"
                    >
                      {hasLink ? (
                        <a
                          href={safeLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="tag-gray hover:text-brand-red transition-colors"
                          title={src.title}
                        >
                          {src.title}
                        </a>
                      ) : (
                        <span className="tag-gray">{src.title}</span>
                      )}
                      {src.source && (
                        <span className="font-display text-[10px] uppercase tracking-wide text-gray-600 border border-brand-midgray px-1 py-0.5 rounded-sm">
                          Source: {src.source}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
