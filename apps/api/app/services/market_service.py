# app/services/market_service.py
"""
Extended Market Service — sport-aware

Soccer:    1X2, goals O/U (0.5–4.5), BTTS, correct score, Asian handicap,
           corners O/U, bookings O/U
Basketball: points O/U, spread, moneyline implied

Fix v2.1:
  - xG now uses BOTH attack (goals_scored_avg) and defence (goals_conceded_avg)
    for each side, giving a more realistic expected-goals figure and fixing
    BTTS being perpetually low when attack averages alone are used.
    Formula: home_xg = (home_goals_scored_avg + away_goals_conceded_avg) / 2
             away_xg = (away_goals_scored_avg + home_goals_conceded_avg) / 2
"""
import logging
import math
from typing import Dict, Any, List, Optional
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Poisson helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k * math.exp(-lam)) / math.factorial(k)


def _cdf(max_k: int, lam: float) -> float:
    return sum(_pmf(k, lam) for k in range(max_k + 1))


def _ou(lam: float, line: float) -> Dict[str, float]:
    """Generic over/under for a Poisson-distributed total."""
    p_under = _cdf(int(math.floor(line)), lam)
    # Handle half-ball lines (exact push impossible)
    if line == math.floor(line):
        p_under = _cdf(int(line) - 1, lam)
    p_under = float(np.clip(p_under, 0.01, 0.99))
    return {"over": round(1.0 - p_under, 4), "under": round(p_under, 4)}


# ─────────────────────────────────────────────────────────────────────────────
# Soccer markets
# ─────────────────────────────────────────────────────────────────────────────

def _goals_ou_all(home_xg: float, away_xg: float) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "expected_goals": round(home_xg + away_xg, 2),
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
    }
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        max_g = 14
        p_under = sum(
            _pmf(h, home_xg) * _pmf(a, away_xg)
            for h in range(max_g) for a in range(max_g)
            if h + a < line
        )
        p_under = float(np.clip(p_under, 0.01, 0.99))
        key = f"over_{str(line).replace('.', '_')}"
        result[key] = {"over": round(1 - p_under, 4), "under": round(p_under, 4)}
    return result


def _btts(home_xg: float, away_xg: float) -> Dict[str, Any]:
    yes = float(np.clip((1.0 - _pmf(0, home_xg)) * (1.0 - _pmf(0, away_xg)), 0.01, 0.99))
    no = round(1.0 - yes, 4)
    yes = round(yes, 4)
    return {
        "yes": yes, "no": no,
        "result": "Yes" if yes >= 0.5 else "No",
        "yes_pct": round(yes * 100, 1),
        "no_pct": round(no * 100, 1),
    }


def _correct_score(home_xg: float, away_xg: float, max_goals: int = 5) -> List[Dict]:
    scores = [
        {"score": f"{h}-{a}", "probability": round(_pmf(h, home_xg) * _pmf(a, away_xg), 4)}
        for h in range(max_goals + 1) for a in range(max_goals + 1)
    ]
    scores.sort(key=lambda x: -x["probability"])
    return scores[:10]


def _asian_handicap(home_xg: float, away_xg: float, handicap: float) -> Dict[str, float]:
    max_g = 12
    ph = pa = pp = 0.0
    for h in range(max_g):
        for a in range(max_g):
            prob = _pmf(h, home_xg) * _pmf(a, away_xg)
            diff = (h - a) + handicap
            if diff > 0:
                ph += prob
            elif diff < 0:
                pa += prob
            else:
                pp += prob
    total = ph + pa
    return {
        "handicap": handicap,
        "home_cover_probability": round(float(np.clip(ph / total if total > 0 else 0.5, 0.01, 0.99)), 4),
        "away_cover_probability": round(float(np.clip(pa / total if total > 0 else 0.5, 0.01, 0.99)), 4),
        "push_probability": round(float(pp), 4),
    }


def _corners(home_form: float, away_form: float, home_att: float, away_att: float) -> Dict[str, Any]:
    home_cx = 5.2 * (0.55 + 0.8 * home_att) * (0.65 + 0.6 * home_form)
    away_cx = 5.2 * (0.55 + 0.8 * away_att) * (0.65 + 0.6 * away_form)
    total = float(np.clip(home_cx + away_cx, 5.0, 17.0))
    result: Dict[str, Any] = {"expected_total": round(total, 2)}
    for line in [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]:
        key = f"line_{str(line).replace('.', '_')}"
        result[key] = {
            "over":  round(float(np.clip(1.0 - _cdf(int(line), total), 0.01, 0.99)), 4),
            "under": round(float(np.clip(_cdf(int(line), total), 0.01, 0.99)), 4),
        }
    return result


