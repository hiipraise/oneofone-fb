# app/ml/prediction_engine.py
"""
Pro-grade prediction engine v2.

ML improvements over v1:
  - Training-size-aware ensemble: ML weight scales with log(n_samples)
    so sparse data gracefully falls back to the calibrated prior
  - Recency-weighted training: matches from last 30 days weighted 2×,
    90 days 1.5×, older 1× — punishes stale signals less
  - Analytical confidence interval via Beta distribution (replaces slow bootstrap)
  - Soft ensemble between ML model and prior (instead of hard switch)
  - Feature importance extraction logged at retrain
  - Calibration via isotonic (n≥100) or Platt sigmoid (n<100)

Fix v2.1:
  - Raw stats (goals_scored_avg, goals_conceded_avg, pts_avg, pts_allowed_avg)
    are NOT 0–1 signals and must NOT be clipped to [0, 1] in features_from_data.

Fix v2.2:
  - Removed manual model version bumping from retrain(). Previously every
    retrain() call incremented the patch version AND wrote back to
    settings.MODEL_VERSION, causing version drift across retrains and
    filename mismatches after server restarts. Version is now stable for
    the entire server lifetime and equals settings.MODEL_VERSION.
"""
import logging
import pickle
import os
from datetime import datetime, timezone, timedelta
from app.utils.timezone import WAT
from typing import Dict, List, Optional, Any, Tuple, Literal, cast

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import StratifiedKFold
from scipy.stats import beta as beta_dist
import warnings
warnings.filterwarnings("ignore")

