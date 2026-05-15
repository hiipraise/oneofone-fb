import React, { useEffect, useMemo, useState } from "react";
import {
  useMetricsSummary,
  usePredictions,
  useResults,
} from "../hooks/useData";

const STORAGE_KEY = "platform-report-task-status-v1";

const DEFAULT_REPORT_THRESHOLDS = {
  accuracy_good: 0.58,
  accuracy_needs: 0.55,
  brier_good: 0.42,
  brier_needs: 0.5,
  resolution_good: 0.5,
  low_confidence: 0.55,
};

function getNumeric(value, fallback = null) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}


function getActualBtts(result) {
  if (result?.home_score == null || result?.away_score == null) return null;
  const homeScore = Number(result.home_score);
  const awayScore = Number(result.away_score);
  if (!Number.isFinite(homeScore) || !Number.isFinite(awayScore)) return null;
  return homeScore > 0 && awayScore > 0 ? "Yes" : "No";
}

function getPredictedBtts(prediction) {
  const btts = prediction?.extended_markets?.btts;
  if (!btts) return null;
  if (["Yes", "No"].includes(btts.result)) return btts.result;

  const yes = Number(btts.yes);
  const no = Number(btts.no);
  if (Number.isFinite(yes) && Number.isFinite(no)) return yes >= no ? "Yes" : "No";
  if (Number.isFinite(yes)) return yes >= 0.5 ? "Yes" : "No";
  if (Number.isFinite(no)) return no >= 0.5 ? "No" : "Yes";
  return null;
}

function emptyMarketAccuracy(label = "GG (Both Teams to Score)", positiveLabel = "Yes", negativeLabel = "No") {
  return {
    label,
    total: 0,
    correct: 0,
    miss: 0,
    accuracy: null,
    [`predicted_${positiveLabel.toLowerCase()}`]: 0,
    [`predicted_${negativeLabel.toLowerCase()}`]: 0,
    [`actual_${positiveLabel.toLowerCase()}`]: 0,
    [`actual_${negativeLabel.toLowerCase()}`]: 0,
    by_prediction: {
      [positiveLabel]: { total: 0, correct: 0, miss: 0, accuracy: null },
      [negativeLabel]: { total: 0, correct: 0, miss: 0, accuracy: null },
    },
    recent: [],
  };
}

function finalizeMarketAccuracy(stats, positiveLabel = "Yes", negativeLabel = "No") {
  const labels = Object.keys(stats?.by_prediction || {}).length
    ? Object.keys(stats.by_prediction)
    : [positiveLabel, negativeLabel];
  const base = emptyMarketAccuracy(stats?.label, labels[0], labels[1]);
  const finalized = {
    ...base,
    ...stats,
    by_prediction: labels.reduce((acc, label) => {
      acc[label] = { ...(base.by_prediction[label] || {}), ...(stats?.by_prediction?.[label] || {}) };
      return acc;
    }, {}),
  };

  if (finalized.total > 0) {
    finalized.accuracy = finalized.correct / finalized.total;
  }

  for (const bucket of Object.values(finalized.by_prediction)) {
    if (bucket.total > 0) bucket.accuracy = bucket.correct / bucket.total;
  }

  finalized.recent = (finalized.recent || []).slice(0, 8);
  return finalized;
}

function buildGgAccuracy(predictions, results) {
  const resultByMatchId = results.reduce((map, result) => {
    if (result?.match_id) map[result.match_id] = result;
    return map;
  }, {});
  const stats = emptyMarketAccuracy();

  for (const prediction of predictions) {
    const result = resultByMatchId[prediction?.match_id];
    const predicted = getPredictedBtts(prediction);
    const actual = getActualBtts(result);
    if (!predicted || !actual) continue;

    const correct = predicted === actual;
    stats.total += 1;
    stats[predicted === "Yes" ? "predicted_yes" : "predicted_no"] += 1;
    stats[actual === "Yes" ? "actual_yes" : "actual_no"] += 1;
    stats.by_prediction[predicted].total += 1;

    if (correct) {
      stats.correct += 1;
      stats.by_prediction[predicted].correct += 1;
    } else {
      stats.miss += 1;
      stats.by_prediction[predicted].miss += 1;
    }

    stats.recent.push({
      matchId: prediction.match_id,
      label: `${prediction.home_team || "Home"} vs ${prediction.away_team || "Away"}`,
      predicted,
      actual,
      correct,
    });
  }

  return finalizeMarketAccuracy(stats);
}

