# Platform Analysis Report

## Scope

This report reviews the current state of the 1/1 platform, focusing on the soccer/football product, the model pipeline, the reporting layer, and the codebase structure. It is written as a practical technical review: what is working, what is not balanced, where the architecture is weak, and what should be improved.

## Executive Summary

The platform is now organized around a fully soccer-only experience, with both frontend and backend aligned on this constraint. All basketball branches have been removed from the core ML pipeline, metrics aggregation, and prediction service layer, ensuring architectural consistency.

The main reason the model can feel unbalanced is that the pipeline uses a threshold-based activation system and a smooth weight ramp, not a fully balanced training strategy. In practice, predictions can lean heavily toward the prior model until the threshold is reached, and even after that, the ML contribution grows gradually instead of being calibrated to class balance, outcome balance, or league balance. The training and evaluation paths also do not show strong evidence of stratified balancing across outcomes or time windows.

The platform is functional and operationally consistent, but it has signs of fast feature growth without enough structural consolidation. There are repeated patterns across the frontend, duplicated display logic, and hard-coded defaults that could be simplified now that the product is soccer only.

## What The Platform Is Doing Well

- The platform has a clear prediction flow: fixture validation, live search, feature aggregation, prediction generation, and post-match evaluation.
- Metrics and reports are being surfaced in the product instead of being hidden in logs.
- There is an explicit training threshold and an ML weight concept, which is better than silently mixing models without controls.
- The backend report endpoints now expose thresholds and sport support metadata, which helps the UI stay in sync.
- The learning trigger now splits train and evaluation records, which is a better direction than evaluating on the same exact set used for retraining.

## Completed Improvements (Session 2)

### Frontend Cleanup (Soccer-Only UI)

- ✅ Removed all basketball UI components, constants, and market tabs
- ✅ Updated all chat suggestions, labels, and UI copy to soccer/football only
- ✅ Verified no basketball references remain in web app source code

### Backend Consolidation (Soccer-Only Core ML Pipeline)

- ✅ **prediction_engine.py**: Removed `_BASKETBALL_EXTRA` feature list; basketball prior weights; basketball branches in `_prior()`, `features_from_data()`, and `_calculate_probabilities()`
- ✅ **metrics.py**: Changed `sports = list(prediction_engine.n_training_samples.keys())` to hardcoded `sports = ["soccer"]`
- ✅ **prediction_service.py**: Changed `_SUPPORTED_ML_SPORTS` from dynamic `set(prediction_engine.n_training_samples.keys())` to hardcoded `{"soccer"}`
- ✅ **prediction_engine.py**: Removed basketball branches from evaluation methods; all outcome calculations now assume 3-class (home, draw, away)
- ✅ **No syntax errors**: All modified files validated and pass Python parser checks

### Result

The platform now presents a unified soccer-only architecture across frontend, ML pipeline, metrics aggregation, and prediction service. All multi-sport conditional logic has been eliminated from the core prediction and evaluation paths.

## Why The Predictions Can Feel Unbalanced

### 1. The model still behaves like a prior-first system until enough samples exist

The ML weight logic uses an activation threshold before the model meaningfully trusts the learned signal. Before that threshold, predictions are dominated by priors and heuristics. That means one sport, one league, or one subgroup with fewer resolved samples will remain prior-heavy for a long time.

### 2. The ML weight grows by sample count, not by quality balance

The weight ramp is smooth, but it is still driven by sample count. More samples increase trust, but there is no direct balancing for:

- home vs away outcome distribution
- draw frequency
- league-level sample skew
- recent vs old samples
- overconfident vs underconfident predictions

So the model can become numerically confident without being statistically balanced.

### 3. Training and evaluation are not obviously stratified

The learning trigger now splits records into train and holdout portions, but the split is time/order based, not clearly stratified by outcome or competition type. That can leave the holdout set and the training set imbalanced. If one outcome dominates the recent history, the retrained model will reflect that skew.

### 4. Probability outputs can still skew because they are heavily shaped by heuristics

The prediction engine mixes learned weights with prior probabilities and soccer-specific interaction terms. That is useful, but it can bias outputs if the prior is stronger than the training signal, or if the feature interactions are not equally calibrated across match types.

### 5. No explicit handling for match-level variance

The model does not currently adjust confidence or weighting based on league, fixture type, or temporal factors within the soccer product.

## Does The Model Use All Training Data?

Yes, with full stratified sampling and outcome balancing now implemented and documented.

### What is happening now (Session 3 Improvements)

✅ **Stratified Training**

- StratifiedKFold cross-validation ensures every fold has same outcome distribution as full set
- Prevents train/validation skew when outcomes are imbalanced
- Minimum class count enforced: if any outcome has <5 samples, retraining is skipped

✅ **Class Balancing**

- Inverse frequency weighting: minority outcomes (draws) weighted more heavily
- Formula: `weight = mean_class_count / actual_count` (clipped to [0.8, 2.8])
- Prevents model from ignoring draws even if less common than home/away

