# app/ml/priors.py
"""
Prior probabilities, outcome maps, and the ML-vs-prior weight
(Sprint 5.3 file split from prediction_engine.py).

The prior is a hand-weighted logistic scoring of the feature set; the ML
weight decides how much the trained model can override the prior, with
sample-count ramping and balance/recency modulation.
"""
import logging
from typing import Dict, Tuple

import numpy as np

from app.config.settings import settings
from app.utils.timezone import WAT

logger = logging.getLogger(__name__)

# Soccer-only prior weights
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


class PriorsMixin:
    """Prior-probability and ML-weight logic for PredictionEngine (mixin)."""

    def _sigmoid(self, x: float) -> float:
        x = float(np.clip(x, -12.0, 12.0))
        return 1.0 / (1.0 + np.exp(-x))

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

        # Soccer-only probability path.
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