function getPredictedCorners(prediction) {
  const corners = prediction?.extended_markets?.corners;
  if (!corners) return null;
  const line = Number.isFinite(Number(corners.line)) ? Number(corners.line) : 9.5;
  if (["Over", "Under"].includes(corners.result)) return { side: corners.result, line };
  const market = corners[`line_${String(line).replace(".", "_")}`] || corners.line_9_5;
  const over = Number(market?.over);
  const under = Number(market?.under);
  if (Number.isFinite(over) && Number.isFinite(under)) return { side: over >= under ? "Over" : "Under", line };
  const expected = Number(corners.expected_total);
  if (Number.isFinite(expected)) return { side: expected > line ? "Over" : "Under", line };
  return null;
}

function getActualCorners(result, line) {
  const actual = Number(result?.actual_corner_total ?? result?.corner_total);
  if (!Number.isFinite(actual)) return null;
  return actual > line ? "Over" : "Under";
}

function buildCornerAccuracy(predictions, results) {
  const resultByMatchId = results.reduce((map, result) => {
    if (result?.match_id) map[result.match_id] = result;
    return map;
  }, {});
  const stats = emptyMarketAccuracy("Corners O/U", "Over", "Under");

  for (const prediction of predictions) {
    const result = resultByMatchId[prediction?.match_id];
    const predicted = getPredictedCorners(prediction);
    if (!predicted) continue;
    const actual = getActualCorners(result, predicted.line);
    if (!actual) continue;

    const correct = predicted.side === actual;
    stats.total += 1;
    stats[`predicted_${predicted.side.toLowerCase()}`] += 1;
    stats[`actual_${actual.toLowerCase()}`] += 1;
    stats.by_prediction[predicted.side].total += 1;

    if (correct) {
      stats.correct += 1;
      stats.by_prediction[predicted.side].correct += 1;
    } else {
      stats.miss += 1;
      stats.by_prediction[predicted.side].miss += 1;
    }

    stats.recent.push({
      matchId: prediction.match_id,
      label: `${prediction.home_team || "Home"} vs ${prediction.away_team || "Away"}`,
      predicted: `${predicted.side} ${predicted.line}`,
      actual: `${actual} ${predicted.line} (${result.actual_corner_total ?? result.corner_total} corners)`,
      correct,
    });
  }

  return finalizeMarketAccuracy(stats, "Over", "Under");
}

function formatPct(value, digits = 1) {
  return value == null ? "N/A" : `${(Number(value) * 100).toFixed(digits)}%`;
}

function StatTile({ label, value, tone = "text-white" }) {
  return (
    <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3">
      <p className="font-display text-[10px] text-gray-600">{label}</p>
      <p className={`font-display text-lg mt-1 ${tone}`}>{value}</p>
    </div>
  );
}

