# app/services/match_validation_service.py
"""
Match Validation Service — The Odds API
Supports: soccer and basketball only.
"""
import logging
import re
import unicodedata
from datetime import datetime, timezone
from app.utils.timezone import now_wat, WAT
from typing import Dict, List, Optional, Any

import requests

from app.config.settings import settings
from app.services.web_search_service import _cache_key, _get_cached, _set_cache

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS: Dict[str, List[str]] = {
    "soccer": [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
        "soccer_uefa_champs_league",
        "soccer_uefa_europa_league",
        "soccer_usa_mls",
        "soccer_portugal_primeira_liga",
        "soccer_netherlands_eredivisie",
        "soccer_brazil_campeonato",
        "soccer_argentina_primera_division",
        "soccer_turkey_super_league",
        "soccer_saudi_premier_league",
        "soccer_mexico_ligamx",
        "soccer_conmebol_copa_libertadores",
    ],
    "basketball": [
        "basketball_nba",
        "basketball_euroleague",
        "basketball_ncaab",
        "basketball_nbl",
    ],
}



ESPN_SCOREBOARD_LEAGUES: Dict[str, List[tuple[str, str, str]]] = {
    "soccer": [
        ("soccer", "eng.1", "Premier League"),
        ("soccer", "esp.1", "LaLiga"),
        ("soccer", "ger.1", "Bundesliga"),
        ("soccer", "ita.1", "Serie A"),
        ("soccer", "fra.1", "Ligue 1"),
        ("soccer", "usa.1", "MLS"),
        ("soccer", "por.1", "Primeira Liga"),
        ("soccer", "ned.1", "Eredivisie"),
        ("soccer", "mex.1", "Liga MX"),
        ("soccer", "uefa.champions", "UEFA Champions League"),
        ("soccer", "uefa.europa", "UEFA Europa League"),
    ],
    "basketball": [
        ("basketball", "nba", "NBA"),
        ("basketball", "mens-college-basketball", "NCAA Men's Basketball"),
    ],
}



ESPN_SPORT_PATH: Dict[str, str] = {
    sport: league_rows[0][0]
    for sport, league_rows in ESPN_SCOREBOARD_LEAGUES.items()
    if league_rows
}

ESPN_LEAGUES: Dict[str, List[str]] = {
    sport: [league for _, league, _ in league_rows]
    for sport, league_rows in ESPN_SCOREBOARD_LEAGUES.items()
}

_MIN_PREFIX = 4