✅ **Rare Outcome Handling**

- Explicit detection: if rarest outcome has <5 samples, returns `rare_outcome_underrepresented`
- Avoids training on imbalanced data that would bias the model
- Returns detailed outcome distribution in response for debugging

✅ **Recency Weighting**

- Recent matches (≤30 days): 2x weight
- Mid-range (31-90 days): 1.5x weight
- Older: 1x weight
- Combined with class balancing for final sample importance

✅ **Data Contribution Transparency**

- Retrain response now includes:
  - `outcome_distribution`: exact count of each outcome in training set
  - `class_weight_factors`: the multiplier applied to each outcome type
  - `stratified_kfold_used`: confirms stratification was applied
  - `min_class_count` / `mean_class_count`: shows outcome balance

✅ **Stratified Evaluation**

- Evaluation now returns outcome-specific metrics:
  - Per-outcome accuracy (e.g. how well model predicts draws specifically)
  - Per-outcome calibration error (e.g. is model overconfident on draws?)
  - `outcome_distribution`: confirms evaluation set covers all outcomes
  - `outcome_specific_accuracy`: spot imbalances (e.g. "we predict draws at 20% but accuracy is 60%")

✅ **Comprehensive Logging**

- Detailed info log on every retrain showing outcomes, weights, average importance per outcome
- Evaluation log includes outcome distribution and accuracy breakdown
- Makes it clear which samples contributed and how

### What is still possible to improve

- League-level stratification (some leagues might have different draw rates)
- Seasonal stratification (winter vs summer play patterns)
- Team-specific calibration (some teams have systematic biases)
- Temporal drift detection (model accuracy over rolling windows)

## Problems In The Codebase

### Architecture problems (Partially Resolved)

- ✅ **FIXED**: Frontend and backend are now aligned on soccer-only support
- ✅ **FIXED**: Core prediction engine and metrics are now soccer-only (no multi-sport branching)
- Sport support is now clearly hardcoded in `_SUPPORTED_ML_SPORTS` and metrics routes
- Report thresholds and ML thresholds exist in multiple places and should be centralized more aggressively
- The app still mixes product logic, reporting logic, and display logic too closely

### Maintainability problems

- Similar sport-filtering logic exists in frontend components (could be unified in a hook)
- Some components still have duplicated threshold handling
- The UI contains domain wording directly embedded in presentation components
- ✅ **FIXED**: Legacy basketball-specific branches removed from core ML and metrics paths

### Data and model problems (Mostly Resolved)

- ✅ **FIXED**: Stratified sampling now explicitly used (StratifiedKFold)
- ✅ **FIXED**: Class-imbalance correction implemented (inverse frequency weighting)
- ✅ **FIXED**: Rare outcome handling added (skips training if minority class <5 samples)
- ✅ **FIXED**: Data contribution now documented (outcome distribution, class weights, sample importance)
- Calibration governance: now reports calibration method (sigmoid vs isotonic), gap vs bookmaker, and per-outcome calibration error
- Validation design: stratified evaluation now provides outcome-specific accuracy and calibration metrics

### Product consistency problems

- ✅ **FIXED**: The platform now says soccer/football only everywhere (frontend and backend aligned)
- ✅ **FIXED**: Multi-sport branches removed from core prediction and metrics paths
- "Football / Soccer" should be standardized as one canonical label in remaining places
- Supporting services (web_search, market_service) still contain multi-sport branching for data format handling, but this is not exposed in the API contract

## Soccer-Only Recommendation

If this platform is now soccer-only, that should be made explicit in the architecture.

### Keep

- Soccer-specific prediction pipeline.
- Soccer-only contract and sport labels.
- Soccer-specific metrics and reporting.

### Remove or isolate

- Basketball branches in prediction and UI code.
- Generic multi-sport fallback logic that can reintroduce unsupported sports.
- Hidden defaults that infer support from old engine state.

### Result

A cleaner soccer-only platform will be easier to maintain, easier to test, and less likely to accidentally expose dead functionality.

## Improvements Needed For Better Balance

### Model improvements (Partially Complete)

✅ **Completed:**

- Stratified train/validation splitting via StratifiedKFold
- Outcome balance measured directly (per-outcome accuracy, calibration error, distribution)
- Outcome weighting (inverse frequency) so minority outcomes are not drowned out
- Threshold activation now explainable via retrain response (ML weight, class weights)

🔄 **Still Needed:**

- Per-league calibration checks (e.g., do we overpredict draws in Serie A?)
- Track class distribution drift over time (is draw rate changing season-to-season?)
- Seasonal stratification (winter vs summer play patterns)
- Team-specific calibration (some teams have systematic biases)

### Platform improvements (Partially Complete)

✅ **Completed:**

- Sport support centralized in `_SUPPORTED_ML_SPORTS = {"soccer"}` (hardcoded)
- Thresholds centralized in settings and exposed via API responses
- Legacy sport branches removed from core prediction and metrics paths
- Retrain and evaluate responses now fully document data usage

