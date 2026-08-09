# app/ml/evaluation.py
"""
Model evaluation for the prediction engine
(Sprint 5.3 file split from prediction_engine.py).

Evaluates on the holdout set created during the learning trigger, with
stratified outcome-specific metrics (accuracy, ECE, Brier, log loss) so
draw calibration is not hidden by the home/away majority.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

import numpy as np

from app.utils.timezone import WAT

logger = logging.getLogger(__name__)


class EvaluationMixin:
    """Evaluation for PredictionEngine (mixin)."""

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