def fetch_available_leagues(sport: str) -> List[Dict]:
    ck = _cache_key("leagues_v3", {"sport": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    if not settings.ODDS_API_KEY:
        return []

    try:
        resp = requests.get(
            f"{ODDS_API_BASE}/sports",
            params={"apiKey": settings.ODDS_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Odds API /sports error: {e}")
        return []

    known = set(SPORT_KEYS.get(sport.lower(), []))
    kws = _sport_keywords(sport)
    leagues = [
        {
            "id": item.get("key"),
            "name": item.get("title", ""),
            "country": item.get("group", ""),
            "active": item.get("active", False),
        }
        for item in resp.json()
        if item.get("key") in known
        or any(kw in item.get("group", "").lower() for kw in kws)
    ]

    _set_cache(ck, leagues)
    logger.info(f"Odds API leagues [{sport}]: {len(leagues)} found")
    return leagues


def search_fixtures(
    home_team: str,
    away_team: str,
    sport: str,
    date: Optional[str] = None,
) -> Optional[Dict]:
    ck = _cache_key("fixture_v3", {
        "h": home_team.lower(), "a": away_team.lower(),
        "s": sport, "d": date,
    })
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    if not settings.ODDS_API_KEY:
        return None

    for sport_key in SPORT_KEYS.get(sport.lower(), []):
        result = _search_in_sport_key(home_team, away_team, sport_key, date)
        if result:
            _set_cache(ck, result)
            logger.info(f"Fixture found [{sport_key}]: {result['home_team']} vs {result['away_team']}")
            return result

    # Dynamic fallback
    for sport_key in _dynamic_sport_keys(sport):
        if sport_key in SPORT_KEYS.get(sport.lower(), []):
            continue
        result = _search_in_sport_key(home_team, away_team, sport_key, date)
        if result:
            _set_cache(ck, result)
            return result

    logger.info(f"No fixture found: {home_team} vs {away_team} [{sport}]")
    return None


def find_matching_espn_event(
    home_team: str,
    away_team: str,
    sport: str,
    date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    sport = sport.lower()
    leagues = ESPN_SCOREBOARD_LEAGUES.get(sport, [])
    if not leagues:
        return None

    target_date = date or datetime.now(WAT).strftime("%Y-%m-%d")

    for espn_sport, league, league_name in leagues:
        try:
            resp = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{league}/scoreboard",
                params={"dates": target_date.replace("-", "")},
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            for event in resp.json().get("events", []):
                competition = (event.get("competitions") or [{}])[0]
                competitors = competition.get("competitors") or []
                home = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not home or not away:
                    continue

                home_name = (
                    home.get("team", {}).get("displayName")
                    or home.get("team", {}).get("shortDisplayName")
                    or ""
                )
                away_name = (
                    away.get("team", {}).get("displayName")
                    or away.get("team", {}).get("shortDisplayName")
                    or ""
                )
                if not (
                    _fuzzy_match(home_team, home_name)
                    and _fuzzy_match(away_team, away_name)
                ):
                    continue

                status = event.get("status", {}).get("type", {})
                return {
                    "fixture_id": event.get("id", ""),
                    "home_team": home_name,
                    "away_team": away_name,
                    "sport": sport,
                    "league": league_name,
                    "league_id": league,
                    "match_date": (event.get("date") or "")[:10] or target_date,
                    "match_time": (event.get("date") or "")[11:16] if event.get("date") else "",
                    "validated": True,
                    "source": "espn",
                    "status": {
                        "name": status.get("name"),
                        "description": status.get("description"),
                        "detail": status.get("detail"),
                        "state": status.get("state"),
                        "completed": bool(status.get("completed")),
                    },
                }
        except Exception as e:
            logger.debug(f"ESPN event search error [{sport}:{league}]: {e}")

    return None


def is_fixture_completed(
    home_team: str,
    away_team: str,
    sport: str,
    date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    event = find_matching_espn_event(home_team, away_team, sport, date)
    if not event:
        return None

    status = event.get("status") or {}
    detail = (status.get("detail") or "").strip().lower()
    state = (status.get("state") or "").strip().lower()
    completed = bool(status.get("completed"))

    if completed or state == "post" or "full time" in detail or detail == "ft":
        return {
            **event,
            "completed": True,
            "status_text": status.get("detail") or status.get("description") or status.get("name"),
        }

    return {
        **event,
        "completed": False,
        "status_text": status.get("detail") or status.get("description") or status.get("name"),
    }


def fetch_today_fixtures(sport: str = "soccer") -> List[Dict]:
    if not settings.ODDS_API_KEY:
        return []

    sport = sport.lower()
    if sport not in SPORT_KEYS:
        logger.warning(f"Unsupported sport for fixture fetch: {sport}")
        return []

    today = now_wat().strftime("%Y-%m-%d")
    fixtures: List[Dict] = []
    seen: set = set()

    for sport_key in SPORT_KEYS[sport][:8]:
        try:
            resp = requests.get(
                f"{ODDS_API_BASE}/sports/{sport_key}/events",
                params={"apiKey": settings.ODDS_API_KEY, "dateFormat": "iso"},
                timeout=10,
            )
            if resp.status_code == 401:
                logger.error("Odds API: invalid key")
                break
            if resp.status_code in (404, 422):
                continue
            if resp.status_code != 200:
                continue

            for event in resp.json():
                commence = event.get("commence_time", "")
                if commence[:10] != today:
                    continue
                fid = event.get("id", "")
                if fid in seen:
                    continue
                seen.add(fid)
                fixtures.append({
                    "fixture_id": fid,
                    "home_team": event.get("home_team"),
                    "away_team": event.get("away_team"),
                    "sport": sport,
                    "league": sport_key.replace("_", " ").title(),
                    "league_id": sport_key,
                    "match_date": today,
                    "match_time": commence[11:16] if len(commence) > 10 else "",
                    "validated": True,
                    "source": "odds_api",
                })
        except Exception as e:
            logger.warning(f"Fixture fetch error [{sport_key}]: {e}")

    logger.info(f"Today fixtures: {len(fixtures)} [{sport}] for {today}")
    return fixtures


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _search_in_sport_key(
    home: str, away: str, sport_key: str, target_date: Optional[str]
) -> Optional[Dict]:
    try:
        resp = requests.get(
            f"{ODDS_API_BASE}/sports/{sport_key}/events",
            params={"apiKey": settings.ODDS_API_KEY, "dateFormat": "iso"},
            timeout=10,
        )
        if resp.status_code in (401, 403, 404, 422):
            return None
        if resp.status_code != 200:
            return None

        for event in resp.json():
            h = event.get("home_team", "")
            a = event.get("away_team", "")
            if not (_fuzzy_match(home, h) and _fuzzy_match(away, a)):
                continue

            commence   = event.get("commence_time", "")
            event_date = commence[:10] if commence else ""

            if target_date and event_date:
                try:
                    td = datetime.strptime(target_date, "%Y-%m-%d")
                    ed = datetime.strptime(event_date, "%Y-%m-%d")
                    if abs((td - ed).days) > 1:
                        continue
                except Exception:
                    pass

            return {
                "fixture_id": event.get("id"),
                "home_team": h,
                "away_team": a,
                "league_name": sport_key.replace("_", " ").title(),
                "league_id": sport_key,
                "match_date": event_date,
                "match_time": commence[11:16] if len(commence) > 10 else "",
                "validated": True,
                "source": "odds_api",
            }
    except Exception as e:
        logger.debug(f"Search error [{sport_key}]: {e}")
    return None


def _dynamic_sport_keys(sport: str) -> List[str]:
    if not settings.ODDS_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{ODDS_API_BASE}/sports",
            params={"apiKey": settings.ODDS_API_KEY},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        kws = _sport_keywords(sport)
        return [
            item["key"] for item in resp.json()
            if any(
                kw in item.get("group", "").lower() or kw in item.get("key", "").lower()
                for kw in kws
            )
        ]
    except Exception:
        return []


def _sport_keywords(sport: str) -> List[str]:
    return {
        "soccer":     ["soccer"],
        "basketball": ["basketball"],
    }.get(sport.lower(), [sport.lower()])


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy matching
# ─────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    noise = r"\b(fc|cf|ac|sc|afc|bfc|as|ss|rc|ud|cd|rcd|sfc|bsc|if|sk|fk|ik|vfl|tsv|sv)\b"
    s = re.sub(noise, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> List[str]:
    return [t for t in _norm(s).split() if len(t) >= 3]


def _acronym(s: str) -> str:
    return "".join(w[0] for w in _norm(s).split() if w)


def _prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            n += 1
        else:
            break
    return n


def _fuzzy_match(inp: str, api: str) -> bool:
    if not inp or not api:
        return False
    ni, na = _norm(inp), _norm(api)
    if not ni or not na:
        return False
    if ni == na:
        return True
    if len(ni) >= 4 and (ni in na or na in ni):
        return True
    ti, ta = set(_tokens(ni)), set(_tokens(na))
    if ti and ta and ti & ta:
        return True
    ai, aa = _acronym(inp), _acronym(api)
    if (len(ai) >= 2 and (ai == na or ai == aa)) or (len(ni) >= 2 and ni == aa):
        return True
    for a in ([ni] + list(ti)):
        for b in ([na] + list(ta)):
            if _prefix_len(a, b) >= _MIN_PREFIX:
                return True
    return False

def fetch_espn_today_fixtures(sport: str = "soccer") -> List[Dict]:
    sport = sport.lower()
    leagues = ESPN_SCOREBOARD_LEAGUES.get(sport, [])
    if not leagues:
        return []

    today = now_wat().strftime("%Y-%m-%d")
    fixtures: List[Dict] = []
    seen: set[tuple[str, str, str]] = set()

    for espn_sport, league, league_name in leagues:
        try:
            resp = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{league}/scoreboard",
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            for event in resp.json().get("events", []):
                commence = event.get("date", "")
                if commence[:10] != today:
                    continue

                competition = (event.get("competitions") or [{}])[0]
                competitors = competition.get("competitors") or []
                home = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not home or not away:
                    continue

                home_name = home.get("team", {}).get("displayName") or home.get("team", {}).get("shortDisplayName")
                away_name = away.get("team", {}).get("displayName") or away.get("team", {}).get("shortDisplayName")
                if not home_name or not away_name:
                    continue

                dedupe_key = (home_name.lower(), away_name.lower(), today)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                fixtures.append({
                    "fixture_id": event.get("id", ""),
                    "home_team": home_name,
                    "away_team": away_name,
                    "sport": sport,
                    "league": league_name,
                    "league_id": league,
                    "match_date": today,
                    "match_time": commence[11:16] if len(commence) > 10 else "",
                    "validated": True,
                    "source": "espn",
                })
        except Exception as e:
            logger.warning(f"ESPN fixture fetch error [{sport}:{league}]: {e}")

    logger.info(f"Today fixtures from ESPN: {len(fixtures)} [{sport}] for {today}")
    return fixtures
