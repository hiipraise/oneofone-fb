// src/components/ExtendedMarketsPanel.jsx
import React, { useEffect, useState } from "react";

function Prob({ value, label }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  const color =
    pct >= 60
      ? "text-brand-greenlight"
      : pct >= 45
        ? "text-yellow-500"
        : "text-brand-redlight";
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className={`font-display text-lg tabular-nums ${color}`}>
        {pct}%
      </span>
      {label && (
        <span className="font-display text-xs text-gray-600">{label}</span>
      )}
    </div>
  );
}

function OURow({ label, over, under }) {
  if (over == null && under == null) return null;
  const oPct = Math.round((over || 0) * 100);
  const uPct = Math.round((under || 0) * 100);
  const oCol =
    oPct >= 60
      ? "text-brand-greenlight"
      : oPct >= 45
        ? "text-yellow-500"
        : "text-gray-400";
  const uCol =
    uPct >= 60
      ? "text-brand-greenlight"
      : uPct >= 45
        ? "text-yellow-500"
        : "text-gray-400";
  return (
    <tr className="border-b border-brand-midgray hover:bg-brand-gray transition-colors">
      <td className="px-3 py-2 font-display text-xs text-gray-500">{label}</td>
      <td
        className={`px-3 py-2 font-display text-xs text-right tabular-nums ${oCol}`}
      >
        {oPct}%
      </td>
      <td
        className={`px-3 py-2 font-display text-xs text-right tabular-nums ${uCol}`}
      >
        {uPct}%
      </td>
    </tr>
  );
}

function TabBtn({ label, active, onClick, badge }) {
  return (
    <button
      onClick={onClick}
      className={`font-display text-xs px-3 py-1.5 rounded-sm border transition-colors whitespace-nowrap ${
        active
          ? "bg-brand-red border-brand-red text-white"
          : "border-brand-midgray text-gray-500 hover:text-white hover:border-gray-500"
      }`}
    >
      {label}
      {badge && (
        <span className="ml-1.5 font-display text-xs text-gray-600">
          {badge}
        </span>
      )}
    </button>
  );
}

