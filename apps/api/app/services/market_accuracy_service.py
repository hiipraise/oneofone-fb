"""
Market Accuracy Service

Analyzes prediction accuracy across specific market types:
  - GG (Goals/Goals) — Both Teams To Score
  - Corners — Corner Kicks Over/Under
  - O/U (Over/Under) — Total Goals Over/Under
  
Calculates:
  - Accuracy by market type
  - Confidence threshold analysis
  - Win rates at different confidence levels
  - Optimal confidence thresholds
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from app.utils.timezone import now_wat, WAT
import numpy as np

logger = logging.getLogger(__name__)


class MarketAccuracyAnalyzer:
    """
    Analyzes prediction accuracy across market types and confidence thresholds.
    """
    
    # Market type definitions
    MARKET_TYPES = {
        "gg": "Both Teams To Score (BTTS)",
        "corners": "Corner Kicks",
        "ou": "Total Goals Over/Under",
    }
    
    # Confidence thresholds for stratified analysis
    CONFIDENCE_THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    
    def __init__(self):
        pass
    
    def analyze_market_accuracy(
        self,
        predictions: List[Dict[str, Any]],
        actual_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze accuracy for each market type.
        
        Args:
            predictions: List of prediction documents from DB
            actual_results: Dict mapping match_id to actual result data
                Expected: {
                    "match_id": {
                        "actual_outcome": "home_win|draw|away_win",
                        "home_score": int,
                        "away_score": int,
                        "match_date": str
                    }
                }
        
        Returns:
            {
                "gg": {...},
                "corners": {...},
                "ou": {...},
                "timestamp": str
            }
        """
        results = {
            "gg": self._analyze_btts(predictions, actual_results),
            "corners": self._analyze_corners(predictions, actual_results),
            "ou": self._analyze_goals_ou(predictions, actual_results),
            "timestamp": now_wat().isoformat(),
        }
        return results

    def _get_extended_markets(self, pred: Dict[str, Any]) -> Dict[str, Any]:
        """Return the extended markets payload with backwards-compatible aliases."""
        extended_markets = pred.get("extended_markets") or {}
        if not isinstance(extended_markets, dict):
            return {}

        if "goals_o_u" not in extended_markets and "goals_over_under" in extended_markets:
            extended_markets = dict(extended_markets)
            extended_markets["goals_o_u"] = extended_markets.get("goals_over_under") or {}

        return extended_markets
    
    def _extract_actual_score(
        self, match_id: str, actual_results: Dict
    ) -> Optional[Tuple[int, int]]:
        """Extract (home_score, away_score) from actual results."""
        if match_id not in actual_results:
            return None
        result = actual_results[match_id]
        home_score = result.get("home_score")
        away_score = result.get("away_score")
        if home_score is None or away_score is None:
            return None
        return (int(home_score), int(away_score))
    
    def _analyze_btts(
        self,
        predictions: List[Dict],
        actual_results: Dict
    ) -> Dict[str, Any]:
        """
        Analyze Both Teams To Score (BTTS) accuracy.
        
        BTTS = Yes if both teams score at least 1 goal.
        """
        correct = 0
        total = 0
        confidence_scores: List[float] = []
        
        for pred in predictions:
            match_id = pred.get("match_id")
            scores = self._extract_actual_score(match_id, actual_results)
            if not scores:
                continue
            
            home_score, away_score = scores
            actual_btts = "yes" if home_score > 0 and away_score > 0 else "no"
            
            # Extract BTTS prediction
            extended_markets = self._get_extended_markets(pred)
            btts_pred = extended_markets.get("btts", {})
            predicted_btts = btts_pred.get("result", "").lower()  # "Yes" or "No"
            
            if not predicted_btts:
                continue
            
            total += 1
            if predicted_btts == actual_btts:
                correct += 1
            
            # Collect confidence
            confidence = btts_pred.get("yes_pct", 50) / 100.0
            if predicted_btts == "no":
                confidence = 1.0 - confidence
            confidence_scores.append(confidence)
        
        accuracy = round(correct / total, 4) if total > 0 else None
        avg_confidence = round(np.mean(confidence_scores), 4) if confidence_scores else None
        
        return {
            "name": self.MARKET_TYPES["gg"],
            "market_type": "gg",
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": accuracy,
            "avg_confidence": avg_confidence,
            "samples": len(confidence_scores),
            "confidence_scores": confidence_scores,
        }
    
    def _analyze_corners(
        self,
        predictions: List[Dict],
        actual_results: Dict
    ) -> Dict[str, Any]:
        """
        Analyze Corners Over/Under accuracy.

        Uses stored actual corner totals when available.
        """
        accuracy_by_line: Dict[float, Dict[str, Any]] = {}
        confidence_by_line: Dict[float, List[float]] = {}

        for line in [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]:
            accuracy_by_line[line] = {"correct": 0, "total": 0}
            confidence_by_line[line] = []

        total = 0
        correct = 0
        confidence_scores: List[float] = []

        def _actual_corner_total(match_id: str) -> Optional[int]:
            result = actual_results.get(match_id) or {}
            total_corners = result.get("total_corners")
            if total_corners is not None:
                return int(total_corners)
            home_corners = result.get("home_corners")
            away_corners = result.get("away_corners")
            if home_corners is not None and away_corners is not None:
                return int(home_corners) + int(away_corners)
            return None

        def _primary_corner_pick(corners: Dict[str, Any]) -> Optional[tuple[float, str, float]]:
            best_line = None
            best_side = None
            best_conf = -1.0
            for line_key, line_data in corners.items():
                if not line_key.startswith("line_"):
                    continue
                try:
                    line_value = float(line_key.replace("line_", "").replace("_", "."))
                except Exception:
                    continue
                over_prob = float(line_data.get("over", 0.5))
                under_prob = float(line_data.get("under", 0.5))
                if over_prob >= under_prob:
                    side = "over"
                    conf = over_prob
                else:
                    side = "under"
                    conf = under_prob
                if conf > best_conf:
                    best_conf = conf
                    best_line = line_value
                    best_side = side
            if best_line is None or best_side is None:
                return None
            return best_line, best_side, best_conf
        
        for pred in predictions:
            match_id = pred.get("match_id")
            actual_total = _actual_corner_total(match_id)
            if actual_total is None:
                continue

            extended_markets = self._get_extended_markets(pred)
            corners = extended_markets.get("corners", {})
            if not corners:
                continue

            primary_pick = _primary_corner_pick(corners)
            if not primary_pick:
                continue

            line_value, predicted_side, confidence = primary_pick
            actual_side = "over" if actual_total > line_value else "under"

            total += 1
            if predicted_side == actual_side:
                correct += 1

            confidence_scores.append(confidence)
            confidence_by_line[line_value].append(confidence)
            accuracy_by_line[line_value]["total"] += 1
            if predicted_side == actual_side:
                accuracy_by_line[line_value]["correct"] += 1
        
        avg_confidence = round(np.mean(confidence_scores), 4) if confidence_scores else None
        accuracy = round(correct / total, 4) if total > 0 else None
        accuracy_per_line = {
            line: {
                "accuracy": round(vals["correct"] / vals["total"], 4),
                "samples": vals["total"],
                "avg_confidence": round(np.mean(confidence_by_line[line]), 4) if confidence_by_line[line] else None,
            }
            for line, vals in accuracy_by_line.items()
            if vals["total"] > 0
        }
        
        return {
            "name": self.MARKET_TYPES["corners"],
            "market_type": "corners",
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": accuracy,
            "avg_confidence": avg_confidence,
            "samples": len(confidence_scores),
            "confidence_scores": confidence_scores,
            "accuracy_per_line": accuracy_per_line,
            "note": "Corner accuracy uses stored total corner counts when available",
        }
    
    def _analyze_goals_ou(
        self,
        predictions: List[Dict],
        actual_results: Dict
    ) -> Dict[str, Any]:
        """
        Analyze Over/Under Goals accuracy.
        
        Tests common O/U lines: 0.5, 1.5, 2.5, 3.5, 4.5
        """
        # Track accuracy per line
        accuracy_by_line: Dict[float, Dict[str, Any]] = {}
        confidence_by_line: Dict[float, List[float]] = {}
        
        for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
            accuracy_by_line[line] = {"correct": 0, "total": 0}
            confidence_by_line[line] = []
        
        overall_correct = 0
        overall_total = 0
        overall_confidence: List[float] = []
        
        for pred in predictions:
            match_id = pred.get("match_id")
            scores = self._extract_actual_score(match_id, actual_results)
            if not scores:
                continue
            
            home_score, away_score = scores
            actual_total = home_score + away_score
            
            extended_markets = self._get_extended_markets(pred)
            goals_ou = extended_markets.get("goals_o_u", {})
            
            for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
                line_key = f"over_{str(line).replace('.', '_')}"
                line_pred = goals_ou.get(line_key, {})
                
                if not line_pred:
                    continue
                
                over_prob = line_pred.get("over", 0.5)
                under_prob = line_pred.get("under", 0.5)
                
                # Predicted outcome
                predicted_ou = "over" if over_prob >= 0.5 else "under"
                actual_ou = "over" if actual_total >= line else "under"
                
                accuracy_by_line[line]["total"] += 1
                overall_total += 1
                
                if predicted_ou == actual_ou:
                    accuracy_by_line[line]["correct"] += 1
                    overall_correct += 1
                
                # Confidence is the max of over/under
                confidence = max(over_prob, under_prob)
                confidence_by_line[line].append(confidence)
                overall_confidence.append(confidence)
        
        # Build per-line accuracy
        accuracy_per_line = {}
        for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
            line_data = accuracy_by_line[line]
            if line_data["total"] > 0:
                accuracy_per_line[line] = {
                    "accuracy": round(
                        line_data["correct"] / line_data["total"],
                        4
                    ),
                    "samples": line_data["total"],
                    "avg_confidence": round(
                        np.mean(confidence_by_line[line]),
                        4
                    ) if confidence_by_line[line] else None,
                }
        
        overall_accuracy = round(overall_correct / overall_total, 4) if overall_total > 0 else None
        overall_avg_conf = round(np.mean(overall_confidence), 4) if overall_confidence else None
        
        return {
            "name": self.MARKET_TYPES["ou"],
            "market_type": "ou",
            "total_predictions": overall_total,
            "correct_predictions": overall_correct,
            "accuracy": overall_accuracy,
            "avg_confidence": overall_avg_conf,
            "samples": len(overall_confidence),
            "confidence_scores": overall_confidence,
            "accuracy_per_line": accuracy_per_line,
        }
    
    def analyze_confidence_thresholds(
        self,
        predictions: List[Dict[str, Any]],
        actual_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze prediction accuracy at different confidence thresholds.
        
        Returns accuracy breakdown for each threshold:
          - 50% confidence and above
          - 60% confidence and above
          - 70% confidence and above
          - etc.
        """
        threshold_results = {}
        
        for threshold in self.CONFIDENCE_THRESHOLDS:
            threshold_predictions = [
                p for p in predictions
                if (p.get("confidence_score") or 0.0) >= threshold
            ]
            
            if not threshold_predictions:
                threshold_results[threshold] = {
                    "threshold": threshold,
                    "count": 0,
                    "accuracy": None,
                    "correct": 0,
                }
                continue
            
            # Calculate accuracy for predictions at this threshold
            correct = 0
            total = 0
            for pred in threshold_predictions:
                match_id = pred.get("match_id")
                if match_id not in actual_results:
                    continue
                
                actual_result = actual_results[match_id]
                actual_outcome = actual_result.get("actual_outcome")
                predicted_outcome = pred.get("predicted_outcome")
                
                if not actual_outcome or not predicted_outcome:
                    continue
                
                total += 1
                if predicted_outcome == actual_outcome:
                    correct += 1
            
            accuracy = round(correct / total, 4) if total > 0 else None
            
            threshold_results[threshold] = {
                "threshold": threshold,
                "count": len(threshold_predictions),
                "scored": total,
                "accuracy": accuracy,
                "correct": correct,
                "accuracy_pct": round(accuracy * 100, 1) if accuracy else None,
            }
        
        # Find the optimal threshold (highest accuracy with minimum samples)
        valid_thresholds = [
            (t, r) for t, r in threshold_results.items()
            if r["accuracy"] is not None and r["scored"] >= 5
        ]
        
        optimal = None
        if valid_thresholds:
            # Sort by accuracy (descending), then by count (descending)
            valid_thresholds.sort(
                key=lambda x: (-x[1]["accuracy"], -x[1]["count"]),
            )
            optimal_threshold, optimal_data = valid_thresholds[0]
            optimal = {
                "threshold": optimal_threshold,
                "accuracy": optimal_data["accuracy"],
                "accuracy_pct": optimal_data["accuracy_pct"],
                "samples": optimal_data["scored"],
            }
        
        return {
            "threshold_breakdown": threshold_results,
            "optimal_threshold": optimal,
            "timestamp": now_wat().isoformat(),
        }
    
    def get_confidence_distribution(
        self,
        predictions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze the distribution of confidence scores.
        
        Returns histogram-style data showing how many predictions
        fall into each confidence bracket.
        """
        confidence_scores = [
            float(p.get("confidence_score") or 0.0)
            for p in predictions
        ]
        
        if not confidence_scores:
            return {"bins": {}, "total": 0}
        
        # Create 10 bins: 0-10%, 10-20%, ..., 90-100%
        bins = {
            f"{i*10}-{(i+1)*10}%": 0
            for i in range(10)
        }
        
        for score in confidence_scores:
            bin_idx = min(int(score * 10), 9)
            bin_key = f"{bin_idx*10}-{(bin_idx+1)*10}%"
            bins[bin_key] += 1
        
        return {
            "bins": bins,
            "total": len(confidence_scores),
            "mean_confidence": round(np.mean(confidence_scores), 4),
            "median_confidence": round(float(np.median(confidence_scores)), 4),
            "std_confidence": round(float(np.std(confidence_scores)), 4),
        }
    
    def get_market_type_counts(
        self,
        predictions: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Count predictions that have predictions for each market type."""
        counts = {"gg": 0, "corners": 0, "ou": 0}
        
        for pred in predictions:
            extended = self._get_extended_markets(pred)
            if extended.get("btts"):
                counts["gg"] += 1
            if extended.get("corners"):
                counts["corners"] += 1
            if extended.get("goals_o_u"):
                counts["ou"] += 1
        
        return counts


# Singleton instance
market_accuracy_analyzer = MarketAccuracyAnalyzer()
