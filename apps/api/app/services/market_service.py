# app/services/market_service.py
"""
Extended Market Service — football/soccer markets

Soccer: 1X2, goals O/U (0.5–4.5), BTTS, correct score, Asian handicap,
        corners O/U, bookings O/U.

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
    best_line = None
    best_confidence = -1.0
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
        confidence = abs(result[key]["over"] - 0.5)
        if confidence > best_confidence:
            best_confidence = confidence
            best_line = (line, result[key])
    if best_line is not None:
        line, odds = best_line
        result["pick"] = {
            "selection": f"{'Over' if odds['over'] >= odds['under'] else 'Under'} {line}",
            "probability": round(max(odds["over"], odds["under"]), 4),
        }
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


def _score_grid(home_xg: float, away_xg: float, max_goals: int = 8) -> List[Dict[str, float]]:
    grid: List[Dict[str, float]] = []
    total = 0.0
    for home_goals in range(max_goals + 1):
        home_prob = _pmf(home_goals, home_xg)
        for away_goals in range(max_goals + 1):
            probability = home_prob * _pmf(away_goals, away_xg)
            total += probability
            grid.append({"home": home_goals, "away": away_goals, "probability": probability})

    if total > 0:
        for item in grid:
            item["probability"] = float(item["probability"] / total)

    return grid


def _three_way_from_grid(grid: List[Dict[str, float]]) -> Dict[str, float]:
    home = sum(item["probability"] for item in grid if item["home"] > item["away"])
    draw = sum(item["probability"] for item in grid if item["home"] == item["away"])
    away = sum(item["probability"] for item in grid if item["home"] < item["away"])
    return {
        "home": round(float(np.clip(home, 0.01, 0.99)), 4),
        "draw": round(float(np.clip(draw, 0.01, 0.99)), 4),
        "away": round(float(np.clip(away, 0.01, 0.99)), 4),
    }


def _best_three_way_choice(probabilities: Dict[str, float]) -> Dict[str, Any]:
    selection = max(probabilities, key=probabilities.get)
    return {
        "selection": selection,
        "probability": round(float(probabilities[selection]), 4),
    }


def _binary_market(yes_label: str, yes_probability: float, no_label: str) -> Dict[str, Any]:
    no_probability = float(np.clip(1.0 - yes_probability, 0.01, 0.99))
    yes_probability = float(np.clip(yes_probability, 0.01, 0.99))
    selection = yes_label if yes_probability >= no_probability else no_label
    return {
        yes_label.lower().replace(" ", "_"): round(yes_probability, 4),
        no_label.lower().replace(" ", "_"): round(no_probability, 4),
        "result": selection,
        "pick": selection,
        "pick_probability": round(max(yes_probability, no_probability), 4),
        "yes_pct": round(yes_probability * 100, 1),
        "no_pct": round(no_probability * 100, 1),
    }


def _ou_market(lam: float, lines: List[float]) -> Dict[str, Any]:
    market: Dict[str, Any] = {}
    for line in lines:
        key = f"over_{str(line).replace('.', '_')}"
        market[key] = _ou(lam, line)
    best_key = max(
        market,
        key=lambda key: abs(market[key]["over"] - 0.5),
    )
    market["pick"] = {
        "selection": f"{'Over' if market[best_key]['over'] >= market[best_key]['under'] else 'Under'} {best_key.replace('over_', '').replace('_', '.')}"
        ,
        "probability": round(max(market[best_key]["over"], market[best_key]["under"]), 4),
    }
    return market


def _team_totals(home_xg: float, away_xg: float) -> Dict[str, Any]:
    return {
        "home": _ou_market(home_xg, [0.5, 1.5, 2.5]),
        "away": _ou_market(away_xg, [0.5, 1.5, 2.5]),
    }


def _half_xg(home_xg: float, away_xg: float, factor: float) -> tuple[float, float]:
    return float(np.clip(home_xg * factor, 0.15, 4.0)), float(np.clip(away_xg * factor, 0.15, 4.0))


def _union_probability(grid: List[Dict[str, float]], predicate) -> float:
    return round(sum(item["probability"] for item in grid if predicate(item)), 4)


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

        full_grid = _score_grid(home_xg, away_xg)
        full_time_three_way = _three_way_from_grid(full_grid)
        full_time_pick = _best_three_way_choice(full_time_three_way)
        readable_three_way = {"home": "Home", "draw": "Draw", "away": "Away"}
        double_chance = {
            "home_or_draw": round(full_time_three_way["home"] + full_time_three_way["draw"], 4),
            "home_or_away": round(full_time_three_way["home"] + full_time_three_way["away"], 4),
            "draw_or_away": round(full_time_three_way["draw"] + full_time_three_way["away"], 4),
        }
        double_chance_pick = max(double_chance, key=double_chance.get)
        readable_double_chance = {
            "home_or_draw": "1X",
            "home_or_away": "12",
            "draw_or_away": "X2",
        }
        dnb = {
            "home": round(full_time_three_way["home"] / max(1.0 - full_time_three_way["draw"], 0.01), 4),
            "away": round(full_time_three_way["away"] / max(1.0 - full_time_three_way["draw"], 0.01), 4),
        }
        dnb_pick = "home" if dnb["home"] >= dnb["away"] else "away"

        first_half_home_xg, first_half_away_xg = _half_xg(home_xg, away_xg, 0.45)
        second_half_home_xg, second_half_away_xg = _half_xg(home_xg, away_xg, 0.55)
        first_half_grid = _score_grid(first_half_home_xg, first_half_away_xg, max_goals=5)
        second_half_grid = _score_grid(second_half_home_xg, second_half_away_xg, max_goals=5)
        first_half_three_way = _three_way_from_grid(first_half_grid)
        second_half_three_way = _three_way_from_grid(second_half_grid)
        first_half_btts = _btts(first_half_home_xg, first_half_away_xg)
        first_half_pick = _best_three_way_choice(first_half_three_way)

        ten_minute_home_xg, ten_minute_away_xg = _half_xg(home_xg, away_xg, 10.0 / 90.0)
        ten_minute_grid = _score_grid(ten_minute_home_xg, ten_minute_away_xg, max_goals=3)
        ten_minute_three_way = _three_way_from_grid(ten_minute_grid)
        ten_minute_pick = _best_three_way_choice(ten_minute_three_way)

        home_win_either_half = round(
            1.0 - (1.0 - first_half_three_way["home"]) * (1.0 - second_half_three_way["home"]),
            4,
        )
        away_win_either_half = round(
            1.0 - (1.0 - first_half_three_way["away"]) * (1.0 - second_half_three_way["away"]),
            4,
        )

        home_or_gg = _union_probability(
            full_grid,
            lambda item: item["home"] > item["away"] or (item["home"] > 0 and item["away"] > 0),
        )
        draw_or_gg = _union_probability(
            full_grid,
            lambda item: item["home"] == item["away"] or (item["home"] > 0 and item["away"] > 0),
        )
        away_or_gg = _union_probability(
            full_grid,
            lambda item: item["home"] < item["away"] or (item["home"] > 0 and item["away"] > 0),
        )
        readable_combo = {
            "home_or_gg": "Home or GG",
            "draw_or_gg": "Draw or GG",
            "away_or_gg": "Away or GG",
        }

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
        markets["one_x_two"] = {
            "home": full_time_three_way["home"],
            "draw": full_time_three_way["draw"],
            "away": full_time_three_way["away"],
            "pick": {"selection": readable_three_way[full_time_pick["selection"]], "probability": full_time_pick["probability"]},
        }
        markets["double_chance"] = {
            **double_chance,
            "pick": {"selection": readable_double_chance[double_chance_pick], "probability": round(double_chance[double_chance_pick], 4)},
        }
        markets["draw_no_bet"] = {
            "home": dnb["home"],
            "away": dnb["away"],
            "pick": {"selection": readable_three_way[dnb_pick], "probability": round(dnb[dnb_pick], 4)},
        }
        markets["btts"]              = btts
        markets["first_half_btts"] = first_half_btts
        markets["first_half_one_x_two"] = {
            "home": first_half_three_way["home"],
            "draw": first_half_three_way["draw"],
            "away": first_half_three_way["away"],
            "pick": {"selection": readable_three_way[first_half_pick["selection"]], "probability": first_half_pick["probability"]},
        }
        markets["ten_minute_one_x_two"] = {
            "home": ten_minute_three_way["home"],
            "draw": ten_minute_three_way["draw"],
            "away": ten_minute_three_way["away"],
            "pick": {"selection": readable_three_way[ten_minute_pick["selection"]], "probability": ten_minute_pick["probability"]},
        }
        markets["either_half"] = {
            "home_win_either_half": home_win_either_half,
            "away_win_either_half": away_win_either_half,
            "pick": {
                "selection": "Home" if home_win_either_half >= away_win_either_half else "Away",
                "probability": round(max(home_win_either_half, away_win_either_half), 4),
            },
        }
        markets["combo_markets"] = {
            "home_or_gg": home_or_gg,
            "draw_or_gg": draw_or_gg,
            "away_or_gg": away_or_gg,
            "pick": {
                "selection": readable_combo[max(
                    {"home_or_gg": home_or_gg, "draw_or_gg": draw_or_gg, "away_or_gg": away_or_gg},
                    key={"home_or_gg": home_or_gg, "draw_or_gg": draw_or_gg, "away_or_gg": away_or_gg}.get,
                )],
                "probability": round(max(home_or_gg, draw_or_gg, away_or_gg), 4),
            },
        }
        markets["correct_score"]     = {
            "top_1": correct_scores[0] if correct_scores else {"score": "1-0", "probability": 0.0},
            "top_3": correct_scores[:3],
            "top_10": correct_scores[:10],
        }
        markets["team_goals_over_under"] = {
            "home": _ou_market(home_xg, [0.5, 1.5, 2.5]),
            "away": _ou_market(away_xg, [0.5, 1.5, 2.5]),
        }
        markets["first_half_goals_over_under"] = _goals_ou_all(first_half_home_xg, first_half_away_xg)
        markets["ten_minute_goals_over_under"] = _goals_ou_all(ten_minute_home_xg, ten_minute_away_xg)
        markets["corners"]           = _corners(home_form, away_form, home_att, away_att)
        markets["team_corners_over_under"] = {
            "home": _ou_market(home_att * 5.2, [3.5, 4.5, 5.5, 6.5, 7.5]),
            "away": _ou_market(away_att * 5.2, [3.5, 4.5, 5.5, 6.5, 7.5]),
        }
        rivalry = abs(h2h_signal - 0.5) * 2.0
        markets["bookings"]          = _bookings(home_form, away_form, rivalry)
        markets["asian_handicap"]    = [
            _asian_handicap(home_xg, away_xg, h)
            for h in [-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5]
        ]
        markets["market_picks"] = [
            {"market": "1X2", "selection": readable_three_way[full_time_pick["selection"]], "probability": full_time_pick["probability"]},
            {"market": "Double Chance", "selection": readable_double_chance[double_chance_pick], "probability": round(double_chance[double_chance_pick], 4)},
            {"market": "Draw No Bet", "selection": readable_three_way[dnb_pick], "probability": round(dnb[dnb_pick], 4)},
            {"market": "Goals O/U", "selection": goals_ou.get("pick", {}).get("selection", "Over 2.5"), "probability": goals_ou.get("pick", {}).get("probability", 0.0)},
            {"market": "BTTS", "selection": btts["result"], "probability": btts["yes"] if btts["result"] == "Yes" else btts["no"]},
            {"market": "First Half 1X2", "selection": readable_three_way[first_half_pick["selection"]], "probability": first_half_pick["probability"]},
            {"market": "10 Minute 1X2", "selection": readable_three_way[ten_minute_pick["selection"]], "probability": ten_minute_pick["probability"]},
            {"market": "Either Half", "selection": "Home" if home_win_either_half >= away_win_either_half else "Away", "probability": round(max(home_win_either_half, away_win_either_half), 4)},
        ]
        markets["consistency_checks"] = {
            "high_over25_requires_high_xg": bool(not (over_25 > 0.6 and (home_xg + away_xg) < 2.4)),
            "btts_no_aligned_scores": bool(not (btts.get("no", 0.0) > 0.58 and any(
                int(s["score"].split("-")[0]) >= 1 and int(s["score"].split("-")[1]) >= 1
                for s in markets["correct_score"]["top_3"]
            ))),
            "xg_total": round(home_xg + away_xg, 3),
        }


    return markets