function OUTable({ data, lines, labelFn, title }) {
  return (
    <div>
      {title && <p className="font-body text-xs text-gray-600 mb-3">{title}</p>}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-brand-midgray bg-brand-darkgray">
              <th className="text-left label px-3 py-2">LINE</th>
              <th className="text-right label px-3 py-2">OVER</th>
              <th className="text-right label px-3 py-2">UNDER</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((key) => {
              const m = data[key];
              if (!m) return null;
              return (
                <OURow
                  key={key}
                  label={labelFn(key)}
                  over={m.over}
                  under={m.under}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function ExtendedMarketsPanel({ markets, sport }) {
  const sportL = (sport || "").toLowerCase();

  // Build tab list based on what data is available and what sport we are
  const allTabs = [
    {
      key: "goals",
      label: "GOALS O/U",
      sports: ["soccer"],
      show: !!markets?.goals_over_under,
    },
    {
      key: "btts",
      label: "BOTH TEAMS TO SCORE",
      sports: ["soccer"],
      show: !!markets?.btts,
    },
    {
      key: "correct_score",
      label: "CORRECT SCORE",
      sports: ["soccer"],
      show: !!markets?.correct_score,
    },
    {
      key: "corners",
      label: "CORNERS",
      sports: ["soccer"],
      show: !!markets?.corners,
    },
    {
      key: "bookings",
      label: "BOOKINGS",
      sports: ["soccer"],
      show: !!markets?.bookings,
    },
    {
      key: "asian",
      label: "ASIAN HC",
      sports: ["soccer"],
      show: !!markets?.asian_handicap,
    },
  ];

  const tabs = allTabs.filter((t) => t.show && t.sports.includes(sportL));

  const [tab, setTab] = useState("");

  useEffect(() => {
    if (!tabs.length) return;
    if (!tabs.find((t) => t.key === tab)) {
      setTab(tabs[0].key);
    }
  }, [tab, tabs]);

  if (!markets || !tabs.length) return null;

  return (
    <div className="card p-4">
      <p className="label mb-3">EXTENDED BETTING MARKETS</p>

      {/* Tabs */}
      <div className="flex gap-1 flex-wrap mb-4 overflow-x-auto pb-1">
        {tabs.map((t) => (
          <TabBtn
            key={t.key}
            label={t.label}
            active={tab === t.key}
            onClick={() => setTab(t.key)}
          />
        ))}
      </div>

      {/* ── Soccer tabs ── */}
      {tab === "goals" && markets.goals_over_under && (
        <div>
          <div className="grid grid-cols-1 gap-3 mb-4 sm:grid-cols-3">
            {[
              {
                label: "EXPECTED GOALS",
                val: markets.goals_over_under.expected_goals?.toFixed(2),
                color: "text-white",
              },
              {
                label: "HOME xG",
                val: markets.goals_over_under.home_xg?.toFixed(2),
                color: "text-brand-greenlight",
              },
              {
                label: "AWAY xG",
                val: markets.goals_over_under.away_xg?.toFixed(2),
                color: "text-brand-redlight",
              },
            ].map(({ label, val, color }) => (
              <div key={label}>
                <span className="label">{label}</span>
                <p className={`font-display text-lg mt-0.5 ${color}`}>
                  {val ?? "-"}
                </p>
              </div>
            ))}
          </div>
          <OUTable
            data={markets.goals_over_under}
            lines={["over_0_5", "over_1_5", "over_2_5", "over_3_5", "over_4_5"]}
            labelFn={(k) => `${k.replace("over_", "").replace("_", ".")} Goals`}
          />
        </div>
      )}

      {tab === "btts" && markets.btts && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {[
            { label: "GG (BOTH SCORE)", val: markets.btts.yes },
            { label: "NG (NO GOAL)", val: markets.btts.no },
          ].map(({ label, val }) => (
            <div
              key={label}
              className="flex flex-col items-center gap-2 p-6 bg-brand-darkgray border border-brand-midgray rounded-sm"
            >
              <span className="label">{label}</span>
              <Prob value={val} />
            </div>
          ))}
        </div>
      )}

      {tab === "correct_score" && markets.correct_score && (
        <div>
          <p className="font-body text-xs text-gray-600 mb-3">
            Top 10 scores by Poisson probability
          </p>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {markets.correct_score.slice(0, 10).map((cs, i) => (
              <div
                key={cs.score}
                className={`border p-2 rounded-sm text-center ${
                  i === 0
                    ? "border-brand-red bg-brand-reddark"
                    : "border-brand-midgray bg-brand-darkgray"
                }`}
              >
                <p
                  className={`font-display text-sm ${i === 0 ? "text-white" : "text-gray-300"}`}
                >
                  {cs.score}
                </p>
                <p
                  className={`font-display text-xs mt-0.5 ${i === 0 ? "text-brand-redlight" : "text-gray-600"}`}
                >
                  {Math.round(cs.probability * 100)}%
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "corners" && markets.corners && (
        <div>
          <div className="grid grid-cols-1 gap-3 mb-4 sm:grid-cols-3">
            <div>
              <span className="label">EXPECTED</span>
              <p className="font-display text-lg text-white mt-0.5">
                {markets.corners.expected_total ?? "-"}
              </p>
            </div>
          </div>
          <OUTable
            data={markets.corners}
            lines={[
              "line_7_5",
              "line_8_5",
              "line_9_5",
              "line_10_5",
              "line_11_5",
              "line_12_5",
            ]}
            labelFn={(k) =>
              `${k.replace("line_", "").replace("_", ".")} Corners`
            }
          />
        </div>
      )}

      {tab === "bookings" && markets.bookings && (
        <div>
          <div className="mb-4">
            <span className="label">EXPECTED CARDS</span>
            <p className="font-display text-lg text-white mt-0.5">
              {markets.bookings.expected_total_cards ?? "-"}
            </p>
          </div>
          <OUTable
            data={markets.bookings}
            lines={["line_2_5", "line_3_5", "line_4_5", "line_5_5"]}
            labelFn={(k) => `${k.replace("line_", "").replace("_", ".")} Cards`}
          />
        </div>
      )}

      {tab === "asian" && markets.asian_handicap && (
        <div>
          <p className="font-body text-xs text-gray-600 mb-3">
            Asian handicap from home team perspective
          </p>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-brand-midgray bg-brand-darkgray">
                  <th className="text-left label px-3 py-2">HANDICAP</th>
                  <th className="text-right label px-3 py-2">HOME COVER</th>
                  <th className="text-right label px-3 py-2">AWAY COVER</th>
                  <th className="text-right label px-3 py-2">PUSH</th>
                </tr>
              </thead>
              <tbody>
                {markets.asian_handicap.map((ah, i) => {
                  const hPct = Math.round(ah.home_cover_probability * 100);
                  const aPct = Math.round(ah.away_cover_probability * 100);
                  return (
                    <tr
                      key={i}
                      className="border-b border-brand-midgray hover:bg-brand-gray transition-colors"
                    >
                      <td className="px-3 py-2 font-display text-xs text-gray-400">
                        {ah.handicap > 0 ? `+${ah.handicap}` : ah.handicap}
                      </td>
                      <td
                        className={`px-3 py-2 font-display text-xs text-right tabular-nums ${hPct >= 55 ? "text-brand-greenlight" : "text-gray-400"}`}
                      >
                        {hPct}%
                      </td>
                      <td
                        className={`px-3 py-2 font-display text-xs text-right tabular-nums ${aPct >= 55 ? "text-brand-greenlight" : "text-gray-400"}`}
                      >
                        {aPct}%
                      </td>
                      <td className="px-3 py-2 font-display text-xs text-right text-gray-600 tabular-nums">
                        {Math.round(ah.push_probability * 100)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
