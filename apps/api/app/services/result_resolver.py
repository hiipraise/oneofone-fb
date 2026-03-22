# app/services/result_resolver.py
"""
Auto-resolution service.

Fetches completed scores from the ESPN public scoreboard API (no key required),
matches them against stored predictions by sport + date + fuzzy team name,
then calls save_actual_result so the ML learning pipeline triggers automatically.

Called by the daily scheduler — never touches FastAPI's Motor client directly.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from app.utils.timezone import WAT
from typing import List, Dict, Optional

import requests

from app.services.match_validation_service import ESPN_LEAGUES, ESPN_SPORT_PATH

logger = logging.getLogger(__name__)

# How many past days to look back for completed scores
_DAYS_FROM = 2


# ── ESPN score fetcher ────────────────────────────────────────────────────────

def _date_range(days_back: int) -> List[str]:
    """Return the last `days_back` dates as YYYYMMDD strings (today first)."""
    today = datetime.now(WAT).date()
    return [
        (today - timedelta(days=d)).strftime("%Y%m%d")
        for d in range(days_back)
    ]


def _fetch_espn_league(sport_path: str, league: str, date_str: str) -> List[Dict]:
    """
    Fetch one ESPN scoreboard page and return completed game dicts.
    Returns [] on any non-200 or parse error — never raises.
    """
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports"
        f"/{sport_path}/{league}/scoreboard"
    )
    try:
        resp = requests.get(url, params={"dates": date_str}, timeout=10)
        if resp.status_code != 200:
            logger.debug(f"[resolver] ESPN {resp.status_code} [{league} {date_str}]")
            return []

        games = []
        for event in resp.json().get("events", []):
            status = event.get("status", {}).get("type", {})
            if not status.get("completed"):
                continue

            competition = (event.get("competitions") or [{}])[0]
            competitors = competition.get("competitors", [])
            if len(competitors) < 2:
                continue

            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue

            try:
                home_score = int(home.get("score", ""))
                away_score = int(away.get("score", ""))
            except (ValueError, TypeError):
                continue

            home_name = (home.get("team") or {}).get("displayName", "")
            away_name = (away.get("team") or {}).get("displayName", "")
            if not home_name or not away_name:
                continue

            # "2026-03-21T19:00:00Z" → "2026-03-21"
            match_date = event.get("date", "")[:10]

            games.append({
                "home_team":  home_name,
                "away_team":  away_name,
                "home_score": home_score,
                "away_score": away_score,
                "match_date": match_date,
            })

        return games

    except requests.exceptions.Timeout:
        logger.warning(f"[resolver] ESPN timeout [{league} {date_str}]")
        return []
    except Exception as e:
        logger.warning(f"[resolver] ESPN error [{league} {date_str}]: {e}")
        return []


def _fetch_completed_scores(sport: str) -> List[Dict]:
    """
    Fetch recently completed games from the ESPN public scoreboard API.
    Returns list of dicts: {home_team, away_team, home_score, away_score, match_date, sport}
    No API key required.
    """
    sport_path = ESPN_SPORT_PATH.get(sport)
    leagues    = ESPN_LEAGUES.get(sport)
    if not sport_path or not leagues:
        logger.warning(f"[resolver] No ESPN config for sport: {sport}")
        return []

    dates     = _date_range(_DAYS_FROM)
    completed = []
    seen      = set()

    for league in leagues:
        for date_str in dates:
            for game in _fetch_espn_league(sport_path, league, date_str):
                game_key = (
                    game["home_team"].lower(),
                    game["away_team"].lower(),
                    game["match_date"],
                )
                if game_key in seen:
                    continue
                seen.add(game_key)
                game["sport"] = sport
                completed.append(game)

    return completed


# ── Team name fuzzy matching ──────────────────────────────────────────────────

_STRIP_WORDS = frozenset([
    "fc", "cf", "sc", "ac", "rc", "af", "afc", "fk", "sk", "bk",
    "united", "city", "town", "athletic", "athletico", "atletico",
    "sporting", "real", "club", "de", "the",
])


def _normalise(name: str) -> List[str]:
    """Return significant lowercase words from a team name."""
    words = re.sub(r"[^a-z0-9\s]", "", name.lower()).split()
    return [w for w in words if len(w) >= 4 and w not in _STRIP_WORDS]


def _names_match(a: str, b: str) -> bool:
    """True if the two team name strings are plausibly the same team."""
    wa = _normalise(a)
    wb = _normalise(b)
    if not wa or not wb:
        return a.lower().strip() == b.lower().strip()
    return any(w in wb for w in wa) or any(w in wa for w in wb)


def _find_matching_prediction(
    completed: Dict,
    stored_predictions: List[Dict],
) -> Optional[Dict]:
    """
    Find a stored prediction that matches a completed ESPN game.
    Matches on: sport, match_date (±1 day tolerance), fuzzy team names.
    """
    target_date  = completed["match_date"]
    target_sport = completed["sport"]

    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        candidate_dates = {
            target_date,
            (dt - timedelta(days=1)).strftime("%Y-%m-%d"),
            (dt + timedelta(days=1)).strftime("%Y-%m-%d"),
        }
    except ValueError:
        candidate_dates = {target_date}

    for pred in stored_predictions:
        if pred.get("sport") != target_sport:
            continue
        if pred.get("match_date") not in candidate_dates:
            continue
        if (
            _names_match(completed["home_team"], pred.get("home_team", "")) and
            _names_match(completed["away_team"], pred.get("away_team", ""))
        ):
            return pred

    return None


def _derive_outcome(home_score: int, away_score: int, sport: str) -> str:
    if home_score > away_score:
        return "home_win"
    if away_score > home_score:
        return "away_win"
    return "draw"


# ── Main async resolver ───────────────────────────────────────────────────────

async def resolve_results() -> Dict:
    """
    Main entry point. Fetches completed scores via ESPN, matches to predictions,
    and persists results. Returns a summary dict for logging.
    """
    from app.config.database import get_db
    from app.services.prediction_service import save_actual_result

    db = get_db()

    cutoff = (datetime.now(WAT) - timedelta(days=3)).strftime("%Y-%m-%d")
    stored: List[Dict] = []
    async for pred in db.predictions.find(
        {"match_date": {"$gte": cutoff}, "deleted_at": None},
        {"match_id": 1, "home_team": 1, "away_team": 1, "sport": 1, "match_date": 1},
    ):
        pred.pop("_id", None)
        stored.append(pred)

    if not stored:
        logger.info("[resolver] No recent predictions found — nothing to resolve")
        return {"resolved": 0, "skipped": 0, "errors": 0}

    already_resolved: set = set()
    async for doc in db.actual_results.find({}, {"match_id": 1}):
        already_resolved.add(doc["match_id"])

    resolved = 0
    skipped  = 0
    errors   = 0

    for sport in ESPN_LEAGUES:
        logger.info(f"[resolver] Fetching completed {sport} scores via ESPN…")
        completed_games = _fetch_completed_scores(sport)

        if not completed_games:
            logger.info(f"[resolver] No completed {sport} games found")
            continue

        logger.info(f"[resolver] {len(completed_games)} completed {sport} games to process")

        for game in completed_games:
            try:
                match = _find_matching_prediction(game, stored)
                if not match:
                    logger.debug(
                        f"[resolver] No prediction for "
                        f"{game['home_team']} vs {game['away_team']} [{sport}]"
                    )
                    skipped += 1
                    continue

                match_id = match["match_id"]

                if match_id in already_resolved:
                    logger.debug(f"[resolver] Already resolved: {match_id}")
                    skipped += 1
                    continue

                outcome = _derive_outcome(game["home_score"], game["away_score"], sport)

                await save_actual_result(
                    match_id       = match_id,
                    home_score     = game["home_score"],
                    away_score     = game["away_score"],
                    actual_outcome = outcome,
                    match_date     = game["match_date"],
                )

                already_resolved.add(match_id)
                resolved += 1
                logger.info(
                    f"[resolver] Resolved: {game['home_team']} {game['home_score']}–"
                    f"{game['away_score']} {game['away_team']} → {outcome}"
                )

            except Exception as e:
                errors += 1
                logger.error(
                    f"[resolver] Failed to resolve "
                    f"{game.get('home_team')} vs {game.get('away_team')}: {e}"
                )

    return {"resolved": resolved, "skipped": skipped, "errors": errors}