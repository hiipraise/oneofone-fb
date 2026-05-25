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
from typing import List, Dict, Optional, Any

import requests

from app.config.settings import settings
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
                "fixture_id": event.get("id", ""),
                "home_team":  home_name,
                "away_team":  away_name,
                "home_score": home_score,
                "away_score": away_score,
                "match_date": match_date,
                "sport_path": sport_path,
                "league": league,
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


def _find_completed_game_for_prediction(
    prediction: Dict,
    completed_games: List[Dict],
) -> Optional[Dict]:
    """Find the completed ESPN game that matches a stored prediction."""
    pred_date = prediction.get("match_date")
    try:
        dt = datetime.strptime(pred_date, "%Y-%m-%d") if pred_date else None
        candidate_dates = {
            pred_date,
            (dt - timedelta(days=1)).strftime("%Y-%m-%d") if dt else None,
            (dt + timedelta(days=1)).strftime("%Y-%m-%d") if dt else None,
        }
        candidate_dates.discard(None)
    except Exception:
        candidate_dates = {pred_date} if pred_date else set()

    for game in completed_games:
        if game.get("sport") != prediction.get("sport"):
            continue
        if candidate_dates and game.get("match_date") not in candidate_dates:
            continue
        if (
            _names_match(game.get("home_team", ""), prediction.get("home_team", ""))
            and _names_match(game.get("away_team", ""), prediction.get("away_team", ""))
        ):
            return game

    return None


def _derive_outcome(home_score: int, away_score: int, sport: str) -> str:
    if home_score > away_score:
        return "home_win"
    if away_score > home_score:
        return "away_win"
    return "draw"


async def resolve_prediction_by_match_id(match_id: str) -> Dict[str, Any]:
    """Resolve a single prediction by match_id using the ESPN scoreboard."""
    from app.config.database import get_db
    from app.services.prediction_service import save_actual_result

    db = get_db()
    prediction = await db.predictions.find_one(
        {"match_id": match_id, "deleted_at": None},
        {
            "_id": 0,
            "match_id": 1,
            "home_team": 1,
            "away_team": 1,
            "sport": 1,
            "match_date": 1,
        },
    )
    if not prediction:
        return {"resolved": False, "reason": "prediction_not_found"}

    if await db.actual_results.find_one({"match_id": match_id}, {"_id": 0, "match_id": 1}):
        return {"resolved": False, "reason": "already_resolved", "match_id": match_id}

    sport = prediction.get("sport", "soccer")
    sport_path = ESPN_SPORT_PATH.get(sport, "")
    leagues = ESPN_LEAGUES.get(sport, [])
    if not sport_path or not leagues:
        return {"resolved": False, "reason": "unsupported_sport", "match_id": match_id}

    dates_to_check = []
    try:
        base_date = datetime.strptime(prediction.get("match_date"), "%Y-%m-%d")
        dates_to_check = [
            base_date.strftime("%Y%m%d"),
            (base_date - timedelta(days=1)).strftime("%Y%m%d"),
            (base_date + timedelta(days=1)).strftime("%Y%m%d"),
        ]
    except Exception:
        dates_to_check = _date_range(_DAYS_FROM)

    completed_games: List[Dict] = []
    seen: set[tuple[str, str, str]] = set()
    for league in leagues:
        for date_str in dates_to_check:
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
                completed_games.append(game)

    game = _find_completed_game_for_prediction(prediction, completed_games)
    if not game:
        return {"resolved": False, "reason": "game_not_found", "match_id": match_id}

    outcome = _derive_outcome(game["home_score"], game["away_score"], sport)
    corner_stats = _fetch_espn_corner_stats(
        game.get("sport_path", sport_path),
        game.get("league", ""),
        game.get("fixture_id", ""),
        game["home_team"],
        game["away_team"],
    )

    await save_actual_result(
        match_id=match_id,
        home_score=game["home_score"],
        away_score=game["away_score"],
        actual_outcome=outcome,
        match_date=game["match_date"],
        corner_stats=corner_stats,
    )

    return {
        "resolved": True,
        "match_id": match_id,
        "home_score": game["home_score"],
        "away_score": game["away_score"],
        "actual_outcome": outcome,
        "match_date": game["match_date"],
    }


