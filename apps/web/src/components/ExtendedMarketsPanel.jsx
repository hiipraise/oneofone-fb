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

// Compact over/under split bar (Sprint 2) — visual indicator per market row.
function MiniSplitBar({ over, under }) {
  const oPct = Math.round((over || 0) * 100);
  const uPct = Math.round((under || 0) * 100);
  const total = oPct + uPct || 1;
  const oShare = Math.round((oPct / total) * 100);
  return (
    <div
      className="flex h-1.5 w-20 rounded-full overflow-hidden bg-brand-darkgray"
      title={`Over ${oPct}% / Under ${uPct}%`}
    >
      <div className="h-full bg-brand-green" style={{ width: `${oShare}%` }} />
      <div
        className="h-full bg-brand-red"
        style={{ width: `${100 - oShare}%` }}
      />
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
      <td className="px-3 py-2">
        <MiniSplitBar over={over} under={under} />
      </td>
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
              <th className="text-left label px-3 py-2">SPLIT</th>
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
  const correctScores =
    markets?.correct_score?.top_10 || markets?.correct_score || [];

  // Build tab list based on what data is available and what sport we are
  const allTabs = [
    {
      key: "summary",
      label: "SUMMARY",
      sports: ["soccer"],
      show: !!markets?.market_picks?.length,
    },
    {
      key: "result",
      label: "RESULTS",
      sports: ["soccer"],
      show:
        !!markets?.one_x_two ||
        !!markets?.double_chance ||
        !!markets?.draw_no_bet,
    },
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
      key: "first_half",
      label: "1ST HALF",
      sports: ["soccer"],
      show:
        !!markets?.first_half_one_x_two ||
        !!markets?.first_half_btts ||
        !!markets?.first_half_goals_over_under,
    },
    {
      key: "ten_minute",
      label: "10 MIN",
      sports: ["soccer"],
      show:
        !!markets?.ten_minute_one_x_two ||
        !!markets?.ten_minute_goals_over_under,
    },
    {
      key: "team_totals",
      label: "TEAM TOTALS",
      sports: ["soccer"],
      show: !!markets?.team_goals_over_under,
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
      key: "team_corners",
      label: "TEAM CORNERS",
      sports: ["soccer"],
      show: !!markets?.team_corners_over_under,
    },
    {
      key: "bookings",
      label: "BOOKINGS",
      sports: ["soccer"],
      show: !!markets?.bookings,
    },
    {
      key: "combo",
      label: "COMBOS",
      sports: ["soccer"],
      show: !!markets?.combo_markets,
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
      {tab === "summary" && markets.market_picks && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {markets.market_picks.map((pick) => (
            <div
              key={`${pick.market}-${pick.selection}`}
              className="border border-brand-midgray bg-brand-darkgray rounded-sm p-4"
            >
              <p className="label mb-2">{pick.market}</p>
              <p className="font-display text-lg text-white">
                {pick.selection}
              </p>
              <p className="font-display text-xs mt-1 text-brand-greenlight tabular-nums">
                {Math.round((pick.probability || 0) * 100)}%
              </p>
              <div className="mt-2 h-1 bg-brand-darkgray rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-green rounded-full"
                  style={{
                    width: `${Math.min(Math.round((pick.probability || 0) * 100), 100)}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "result" &&
        (markets.one_x_two || markets.double_chance || markets.draw_no_bet) && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            {markets.one_x_two && (
              <div className="border border-brand-midgray bg-brand-darkgray rounded-sm p-4">
                <p className="label mb-3">1X2</p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    ["HOME", markets.one_x_two.home],
                    ["DRAW", markets.one_x_two.draw],
                    ["AWAY", markets.one_x_two.away],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span className="label text-[10px]">{label}</span>
                      <Prob value={value} />
                    </div>
                  ))}
                </div>
                <p className="font-body text-xs text-gray-600 mt-3">
                  Pick: {markets.one_x_two.pick?.selection || "-"}
                </p>
              </div>
            )}
            {markets.double_chance && (
              <div className="border border-brand-midgray bg-brand-darkgray rounded-sm p-4">
                <p className="label mb-3">DOUBLE CHANCE</p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    ["1X", markets.double_chance.home_or_draw],
                    ["12", markets.double_chance.home_or_away],
                    ["X2", markets.double_chance.draw_or_away],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span className="label text-[10px]">{label}</span>
                      <Prob value={value} />
                    </div>
                  ))}
                </div>
                <p className="font-body text-xs text-gray-600 mt-3">
                  Pick: {markets.double_chance.pick?.selection || "-"}
                </p>
              </div>
            )}
            {markets.draw_no_bet && (
              <div className="border border-brand-midgray bg-brand-darkgray rounded-sm p-4">
                <p className="label mb-3">DRAW NO BET</p>
                <div className="grid grid-cols-2 gap-2 text-center">
                  {[
                    ["HOME", markets.draw_no_bet.home],
                    ["AWAY", markets.draw_no_bet.away],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span className="label text-[10px]">{label}</span>
                      <Prob value={value} />
                    </div>
                  ))}
                </div>
                <p className="font-body text-xs text-gray-600 mt-3">
                  Pick: {markets.draw_no_bet.pick?.selection || "-"}
                </p>
              </div>
            )}
          </div>
        )}

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
          <p className="font-body text-xs text-gray-600 mb-3">
            Pick: {markets.goals_over_under.pick?.selection || "-"}
          </p>
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

      {tab === "first_half" &&
        (markets.first_half_one_x_two ||
          markets.first_half_btts ||
          markets.first_half_goals_over_under) && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            {markets.first_half_one_x_two && (
              <div className="border border-brand-midgray bg-brand-darkgray rounded-sm p-4">
                <p className="label mb-3">1ST HALF 1X2</p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    ["HOME", markets.first_half_one_x_two.home],
                    ["DRAW", markets.first_half_one_x_two.draw],
                    ["AWAY", markets.first_half_one_x_two.away],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span className="label text-[10px]">{label}</span>
                      <Prob value={value} />
                    </div>
                  ))}
                </div>
                <p className="font-body text-xs text-gray-600 mt-3">
                  Pick: {markets.first_half_one_x_two.pick?.selection || "-"}
                </p>
              </div>
            )}
            {markets.first_half_btts && (
              <div className="border border-brand-midgray bg-brand-darkgray rounded-sm p-4">
                <p className="label mb-3">1ST HALF BTTS</p>
                <div className="grid grid-cols-2 gap-2 text-center">
                  {[
                    ["GG", markets.first_half_btts.yes],
                    ["NG", markets.first_half_btts.no],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span className="label text-[10px]">{label}</span>
                      <Prob value={value} />
                    </div>
                  ))}
                </div>
              </div>
            )}
            {markets.first_half_goals_over_under && (
              <div>
                <p className="font-body text-xs text-gray-600 mb-3">
                  First-half scoring lines
                </p>
                <OUTable
                  data={markets.first_half_goals_over_under}
                  lines={[
                    "over_0_5",
                    "over_1_5",
                    "over_2_5",
                    "over_3_5",
                    "over_4_5",
                  ]}
                  labelFn={(k) =>
                    `${k.replace("over_", "").replace("_", ".")} Goals`
                  }
                />
              </div>
            )}
          </div>
        )}

      {tab === "ten_minute" &&
        (markets.ten_minute_one_x_two ||
          markets.ten_minute_goals_over_under) && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {markets.ten_minute_one_x_two && (
              <div className="border border-brand-midgray bg-brand-darkgray rounded-sm p-4">
                <p className="label mb-3">10 MINUTE 1X2</p>
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    ["HOME", markets.ten_minute_one_x_two.home],
                    ["DRAW", markets.ten_minute_one_x_two.draw],
                    ["AWAY", markets.ten_minute_one_x_two.away],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span className="label text-[10px]">{label}</span>
                      <Prob value={value} />
                    </div>
                  ))}
                </div>
                <p className="font-body text-xs text-gray-600 mt-3">
                  Pick: {markets.ten_minute_one_x_two.pick?.selection || "-"}
                </p>
              </div>
            )}
            {markets.ten_minute_goals_over_under && (
              <div>
                <p className="font-body text-xs text-gray-600 mb-3">
                  10-minute scoring lines
                </p>
                <OUTable
                  data={markets.ten_minute_goals_over_under}
                  lines={[
                    "over_0_5",
                    "over_1_5",
                    "over_2_5",
                    "over_3_5",
                    "over_4_5",
                  ]}
                  labelFn={(k) =>
                    `${k.replace("over_", "").replace("_", ".")} Goals`
                  }
                />
              </div>
            )}
          </div>
        )}

      {tab === "team_totals" && markets.team_goals_over_under && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {[
            ["HOME TEAM", markets.team_goals_over_under.home],
            ["AWAY TEAM", markets.team_goals_over_under.away],
          ].map(([title, data]) => (
            <div key={title}>
              <p className="label mb-3">{title}</p>
              <OUTable
                data={data}
                lines={["over_0_5", "over_1_5", "over_2_5"]}
                labelFn={(k) =>
                  `${k.replace("over_", "").replace("_", ".")} Goals`
                }
              />
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
            {correctScores.slice(0, 10).map((cs, i) => (
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

      {tab === "team_corners" && markets.team_corners_over_under && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {[
            ["HOME TEAM", markets.team_corners_over_under.home],
            ["AWAY TEAM", markets.team_corners_over_under.away],
          ].map(([title, data]) => (
            <div key={title}>
              <p className="label mb-3">{title}</p>
              <OUTable
                data={data}
                lines={[
                  "over_3_5",
                  "over_4_5",
                  "over_5_5",
                  "over_6_5",
                  "over_7_5",
                ]}
                labelFn={(k) =>
                  `${k.replace("over_", "").replace("_", ".")} Corners`
                }
              />
            </div>
          ))}
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

      {tab === "combo" && markets.combo_markets && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            { label: "HOME OR GG", val: markets.combo_markets.home_or_gg },
            { label: "DRAW OR GG", val: markets.combo_markets.draw_or_gg },
            { label: "AWAY OR GG", val: markets.combo_markets.away_or_gg },
          ].map(({ label, val }) => (
            <div
              key={label}
              className="flex flex-col items-center gap-2 p-6 bg-brand-darkgray border border-brand-midgray rounded-sm"
            >
              <span className="label text-center">{label}</span>
              <Prob value={val} />
            </div>
          ))}
          <div className="sm:col-span-3">
            <p className="font-body text-xs text-gray-600">
              Pick: {markets.combo_markets.pick?.selection || "-"}
            </p>
          </div>
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
