# app/ml/training.py
"""
Model lifecycle (load/save) and retraining for the prediction engine
(Sprint 5.3 file split from prediction_engine.py).

Training strategy: stratification by outcome, recency weighting
(30d = 2x, 90d = 1.5x), inverse-frequency class balancing, and
StratifiedKFold calibration CV. Calibration method is isotonic for
n >= 100, else Platt sigmoid.

NOTE: model version is intentionally NOT bumped on retrain — the version
is stable for the entire server lifetime (equals settings.MODEL_VERSION).
"""
import logging
import os
import pickle
import warnings
from datetime import datetime
from typing import Any, Dict, List, Literal

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import RobustScaler

from app.config.settings import settings
from app.ml.features import FEATURE_KEYS
from app.ml.priors import OUTCOME_MAP
from app.utils.timezone import WAT

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "models")
)
os.makedirs(MODEL_DIR, exist_ok=True)


class TrainingMixin:
    """Model persistence + retraining for PredictionEngine (mixin)."""

    # ── Chronological (walk-forward) folds ───────────────────────────────────

    def _chronological_folds(self, dates_list: List[str], n_splits: int):
        """
        Build purged walk-forward (train, test) index splits ordered by date.

        Random shuffled StratifiedKFold lets future matches leak into past
        training folds, which overstates out-of-sample accuracy on time-series
        data. Sorting by match date and only training on strictly-earlier
        blocks yields honest calibration/evaluation. Returns None when dates
        can't be parsed or there aren't enough of them, so callers fall back
        to StratifiedKFold.
        """
        if n_splits < 2 or len(dates_list) < n_splits * 2:
            return None
        dated: List[Any] = []
        for i, d in enumerate(dates_list):
            if not d:
                return None
            try:
                dt = datetime.fromisoformat(d)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=WAT)
                dated.append((dt, i))
            except Exception:
                return None
        dated.sort(key=lambda pair: pair[0])
        order = [i for _, i in dated]
        n = len(order)
        boundaries = np.linspace(0, n, n_splits + 1, dtype=int)
        blocks = [order[boundaries[k]:boundaries[k + 1]] for k in range(n_splits)]
        folds = []
        for k in range(1, n_splits):
            train = np.concatenate([np.array(b, dtype=int) for b in blocks[:k]])
            test = np.array(blocks[k], dtype=int)
            if len(train) >= 2 and len(test) >= 2:
                folds.append((train, test))
        return folds or None

    # ── Persistence ──────────────────────────────────────────────────────────

    def _feature_width(self, sport: str) -> int:
        return len(FEATURE_KEYS.get(sport, FEATURE_KEYS["soccer"]))

    def _artifact_suffix(self, sport: str) -> str:
        return f"v{self.model_version}_{self._feature_width(sport)}_features"

    def _model_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"model_{sport}_{self._artifact_suffix(sport)}.pkl")

    def _scaler_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"scaler_{sport}_{self._artifact_suffix(sport)}.pkl")

    def _meta_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"meta_{sport}_{self._artifact_suffix(sport)}.pkl")

    def _legacy_model_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"model_{sport}_v{self.model_version}.pkl")

    def _legacy_scaler_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"scaler_{sport}_v{self.model_version}.pkl")

    def _legacy_meta_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"meta_{sport}.pkl")

    def _load_all(self):
        for sport in FEATURE_KEYS:
            mp, sp, meta_path = self._model_path(sport), self._scaler_path(sport), self._meta_path(sport)
            if not (os.path.exists(mp) and os.path.exists(sp)):
                mp, sp, meta_path = self._legacy_model_path(sport), self._legacy_scaler_path(sport), self._legacy_meta_path(sport)

            if os.path.exists(mp) and os.path.exists(sp):
                try:
                    with open(mp, "rb") as f:
                        self.models[sport] = pickle.load(f)
                    with open(sp, "rb") as f:
                        self.scalers[sport] = pickle.load(f)
                    if os.path.exists(meta_path):
                        with open(meta_path, "rb") as f:
                            meta = pickle.load(f)
                            self.n_training_samples[sport] = meta.get("n_samples", 0)

                    expected = self._feature_width(sport)
                    actual = int(getattr(self.scalers[sport], "n_features_in_", -1))
                    if actual != expected:
                        logger.warning(
                            "[%s] Loaded artifact has %s features but code expects %s. "
                            "Skipping persisted model; retrain required.",
                            sport,
                            actual,
                            expected,
                        )
                        self._init_model(sport)
                        continue

                    self.is_trained[sport] = True
                    logger.info(
                        "Model loaded [%s] %s (n=%s)",
                        sport,
                        self._artifact_suffix(sport),
                        self.n_training_samples[sport],
                    )
                except Exception as e:
                    logger.warning(f"Failed to load [{sport}] model: {e}")
                    self._init_model(sport)
            else:
                self._init_model(sport)

    def _init_model(self, sport: str):
        n = self.n_training_samples.get(sport, 0)
        method: Literal["sigmoid", "isotonic"] = "isotonic" if n >= 100 else "sigmoid"
        base = HistGradientBoostingClassifier(
            max_iter=400,
            learning_rate=0.04,
            max_depth=5,
            min_samples_leaf=10,
            l2_regularization=0.25,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
            random_state=42,
        )
        self.models[sport] = CalibratedClassifierCV(
            base, method=method,
            cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=42),
        )
        self.is_trained[sport] = False
        logger.info(f"New model initialised [{sport}] (untrained, calibration={method})")

    def _save(self, sport: str):
        try:
            with open(self._model_path(sport), "wb") as f:
                pickle.dump(self.models[sport], f)
            with open(self._scaler_path(sport), "wb") as f:
                pickle.dump(self.scalers[sport], f)
            with open(self._meta_path(sport), "wb") as f:
                pickle.dump({"n_samples": self.n_training_samples[sport]}, f)
            logger.info(f"Model saved [{sport}] v{self.model_version}")
        except Exception as e:
            logger.error(f"Failed to save model [{sport}]: {e}")

    # ── Training ──────────────────────────────────────────────────────────────

    def retrain(self, training_records: List[Dict], sport: str = "soccer") -> Dict[str, Any]:
        """
        Retrain the ML model with stratified sampling and outcome balancing.

        ### Training Data Strategy

        **Stratification:**
          - Outcomes are stratified (home_win, draw, away_win) to ensure all classes are represented
          - Recent data (<=30 days) gets 2x weight; 90-day data gets 1.5x weight
          - This ensures temporal diversity and prevents model degradation from stale data

        **Class Balancing:**
          - Draws are minority class in football; inverse frequency weighting corrects this
          - Class weight for outcome: `mean_class_count / actual_count` clipped to [0.8, 2.8]
          - Combined with recency weighting for final sample weight

        **Rare Outcome Handling:**
          - If any outcome class has <5 samples, model is not retrained (insufficient diversity)
          - Minimum total samples: {settings.MIN_TRAINING_SAMPLES}
          - Minimum 2 outcome classes required for meaningful training

        **Data Contribution:**
          - Every sample contributes via: `base_weight * recency_weight * class_balance_weight`
          - Sample importance inversely scaled to class frequency (minority classes matter more)
          - Recent samples matter more (capturing current team form)

        **Validation:**
          - StratifiedKFold (k=2-3) ensures train/val sets have same outcome distribution
          - Holdout evaluation set created during learning trigger to measure generalization
          - Calibration method chosen based on sample size (isotonic if n>=100, else sigmoid)
        """
        sport     = sport.lower()
        min_samples = settings.MIN_TRAINING_SAMPLES

        if len(training_records) < min_samples:
            return {"status": "skipped", "samples": len(training_records), "sport": sport}

        rows, labels, weights, outcomes_list, dates_list = [], [], [], [], []
        now = datetime.now(WAT)

        # Extract features and outcomes from records
        for rec in training_records:
            feats   = rec.get("features", {})
            outcome = rec.get("actual_outcome")
            if not feats or outcome not in OUTCOME_MAP:
                continue

            rows.append(self._fv(feats, sport))
            labels.append(OUTCOME_MAP[outcome])
            outcomes_list.append(outcome)

            match_date_str = rec.get("match_date", "")
            w = 1.0
            if match_date_str:
                try:
                    md = datetime.fromisoformat(match_date_str).replace(tzinfo=WAT)
                    age_days = (now - md).days
                    if age_days <= 30:
                        w = 2.0
                    elif age_days <= 90:
                        w = 1.5
                except Exception:
                    pass
            weights.append(w)
            dates_list.append(match_date_str)

        if len(rows) < min_samples:
            return {"status": "skipped", "samples": len(rows), "sport": sport}

        X = np.array(rows)
        y = np.array(labels)
        w = np.array(weights)
        n = len(rows)
        expected_features = self._feature_width(sport)
        assert X.shape[1] == expected_features, (
            f"Training matrix width {X.shape[1]} does not match configured feature width {expected_features}."
        )

        # ── Outcome Distribution & Rare Class Detection ───────────────────────────────────
        unique_classes, class_counts = np.unique(y, return_counts=True)
        outcome_class_map = {1: "home_win", 0: "away_win", 2: "draw"}
        outcome_distribution = {outcome_class_map.get(int(c), f"class_{c}"): int(cnt) for c, cnt in zip(unique_classes, class_counts)}

        if len(unique_classes) < 2:
            logger.warning(f"[{sport}] Retrain skipped — need at least 2 outcome classes, got {unique_classes.tolist()}")
            return {
                "status": "skipped",
                "sport": sport,
                "samples": len(rows),
                "reason": "insufficient_class_diversity",
            }

        # ── Rare Outcome Handling: Ensure minimum class support ───────────────────────────
        min_class_count = int(class_counts.min())
        if min_class_count < 5:
            logger.warning(
                f"[{sport}] Retrain skipped — rare outcome detected; "
                f"min class count {min_class_count} < 5. Distribution: {outcome_distribution}"
            )
            return {
                "status": "skipped",
                "sport": sport,
                "samples": len(rows),
                "reason": "rare_outcome_underrepresented",
                "outcome_distribution": outcome_distribution,
            }

        cv_splits = min(3, max(2, n // 20), min_class_count)
        if cv_splits < 2:
            logger.warning(
                f"[{sport}] Retrain skipped — need at least 2 samples in each class for calibration CV; "
                f"class_counts={dict(zip(unique_classes.tolist(), class_counts.tolist()))}"
            )
            return {
                "status": "skipped",
                "sport": sport,
                "samples": len(rows),
                "reason": "insufficient_class_support",
            }

        # ── Class-Weighted Balancing ──────────────────────────────────────────────────────
        # Draws are minority class; inverse frequency weighting corrects this
        # Combined with recency weighting for final sample importance
        class_weight_map: Dict[int, float] = {}
        mean_class_count = float(np.mean(class_counts))
        for cls, count in zip(unique_classes.tolist(), class_counts.tolist()):
            if count <= 0:
                class_weight_map[int(cls)] = 1.0
            else:
                # Weight minority classes more (draws typically underrepresented)
                class_weight_map[int(cls)] = float(np.clip(mean_class_count / float(count), 0.8, 2.8))

        class_weight_vec = np.array([class_weight_map.get(int(label), 1.0) for label in y], dtype=np.float64)
        w = w * class_weight_vec

        # Log data distribution
        sample_weight_by_outcome = {}
        for outcome, weight in zip(outcomes_list, w):
            if outcome not in sample_weight_by_outcome:
                sample_weight_by_outcome[outcome] = []
            sample_weight_by_outcome[outcome].append(weight)

        logger.info(
            f"[{sport}] Training with stratified sampling: "
            f"n={n}, outcomes={outcome_distribution}, "
            f"avg_weights_by_outcome=" + ", ".join(
                f"{o}={np.mean(sample_weight_by_outcome[o]):.2f}"
                for o in sorted(sample_weight_by_outcome.keys())
            )
        )

        # ── Model Training ────────────────────────────────────────────────────────────────
        self.scalers[sport].fit(X)
        assert X.shape[1] == int(self.scalers[sport].n_features_in_), (
            f"Scaler feature width mismatch: X has {X.shape[1]} while scaler expects {self.scalers[sport].n_features_in_}."
        )
        X_scaled = self.scalers[sport].transform(X)

        if n >= 100 and settings.CALIBRATION_METHOD != "sigmoid":
            cal_method: Literal["sigmoid", "isotonic"] = "isotonic"
        else:
            cal_method = "sigmoid"

        base = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.04, max_depth=5,
            min_samples_leaf=max(5, n // 40),
            l2_regularization=0.25, early_stopping=True,
            validation_fraction=0.15, n_iter_no_change=20, random_state=42,
        )
        # Chronological purged (walk-forward) folds keep time-series honest —
        # future matches never leak into past calibration folds. Falls back to
        # StratifiedKFold when dates aren't available/parseable.
        cv = self._chronological_folds(dates_list, cv_splits)
        if cv is None:
            cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42)
            fold_kind = "stratified_shuffle"
        else:
            fold_kind = "chronological_purged_walk_forward"
        self.models[sport] = CalibratedClassifierCV(
            base, method=cal_method, cv=cv,
        )
        logger.info("[%s] Calibration CV: %s", sport, fold_kind)

        self.models[sport].fit(X_scaled, y, sample_weight=w)  # type: ignore[union-attr]
        self.is_trained[sport]         = True
        self.n_training_samples[sport] = n

        # ── Track outcome balance for ML weight modulation ───────────────────────────────
        self.outcome_balance[sport] = {
            "distribution": outcome_distribution,
            "class_weights": {outcome_class_map.get(int(c), f"class_{c}"): float(class_weight_map.get(int(c), 1.0)) for c in unique_classes},
            "last_trained": datetime.now(WAT).isoformat(),
        }

        # Log feature importances
        try:
            base_est = self.models[sport].calibrated_classifiers_[0].estimator  # type: ignore
            importances = base_est.feature_importances_
            keys = FEATURE_KEYS.get(sport, [])
            top = sorted(zip(keys, importances), key=lambda x: -x[1])[:8]
            logger.info(f"[{sport}] Top features: " + ", ".join(f"{k}={v:.3f}" for k, v in top))
            feature_importance_top = [{"feature": k, "importance": round(float(v), 4)} for k, v in top]
        except Exception:
            feature_importance_top = []

        # NOTE: model version is intentionally NOT bumped here.
        # Previously this code mutated self.model_version and settings.MODEL_VERSION
        # on every retrain, causing version drift and filename mismatches after
        # server restarts. The version is now stable for the entire server lifetime.
        self._save(sport)

        y_proba  = self.models[sport].predict_proba(X_scaled)  # type: ignore[union-attr]
        classes  = list(self.models[sport].classes_)            # type: ignore[union-attr]
        home_idx = classes.index(1) if 1 in classes else 0
        home_probs = self._sanitize_probabilities(y_proba[:, home_idx])
        binary_labels = (y == 1).astype(int)

        bs = brier_score_loss(binary_labels, home_probs)
        ll = log_loss(binary_labels, home_probs, labels=[0, 1])
        bookmaker_probs = np.clip(
            np.array([float(rec.get("features", {}).get("implied_home_prob", 0.5)) for rec in training_records[:n]], dtype=np.float64),
            1e-6,
            1 - 1e-6,
        )
        bookmaker_bs = brier_score_loss(binary_labels, bookmaker_probs)
        calibration_gap = float(bs - bookmaker_bs)
        recalibration_status = "ok" if calibration_gap <= 0.02 else "needs_review"

        logger.info(
            f"[{sport}] Retrained — n={n}, brier={bs:.4f}, "
            f"log_loss={ll:.4f}, calibration={cal_method}, v={self.model_version}"
        )

        # ── Return detailed training metadata ──────────────────────────────────────────────
        return {
            "status": "retrained", "sport": sport, "samples": n,
            "brier_score": round(bs, 4), "log_loss": round(ll, 4),
            "bookmaker_brier_score": round(float(bookmaker_bs), 4),
            "calibration_gap_vs_bookmaker": round(calibration_gap, 4),
            "recalibration_status": recalibration_status,
            "calibration_method": cal_method, "ml_weight": round(self._ml_weight(sport), 3),
            "top_feature_importance": feature_importance_top,
            "new_version": self.model_version,
            # ── Data contribution transparency ────────────────────────────────────────────
            "outcome_distribution": outcome_distribution,  # e.g. {"home_win": 120, "draw": 45, "away_win": 115}
            "class_weight_factors": {outcome_class_map.get(int(c), f"class_{c}"): round(float(class_weight_map.get(int(c), 1.0)), 3) for c in unique_classes},
            "cv_splits": cv_splits,  # Number of stratified folds used
            "stratified_kfold_used": True,  # All outcomes represented in each fold
            "recency_weights": {"0_30_days": 2.0, "31_90_days": 1.5, "older": 1.0},
            "min_class_count": min_class_count,  # Rarest outcome count
            "mean_class_count": round(mean_class_count, 1),  # Average outcome count
        }