def _parse_corner_value(value) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        match = re.search(r"\d+", text.replace(",", ""))
        return int(match.group(0)) if match else None
    except Exception:
        return None


def _extract_espn_corner_stats(summary: Dict[str, Any], home_team: str, away_team: str) -> Optional[Dict[str, int | str]]:
    """Extract corner totals from ESPN summary payloads."""
    home_norm = home_team.lower()
    away_norm = away_team.lower()

    def _team_name(team_obj: Any) -> str:
        if not isinstance(team_obj, dict):
            return ""
        return (
            team_obj.get("displayName")
            or team_obj.get("shortDisplayName")
            or team_obj.get("name")
            or ""
        )

    def _team_bucket(name: str) -> Optional[str]:
        if not name:
            return None
        lowered = name.lower()
        if _names_match(home_norm, lowered):
            return "home"
        if _names_match(away_norm, lowered):
            return "away"
        return None

    def _record(bucket: Dict[str, Optional[int]], team_name: str, stat_name: str, value: Any) -> None:
        if "corner" not in stat_name.lower():
            return
        corners = _parse_corner_value(value)
        if corners is None:
            return
        team_bucket = _team_bucket(team_name)
        if team_bucket:
            bucket[team_bucket] = corners

    # Preferred ESPN payload shapes: boxscore/team statistics blocks.
    bucket: Dict[str, Optional[int]] = {"home": None, "away": None}
    for block in summary.get("boxscore", {}).get("players", []) or []:
        team_name = _team_name(block.get("team"))
        stat_groups = block.get("statistics") or block.get("stats") or []
        for item in stat_groups:
            if not isinstance(item, dict):
                continue
            stat_name = item.get("name") or item.get("label") or item.get("displayName") or ""
            if not stat_name and "statistics" in item:
                stat_name = item.get("title") or ""
            if not stat_name:
                continue
            for candidate in (item.get("value"), item.get("displayValue"), item.get("summary")):
                _record(bucket, team_name, stat_name, candidate)

    if bucket["home"] is not None and bucket["away"] is not None:
        return {
            "home_corners": bucket["home"],
            "away_corners": bucket["away"],
            "total_corners": bucket["home"] + bucket["away"],
            "source": "espn_summary",
        }

    # Fallback: recursively scan the JSON for a corner stat object.
    def _walk(node: Any, team_hint: str = "") -> None:
        if bucket["home"] is not None and bucket["away"] is not None:
            return
        if isinstance(node, dict):
            current_team = team_hint
            if "team" in node:
                current_team = _team_name(node.get("team")) or current_team
            name = node.get("name") or node.get("label") or node.get("displayName") or node.get("title") or ""
            if name:
                for candidate in (node.get("value"), node.get("displayValue"), node.get("summary")):
                    _record(bucket, current_team, name, candidate)
            for value in node.values():
                _walk(value, current_team)
        elif isinstance(node, list):
            for item in node:
                _walk(item, team_hint)

    _walk(summary)
    if bucket["home"] is not None and bucket["away"] is not None:
        return {
            "home_corners": bucket["home"],
            "away_corners": bucket["away"],
            "total_corners": bucket["home"] + bucket["away"],
            "source": "espn_summary_scan",
        }

    return None


def _fetch_espn_corner_stats(sport_path: str, league: str, fixture_id: str, home_team: str, away_team: str) -> Optional[Dict[str, int | str]]:
    if not fixture_id:
        return None

    try:
        resp = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/{league}/summary",
            params={"event": fixture_id},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return _extract_espn_corner_stats(resp.json(), home_team, away_team)
    except Exception as e:
        logger.debug(f"[resolver] ESPN corner fetch failed: {e}")
        return None