function AccuracyBar({ label, total, correct, accuracy }) {
  const pct = Math.round((accuracy ?? 0) * 100);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="font-display text-xs text-gray-400">{label}</span>
        <span className="font-display text-xs text-gray-600 tabular-nums">
          {total ? `${correct}/${total} · ${pct}%` : "No data"}
        </span>
      </div>
      <div className="h-2 bg-brand-darkgray rounded-full overflow-hidden border border-brand-midgray">
        <div
          className="h-full bg-brand-green rounded-full transition-all duration-700"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function MarketAccuracyDashboard({ marketAccuracy, title, description, sampleLabel, positiveLabel, negativeLabel }) {
  const positiveBucket = marketAccuracy.by_prediction?.[positiveLabel] || {};
  const negativeBucket = marketAccuracy.by_prediction?.[negativeLabel] || {};
  const correctPct = marketAccuracy.total ? (marketAccuracy.correct / marketAccuracy.total) * 100 : 0;
  const missPct = marketAccuracy.total ? (marketAccuracy.miss / marketAccuracy.total) * 100 : 0;

  return (
    <section className="card p-5 mb-4">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-2 mb-4">
        <div>
          <p className="label mb-2">MARKET ACCURACY BY TYPE</p>
          <h2 className="font-display text-lg text-white tracking-wide">{title}</h2>
          <p className="font-body text-xs text-gray-600 mt-1">{description}</p>
        </div>
        <span className="font-display text-xs text-gray-600">
          Resolved {sampleLabel} samples: {marketAccuracy.total}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-5">
        <StatTile label={`${sampleLabel.toUpperCase()} ACCURACY`} value={formatPct(marketAccuracy.accuracy)} tone="text-brand-greenlight" />
        <StatTile label="CORRECT" value={marketAccuracy.correct} tone="text-brand-greenlight" />
        <StatTile label="MISSES" value={marketAccuracy.miss} tone="text-brand-redlight" />
        <StatTile label={`ACTUAL ${positiveLabel.toUpperCase()}`} value={marketAccuracy[`actual_${positiveLabel.toLowerCase()}`] || 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="space-y-4">
          <AccuracyBar
            label={`Predicted ${sampleLabel} ${positiveLabel}`}
            total={positiveBucket.total || 0}
            correct={positiveBucket.correct || 0}
            accuracy={positiveBucket.accuracy}
          />
          <AccuracyBar
            label={`Predicted ${sampleLabel} ${negativeLabel}`}
            total={negativeBucket.total || 0}
            correct={negativeBucket.correct || 0}
            accuracy={negativeBucket.accuracy}
          />

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="font-display text-xs text-gray-400">Correct vs Miss Breakdown</span>
              <span className="font-display text-xs text-gray-600 tabular-nums">
                {Math.round(correctPct)}% / {Math.round(missPct)}%
              </span>
            </div>
            <div className="flex h-3 bg-brand-darkgray rounded-full overflow-hidden border border-brand-midgray">
              <div className="bg-brand-green" style={{ width: `${correctPct}%` }} />
              <div className="bg-brand-red" style={{ width: `${missPct}%` }} />
            </div>
          </div>
        </div>

        <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3">
          <p className="label mb-2">RECENT {sampleLabel.toUpperCase()} RESOLUTIONS</p>
          <div className="space-y-2">
            {marketAccuracy.recent?.length ? (
              marketAccuracy.recent.map((item) => (
                <div key={item.matchId} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-display text-xs text-white truncate">{item.label}</p>
                    <p className="font-display text-[10px] text-gray-600">
                      Pred {item.predicted} · Actual {item.actual}
                    </p>
                  </div>
                  <span className={`font-display text-[10px] px-2 py-0.5 rounded-sm border shrink-0 ${
                    item.correct
                      ? "text-brand-greenlight bg-brand-greendark border-brand-green"
                      : "text-brand-redlight bg-brand-reddark border-brand-red"
                  }`}>
                    {item.correct ? "CORRECT" : "MISS"}
                  </span>
                </div>
              ))
            ) : (
              <p className="font-body text-xs text-gray-600">
                No resolved {sampleLabel} samples yet. Submit final scores and corner totals to activate this accuracy report.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function buildReport(summary, predictions, results) {
  const thresholds = summary?.report_thresholds || DEFAULT_REPORT_THRESHOLDS;
  const accuracy = getNumeric(
    summary?.performance_metrics_all_sports?.accuracy,
  );
  const brier = getNumeric(
    summary?.performance_metrics_all_sports?.brier_score,
  );
  const totalPredictions = getNumeric(summary?.total_predictions, 0);
  const scoredResolved = getNumeric(
    summary?.total_resolved_scored,
    getNumeric(summary?.total_resolved, 0),
  );
  const rawResolved = getNumeric(summary?.total_resolved_raw, 0);
  const summaryGgAccuracy = summary?.market_accuracy_by_type?.gg || null;
  const localGgAccuracy = buildGgAccuracy(predictions, results);
  const ggAccuracy = summaryGgAccuracy
    ? finalizeMarketAccuracy({
        ...emptyMarketAccuracy(summaryGgAccuracy.label),
        ...summaryGgAccuracy,
        recent: localGgAccuracy.recent,
      })
    : localGgAccuracy;
  const summaryCornerAccuracy = summary?.market_accuracy_by_type?.corners || null;
  const localCornerAccuracy = buildCornerAccuracy(predictions, results);
  const cornerAccuracy = summaryCornerAccuracy
    ? finalizeMarketAccuracy({
        ...emptyMarketAccuracy(summaryCornerAccuracy.label, "Over", "Under"),
        ...summaryCornerAccuracy,
        recent: localCornerAccuracy.recent,
      }, "Over", "Under")
    : localCornerAccuracy;

  const highConfidence = predictions.filter(
    (p) => (p?.confidence_score ?? 0) >= 0.75,
  ).length;
  const lowConfidence = predictions.filter(
    (p) => (p?.confidence_score ?? 0) < thresholds.low_confidence,
  ).length;
  const resolutionRate =
    totalPredictions > 0 ? scoredResolved / totalPredictions : 0;

  const working = [];
  if (accuracy !== null && accuracy >= thresholds.accuracy_good) {
    working.push(
      `Model accuracy is ${(accuracy * 100).toFixed(1)}%, indicating healthy baseline decision quality.`,
    );
  }
  if (brier !== null && brier <= thresholds.brier_good) {
    working.push(
      `Calibration quality is acceptable (Brier ${brier.toFixed(4)}).`,
    );
  }
  if (highConfidence > 0) {
    working.push(
      `${highConfidence} recent predictions were made with high confidence (≥ 75%).`,
    );
  }
  if (ggAccuracy.total > 0 && ggAccuracy.accuracy >= thresholds.accuracy_good) {
    working.push(
      `GG market accuracy is ${formatPct(ggAccuracy.accuracy)}, showing strong Both Teams to Score tracking.`,
    );
  }
  if (cornerAccuracy.total > 0 && cornerAccuracy.accuracy >= thresholds.accuracy_good) {
    working.push(
      `Corner market accuracy is ${formatPct(cornerAccuracy.accuracy)}, showing strong corner O/U tracking.`,
    );
  }

  const needsImprovement = [];
  if (accuracy === null || accuracy < thresholds.accuracy_needs) {
    needsImprovement.push(
      "Accuracy is below target and should be improved with more validated training examples.",
    );
  }
  if (brier === null || brier > thresholds.brier_needs) {
    needsImprovement.push(
      "Probability calibration appears weak; confidence likely needs recalibration.",
    );
  }
  if (resolutionRate < thresholds.resolution_good) {
    needsImprovement.push(
      `Only ${(resolutionRate * 100).toFixed(1)}% of predictions are scored in metrics; result submission coverage is low.`,
    );
  }
  if (lowConfidence > highConfidence) {
    needsImprovement.push(
      "Low-confidence predictions are dominating recent output.",
    );
  }
  if (ggAccuracy.total === 0) {
    needsImprovement.push(
      "GG accuracy has no resolved samples yet; submit final scores to track Both Teams to Score performance.",
    );
  } else if (ggAccuracy.accuracy < thresholds.accuracy_needs) {
    needsImprovement.push(
      `GG market accuracy is ${formatPct(ggAccuracy.accuracy)}, below the target for Both Teams to Score picks.`,
    );
  }
  if (cornerAccuracy.total === 0) {
    needsImprovement.push(
      "Corner accuracy has no resolved samples yet; submit final corner totals to track corner O/U performance.",
    );
  } else if (cornerAccuracy.accuracy < thresholds.accuracy_needs) {
    needsImprovement.push(
      `Corner market accuracy is ${formatPct(cornerAccuracy.accuracy)}, below the target for corner O/U picks.`,
    );
  }

  const suggestions = [
    "Automate post-match result ingestion to increase resolved + scored volume.",
    "Prioritize per-sport model retraining when sample counts cross activation thresholds.",
    "Add a weekly calibration review to compare confidence buckets vs actual win rates.",
    "Review GG Yes/No misses separately to improve Both Teams to Score market calibration.",
    "Review corner Over/Under misses separately to improve corner market calibration.",
  ];

  const generatedTasks = [
    {
      id: "task-improve-resolution",
      title: "Increase scored resolution coverage to 70%",
      detail: `Current scored coverage: ${(resolutionRate * 100).toFixed(1)}% (${scoredResolved}/${totalPredictions || 0}).`,
    },
    {
      id: "task-calibration-audit",
      title: "Run calibration audit on latest 100 predictions",
      detail:
        brier !== null
          ? `Latest Brier score is ${brier.toFixed(4)}.`
          : "Brier score unavailable; investigate metrics collection.",
    },
    {
      id: "task-data-quality",
      title: "Review unresolved submitted results",
      detail: `${rawResolved} results submitted, ${scoredResolved} currently scored in model metrics.`,
    },
    {
      id: "task-gg-market-review",
      title: "Review GG market misses",
      detail: ggAccuracy.total
        ? `GG accuracy is ${formatPct(ggAccuracy.accuracy)} across ${ggAccuracy.total} resolved samples (${ggAccuracy.miss} misses).`
        : "No GG samples are resolved yet; add final scores for BTTS tracking.",
    },
    {
      id: "task-corner-market-review",
      title: "Review corner market misses",
      detail: cornerAccuracy.total
        ? `Corner accuracy is ${formatPct(cornerAccuracy.accuracy)} across ${cornerAccuracy.total} resolved samples (${cornerAccuracy.miss} misses).`
        : "No corner samples are resolved yet; add final corner totals for O/U tracking.",
    },
  ];

  return {
    overview: `This AI report analyzes platform performance using live model metrics and recent platform activity. It highlights what is working, where to improve, and the next actions for your team.`,
    working,
    needsImprovement,
    suggestions,
    generatedTasks,
    generatedAt: new Date().toISOString(),
    facts: {
      totalPredictions,
      scoredResolved,
      rawResolved,
      accuracy,
      brier,
      ggAccuracy,
      cornerAccuracy,
      resultsCount: results.length,
      predictionsCount: predictions.length,
    },
  };
}

export default function ReportsPage() {
  const { data: summary, loading: summaryLoading } = useMetricsSummary();
  const { data: predictions, loading: predictionsLoading } = usePredictions(
    null,
    100,
  );
  const { data: results, loading: resultsLoading } = useResults(100);

  const report = useMemo(
    () => buildReport(summary, predictions, results),
    [summary, predictions, results],
  );

  const [taskStatus, setTaskStatus] = useState({});

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") setTaskStatus(parsed);
    } catch {
      setTaskStatus({});
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(taskStatus));
  }, [taskStatus]);

  const toggleTask = (taskId) => {
    setTaskStatus((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  const loading = summaryLoading || predictionsLoading || resultsLoading;

  return (
    <div className="max-w-full animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6 gap-2">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">
            AI PLATFORM REPORT
          </h1>
          <p className="font-body text-xs text-gray-600 mt-1">
            Auto-generated analysis of what is working, what needs improvement,
            and recommended tasks.
          </p>
        </div>
        <span className="font-display text-xs text-gray-600">
          Generated: {new Date(report.generatedAt).toLocaleString()}
        </span>
      </div>

      {loading ? (
        <div className="card p-6 animate-pulse">
          <div className="h-4 w-56 bg-brand-midgray rounded mb-3" />
          <div className="h-3 w-full bg-brand-midgray rounded mb-2" />
          <div className="h-3 w-5/6 bg-brand-midgray rounded" />
        </div>
      ) : (
        <>
          <section className="card p-5 mb-4">
            <p className="label mb-2">PLATFORM OVERVIEW</p>
            <p className="font-body text-sm text-gray-300 leading-6">
              {report.overview}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mt-4">
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">
                  PREDICTIONS
                </p>
                <p className="font-display text-sm text-white">
                  {report.facts.totalPredictions}
                </p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">SCORED</p>
                <p className="font-display text-sm text-white">
                  {report.facts.scoredResolved}
                </p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">
                  SUBMITTED RESULTS
                </p>
                <p className="font-display text-sm text-white">
                  {report.facts.rawResolved}
                </p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">
                  ACCURACY
                </p>
                <p className="font-display text-sm text-white">
                  {report.facts.accuracy != null
                    ? `${(report.facts.accuracy * 100).toFixed(1)}%`
                    : "N/A"}
                </p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">BRIER</p>
                <p className="font-display text-sm text-white">
                  {report.facts.brier != null
                    ? report.facts.brier.toFixed(4)
                    : "N/A"}
                </p>
              </div>
              <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-2">
                <p className="font-display text-[10px] text-gray-600">
                  LIVE WINDOW
                </p>
                <p className="font-display text-sm text-white">
                  {report.facts.predictionsCount} preds
                </p>
              </div>
            </div>
          </section>

          <MarketAccuracyDashboard
            marketAccuracy={report.facts.ggAccuracy}
            title="GG (BOTH TEAMS TO SCORE)"
            description="Compares GG Yes/No predictions against final scores where both home and away scores are available."
            sampleLabel="GG"
            positiveLabel="Yes"
            negativeLabel="No"
          />
          <MarketAccuracyDashboard
            marketAccuracy={report.facts.cornerAccuracy}
            title="CORNERS OVER/UNDER"
            description="Compares the primary corner O/U prediction against submitted final corner totals."
            sampleLabel="Corners"
            positiveLabel="Over"
            negativeLabel="Under"
          />

          <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <div className="card p-5">
              <p className="label mb-3">WHAT IS WORKING</p>
              <ul className="space-y-2">
                {report.working.length ? (
                  report.working.map((item, idx) => (
                    <li key={idx} className="font-body text-sm text-gray-300">
                      ✅ {item}
                    </li>
                  ))
                ) : (
                  <li className="font-body text-sm text-gray-500">
                    No strong positives detected yet.
                  </li>
                )}
              </ul>
            </div>

            <div className="card p-5">
              <p className="label mb-3">NEEDS IMPROVEMENT</p>
              <ul className="space-y-2">
                {report.needsImprovement.length ? (
                  report.needsImprovement.map((item, idx) => (
                    <li key={idx} className="font-body text-sm text-gray-300">
                      ⚠ {item}
                    </li>
                  ))
                ) : (
                  <li className="font-body text-sm text-gray-500">
                    No immediate performance risks detected.
                  </li>
                )}
              </ul>
            </div>
          </section>

          <section className="card p-5 mb-4">
            <p className="label mb-3">AI SUGGESTIONS</p>
            <ul className="space-y-2">
              {report.suggestions.map((item, idx) => (
                <li key={idx} className="font-body text-sm text-gray-300">
                  • {item}
                </li>
              ))}
            </ul>
          </section>

          <section className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="label">ACTION TASKS</p>
              <p className="font-display text-xs text-gray-600">
                Mark done as you execute platform improvements
              </p>
            </div>

            <div className="space-y-2">
              {report.generatedTasks.map((task) => (
                <label
                  key={task.id}
                  className="flex items-start gap-3 p-3 border border-brand-midgray rounded-sm hover:border-gray-600 transition-colors cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={Boolean(taskStatus[task.id])}
                    onChange={() => toggleTask(task.id)}
                    className="mt-1"
                  />
                  <div>
                    <p
                      className={`font-display text-sm ${taskStatus[task.id] ? "text-brand-greenlight line-through" : "text-white"}`}
                    >
                      {task.title}
                    </p>
                    <p className="font-body text-xs text-gray-600 mt-1">
                      {task.detail}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
