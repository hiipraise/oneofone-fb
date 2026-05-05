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
import math
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
    "home_conceding_freq", "away_conceding_freq",
    "home_form_last5", "away_form_last5",
    "goal_diff_trend_home", "goal_diff_trend_away",
    "home_away_split_strength", "away_split_strength",
    "market_move_home", "market_move_away",
    "attack_home_defense_away",
    "attack_away_defense_home",
    "form_home_away_weakness",
    "odds_form_interaction",
    "xg_home_prior", "xg_away_prior", "xg_total_prior",
]
# Soccer-only platform (basketball support removed)
FEATURE_KEYS: Dict[str, List[str]] = {
    "soccer": _COMMON_FEATURES + _SOCCER_EXTRA,
}

# Soccer-only defaults (basketball normalised 0–1 internally removed)
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
    "home_conceding_freq": 0.72, "away_conceding_freq": 0.76,
    "home_form_last5": 0.5, "away_form_last5": 0.5,
    "goal_diff_trend_home": 0.5, "goal_diff_trend_away": 0.5,
    "home_away_split_strength": 0.5, "away_split_strength": 0.5,
    "market_move_home": 0.0, "market_move_away": 0.0,
    "attack_home_defense_away": 0.5,
    "attack_away_defense_home": 0.5,
    "form_home_away_weakness": 0.5,
    "odds_form_interaction": 0.5,
    "xg_home_prior": 1.35, "xg_away_prior": 1.10, "xg_total_prior": 2.45,
}

# Keys that carry raw values outside [0, 1] — must NOT be clipped
_RAW_STAT_KEYS = frozenset({
    "home_goals_scored_avg", "home_goals_conceded_avg",
    "away_goals_scored_avg", "away_goals_conceded_avg",
    "home_pts_avg", "away_pts_avg",
    "home_pts_allowed_avg", "away_pts_allowed_avg",
    "xg_home_prior", "xg_away_prior", "xg_total_prior",
    "market_move_home", "market_move_away",
})

