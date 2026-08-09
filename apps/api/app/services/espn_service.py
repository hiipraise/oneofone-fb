# app/services/espn_service.py
"""
ESPN public API lookups (Sprint 5.3 file split).

Extracted from web_search_service.py: this module owns every direct ESPN
HTTP call (team search + team record). ESPN is the primary free structured
source — no key, no quota — so it is used aggressively before any paid
search provider is consulted. The orchestration layer in
web_search_service.py combines these lookups with search results.
"""
import logging
import re
from typing import Any, Dict, Optional

import numpy as np
import requests

from app.services.cache_utils import (
    CACHE_TTL_LONG,
    CACHE_TTL_MEDIUM,
    _cache_key,
    _get_cached,
    _set_cache,
)

logger = logging.getLogger(__name__)

ESPN_SPORT_MAP = {
    "soccer": ("soccer", "eng.1"),
}
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
_SOCCER_ESPN_LEAGUES = (
    "eng.1", "eng.2", "esp.1", "esp.2", "ger.1", "ita.1", "fra.1",
    "uefa.champions", "uefa.europa", "usa.1", "por.1", "ned.1",
    "arg.1", "bra.1", "tur.1", "mex.1", "ksa.1",
)
# Platform is soccer-only


def _espn_team_search(team_name: str, sport: str) -> Optional[Dict]:
    ck = _cache_key("espn_team_v2", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    espn_sport, default_league = ESPN_SPORT_MAP.get(sport, ("soccer", "eng.1"))
    # Platform is soccer-only — default to soccer leagues for supported sport
    leagues = _SOCCER_ESPN_LEAGUES if sport == "soccer" else (default_league,)
    try:
        tl = team_name.lower()
        for league in leagues:
            resp = requests.get(f"{ESPN_BASE}/{espn_sport}/{league}/teams", timeout=8)
            if resp.status_code != 200:
                continue
            teams = resp.json().get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
            for entry in teams:
                t = entry.get("team", {})
                names = [
                    t.get("displayName", "").lower(),
                    t.get("shortDisplayName", "").lower(),
                    t.get("name", "").lower(),
                    t.get("nickname", "").lower(),
                ]
                if any(tl in n or n in tl for n in names if n):
                    found = dict(t)
                    found["_league"] = league
                    _set_cache(ck, found, ttl=CACHE_TTL_LONG)
                    return found
    except Exception as e:
        logger.debug(f"ESPN team search [{sport}]: {e}")
    return None


def _espn_team_record(team_name: str, sport: str) -> Dict[str, Any]:
    ck = _cache_key("espn_record_v2", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    result: Dict[str, Any] = {
        "espn_win_pct": 0.5,
        "ranking_signal": 0.5,
        "espn_data_available": False,
    }

    team = _espn_team_search(team_name, sport)
    if not team:
        return result

    team_id = team.get("id")
    if not team_id:
        return result

    espn_sport, default_league = ESPN_SPORT_MAP.get(sport, ("soccer", "eng.1"))
    league = team.get("_league", default_league)
    try:
        resp = requests.get(f"{ESPN_BASE}/{espn_sport}/{league}/teams/{team_id}", timeout=8)
        if resp.status_code != 200:
            return result

        data = resp.json().get("team", {})
        record = data.get("record", {}).get("items", [])
        if record:
            stats  = {s["name"]: s["value"] for s in record[0].get("stats", [])}
            wins   = float(stats.get("wins", 0))
            losses = float(stats.get("losses", 0))
            total  = wins + losses + float(stats.get("ties", 0)) + float(stats.get("draws", 0))
            if total > 0:
                result["espn_win_pct"]        = float(min(wins / total, 1.0))
                result["espn_data_available"] = True

        standing   = data.get("standingSummary", "")
        rank_match = re.search(r"(\d+)(st|nd|rd|th)", standing)
        if rank_match:
            rank = int(rank_match.group(1))
            result["ranking_signal"] = float(np.clip(1.0 - (rank - 1) / 20.0, 0.05, 1.0))

        _set_cache(ck, result, ttl=CACHE_TTL_MEDIUM)
    except Exception as e:
        logger.debug(f"ESPN record [{team_name}]: {e}")

    return result