from app.config.settings import settings

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "models")
)
os.makedirs(MODEL_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Feature definitions
# ─────────────────────────────────────────────────────────────────────────────

_COMMON_FEATURES = [
    "home_form_rating", "away_form_rating",
    "home_win_rate_signal", "away_win_rate_signal",
    "home_ranking_signal", "away_ranking_signal",
    "home_advantage_signal", "h2h_home_win_rate",
    "home_injury_impact", "away_injury_impact",
    "home_espn_win_pct", "away_espn_win_pct",
    "implied_home_prob", "implied_away_prob",
    "home_momentum", "away_momentum",
    "form_delta",
]
_SOCCER_EXTRA = [
    "home_goals_scored_avg", "home_goals_conceded_avg",
    "away_goals_scored_avg", "away_goals_conceded_avg",
    "home_clean_sheet_rate", "away_clean_sheet_rate",
]
_BASKETBALL_EXTRA = [
    "home_pts_avg", "away_pts_avg",
    "home_pts_allowed_avg", "away_pts_allowed_avg",
    "home_pace_signal", "away_pace_signal",
]
FEATURE_KEYS: Dict[str, List[str]] = {
    "soccer":     _COMMON_FEATURES + _SOCCER_EXTRA,
    "basketball": _COMMON_FEATURES + _BASKETBALL_EXTRA,
}

_DEFAULTS: Dict[str, float] = {
    "home_form_rating": 0.5, "away_form_rating": 0.5,
    "home_win_rate_signal": 0.5, "away_win_rate_signal": 0.5,
    "home_ranking_signal": 0.5, "away_ranking_signal": 0.5,
    "home_advantage_signal": 0.54, "h2h_home_win_rate": 0.5,
    "home_injury_impact": 0.0, "away_injury_impact": 0.0,
    "home_espn_win_pct": 0.5, "away_espn_win_pct": 0.5,
    "implied_home_prob": 0.5, "implied_away_prob": 0.5,
    "home_momentum": 0.5, "away_momentum": 0.5,
    "form_delta": 0.5,
    # soccer — raw averages (NOT clipped to 0–1)
    "home_goals_scored_avg": 1.40, "home_goals_conceded_avg": 1.10,
    "away_goals_scored_avg": 1.15, "away_goals_conceded_avg": 1.35,
    "home_clean_sheet_rate": 0.28, "away_clean_sheet_rate": 0.22,
    # basketball — normalised 0–1 internally
    "home_pts_avg": 0.5, "away_pts_avg": 0.5,
    "home_pts_allowed_avg": 0.5, "away_pts_allowed_avg": 0.5,
    "home_pace_signal": 0.5, "away_pace_signal": 0.5,
}

# Keys that carry raw values outside [0, 1] — must NOT be clipped
_RAW_STAT_KEYS = frozenset({
    "home_goals_scored_avg", "home_goals_conceded_avg",
    "away_goals_scored_avg", "away_goals_conceded_avg",
    "home_pts_avg", "away_pts_avg",
    "home_pts_allowed_avg", "away_pts_allowed_avg",
})

_PRIOR: Dict[str, Dict[str, float]] = {
    "soccer": {
        "home_form_rating": 0.22, "away_form_rating": -0.18,
        "home_win_rate_signal": 0.14, "away_win_rate_signal": -0.11,
        "home_advantage_signal": 0.16, "h2h_home_win_rate": 0.09,
        "home_ranking_signal": 0.07, "away_ranking_signal": -0.07,
        "home_injury_impact": -0.07, "away_injury_impact": 0.07,
        "implied_home_prob": 0.22, "implied_away_prob": -0.17,
        "home_espn_win_pct": 0.09, "away_espn_win_pct": -0.07,
        "home_momentum": 0.12, "away_momentum": -0.10,
        "form_delta": 0.10,
        "home_goals_scored_avg": 0.06, "away_goals_conceded_avg": 0.06,
        "away_goals_scored_avg": -0.05, "home_goals_conceded_avg": -0.05,
        "home_clean_sheet_rate": 0.04, "away_clean_sheet_rate": -0.04,
    },
    "basketball": {
        "home_form_rating": 0.20, "away_form_rating": -0.16,
        "home_win_rate_signal": 0.16, "away_win_rate_signal": -0.13,
        "home_advantage_signal": 0.14, "h2h_home_win_rate": 0.08,
        "home_ranking_signal": 0.08, "away_ranking_signal": -0.08,
        "home_injury_impact": -0.09, "away_injury_impact": 0.09,
        "implied_home_prob": 0.24, "implied_away_prob": -0.18,
        "home_espn_win_pct": 0.11, "away_espn_win_pct": -0.08,
        "home_momentum": 0.10, "away_momentum": -0.08,
        "form_delta": 0.08,
        "home_pts_avg": 0.06, "away_pts_allowed_avg": 0.06,
        "away_pts_avg": -0.05, "home_pts_allowed_avg": -0.05,
        "home_pace_signal": 0.03, "away_pace_signal": -0.03,
    },
}

OUTCOME_MAP  = {"home_win": 1, "away_win": 0, "draw": 2}
OUTCOME_RMAP = {v: k for k, v in OUTCOME_MAP.items()}

_ML_WEIGHT_SCALE = 0.25


# ─────────────────────────────────────────────────────────────────────────────
# PredictionEngine
# ─────────────────────────────────────────────────────────────────────────────

class PredictionEngine:

    def __init__(self):
        self.models: Dict[str, Optional[CalibratedClassifierCV]] = {s: None for s in FEATURE_KEYS}
        self.scalers: Dict[str, RobustScaler] = {s: RobustScaler() for s in FEATURE_KEYS}
        self.is_trained: Dict[str, bool] = {s: False for s in FEATURE_KEYS}
        self.n_training_samples: Dict[str, int] = {s: 0 for s in FEATURE_KEYS}
        # Version is fixed for the server lifetime — never mutated after init
        self.model_version = settings.MODEL_VERSION
        self._load_all()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _model_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"model_{sport}_v{self.model_version}.pkl")

    def _scaler_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"scaler_{sport}_v{self.model_version}.pkl")

    def _meta_path(self, sport: str) -> str:
        return os.path.join(MODEL_DIR, f"meta_{sport}.pkl")

    def _load_all(self):
        for sport in FEATURE_KEYS:
            mp, sp = self._model_path(sport), self._scaler_path(sport)
            if os.path.exists(mp) and os.path.exists(sp):
                try:
                    with open(mp, "rb") as f:
                        self.models[sport] = pickle.load(f)
                    with open(sp, "rb") as f:
                        self.scalers[sport] = pickle.load(f)
                    if os.path.exists(self._meta_path(sport)):
                        with open(self._meta_path(sport), "rb") as f:
                            meta = pickle.load(f)
                            self.n_training_samples[sport] = meta.get("n_samples", 0)
                    self.is_trained[sport] = True
                    logger.info(f"Model loaded [{sport}] v{self.model_version} "
                                f"(n={self.n_training_samples[sport]})")
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

    # ── Feature construction ──────────────────────────────────────────────────

    def features_from_data(
        self,
        home_data: Dict, away_data: Dict, h2h_data: Dict,
        odds_data: Dict, home_venue: Dict, sport: str = "soccer",
    ) -> Dict[str, float]:
        sport = sport.lower()
        f: Dict[str, float] = dict(_DEFAULTS)

        f["home_form_rating"]     = float(home_data.get("form_rating", 0.5))
        f["away_form_rating"]     = float(away_data.get("form_rating", 0.5))
        f["home_win_rate_signal"] = float(home_data.get("win_rate_signal", 0.5))
        f["away_win_rate_signal"] = float(away_data.get("win_rate_signal", 0.5))
        f["home_ranking_signal"]  = float(home_data.get("ranking_signal", 0.5))
        f["away_ranking_signal"]  = float(away_data.get("ranking_signal", 0.5))
        f["home_espn_win_pct"]    = float(home_data.get("espn_win_pct", 0.5))
        f["away_espn_win_pct"]    = float(away_data.get("espn_win_pct", 0.5))
        f["home_momentum"]        = float(home_data.get("momentum", 0.5))
        f["away_momentum"]        = float(away_data.get("momentum", 0.5))

        raw_delta = f["home_form_rating"] - f["away_form_rating"]
        f["form_delta"] = float(np.clip((raw_delta + 1.0) / 2.0, 0.0, 1.0))

        f["home_advantage_signal"] = float(home_venue.get("home_advantage_signal", 0.54))
        f["home_injury_impact"]    = float(home_data.get("estimated_squad_impact", 0.0))
        f["away_injury_impact"]    = float(away_data.get("estimated_squad_impact", 0.0))

        h2h_total = h2h_data.get("total_games", 0)
        f["h2h_home_win_rate"] = (
            h2h_data.get("home_wins", 0) / h2h_total if h2h_total > 0 else 0.5
        )

        if odds_data.get("implied_home_prob") is not None:
            f["implied_home_prob"] = float(odds_data["implied_home_prob"])
        if odds_data.get("implied_away_prob") is not None:
            f["implied_away_prob"] = float(odds_data["implied_away_prob"])

        if sport == "soccer":
            f["home_goals_scored_avg"]   = float(home_data.get("goals_scored_avg", 1.40))
            f["home_goals_conceded_avg"] = float(home_data.get("goals_conceded_avg", 1.10))
            f["away_goals_scored_avg"]   = float(away_data.get("goals_scored_avg", 1.15))
            f["away_goals_conceded_avg"] = float(away_data.get("goals_conceded_avg", 1.35))
            f["home_clean_sheet_rate"]   = float(home_data.get("clean_sheet_rate", 0.28))
            f["away_clean_sheet_rate"]   = float(away_data.get("clean_sheet_rate", 0.22))

        elif sport == "basketball":
            def _norm_pts(v: float) -> float:
                return float(np.clip((v - 80.0) / 60.0, 0.0, 1.0))
            f["home_pts_avg"]         = _norm_pts(float(home_data.get("pts_avg", 110.0)))
            f["away_pts_avg"]         = _norm_pts(float(away_data.get("pts_avg", 110.0)))
            f["home_pts_allowed_avg"] = 1.0 - _norm_pts(float(home_data.get("pts_allowed_avg", 110.0)))
            f["away_pts_allowed_avg"] = 1.0 - _norm_pts(float(away_data.get("pts_allowed_avg", 110.0)))
            f["home_pace_signal"]     = float(home_data.get("pace_signal", 0.5))
            f["away_pace_signal"]     = float(away_data.get("pace_signal", 0.5))

        for k in list(f):
            f[k] = self._sanitize_value(k, f[k])

        return f

    def _sanitize_value(self, key: str, value: Any) -> float:
        default = _DEFAULTS.get(key, 0.5)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = default

        if not np.isfinite(numeric):
            numeric = default

        if key not in _RAW_STAT_KEYS:
            numeric = float(np.clip(numeric, 0.0, 1.0))
        return numeric

    def _sanitize_probabilities(self, probabilities: np.ndarray) -> np.ndarray:
        sanitized = np.asarray(probabilities, dtype=np.float64)
        sanitized = np.nan_to_num(sanitized, nan=0.5, posinf=1.0, neginf=0.0)
        return np.clip(sanitized, 1e-6, 1.0 - 1e-6)

    def _fv(self, features: Dict[str, float], sport: str) -> np.ndarray:
        keys = FEATURE_KEYS.get(sport, FEATURE_KEYS["soccer"])
        return np.array([self._sanitize_value(k, features.get(k, _DEFAULTS.get(k, 0.5))) for k in keys], dtype=np.float64)

    # ── Prior prediction ──────────────────────────────────────────────────────

    def _prior(self, features: Dict[str, float], sport: str) -> Tuple[float, float, float]:
        weights = _PRIOR.get(sport, _PRIOR["soccer"])
        score = 0.50
        for feat, w in weights.items():
            score += w * (features.get(feat, 0.5) - 0.5)

        home_prob = float(np.clip(score, 0.08, 0.92))

        if sport == "basketball":
            away_prob = float(np.clip(1.0 - home_prob, 0.08, 0.92))
            total = home_prob + away_prob
            if total <= 0:
                return (0.5, 0.5, 0.0)
            return home_prob / total, away_prob / total, 0.0

        evenness = 1.0 - abs(home_prob - 0.50) * 2.0
        draw_prob = float(np.clip(0.26 * evenness, 0.04, 0.35))
        away_prob = float(np.clip(1.0 - home_prob - draw_prob, 0.05, 0.85))

        total = home_prob + away_prob + draw_prob
        if total <= 0:
            return (1/3, 1/3, 1/3)
        return home_prob / total, away_prob / total, draw_prob / total

    def _ml_weight(self, sport: str) -> float:
        n = self.n_training_samples.get(sport, 0)
        if n < 30:
            return 0.0
        import math
        w = _ML_WEIGHT_SCALE * math.log10(n)
        return float(min(w, 0.92))

    # ── Main predict ──────────────────────────────────────────────────────────

    def predict(self, features: Dict[str, float], sport: str = "soccer") -> Dict[str, Any]:
        sport = sport.lower()
        fv    = self._fv(features, sport)
        model = self.models.get(sport)

        prior_h, prior_a, prior_d = self._prior(features, sport)
        w_ml = self._ml_weight(sport)

        if self.is_trained.get(sport) and model is not None and w_ml > 0:
            try:
                fv_scaled = self.scalers[sport].transform(fv.reshape(1, -1))
                probs_arr = self._sanitize_probabilities(model.predict_proba(fv_scaled)[0])
                classes   = list(model.classes_)
                class_map = dict(zip(classes, probs_arr))

                ml_h = float(class_map.get(1, 0.33))
                ml_a = float(class_map.get(0, 0.33))
                ml_d = float(class_map.get(2, 0.0)) if 2 in class_map else max(0.0, 1.0 - ml_h - ml_a)

                home_prob = w_ml * ml_h + (1 - w_ml) * prior_h
                away_prob = w_ml * ml_a + (1 - w_ml) * prior_a
                draw_prob = w_ml * ml_d + (1 - w_ml) * prior_d

            except Exception as e:
                logger.warning(f"[{sport}] ML predict error, using prior: {e}")
                home_prob, away_prob, draw_prob = prior_h, prior_a, prior_d
                w_ml = 0.0
        else:
            home_prob, away_prob, draw_prob = prior_h, prior_a, prior_d
            w_ml = 0.0

        home_prob = float(np.clip(home_prob, 0.03, 0.97))
        away_prob = float(np.clip(away_prob, 0.03, 0.97))
        if sport == "basketball":
            draw_prob = 0.0
            total = home_prob + away_prob
        else:
            draw_prob = float(np.clip(draw_prob, 0.0,  0.42))
            total = home_prob + away_prob + draw_prob
        home_prob, away_prob, draw_prob = home_prob / total, away_prob / total, draw_prob / total

        probs_map = {"home_win": home_prob, "away_win": away_prob}
        if sport != "basketball" and draw_prob > 0.0:
            probs_map["draw"] = draw_prob

        predicted_outcome = max(probs_map, key=probs_map.__getitem__)
        winning_prob      = probs_map[predicted_outcome]

        n_outcomes = 2 if sport == "basketball" else 3
        baseline   = 1.0 / n_outcomes
        confidence = float(np.clip((winning_prob - baseline) / (1.0 - baseline), 0.0, 1.0))

        ci_low, ci_high = self._analytical_ci(features, home_prob, sport)

        return {
            "home_win_probability":       round(home_prob, 4),
            "away_win_probability":       round(away_prob, 4),
            "draw_probability":           round(draw_prob, 4),
            "predicted_outcome":          predicted_outcome,
            "confidence_score":           round(confidence, 4),
            "confidence_interval_low":    round(ci_low, 4),
            "confidence_interval_high":   round(ci_high, 4),
            "model_version":              self.model_version,
            "is_trained_model":           self.is_trained.get(sport, False),
            "ml_weight":                  round(w_ml, 3),
            "sport":                      sport,
        }

    def _analytical_ci(
        self,
        features: Dict[str, float],
        home_prob: float,
        sport: str,
    ) -> Tuple[float, float]:
        key_signals = [
            features.get("implied_home_prob", 0.5),
            features.get("home_form_rating",  0.5),
            features.get("home_espn_win_pct", 0.5),
            features.get("h2h_home_win_rate", 0.5),
        ]
        signal_strength = float(np.mean([abs(s - 0.5) * 2.0 for s in key_signals]))

        n_eff = self.n_training_samples.get(sport, 0)

        import math
        pseudo_count = 5.0 + signal_strength * 15.0 + math.log1p(n_eff) * 1.5

        a = home_prob * pseudo_count
        b = (1.0 - home_prob) * pseudo_count

        ci_low  = float(np.clip(beta_dist.ppf(0.10, max(a, 0.1), max(b, 0.1)), 0.0, 1.0))
        ci_high = float(np.clip(beta_dist.ppf(0.90, max(a, 0.1), max(b, 0.1)), 0.0, 1.0))

        if ci_high - ci_low < 0.04:
            mid = (ci_low + ci_high) / 2
            ci_low, ci_high = mid - 0.02, mid + 0.02

        return ci_low, ci_high

    # ── Training ──────────────────────────────────────────────────────────────

    def retrain(self, training_records: List[Dict], sport: str = "soccer") -> Dict[str, Any]:
        sport     = sport.lower()
        min_samples = settings.MIN_TRAINING_SAMPLES

        if len(training_records) < min_samples:
            return {"status": "skipped", "samples": len(training_records), "sport": sport}

        rows, labels, weights = [], [], []
        now = datetime.now(WAT)

        for rec in training_records:
            feats   = rec.get("features", {})
            outcome = rec.get("actual_outcome")
            if not feats or outcome not in OUTCOME_MAP:
                continue

            rows.append(self._fv(feats, sport))
            labels.append(OUTCOME_MAP[outcome])

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

        if len(rows) < min_samples:
            return {"status": "skipped", "samples": len(rows), "sport": sport}

        X = np.array(rows)
        y = np.array(labels)
        w = np.array(weights)
        n = len(rows)

        unique_classes, class_counts = np.unique(y, return_counts=True)
        if len(unique_classes) < 2:
            logger.warning(f"[{sport}] Retrain skipped — need at least 2 outcome classes, got {unique_classes.tolist()}")
            return {
                "status": "skipped",
                "sport": sport,
                "samples": len(rows),
                "reason": "insufficient_class_diversity",
            }

        min_class_count = int(class_counts.min())
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

        self.scalers[sport].fit(X)
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
        self.models[sport] = CalibratedClassifierCV(
            base, method=cal_method,
            cv=StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42),
        )

        self.models[sport].fit(X_scaled, y, sample_weight=w)  # type: ignore[union-attr]
        self.is_trained[sport]         = True
        self.n_training_samples[sport] = n

        # Log feature importances
        try:
            base_est = self.models[sport].calibrated_classifiers_[0].estimator  # type: ignore
            importances = base_est.feature_importances_
            keys = FEATURE_KEYS.get(sport, [])
            top = sorted(zip(keys, importances), key=lambda x: -x[1])[:8]
            logger.info(f"[{sport}] Top features: " + ", ".join(f"{k}={v:.3f}" for k, v in top))
        except Exception:
            pass

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

        logger.info(
            f"[{sport}] Retrained — n={n}, brier={bs:.4f}, "
            f"log_loss={ll:.4f}, calibration={cal_method}, v={self.model_version}"
        )
        return {
            "status": "retrained", "sport": sport, "samples": n,
            "brier_score": round(bs, 4), "log_loss": round(ll, 4),
            "calibration_method": cal_method, "ml_weight": round(self._ml_weight(sport), 3),
            "new_version": self.model_version,
        }

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, records: List[Dict], sport: str = "soccer") -> Dict[str, float]:
        if not records:
            return {}
        probs_home, actuals = [], []
        for rec in records:
            pred = self._sanitize_probabilities(np.array([rec.get("home_win_probability", 0.5)], dtype=np.float64))[0]
            actual = rec.get("actual_outcome")
            if actual is None:
                continue
            probs_home.append(float(pred))
            actuals.append(1 if actual == "home_win" else 0)

        if len(probs_home) < 2:
            return {}

        p  = np.array(probs_home)
        y  = np.array(actuals)
        ll = float(log_loss(y, p, labels=[0, 1]))
        bs = float(brier_score_loss(y, p))
        predicted_home = (p >= 0.5).astype(int)
        accuracy = float(np.mean(predicted_home == y))

        n_bins = 10
        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            mask = (p >= bin_edges[i]) & (p < bin_edges[i + 1])
            if mask.sum() > 0:
                ece += mask.sum() * abs(p[mask].mean() - y[mask].mean())
        ece = float(ece / max(len(p), 1))

        return {
            "brier_score": round(bs, 4), "log_loss": round(ll, 4),
            "calibration_error": round(ece, 4), "accuracy": round(accuracy, 4),
            "total_predictions": len(probs_home), "sport": sport,
            "ml_weight": round(self._ml_weight(sport), 3),
            "n_training_samples": self.n_training_samples.get(sport, 0),
        }


# Singleton
prediction_engine = PredictionEngine()


def get_current_model_version() -> str:
    return prediction_engine.model_version
