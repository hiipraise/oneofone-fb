import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  useMetricsSummary,
  usePredictions,
  useResults,
} from "../hooks/useData";

const STORAGE_KEY = "platform-report-task-status-v1";
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

function renderMarkdown(markdown) {
  if (!markdown) return null;
  const lines = markdown.split("\n");
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("# ")) {
      elements.push(
        <h1 key={i} className="text-2xl font-bold text-white mt-6 mb-3">
          {line.slice(2)}
        </h1>,
      );
    } else if (line.startsWith("## ")) {
      elements.push(
        <h2 key={i} className="text-xl font-bold text-white mt-5 mb-2">
          {line.slice(3)}
        </h2>,
      );
    } else if (line.startsWith("### ")) {
      elements.push(
        <h3 key={i} className="text-lg font-semibold text-gray-200 mt-4 mb-2">
          {line.slice(4)}
        </h3>,
      );
    } else if (line.startsWith("- ")) {
      elements.push(
        <li key={i} className="text-sm text-gray-300 ml-4">
          {line.slice(2)}
        </li>,
      );
    } else if (line.startsWith("✅ ")) {
      elements.push(
        <div key={i} className="text-sm text-green-400 ml-4">
          {line}
        </div>,
      );
    } else if (line.startsWith("🔄 ")) {
      elements.push(
        <div key={i} className="text-sm text-yellow-400 ml-4">
          {line}
        </div>,
      );
    } else if (line.trim() === "") {
      elements.push(<div key={i} className="h-2" />);
    } else if (line.trim()) {
      elements.push(
        <p key={i} className="text-sm text-gray-300 leading-6">
          {line}
        </p>,
      );
    }

    i++;
  }

  return <div className="space-y-2">{elements}</div>;
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

  const suggestions = [
    "Automate post-match result ingestion to increase resolved + scored volume.",
    "Prioritize per-sport model retraining when sample counts cross activation thresholds.",
    "Add a weekly calibration review to compare confidence buckets vs actual win rates.",
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
  const [activeTab, setActiveTab] = useState("quick-report");
  const [platformAnalysis, setPlatformAnalysis] = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);

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

  useEffect(() => {
    if (
      activeTab === "platform-analysis" &&
      !platformAnalysis &&
      !analysisLoading
    ) {
      setAnalysisLoading(true);
      axios
        .get(`${API_BASE}/reports/platform-analysis`)
        .then((res) => {
          setPlatformAnalysis(res.data);
          setAnalysisLoading(false);
        })
        .catch((err) => {
          console.error("Error fetching platform analysis:", err);
          setAnalysisLoading(false);
        });
    }
  }, [activeTab, platformAnalysis, analysisLoading]);

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
          {activeTab === "quick-report"
            ? `Generated: ${new Date(report.generatedAt).toLocaleString()}`
            : platformAnalysis?.lastUpdated
              ? `Last Updated: ${new Date(platformAnalysis.lastUpdated).toLocaleString()}`
              : ""}
        </span>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-4 mb-6 border-b border-brand-midgray">
        <button
          onClick={() => setActiveTab("quick-report")}
          className={`pb-3 font-display text-sm transition-colors ${
            activeTab === "quick-report"
              ? "text-brand-gold border-b-2 border-brand-gold"
              : "text-gray-600 hover:text-gray-400"
          }`}
        >
          QUICK REPORT
        </button>
        <button
          onClick={() => setActiveTab("platform-analysis")}
          className={`pb-3 font-display text-sm transition-colors ${
            activeTab === "platform-analysis"
              ? "text-brand-gold border-b-2 border-brand-gold"
              : "text-gray-600 hover:text-gray-400"
          }`}
        >
          PLATFORM ANALYSIS
        </button>
      </div>

      {/* Quick Report Tab */}
      {activeTab === "quick-report" && (
        <>
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
                    <p className="font-display text-[10px] text-gray-600">
                      SCORED
                    </p>
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
                    <p className="font-display text-[10px] text-gray-600">
                      BRIER
                    </p>
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

              <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                <div className="card p-5">
                  <p className="label mb-3">WHAT IS WORKING</p>
                  <ul className="space-y-2">
                    {report.working.length ? (
                      report.working.map((item, idx) => (
                        <li
                          key={idx}
                          className="font-body text-sm text-gray-300"
                        >
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
                        <li
                          key={idx}
                          className="font-body text-sm text-gray-300"
                        >
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
        </>
      )}

      {/* Platform Analysis Tab */}
      {activeTab === "platform-analysis" && (
        <>
          {analysisLoading ? (
            <div className="card p-6 animate-pulse">
              <div className="h-4 w-56 bg-brand-midgray rounded mb-3" />
              <div className="h-3 w-full bg-brand-midgray rounded mb-2" />
              <div className="h-3 w-5/6 bg-brand-midgray rounded" />
            </div>
          ) : platformAnalysis?.exists ? (
            <div className="card p-6">
              <div className="prose prose-invert max-w-none">
                {renderMarkdown(platformAnalysis.content)}
              </div>
            </div>
          ) : (
            <div className="card p-6">
              <p className="font-body text-sm text-gray-600">
                {platformAnalysis?.message ||
                  "Unable to load platform analysis"}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
