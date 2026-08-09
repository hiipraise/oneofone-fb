# app/ml/calibration.py
"""
Live prediction + analytical confidence interval for the prediction engine
(Sprint 5.3 file split from prediction_engine.py).

The prediction path soft-ensembles the ML model (when trained and weight
> 0) with the calibrated prior, pulls toward implied market odds on low
confidence, and reconciles with a Poisson goal matrix for soccer. The
confidence interval is computed analytically via a Beta distribution.
"""
import logging
from typing import Any, Dict, Tuple

import numpy as np
from scipy.stats import beta as beta_dist

logger = logging.getLogger(__name__)


class CalibrationMixin:
    """Probability calibration + predict for PredictionEngine (mixin)."""

    def _sanitize_probabilities(self, probabilities: np.ndarray) -> np.ndarray:
        sanitized = np.asarray(probabilities, dtype=np.float64)
        sanitized = np.nan_to_num(sanitized, nan=0.5, posinf=1.0, neginf=0.0)
        return np.clip(sanitized, 1e-6, 1.0 - 1e-6)

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
        # Sample-aware market pull: when the ML model is weak or untrained
        # (low ml_weight) the de-vigged bookmaker line carries most of the
        # signal, so we lean on it harder; as the model matures we fade the
        # pull and trust our own probabilities more.
        model_weakness = float(np.clip(1.0 - w_ml, 0.0, 1.0))
        market_pull = (0.05 + 0.25 * model_weakness) * low_conf
        market_pull = float(np.clip(market_pull, 0.0, 0.35))

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