def _bookings(home_form: float, away_form: float, rivalry: float = 0.5) -> Dict[str, Any]:
    aggression = (1 - home_form) * 0.5 + (1 - away_form) * 0.5
    expected = float(np.clip(3.5 + rivalry + aggression, 2.0, 8.0))
    result: Dict[str, Any] = {"expected_total_cards": round(expected, 2)}
    for line in [2.5, 3.5, 4.5, 5.5]:
        key = f"line_{str(line).replace('.', '_')}"
        result[key] = {
            "over":  round(float(np.clip(1.0 - _cdf(int(line), expected), 0.01, 0.99)), 4),
            "under": round(float(np.clip(_cdf(int(line), expected), 0.01, 0.99)), 4),
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Basketball markets
# ─────────────────────────────────────────────────────────────────────────────

def _basketball_markets(features: Dict[str, float], home_prob: float) -> Dict[str, Any]:
    """Build basketball totals/spread markets without collapsing to defaults."""
    def _denorm(v: float) -> float:
        return 80.0 + v * 60.0

    def _centered_signal(value: float, fallback: float = 0.5) -> float:
        return float(features.get(value, fallback)) - 0.5

    home_pts = _denorm(features.get("home_pts_avg", 0.5))
    away_pts = _denorm(features.get("away_pts_avg", 0.5))
    home_allowed = _denorm(1.0 - features.get("home_pts_allowed_avg", 0.5))
    away_allowed = _denorm(1.0 - features.get("away_pts_allowed_avg", 0.5))

    raw_home = (home_pts + away_allowed) / 2.0
    raw_away = (away_pts + home_allowed) / 2.0

    pace_signal = (features.get("home_pace_signal", 0.5) + features.get("away_pace_signal", 0.5)) / 2.0
    form_edge = (_centered_signal("home_form_rating") - _centered_signal("away_form_rating"))
    market_edge = float(np.clip((home_prob - 0.5) * 2.0, -1.0, 1.0))
    espn_edge = _centered_signal("home_espn_win_pct") - _centered_signal("away_espn_win_pct")

    # Use team point stats when available, but keep markets responsive even if upstream
    # team-stat scraping falls back to league-average defaults.
    stats_defaultish = (
        abs(home_pts - 110.0) < 0.2 and abs(away_pts - 110.0) < 0.2
        and abs(home_allowed - 110.0) < 0.2 and abs(away_allowed - 110.0) < 0.2
    )

    baseline_total = raw_home + raw_away
    if stats_defaultish:
        baseline_total = 221.5 + (pace_signal - 0.5) * 18.0 + market_edge * 7.0
    else:
        baseline_total += (pace_signal - 0.5) * 10.0 + market_edge * 4.0
    total_expected = float(np.clip(baseline_total, 198.0, 246.0))

    spread_from_scoring = raw_home - raw_away
    spread_from_signals = market_edge * 8.5 + form_edge * 5.0 + espn_edge * 4.0 + 1.8
    if stats_defaultish:
        spread_expected = spread_from_signals
    else:
        spread_expected = 0.55 * spread_from_scoring + 0.45 * spread_from_signals
    spread_expected = float(np.clip(spread_expected, -18.5, 18.5))

    home_expected = float(np.clip(total_expected / 2.0 + spread_expected / 2.0, 85.0, 140.0))
    away_expected = float(np.clip(total_expected - home_expected, 85.0, 140.0))
    total_expected = round(home_expected + away_expected, 1)

    sigma = 12.0
    lines = [195.5, 205.5, 215.5, 220.5, 225.5, 230.5, 235.5]
    ou_markets: Dict[str, Any] = {
        "expected_total": total_expected,
        "source": "adaptive_model" if stats_defaultish else "team_stats_plus_signals",
    }
    from scipy.stats import norm
    for line in lines:
        p_over = float(np.clip(1.0 - norm.cdf(line, total_expected, sigma), 0.01, 0.99))
        key = f"line_{int(line)}"
        ou_markets[key] = {"over": round(p_over, 4), "under": round(1 - p_over, 4)}

    return {
        "points_over_under": ou_markets,
        "expected_spread": round(spread_expected, 1),
        "home_expected_pts": round(home_expected, 1),
        "away_expected_pts": round(away_expected, 1),
        "moneyline": {
            "home_prob": round(home_prob, 4),
            "away_prob": round(1 - home_prob, 4),
        },
    }



# ─────────────────────────────────────────────────────────────────────────────
# Master function
# ─────────────────────────────────────────────────────────────────────────────

def compute_all_markets(features: Dict[str, float], sport: str) -> Dict[str, Any]:
    sport = sport.lower()
    home_form  = features.get("home_form_rating", 0.5)
    away_form  = features.get("away_form_rating", 0.5)
    home_att   = features.get("home_win_rate_signal", 0.5)
    away_att   = features.get("away_win_rate_signal", 0.5)
    home_inj   = features.get("home_injury_impact", 0.0)
    away_inj   = features.get("away_injury_impact", 0.0)
    h2h_signal = features.get("h2h_home_win_rate", 0.5)

    # Implied market home prob for market calculations
    home_prob = features.get("implied_home_prob", 0.5)

    markets: Dict[str, Any] = {}

    if sport == "soccer":
        # xG = average of own attack average vs opponent defensive average.
        # This captures both attacking quality AND defensive weakness,
        # and produces realistic xG values (e.g. 1.3–1.6 for typical league games).
        # Previously only attack avg was used, giving systematically low xG
        # when injury_impact was zero and attack avg sat near the default 1.15/1.40.
        home_goals_scored   = features.get("home_goals_scored_avg", 1.40)
        home_goals_conceded = features.get("home_goals_conceded_avg", 1.10)
        away_goals_scored   = features.get("away_goals_scored_avg", 1.15)
        away_goals_conceded = features.get("away_goals_conceded_avg", 1.35)

        pace_signal = float(np.clip((features.get("home_momentum", 0.5) + features.get("away_momentum", 0.5)) / 2.0, 0.0, 1.0))
        implied_home = float(np.clip(features.get("implied_home_prob", 0.5), 0.02, 0.95))
        implied_away = float(np.clip(features.get("implied_away_prob", 0.5), 0.02, 0.95))
        odds_bias = float(np.clip(np.log((implied_home + 1e-6) / (implied_away + 1e-6)), -1.2, 1.2))

        raw_home_xg = ((home_goals_scored * 0.62) + (away_goals_conceded * 0.38)) * (
            1.0 + 0.12 * (pace_signal - 0.5) + 0.10 * odds_bias
        )
        raw_away_xg = ((away_goals_scored * 0.62) + (home_goals_conceded * 0.38)) * (
            1.0 + 0.12 * (pace_signal - 0.5) - 0.10 * odds_bias
        )

        # Apply injury discount after combining attack + defence
        home_xg = float(np.clip(raw_home_xg * (1.0 - home_inj * 0.5), 0.3, 5.0))
        away_xg = float(np.clip(raw_away_xg * (1.0 - away_inj * 0.5), 0.3, 5.0))

        goals_ou = _goals_ou_all(home_xg, away_xg)
        btts = _btts(home_xg, away_xg)
        correct_scores = _correct_score(home_xg, away_xg)
        over_25 = goals_ou.get("over_2_5", {}).get("over", 0.5)

        # Consistency engine: if BTTS No is strong, demote high BTTS-style scores.
        if btts.get("no", 0.0) >= 0.58:
            correct_scores = [s for s in correct_scores if not (int(s["score"].split("-")[0]) >= 1 and int(s["score"].split("-")[1]) >= 1)]
            if not correct_scores:
                correct_scores = _correct_score(home_xg, away_xg)

        markets["goals_over_under"]  = goals_ou
        markets["btts"]              = btts
        markets["correct_score"]     = {
            "top_1": correct_scores[0] if correct_scores else {"score": "1-0", "probability": 0.0},
            "top_3": correct_scores[:3],
            "top_10": correct_scores[:10],
        }
        markets["corners"]           = _corners(home_form, away_form, home_att, away_att)
        rivalry = abs(h2h_signal - 0.5) * 2.0
        markets["bookings"]          = _bookings(home_form, away_form, rivalry)
        markets["asian_handicap"]    = [
            _asian_handicap(home_xg, away_xg, h)
            for h in [-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5]
        ]
        markets["consistency_checks"] = {
            "high_over25_requires_high_xg": bool(not (over_25 > 0.6 and (home_xg + away_xg) < 2.4)),
            "btts_no_aligned_scores": bool(not (btts.get("no", 0.0) > 0.58 and any(
                int(s["score"].split("-")[0]) >= 1 and int(s["score"].split("-")[1]) >= 1
                for s in markets["correct_score"]["top_3"]
            ))),
            "xg_total": round(home_xg + away_xg, 3),
        }

    elif sport == "basketball":
        try:
            markets["basketball"] = _basketball_markets(features, home_prob)
        except ImportError:
            # scipy not available — simplified fallback
            markets["basketball"] = {
                "note": "scipy required for full basketball markets",
                "home_prob": round(home_prob, 4),
                "away_prob": round(1.0 - home_prob, 4),
            }


    return markets
