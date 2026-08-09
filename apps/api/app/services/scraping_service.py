"""Free football scraping helpers with lightweight in-memory pacing/cache.

These helpers intentionally avoid paid providers and keep request volume low.
They return best-effort dictionaries so prediction generation can record source
provenance without failing when a public endpoint changes shape.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup, Comment

from app.config.settings import settings

logger = logging.getLogger(__name__)
_CACHE: dict[str, tuple[float, Any]] = {}
_LAST_REQUEST_AT = 0.0


@dataclass(frozen=True)
class ScrapeResult:
    source: str
    available: bool
    data: Dict[str, Any]
    reason: Optional[str] = None


def _get(key: str) -> Any:
    item = _CACHE.get(key)
    if not item:
        return None
    expires, value = item
    if expires <= time.time():
        _CACHE.pop(key, None)
        return None
    return value


def _set(key: str, value: Any, ttl: int = 21_600) -> Any:
    _CACHE[key] = (time.time() + ttl, value)
    return value


def _request(url: str, **kwargs) -> Optional[requests.Response]:
    global _LAST_REQUEST_AT
    wait = max(0.0, settings.SCRAPING_DELAY_SECONDS - (time.time() - _LAST_REQUEST_AT))
    if wait:
        time.sleep(wait)
    _LAST_REQUEST_AT = time.time()
    try:
        return requests.get(url, timeout=10, headers={"User-Agent": "OneOfOneBot/1.0"}, **kwargs)
    except Exception as exc:
        logger.debug("Free scrape request failed for %s: %s", url, exc)
        return None


def fetch_fbref_match_report(url: str) -> ScrapeResult:
    key = f"fbref:{url}"
    cached = _get(key)
    if cached is not None:
        return cached
    resp = _request(url)
    if not resp or resp.status_code != 200:
        return _set(key, ScrapeResult("fbref", False, {}, "request_failed"))
    soup = BeautifulSoup(resp.text, "lxml")
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        soup.append(BeautifulSoup(comment, "lxml"))
    text = soup.get_text(" ", strip=True).lower()
    data = {"has_xg": " xg " in f" {text} ", "has_shots": "shots" in text}
    return _set(key, ScrapeResult("fbref", any(data.values()), data, None if any(data.values()) else "no_stats"))


def fetch_understat_match(match_id: str) -> ScrapeResult:
    key = f"understat:{match_id}"
    cached = _get(key)
    if cached is not None:
        return cached
    resp = _request(f"https://understat.com/match/{match_id}")
    if not resp or resp.status_code != 200:
        return _set(key, ScrapeResult("understat", False, {}, "request_failed"))
    match = re.search(r"shotsData\s*=\s*JSON\.parse\('(.+?)'\)", resp.text)
    if not match:
        return _set(key, ScrapeResult("understat", False, {}, "shots_json_missing"))
    try:
        raw = match.group(1).encode("utf-8").decode("unicode_escape")
        data = json.loads(raw)
        return _set(key, ScrapeResult("understat", True, {"shots": data}))
    except Exception as exc:
        return _set(key, ScrapeResult("understat", False, {}, f"parse_failed:{exc}"))


def fetch_sofascore_corners(event_id: str) -> ScrapeResult:
    key = f"sofascore:corners:{event_id}"
    cached = _get(key)
    if cached is not None:
        return cached
    resp = _request(f"https://www.sofascore.com/api/v1/event/{event_id}/statistics")
    if not resp or resp.status_code != 200:
        return _set(key, ScrapeResult("sofascore", False, {}, "request_failed"))
    try:
        payload = resp.json()
        for group in payload.get("statistics", []):
            for item in group.get("groups", []):
                for stat in item.get("statisticsItems", []):
                    name = str(stat.get("name", "")).lower()
                    if "corner" in name:
                        home = int(float(str(stat.get("home", 0)).replace("%", "")))
                        away = int(float(str(stat.get("away", 0)).replace("%", "")))
                        return _set(key, ScrapeResult("sofascore", True, {"home_corners": home, "away_corners": away, "total_corners": home + away}))
    except Exception as exc:
        return _set(key, ScrapeResult("sofascore", False, {}, f"parse_failed:{exc}"))
    return _set(key, ScrapeResult("sofascore", False, {}, "corner_stat_missing"))


# ── Understat real-xG lookup (Sprint 8: prediction-engine improvement) ─────
# Understat covers EPL, La Liga, Bundesliga, Serie A, Ligue 1 and RFPL only;
# fixtures outside those leagues silently fall back to the engine's heuristic.
# All lookups go through the shared in-memory cache + request pacing.
_UNDERSTAT_LEAGUE_KEYS = {
    "premier league": "EPL", "epl": "EPL", "english premier league": "EPL",
    "la liga": "La_Liga", "laliga": "La_Liga", "spanish la liga": "La_Liga",
    "bundesliga": "Bundesliga", "german bundesliga": "Bundesliga", "1. bundesliga": "Bundesliga",
    "serie a": "Serie_A", "seriea": "Serie_A", "italian serie a": "Serie_A",
    "ligue 1": "Ligue_1", "ligue1": "Ligue_1", "french ligue 1": "Ligue_1",
    "rfpl": "RFPL", "russian premier league": "RFPL",
}


def _norm_team(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _understat_league_key(league: str) -> Optional[str]:
    if not league:
        return None
    return _UNDERSTAT_LEAGUE_KEYS.get(league.strip().lower())


def lookup_understat_match_id(home_team: str, away_team: str, league: str = "") -> Optional[str]:
    """Find the Understat match id for a fixture by team names (best-effort)."""
    lkey = _understat_league_key(league)
    if not lkey:
        return None
    key = f"understat:league:{lkey}"
    cached = _get(key)
    if cached is None:
        resp = _request(f"https://understat.com/league/{lkey}")
        if not resp or resp.status_code != 200:
            return None
        match = re.search(r"datesData\s*=\s*JSON\.parse\('(.+?)'\)", resp.text)
        if not match:
            return None
        try:
            raw = match.group(1).encode("utf-8").decode("unicode_escape")
            fixtures = json.loads(raw)
        except Exception as exc:
            logger.debug("Understat league page parse failed: %s", exc)
            return None
        _set(key, fixtures, ttl=21_600)
    else:
        fixtures = cached

    h_n = _norm_team(home_team)
    a_n = _norm_team(away_team)
    if not h_n or not a_n:
        return None
    for fx in fixtures or []:
        fh = _norm_team(fx.get("h") or "")
        fa = _norm_team(fx.get("a") or "")
        exact = (fh == h_n and fa == a_n)
        contained = (
            fh and fa and len(fh) >= 4 and len(fa) >= 4
            and (fh in h_n or h_n in fh) and (fa in a_n or a_n in fa)
        )
        if exact or contained:
            mid = str(fx.get("id") or "")
            if mid:
                return mid
    return None


def fetch_understat_match_xg(match_id: str) -> ScrapeResult:
    """Extract per-team expected goals from an Understat match page."""
    res = fetch_understat_match(match_id)
    if not res.available:
        return res
    shots = res.data.get("shots") or {}
    h_shots = shots.get("h") or []
    a_shots = shots.get("a") or []
    try:
        xg_home = round(sum(float(s.get("xG", 0) or 0) for s in h_shots), 3)
        xg_away = round(sum(float(s.get("xG", 0) or 0) for s in a_shots), 3)
    except Exception as exc:
        return ScrapeResult("understat", False, {}, f"xg_parse_failed:{exc}")
    if xg_home <= 0 and xg_away <= 0:
        return ScrapeResult("understat", False, {}, "no_xg_data")
    return ScrapeResult("understat", True, {"home_xg": xg_home, "away_xg": xg_away})


def lookup_understat_xg(home_team: str, away_team: str, league: str = "") -> Dict[str, Any]:
    """
    Best-effort real expected-goals lookup (JSON-safe, cache-friendly).

    Returns either {"available": True, "source": "understat", "home_xg": ..,
    "away_xg": ..} or {"available": False, "reason": ..} — never raises, so the
    prediction pipeline can call this without failing the fixture.
    """
    match_id = lookup_understat_match_id(home_team, away_team, league)
    if not match_id:
        return {"available": False, "reason": "match_id_not_found", "source": "understat"}
    res = fetch_understat_match_xg(match_id)
    if not res.available:
        return {"available": False, "reason": res.reason or "no_xg", "source": "understat"}
    return {
        "available": True, "source": "understat",
        "home_xg": res.data["home_xg"], "away_xg": res.data["away_xg"],
    }


def fetch_openligadb_matches(league: str = "bl1", season: int | None = None) -> ScrapeResult:
    season_part = f"/{season}" if season else ""
    url = f"https://api.openligadb.de/getmatchdata/{league}{season_part}"
    key = f"openligadb:{league}:{season or 'current'}"
    cached = _get(key)
    if cached is not None:
        return cached
    resp = _request(url)
    if not resp or resp.status_code != 200:
        return _set(key, ScrapeResult("openligadb", False, {}, "request_failed"))
    try:
        return _set(key, ScrapeResult("openligadb", True, {"matches": resp.json()}))
    except Exception as exc:
        return _set(key, ScrapeResult("openligadb", False, {}, f"parse_failed:{exc}"))