# Soccer-only prior weights (basketball branch removed)
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
        # Outcome balance tracking for ML weight modulation
        self.outcome_balance: Dict[str, Dict[str, Any]] = {s: {} for s in FEATURE_KEYS}
        # Version is fixed for the server lifetime — never mutated after init
        self.model_version = settings.MODEL_VERSION
        self._load_all()

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
            f["home_conceding_freq"] = float(np.clip(1.0 - f["home_clean_sheet_rate"], 0.0, 1.0))
            f["away_conceding_freq"] = float(np.clip(1.0 - f["away_clean_sheet_rate"], 0.0, 1.0))
            f["home_form_last5"] = float(home_data.get("form_last5_weighted", f["home_form_rating"]))
            f["away_form_last5"] = float(away_data.get("form_last5_weighted", f["away_form_rating"]))
            home_gd_trend_raw = float(home_data.get("goal_diff_trend", 0.0))
            away_gd_trend_raw = float(away_data.get("goal_diff_trend", 0.0))
            f["goal_diff_trend_home"] = float(np.clip((home_gd_trend_raw + 2.0) / 4.0, 0.0, 1.0))
            f["goal_diff_trend_away"] = float(np.clip((away_gd_trend_raw + 2.0) / 4.0, 0.0, 1.0))
            f["home_away_split_strength"] = float(home_data.get("home_split_strength", f["home_form_rating"]))
            f["away_split_strength"] = float(away_data.get("away_split_strength", f["away_form_rating"]))
            f["market_move_home"] = float(np.clip(odds_data.get("market_move_home", 0.0), -0.2, 0.2))
            f["market_move_away"] = float(np.clip(odds_data.get("market_move_away", 0.0), -0.2, 0.2))

            atk_home = float(np.clip(f["home_goals_scored_avg"] / 2.5, 0.0, 1.0))
            def_away_weak = float(np.clip(f["away_goals_conceded_avg"] / 2.5, 0.0, 1.0))
            atk_away = float(np.clip(f["away_goals_scored_avg"] / 2.5, 0.0, 1.0))
            def_home_weak = float(np.clip(f["home_goals_conceded_avg"] / 2.5, 0.0, 1.0))
            f["attack_home_defense_away"] = atk_home * def_away_weak
            f["attack_away_defense_home"] = atk_away * def_home_weak
            away_weakness = float(np.clip((f["away_conceding_freq"] + (1.0 - f["away_form_rating"])) / 2.0, 0.0, 1.0))
            f["form_home_away_weakness"] = f["home_form_last5"] * away_weakness
            f["odds_form_interaction"] = float(np.clip(f["implied_home_prob"] * (0.5 + f["form_delta"]), 0.0, 1.0))
            xg_home, xg_away = self._estimate_soccer_xg(f)
            f["xg_home_prior"] = xg_home
            f["xg_away_prior"] = xg_away
            f["xg_total_prior"] = xg_home + xg_away

        # Basketball branch removed (soccer-only)

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

    def _align_feature_vector(self, fv: np.ndarray, sport: str) -> np.ndarray:
        """Align live feature vectors with persisted scaler/model input width."""
        expected = getattr(self.scalers.get(sport), "n_features_in_", None)
        if expected is None and self.models.get(sport) is not None:
            expected = getattr(self.models[sport], "n_features_in_", None)
        if expected is None:
            return fv

        expected = int(expected)
        current = int(fv.shape[0])
        if current == expected:
            return fv

        if current > expected:
            logger.info(
                "[%s] Trimming feature vector from %s to %s for model compatibility",
                sport,
                current,
                expected,
            )
            return fv[:expected]

        keys = FEATURE_KEYS.get(sport, FEATURE_KEYS["soccer"])
        defaults = []
        for idx in range(current, expected):
            if idx < len(keys):
                key = keys[idx]
                defaults.append(self._sanitize_value(key, _DEFAULTS.get(key, 0.5)))
            else:
                defaults.append(0.5)
        pad = np.array(defaults, dtype=np.float64)
        logger.info(
            "[%s] Padding feature vector from %s to %s for model compatibility",
            sport,
            current,
            expected,
        )
        return np.concatenate([fv, pad])

    def _sigmoid(self, x: float) -> float:
        x = float(np.clip(x, -12.0, 12.0))
        return 1.0 / (1.0 + np.exp(-x))

    def _estimate_soccer_xg(self, features: Dict[str, float]) -> Tuple[float, float]:
        attack_home = float(np.clip(features.get("home_goals_scored_avg", 1.4), 0.2, 4.0))
        defense_home = float(np.clip(features.get("home_goals_conceded_avg", 1.1), 0.2, 4.0))
        attack_away = float(np.clip(features.get("away_goals_scored_avg", 1.15), 0.2, 4.0))
        defense_away = float(np.clip(features.get("away_goals_conceded_avg", 1.35), 0.2, 4.0))

        pace = float(np.clip((features.get("home_momentum", 0.5) + features.get("away_momentum", 0.5)) / 2.0, 0.0, 1.0))
        form_edge = float(np.clip(features.get("form_delta", 0.5) - 0.5, -0.5, 0.5))
        imp_home = float(np.clip(features.get("implied_home_prob", 0.5), 0.02, 0.9))
        imp_away = float(np.clip(features.get("implied_away_prob", 0.5), 0.02, 0.9))
        odds_bias = np.log((imp_home + 1e-6) / (imp_away + 1e-6))

        base_home = (attack_home * 0.62 + defense_away * 0.38)
        base_away = (attack_away * 0.62 + defense_home * 0.38)

        xg_home = base_home * (1.0 + 0.12 * form_edge + 0.14 * pace + 0.08 * odds_bias)
        xg_away = base_away * (1.0 - 0.12 * form_edge + 0.14 * pace - 0.08 * odds_bias)

        home_inj = float(np.clip(features.get("home_injury_impact", 0.0), 0.0, 0.5))
        away_inj = float(np.clip(features.get("away_injury_impact", 0.0), 0.0, 0.5))
        xg_home *= (1.0 - home_inj * 0.55)
        xg_away *= (1.0 - away_inj * 0.55)
        return float(np.clip(xg_home, 0.2, 4.5)), float(np.clip(xg_away, 0.2, 4.5))

    def _poisson_prob_matrix(self, home_xg: float, away_xg: float, max_goals: int = 8) -> np.ndarray:
        mat = np.zeros((max_goals + 1, max_goals + 1), dtype=np.float64)
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                mat[h, a] = ((home_xg ** h * np.exp(-home_xg)) / math.factorial(h)) * (
                    (away_xg ** a * np.exp(-away_xg)) / math.factorial(a)
                )
        total = float(np.sum(mat))
        if total <= 0:
            return np.full_like(mat, 1.0 / mat.size)
        return mat / total

    # ── Prior prediction ──────────────────────────────────────────────────────

    def _prior(self, features: Dict[str, float], sport: str) -> Tuple[float, float, float]:
        weights = _PRIOR.get(sport, _PRIOR["soccer"])
        score = 0.0
        for feat, w in weights.items():
            score += w * (features.get(feat, 0.5) - 0.5)

        if sport == "soccer":
            interaction = (
                0.22 * (features.get("attack_home_defense_away", 0.5) - 0.5)
                - 0.18 * (features.get("attack_away_defense_home", 0.5) - 0.5)
                + 0.15 * (features.get("form_home_away_weakness", 0.5) - 0.5)
                + 0.17 * (features.get("odds_form_interaction", 0.5) - 0.5)
            )
            score += interaction
        home_prob = float(np.clip(self._sigmoid(score), 0.06, 0.94))

        # Soccer-only: basketball branch removed
        xg_home, xg_away = self._estimate_soccer_xg(features)
        xg_total = xg_home + xg_away
        strength_similarity = 1.0 - min(1.0, abs(home_prob - 0.5) * 2.0)
        defensive_balance = float(np.clip((features.get("home_clean_sheet_rate", 0.28) + features.get("away_clean_sheet_rate", 0.22)) / 2.0, 0.0, 1.0))
        low_total_factor = float(np.clip((2.8 - xg_total) / 2.3, 0.0, 1.0))
        draw_prob = float(np.clip(0.08 + 0.23 * strength_similarity * 0.55 + 0.24 * low_total_factor * 0.30 + 0.20 * defensive_balance * 0.15, 0.05, 0.34))
        away_prob = float(np.clip(1.0 - home_prob - draw_prob, 0.05, 0.85))

        total = home_prob + away_prob + draw_prob
        if total <= 0:
            return (1/3, 1/3, 1/3)
        return home_prob / total, away_prob / total, draw_prob / total

    def _ml_weight(self, sport: str) -> float:
        """
        Calculate ML weight with balance awareness.
        
        ### Weight Calculation Strategy
        
        **Sample-Count Ramp:**
          - Minimum activation: 30 samples
          - Full ramp: 30 → 240 samples (scales logarithmically)
          - Reaches baseline weight of 0.93 at 240 samples
        
        **Balance Modifier:**
          - If outcome distribution is balanced (no class has >65% share):
            - Base weight can go up to 0.98 (higher ML trust)
          - If outcome distribution is imbalanced (one class >65%):
            - Base weight capped at 0.90 (maintain higher prior dependency)
        
        **Recency Modifier:**
          - If model evaluated recently (evaluation exists): +0.02 bonus
          - Rewards models that pass recent validation
        
        Result: Sample-driven with quality modulation, never below 0.0, never above 0.98
        """
        n = self.n_training_samples.get(sport, 0)
        min_samples = max(int(settings.MIN_TRAINING_SAMPLES), 1)
        if n < min_samples:
            return 0.0

        import math

        # ── Sample-count ramp (core signal) ───────────────────────────────────
        scaled = math.log1p(n - min_samples + 1.0)
        span = math.log1p((min_samples * 8) - min_samples + 1.0)
        progress = float(np.clip(scaled / max(span, 1e-6), 0.0, 1.0))
        smooth = progress * progress * (3.0 - 2.0 * progress)
        
        # ── Balance awareness: adjust ceiling based on outcome distribution ────
        balance_data = self.outcome_balance.get(sport, {})
        outcome_dist = balance_data.get("distribution", {})
        
        balance_factor = 1.0
        if outcome_dist:
            # Check if any outcome has >65% share (imbalanced)
            max_share = max(outcome_dist.values(), default=0) / max(sum(outcome_dist.values()), 1)
            if max_share > 0.65:
                # Imbalanced: cap at 0.90 (more prior dependency)
                balance_factor = 0.90
            else:
                # Well-balanced: allow up to 0.98
                balance_factor = 0.98
        
        # ── Recency bonus: recent evaluation +0.02 ─────────────────────────────
        recency_bonus = 0.0
        if balance_data.get("last_evaluated"):
            from datetime import datetime, timedelta
            try:
                last_eval = datetime.fromisoformat(balance_data.get("last_evaluated"))
                days_since = (datetime.now(WAT) - last_eval).days
                if days_since <= 7:
                    recency_bonus = 0.02  # Bonus if evaluated within past week
            except Exception:
                pass
        
        # ── Assemble final weight ──────────────────────────────────────────────
        weight = 0.15 + (0.78 * smooth)  # baseline: 0.15-0.93
        weight = weight * balance_factor  # modulate by balance
        weight += recency_bonus
        
        return float(np.clip(weight, 0.0, balance_factor))

    # ── Main predict ──────────────────────────────────────────────────────────

    def predict(self, features: Dict[str, float], sport: str = "soccer") -> Dict[str, Any]:
        sport = sport.lower()
        fv    = self._fv(features, sport)
        model = self.models.get(sport)

        prior_h, prior_a, prior_d = self._prior(features, sport)
        w_ml = self._ml_weight(sport)

        if self.is_trained.get(sport) and model is not None and w_ml > 0:
            try:
                fv_aligned = self._align_feature_vector(fv, sport)
                fv_scaled = self.scalers[sport].transform(fv_aligned.reshape(1, -1))
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

        implied_h = float(np.clip(features.get("implied_home_prob", home_prob), 0.02, 0.96))
        implied_a = float(np.clip(features.get("implied_away_prob", away_prob), 0.02, 0.96))
        implied_d = float(np.clip(1.0 - implied_h - implied_a, 0.01, 0.6))  # Soccer-only

        sample_factor = float(np.clip(np.log1p(self.n_training_samples.get(sport, 0)) / 6.0, 0.0, 1.0))
        dispersion = float(abs(home_prob - away_prob))
        low_conf = float(np.clip(1.0 - (dispersion * 1.6 + sample_factor), 0.0, 1.0))
        market_pull = 0.12 * low_conf

        home_prob = (1.0 - market_pull) * home_prob + market_pull * implied_h
        away_prob = (1.0 - market_pull) * away_prob + market_pull * implied_a
        # Soccer-only: always include draw prob adjustment
        draw_prob = (1.0 - market_pull) * draw_prob + market_pull * implied_d

        if sport == "soccer":
            xg_home, xg_away = self._estimate_soccer_xg(features)
            pmat = self._poisson_prob_matrix(xg_home, xg_away, max_goals=7)
            p_home = float(np.tril(pmat, -1).sum())
            p_draw = float(np.trace(pmat))
            p_away = float(np.triu(pmat, 1).sum())
            # Poisson-informed reconciliation for consistency.
            home_prob = 0.78 * home_prob + 0.22 * p_home
            away_prob = 0.78 * away_prob + 0.22 * p_away
            draw_prob = 0.78 * draw_prob + 0.22 * p_draw
            # Draw balancing:
            # increase draw support for "tight" games where teams are near parity
            # and expected goals are low (typical draw conditions in football).
            parity = float(np.clip(1.0 - abs(home_prob - away_prob) * 2.0, 0.0, 1.0))
            low_total = float(np.clip((3.0 - (xg_home + xg_away)) / 2.0, 0.0, 1.0))
            draw_floor = float(np.clip(0.07 + 0.07 * parity + 0.04 * low_total, 0.06, 0.22))
            if draw_prob < draw_floor:
                lift = draw_floor - draw_prob
                home_prob = max(0.01, home_prob - (lift * 0.5))
                away_prob = max(0.01, away_prob - (lift * 0.5))
                draw_prob = draw_floor
            features["xg_home_prior"] = round(xg_home, 4)
            features["xg_away_prior"] = round(xg_away, 4)
            features["xg_total_prior"] = round(xg_home + xg_away, 4)
            features["poisson_draw_prob"] = round(p_draw, 4)

        home_prob = float(np.clip(home_prob, 0.03, 0.97))
        away_prob = float(np.clip(away_prob, 0.03, 0.97))
        # Soccer-only: always include draw prob
        draw_prob = float(np.clip(draw_prob, 0.0,  0.42))
        total = home_prob + away_prob + draw_prob
        home_prob, away_prob, draw_prob = home_prob / total, away_prob / total, draw_prob / total

        probs_map = {"home_win": home_prob, "away_win": away_prob}
        # Soccer-only: always include draw
        if draw_prob > 0.0:
            probs_map["draw"] = draw_prob

        sorted_probs = sorted(probs_map.items(), key=lambda kv: kv[1], reverse=True)
        predicted_outcome = sorted_probs[0][0]
        winning_prob = sorted_probs[0][1]
        runner_up = sorted_probs[1][1] if len(sorted_probs) > 1 else 0.0

        # Soccer-only: always 3 outcomes
        n_outcomes = 3
        baseline   = 1.0 / n_outcomes
        gap_component = float(np.clip((winning_prob - runner_up) / 0.55, 0.0, 1.0))
        strength_component = float(np.clip((winning_prob - baseline) / (1.0 - baseline), 0.0, 1.0))
        market_vec = np.array([implied_h, implied_a, implied_d], dtype=np.float64)
        model_vec = np.array([home_prob, away_prob, draw_prob], dtype=np.float64)
        prior_vec = np.array([prior_h, prior_a, prior_d], dtype=np.float64)
        agreement = 1.0 - min(1.0, float(np.mean(np.abs(model_vec - market_vec)) + np.mean(np.abs(model_vec - prior_vec))))
        confidence = float(np.clip(0.5 * gap_component + 0.25 * strength_component + 0.25 * agreement, 0.0, 1.0))
        tier = "high" if confidence >= 0.72 else ("medium" if confidence >= 0.48 else "low")

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
            "confidence_tier":            tier,
            "market_edge_home":           round(home_prob - implied_h, 4),
            "market_edge_away":           round(away_prob - implied_a, 4),
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
        # StratifiedKFold ensures each fold has same outcome distribution as full set
        self.models[sport] = CalibratedClassifierCV(
            base, method=cal_method,
            cv=StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42),
        )

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

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, records: List[Dict], sport: str = "soccer") -> Dict[str, Any]:
        """
        Evaluate model performance with stratified outcome-specific metrics.
        
        ### Evaluation Strategy
        
        **Stratification:**
          - Metrics are computed per outcome (home_win, draw, away_win)
          - This reveals if model is calibrated equally across all outcomes
          - Especially important for draws (typically minority class)
        
        **Metrics Computed:**
          - Brier Score: mean squared error between predicted and actual probabilities
          - Log Loss: penalizes confident wrong predictions more heavily
          - Calibration Error (ECE): measures if predicted confidence matches actual accuracy
          - Outcome-specific accuracy: how often top-1 prediction is correct per outcome
        
        **Data Usage:**
          - Holdout set used (created during learning trigger)
          - No data leakage from training set
          - Distribution should match training set outcomes
        """
        if not records:
            return {}

        entries = []
        for rec in records:
            actual = rec.get("actual_outcome")
            if actual is None:
                continue
            ph  = float(np.clip(rec.get("home_win_probability", 0.5), 1e-9, 1 - 1e-9))
            pd_ = float(np.clip(rec.get("draw_probability",      0.0), 1e-9, 1 - 1e-9))
            pa  = float(np.clip(rec.get("away_win_probability",  0.5), 1e-9, 1 - 1e-9))
            # renormalise in case stored values don't sum to 1 exactly
            total = ph + pd_ + pa
            if total > 0:
                ph, pd_, pa = ph / total, pd_ / total, pa / total
            entries.append((ph, pd_, pa, actual))

        if len(entries) < 2:
            return {}

        n = len(entries)
        ph_arr  = np.array([e[0] for e in entries])
        pd_arr  = np.array([e[1] for e in entries])
        pa_arr  = np.array([e[2] for e in entries])
        y_home  = np.array([1.0 if e[3] == "home_win"  else 0.0 for e in entries])
        y_draw  = np.array([1.0 if e[3] == "draw"       else 0.0 for e in entries])
        y_away  = np.array([1.0 if e[3] == "away_win"  else 0.0 for e in entries])

        # ── Outcome Distribution & Stratified Metrics ─────────────────────────────────────
        outcome_counts = {
            "home_win": int(y_home.sum()),
            "draw": int(y_draw.sum()),
            "away_win": int(y_away.sum()),
        }

        # Soccer-only: always include draw outcome
        # ── Multiclass Brier Score ────────────────────────────────────────────────
        bs = float(np.mean(
            (ph_arr - y_home) ** 2 +
            (pd_arr - y_draw) ** 2 +
            (pa_arr - y_away) ** 2
        ))

        # ── Multiclass Log Loss ───────────────────────────────────────────────────
        eps = 1e-9
        ll = -float(np.mean(
            y_home * np.log(np.clip(ph_arr, eps, 1.0)) +
            y_draw * np.log(np.clip(pd_arr, eps, 1.0)) +
            y_away * np.log(np.clip(pa_arr, eps, 1.0))
        ))

        # ── Accuracy (argmax) ─────────────────────────────────────────────────────
        stacked    = np.stack([ph_arr, pd_arr, pa_arr], axis=1)
        pred_class = np.argmax(stacked, axis=1)          # 0=home 1=draw 2=away
        true_class = np.where(y_home == 1, 0, np.where(y_draw == 1, 1, 2))
        accuracy   = float(np.mean(pred_class == true_class))

        # ── Outcome-specific accuracy ───────────────────────────────────────────────────
        outcome_specific_accuracy = {}
        for outcome_label, outcome_name in [(0, "home_win"), (1, "draw"), (2, "away_win")]:
            mask = true_class == outcome_label
            if mask.sum() > 0:
                outcome_specific_accuracy[outcome_name] = float(np.mean(pred_class[mask] == outcome_label))

        # ── ECE averaged across all outcome heads ─────────────────────────────────
        outcome_pairs = [(ph_arr, y_home, "home_win"), (pa_arr, y_away, "away_win"), (pd_arr, y_draw, "draw")]

        n_bins     = 10
        bin_edges  = np.linspace(0.0, 1.0, n_bins + 1)
        ece_total  = 0.0
        outcome_calibration = {}
        for p_arr, y_arr, outcome_name in outcome_pairs:
            outcome_ece = 0.0
            for i in range(n_bins):
                mask = (
                    (p_arr >= bin_edges[i]) & (p_arr <= bin_edges[i + 1])
                    if i == n_bins - 1
                    else (p_arr >= bin_edges[i]) & (p_arr < bin_edges[i + 1])
                )
                if mask.sum() > 0:
                    outcome_ece += mask.sum() * abs(p_arr[mask].mean() - y_arr[mask].mean())
            outcome_ece /= max(n, 1)
            outcome_calibration[outcome_name] = float(round(outcome_ece, 4))
            ece_total += outcome_ece
        ece = float(ece_total / len(outcome_pairs))

        logger.info(
            f"[{sport}] Evaluated: n={n}, accuracy={accuracy:.3f}, "
            f"brier={bs:.4f}, calibration={ece:.4f}, "
            f"outcome_dist={outcome_counts}"
        )
        
        # ── Update evaluation timestamp for ML weight recency bonus ────────────────────────
        if sport in self.outcome_balance:
            self.outcome_balance[sport]["last_evaluated"] = datetime.now(WAT).isoformat()

        return {
            "brier_score":                 round(bs,       4),
            "log_loss":                    round(ll,       4),
            "calibration_error":           round(ece,      4),
            "accuracy":                    round(accuracy, 4),
            "total_predictions":           n,
            "sport":                       sport,
            "ml_weight":                   round(self._ml_weight(sport), 3),
            "n_training_samples":          self.n_training_samples.get(sport, 0),
            # ── Stratified outcome metrics ──────────────────────────────────────────────
            "outcome_distribution":        outcome_counts,  # e.g. {"home_win": 45, "draw": 12, "away_win": 43}
            "outcome_specific_accuracy":   {k: round(v, 4) for k, v in outcome_specific_accuracy.items()},
            "outcome_calibration_error":   outcome_calibration,  # Per-outcome ECE
            "stratified_evaluation_used":  True,
        }


# Singleton
prediction_engine = PredictionEngine()


def get_current_model_version() -> str:
    return prediction_engine.model_version