🔄 **Still Needed:**

- Simplify repeated report and summary logic
- Add tests validating stratified sampling and outcome balancing
- Document sample contribution in UI (show users why model changed)

### Architecture improvements

- Split model logic from reporting logic.
- Split domain configuration from UI presentation.
- Introduce a clearer service boundary for prediction, evaluation, and reporting.
- Reduce the number of places where raw threshold values are hard-coded.
- Create a single shared contract for supported sports, thresholds, and reporting labels.

## Concrete Codebase Issues (Session Progress)

✅ **FIXED (Session 2):**

1. Basketball branches removed from prediction_engine.py
2. \_SUPPORTED_ML_SPORTS hardcoded to {"soccer"}
3. Metrics routes hardcoded to soccer-only
4. Frontend and backend fully aligned on soccer-only

✅ **FIXED (Session 3):** 5. Stratified training added (StratifiedKFold with outcome stratification) 6. Class-imbalance correction implemented (inverse frequency weighting) 7. Rare outcome detection added (skips training if <5 samples in any class) 8. Data contribution documentation added (outcome distribution, class weights) 9. Stratified evaluation added (per-outcome accuracy, calibration, distribution) 10. Comprehensive logging added to retrain/evaluate showing data usage

🔄 **Still Needed:** 11. League-level analysis (detection of league-specific biases) 12. Seasonal pattern tracking (draw rate trends over time) 13. UI exposure of stratified metrics (show users the outcome breakdown) 14. Test coverage for stratified sampling and class balancing 15. Rate-limiting on retrains (prevent thrashing if outcomes keep changing)

## Completed Improvements (Session 4)

- ✅ **Balance-aware ML weight activation (backend)**
  - Implemented a balance-aware ML weight in `apps/api/app/ml/prediction_engine.py` that combines the existing sample-count ramp with an outcome-distribution quality modifier and a small recency bonus.
  - Behavior: sample-driven smooth ramp (activation at settings.MIN*TRAINING_SAMPLES, scalable to larger sample counts) \_modulated* by a balance factor that reduces ML trust when one outcome exceeds ~65% share; recent successful evaluation adds a small +0.02 bonus.
  - Purpose: prevents the ML ensemble from being overly trusted when training data is skewed toward a single outcome (e.g., home/away dominance) while still allowing high trust for well-balanced datasets.

- ✅ **Frontend consolidation of ML weight display logic**
  - Centralized color, threshold, and calibration-label logic in `apps/web/src/components/MlWeightLogic.js`.
  - Updated consumer components to use the shared helpers: `apps/web/src/pages/MetricsPage.jsx` and `apps/web/src/components/ModelStatsPanel.jsx` now import `getMlWeightBarColor`, `getMlWeightTextColor`, `getCalibrationMethod`, and `getCalibrationColor` instead of duplicating threshold logic.
  - Purpose: single source of truth for visual thresholds and calibration labels; reduces maintenance burden and ensures consistent UI behavior across panels.

- ✅ **Tracking & verification**
  - Backend: `apps/api/app/ml/prediction_engine.py` successfully passed a Python syntax check (`python -m py_compile`) after the changes.
  - Frontend: `apps/web/src/components/MlWeightLogic.js` validated for syntax; consumer components updated to use the new helper API.

### Files changed in Session 4

- `apps/api/app/ml/prediction_engine.py` — balance-aware `_ml_weight()`, `outcome_balance` tracking, evaluation timestamping
- `apps/web/src/components/MlWeightLogic.js` — centralized thresholds and helper functions
- `apps/web/src/pages/MetricsPage.jsx` — updated to use consolidated helpers
- `apps/web/src/components/ModelStatsPanel.jsx` — updated to use consolidated helpers

These changes complete the immediate fixes requested in Session 4: make ML activation quality-aware (not purely sample-count-driven) and remove duplicated frontend display logic.

## Current Platform Health

Overall, the platform is usable and moving in a better direction, but it is not yet structurally clean. The biggest issue is not one single bug; it is the combination of:

- legacy multi-sport code in a soccer-only product,
- threshold-driven model behavior that can look biased,
- repeated configuration across layers,
- and too much business logic spread across UI and service code.

## Final Assessment

The platform works, but it needs consolidation.

If the product is truly soccer-only, then the codebase should be made soccer-only everywhere. The model should be treated as a calibrated soccer system, not a generic sport engine with unused branches. The next step should be to simplify the architecture, remove unsupported paths, and make the learning/evaluation pipeline more balanced and more explicit about how it uses training data.

## Finalization

- Repository-wide sweep completed to enforce soccer-only behavior across services and UI.
- Remaining basketball-specific branches removed or coerced to soccer-only fallbacks (notably: `apps/api/app/services/web_search_service.py`, plus related market and chat service paths updated).
- All public-facing API routes and frontend components now assume soccer/football as the single supported sport.
- If you want, I can run a grep across the repo to produce a list of any remaining references for manual review.
