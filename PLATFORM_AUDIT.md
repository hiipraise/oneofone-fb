# OneOfOne Platform Audit and Improvement Plan

## 1. Executive Summary
OneOfOne is already directionally sound as a football-only prediction product: FastAPI, MongoDB, React/Vite, Chart.js, and scikit-learn are appropriate free/open-source foundations. The biggest product risk is not lack of visual polish; it is trust. Users need evidence that predictions are calibrated, resolved, and evaluated on football-only data. This change set fixes the highest-signal operational bugs found during the audit: dashboard chart requests now use the configured API client instead of hard-coded `/api` fetches, metrics endpoints now default to football-only records, and scheduler logs no longer surface legacy basketball/NBA entries.

## 2. Overall Platform Score
- Architecture: 6.5/10 — clear app split, but the scheduler and prediction engine still centralize too many responsibilities.
- UX: 6/10 — useful pages exist, but confidence/calibration evidence must be more prominent than chat/report chrome.
- Performance: 6.5/10 — acceptable for current scale; repeated dashboard calls and unbounded historical reads should be tightened.
- Maintainability: 5.5/10 — football-only scope is partly implemented, but legacy multisport vocabulary remains in services and UI copy.
- Prediction Quality: 5/10 — scikit-learn calibration is present, but free-data feature quality, leakage controls, and time-series validation need stronger guarantees.

## 3. Critical Issues
1. Football-only data boundaries must be enforced at the API layer, not just the UI. Metrics, logs, and summaries should never mix basketball with soccer.
2. Dashboard analytical cards must use the shared Axios client. Hard-coded `fetch('/api/...')` breaks under any non-root API base URL and produces the observed `Unexpected token '<'` SPA fallback symptom.
3. Scheduler restart recovery is incomplete unless APScheduler job persistence is enabled. Because MongoDB already exists, use `apscheduler.jobstores.mongodb` before considering a larger scheduler rewrite.
4. Prediction quality depends more on data lineage and validation than adding another model. Do not add XGBoost/LightGBM until time-series validation, calibration reporting, and feature provenance are reliable.

## 4. Medium-Priority Issues
- `prediction_engine.py` is a large single-file engine. Split feature extraction, priors, training, evaluation, and persistence.
- `reports.py` appears to summarize existing metrics rather than generating unique data. It is a deletion candidate unless usage proves otherwise.
- Chat adds cost and product ambiguity. Retain only if redesigned as a contextual explanation layer attached to a prediction, not as a separate destination.
- Market accuracy should include ROI only when odds snapshots and staking assumptions are recorded; otherwise ROI charts are decorative and misleading.

## 5. Low-Priority Issues
- A draggable floating bento is attractive but unnecessary for eight routes. Prefer a compact responsive rail/topbar unless user testing shows navigation friction.
- Streak visualizations are secondary. Calibration, resolved coverage, and rolling Brier/log-loss trends improve decisions more directly.
- More visualization libraries are not yet justified. Chart.js can cover line, bar, scatter, distribution, calibration, and rolling windows with small custom components.

## 6. Dead Code and Features to Remove
- Remove remaining basketball/NBA branches and copy from services once data migration is complete.
- Consider removing Reports if it remains a formatted Metrics duplicate.
- Merge Chat History into Chat or remove both if prediction decisions do not depend on chat transcripts.

## 7. Performance Improvements
- Add Mongo indexes for `predictions(sport, deleted_at, match_date)`, `actual_results(sport, match_date, match_id)`, and `system_logs(source, sport, timestamp)`.
- Cache metrics summary for a short TTL because multiple dashboard panels request related aggregate data.
- Bound all historical scans by date and sport.

## 8. UI/UX Improvements
- Keep navigation boring and reliable: compact rail on desktop, bottom tabs or menu on mobile.
- Elevate calibration and resolved coverage above raw confidence.
- Show “data unavailable” with the missing prerequisite: no resolved results, no odds, no confidence scores, or API unavailable.

## 9. Prediction Engine Improvements
- First add football-specific baselines: Elo plus Poisson/Dixon-Coles goal model.
- Keep HistGradientBoosting as the first ML model; add LightGBM only after enough clean labeled samples exist.
- Use time-series validation only. Random splits leak future team strength into past matches.
- Report log loss, Brier score, expected calibration error, and resolved coverage on every model version.

## 10. Data Pipeline Improvements
- Prefer stable fixture/result APIs where available and cache aggressively.
- Treat DuckDuckGo/general search as enrichment fallback, not the primary data pipeline.
- Store source provenance and fetch timestamp per feature.
- Add idempotency keys for scheduled predictions and resolutions.

## 11. Open-Source Tool Recommendations
- ML: scikit-learn now; LightGBM later if data volume supports it.
- Evaluation: evidently or custom notebook reports for calibration drift.
- Experiment tracking: MLflow local/file backend.
- Scheduling: APScheduler with MongoDB job store for now; Celery/Redis only if job volume grows.
- Caching: Redis or Mongo TTL collections.
- Observability: OpenTelemetry plus Prometheus/Grafana when deployed.
- Visualization: continue Chart.js before adding Recharts/visx.

## 12. Security Review
- Keep API keys server-side only.
- Validate all route params against football-only enums.
- Avoid returning raw upstream errors to clients.
- Add rate limits around prediction generation, chat, search, and scheduler trigger endpoints.

## 13. Scalability Review
- Current architecture is sufficient for small traffic.
- The next bottlenecks will be repeated scraping/search calls, scheduler idempotency, and unindexed aggregate reads.
- Split scheduler workers only after job persistence and dedupe are in place.

## 14. Refactoring Opportunities
- Split `prediction_engine.py` into `features.py`, `priors.py`, `training.py`, `calibration.py`, and `evaluation.py`.
- Split `market_service.py` into football market calculators by market group.
- Delete `sport_key_catalog.py` if OneOfOne will permanently remain soccer-only; otherwise rename it to `football_league_catalog.py` to remove false multisport abstraction.

## 15. Prioritized Roadmap
### Quick Wins
1. Enforce football-only metrics and logs.
2. Fix hard-coded dashboard chart API calls.
3. Add Mongo indexes and short TTL caching for metrics summary.
4. Make empty states explain missing data prerequisites.

### Near Term
1. Add persisted APScheduler Mongo job store and idempotency guards.
2. Add calibration endpoint with buckets and ECE.
3. Add Elo and Poisson baselines.
4. Remove or merge Reports and Chat after usage review.

### Long Term
1. Build a feature store table/collection with provenance.
2. Add time-series training pipeline and MLflow tracking.
3. Evaluate LightGBM/GBTs only after sufficient clean samples.
4. Add odds snapshot storage before any ROI chart claims.

## 16. Code-Level Recommendations
- `apps/web/src/charts/MarketAccuracyChart.jsx`: use the shared API client so deployed base URLs work.
- `apps/web/src/charts/ConfidenceThresholdChart.jsx`: same API-client fix.
- `apps/api/app/routes/metrics.py`: keep summary, history, market, and confidence endpoints soccer-scoped by default.
- `apps/api/app/routes/scheduler.py`: default logs to soccer and exclude legacy basketball/NBA messages.
- `apps/api/app/scheduler/daily_scheduler.py`: add Mongo job store and idempotent job keys.
- `apps/api/app/ml/prediction_engine.py`: split responsibilities and add time-series validation reports.
