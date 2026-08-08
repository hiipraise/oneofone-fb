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
