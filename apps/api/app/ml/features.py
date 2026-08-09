# app/ml/features.py
"""
Feature definitions and construction for the prediction engine
(Sprint 5.3 file split from prediction_engine.py).

Owns the feature catalog (FEATURE_KEYS / _DEFAULTS / _RAW_STAT_KEYS) and
the feature-vector helpers used by both training and live prediction.

Raw stats (goals_scored_avg, goals_conceded_avg, pts_avg, pts_allowed_avg,
xg_*_prior, market_move_*) are NOT 0-1 signals and must NOT be clipped to
[0, 1] — see _RAW_STAT_KEYS.
"""
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

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
# Soccer-only platform
FEATURE_KEYS: Dict[str, List[str]] = {
    "soccer": _COMMON_FEATURES + _SOCCER_EXTRA,
}

# Soccer-only defaults
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


class FeaturesMixin:
    """Feature construction helpers for PredictionEngine (mixin)."""

    # ── Feature construction ──────────────────────────────────────────────────

    def features_from_data(
        self,
        home_data: Dict, away_data: Dict, h2h_data: Dict,
        odds_data: Dict, home_venue: Dict, sport: str = "soccer",
        scraped_xg: Optional[Dict[str, Any]] = None,
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
            # Real expected goals (Understat) when the free source covers the
            # fixture; otherwise fall back to the heuristic estimate. The
            # xg_from_scrape marker lets _estimate_soccer_xg / predict() / the
            # Poisson matrix reuse the real values instead of recomputing them.
            scraped_home_xg = float((scraped_xg or {}).get("home_xg") or 0.0)
            scraped_away_xg = float((scraped_xg or {}).get("away_xg") or 0.0)
            if scraped_home_xg > 0 and scraped_away_xg > 0:
                f["xg_from_scrape"] = 1.0
                f["xg_home_prior"] = float(np.clip(scraped_home_xg, 0.2, 4.5))
                f["xg_away_prior"] = float(np.clip(scraped_away_xg, 0.2, 4.5))
                f["xg_total_prior"] = f["xg_home_prior"] + f["xg_away_prior"]
            else:
                xg_home, xg_away = self._estimate_soccer_xg(f)
                f["xg_home_prior"] = xg_home
                f["xg_away_prior"] = xg_away
                f["xg_total_prior"] = xg_home + xg_away

        # Soccer-only features are normalized here.

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

    def _estimate_soccer_xg(self, features: Dict[str, float]) -> Tuple[float, float]:
        # Real xG captured from a scrape at feature-construction time wins over
        # the heuristic — used by predict()'s Poisson matrix and the draw prior
        # so every downstream consumer sees the same expected goals.
        if features.get("xg_from_scrape"):
            xg_home = float(np.clip(features.get("xg_home_prior", 1.4), 0.2, 4.5))
            xg_away = float(np.clip(features.get("xg_away_prior", 1.1), 0.2, 4.5))
            return xg_home, xg_away
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