def _rapidapi_headers() -> Dict[str, str]:
    return {
        "X-RapidAPI-Key": settings.RAPID_API_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
    }


def _safe_int(value) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))
    except Exception:
        return None


def _fetch_corner_stats(home_team: str, away_team: str, match_date: str) -> Optional[Dict[str, int | str]]:
    if not settings.RAPID_API_KEY:
        return None

    try:
        home_resp = requests.get(
            "https://api-football-v1.p.rapidapi.com/v3/teams",
            headers=_rapidapi_headers(),
            params={"search": home_team},
            timeout=8,
        )
        away_resp = requests.get(
            "https://api-football-v1.p.rapidapi.com/v3/teams",
            headers=_rapidapi_headers(),
            params={"search": away_team},
            timeout=8,
        )
        if home_resp.status_code != 200 or away_resp.status_code != 200:
            return None

        home_ids = [
            item.get("team", {}).get("id")
            for item in home_resp.json().get("response", [])
            if item.get("team", {}).get("id")
        ]
        away_names = {
            item.get("team", {}).get("name", "").lower()
            for item in away_resp.json().get("response", [])
            if item.get("team", {}).get("name")
        }

        for team_id in home_ids[:3]:
            fixtures_resp = requests.get(
                "https://api-football-v1.p.rapidapi.com/v3/fixtures",
                headers=_rapidapi_headers(),
                params={"date": match_date, "team": team_id},
                timeout=8,
            )
            if fixtures_resp.status_code != 200:
                continue

            for fixture in fixtures_resp.json().get("response", []):
                teams = fixture.get("teams", {})
                fixture_home = (teams.get("home", {}) or {}).get("name", "").lower()
                fixture_away = (teams.get("away", {}) or {}).get("name", "").lower()
                if not fixture_home or not fixture_away:
                    continue
                if away_names and fixture_away not in away_names:
                    continue

                fixture_id = fixture.get("fixture", {}).get("id")
                if not fixture_id:
                    continue

                stats_resp = requests.get(
                    "https://api-football-v1.p.rapidapi.com/v3/fixtures/statistics",
                    headers=_rapidapi_headers(),
                    params={"fixture": fixture_id},
                    timeout=8,
                )
                if stats_resp.status_code != 200:
                    continue

                home_corners = None
                away_corners = None
                for entry in stats_resp.json().get("response", []):
                    team_name = (entry.get("team", {}) or {}).get("name", "").lower()
                    stats = {item.get("type"): item.get("value") for item in entry.get("statistics", [])}
                    corners = _safe_int(stats.get("Corner Kicks") or stats.get("corners"))
                    if corners is None:
                        continue
                    if team_name == fixture_home:
                        home_corners = corners
                    elif team_name == fixture_away:
                        away_corners = corners

                if home_corners is None or away_corners is None:
                    continue

                return {
                    "home_corners": home_corners,
                    "away_corners": away_corners,
                    "total_corners": home_corners + away_corners,
                    "source": "rapidapi_fixture_statistics",
                }
    except Exception as e:
        logger.debug(f"[resolver] RapidAPI corner fetch failed: {e}")

    return None


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
                corner_stats = _fetch_espn_corner_stats(
                    game.get("sport_path", ESPN_SPORT_PATH.get(sport, "")),
                    game.get("league", ""),
                    game.get("fixture_id", ""),
                    game["home_team"],
                    game["away_team"],
                ) or _fetch_corner_stats(game["home_team"], game["away_team"], game["match_date"])

                await save_actual_result(
                    match_id       = match_id,
                    home_score     = game["home_score"],
                    away_score     = game["away_score"],
                    actual_outcome = outcome,
                    match_date     = game["match_date"],
                    corner_stats   = corner_stats,
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