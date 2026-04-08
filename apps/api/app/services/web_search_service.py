# app/services/web_search_service.py
"""
Web Search & Data Service

Search provider hierarchy (quota-free to quota-heavy):
  1. ESPN public API          — free, no key, no quota
  2. Odds API                 — free tier, no quota impact
  3. Serper.dev               — 2,500 free searches/month (10× SerpAPI)
  4. DuckDuckGo (ddgs)        — unlimited fallback, no key required
  5. Statistical defaults     — last resort

SerpAPI has been removed entirely. Add to .env:
    SERPER_API_KEY=<your key from serper.dev — free signup>

Budget tracking now reflects Serper.dev's 2,500/month limit.
DuckDuckGo calls are NOT quota-counted (they're free).
"""
import json
import asyncio
import logging
import re
import time
import hashlib
import threading
from datetime import datetime
from app.utils.timezone import now_wat
from typing import Dict, List, Optional, Any

import numpy as np
import requests

from app.config.settings import settings
from app.services.sport_key_catalog import SPORT_KEYS

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cache configuration  (unchanged — stable interface)
# ─────────────────────────────────────────────────────────────────────────────

CACHE_TTL_SHORT  = 3_600   #  1 h
CACHE_TTL_MEDIUM = 21_600  #  6 h
CACHE_TTL_LONG   = 86_400  # 24 h

# NOTE:
# File-based cache/quota state causes drift across pods and serverless instances.
# Keep runtime state in memory by default (portable + free), and let Mongo-backed
# quota_service provide persisted monthly accounting for production dashboards.
ENABLE_FILE_CACHE = False

_mem_cache: Dict[str, Dict] = {}
_quota_state: Dict[str, Any] = {"month": "", "count": 0}


def _cache_key(ns: str, params: Optional[dict] = None) -> str:
    return hashlib.md5((ns + str(sorted((params or {}).items()))).encode()).hexdigest()


def _get_cached(key: str) -> Optional[Any]:
    entry = _mem_cache.get(key)
    if entry and time.time() - entry["ts"] < entry.get("ttl", CACHE_TTL_MEDIUM):
        return entry["data"]
    return None


def _set_cache(key: str, data: Any, ttl: int = CACHE_TTL_MEDIUM) -> None:
    _mem_cache[key] = {"ts": time.time(), "data": data, "ttl": ttl}


# ─────────────────────────────────────────────────────────────────────────────
# Monthly Serper.dev quota tracker  (2,500 free/month)
# ─────────────────────────────────────────────────────────────────────────────

MONTHLY_BUDGET = 2_400  # hard cap; keeps 100 buffer from the 2,500 free limit


def _quota_load() -> Dict:
    return dict(_quota_state)


def _quota_save(data: Dict) -> None:
    _quota_state.update(
        {
            "month": str(data.get("month", "")),
            "count": int(data.get("count", 0)),
        }
    )


def _quota_check() -> bool:
    data = _quota_load()
    current_month = now_wat().strftime("%Y-%m")
    if data.get("month") != current_month:
        data = {"month": current_month, "count": 0}
    if data["count"] >= MONTHLY_BUDGET:
        logger.warning(
            f"Serper.dev monthly budget exhausted ({data['count']}/{MONTHLY_BUDGET}). "
            "Falling back to DuckDuckGo."
        )
        return False
    return True


def _quota_increment() -> None:
    data = _quota_load()
    current_month = now_wat().strftime("%Y-%m")
    if data.get("month") != current_month:
        data = {"month": current_month, "count": 0}
    data["count"] = data.get("count", 0) + 1
    _quota_save(data)
    logger.debug(f"Serper quota: {data['count']}/{MONTHLY_BUDGET} this month")
    _persist_quota_increment_async()


def _persist_quota_increment_async() -> None:
    """
    Mirror in-memory Serper usage to Mongo so dashboards stay accurate
    across instances. Best effort only.
    """
    try:
        from app.services.quota_service import record_serper_calls

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(record_serper_calls(1))
            return
        except RuntimeError:
            pass

        def _runner():
            try:
                asyncio.run(record_serper_calls(1))
            except Exception as exc:
                logger.debug(f"Serper quota persistence background task failed: {exc}")

        threading.Thread(target=_runner, daemon=True).start()
    except Exception as e:
        logger.debug(f"Serper quota persistence skipped: {e}")


def get_serper_usage() -> Dict:
    """Return current Serper.dev monthly usage snapshot."""
    data = _quota_load()
    current_month = now_wat().strftime("%Y-%m")
    if data.get("month") != current_month:
        return {
            "month": current_month, "used": 0,
            "budget": MONTHLY_BUDGET, "remaining": MONTHLY_BUDGET,
        }
    return {
        "month":     data["month"],
        "used":      data["count"],
        "budget":    MONTHLY_BUDGET,
        "remaining": max(0, MONTHLY_BUDGET - data["count"]),
    }


def get_serpapi_usage() -> Dict:
    """Backward-compatible wrapper. Use get_serper_usage()."""
    return get_serper_usage()


# ─────────────────────────────────────────────────────────────────────────────
# DuckDuckGo fallback  (zero cost, no key, no quota)
# ─────────────────────────────────────────────────────────────────────────────

def _duckduckgo_html_search(query: str, num_results: int = 5) -> List[Dict]:
    """
    Lightweight DuckDuckGo HTML search that avoids multi-engine scraping.
    This path is more stable in hosted environments where third-party engines
    frequently return captchas/rate-limits.
    """
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.debug(
                f"DuckDuckGo HTML returned {resp.status_code} for query [{query[:50]}]"
            )
            return []

        html = resp.text
        links = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippets = re.findall(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|'
            r'<div[^>]*class="result__snippet"[^>]*>(.*?)</div>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        results: List[Dict] = []
        for idx, (href, title_html) in enumerate(links[:num_results]):
            raw_snippet = ""
            if idx < len(snippets):
                raw_snippet = snippets[idx][0] or snippets[idx][1]
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()
            results.append(
                {
                    "title": title,
                    "link": href,
                    "snippet": snippet,
                }
            )
        return results
    except Exception as e:
        logger.debug(f"DuckDuckGo HTML search error [{query[:50]}]: {e}")
        return []


def _duckduckgo_search(query: str, num_results: int = 5) -> List[Dict]:
    """
    Use the `duckduckgo-search` package as a free fallback.
    Install: pip install duckduckgo-search
    Completely free — no API key, no monthly limit.
    Results are slightly less precise than Google but sufficient for sports context.
    """
    # Prefer the direct HTML endpoint first to avoid noisy multi-engine failures.
    html_results = _duckduckgo_html_search(query=query, num_results=num_results)
    if html_results:
        return html_results

    try:
        DDGS = None
        try:
            from ddgs import DDGS as _DDGS  # package renamed from duckduckgo_search
            DDGS = _DDGS
        except ImportError:
            from duckduckgo_search import DDGS as _DDGS
            DDGS = _DDGS

        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=num_results))
        return [
            {
                "title":   r.get("title", ""),
                "link":    r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in raw
        ]
    except ImportError:
        logger.warning(
            "No DuckDuckGo provider installed. "
            "Run: pip install ddgs (or duckduckgo-search)."
        )
        return []
    except Exception as e:
        logger.warning(
            f"DuckDuckGo search error [{query[:50]}]: {e} "
            "(after HTML fallback path)"
        )
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Serper.dev  (primary paid search — 2,500 free/month)
# ─────────────────────────────────────────────────────────────────────────────

_serp_lock         = threading.Lock()
_serp_last_call_ts = 0.0
_MIN_CALL_INTERVAL = 0.5         # serper.dev handles higher throughput than SerpAPI
_MAX_RETRIES       = 2
_RETRY_BACKOFF     = [2.0, 5.0]


def _throttle() -> None:
    global _serp_last_call_ts
    with _serp_lock:
        elapsed = time.time() - _serp_last_call_ts
        if elapsed < _MIN_CALL_INTERVAL:
            time.sleep(_MIN_CALL_INTERVAL - elapsed)
        _serp_last_call_ts = time.time()


def _serper_search(query: str, num_results: int = 5) -> List[Dict]:
    """
    Serper.dev Google Search API.
    Sign up free at https://serper.dev — 2,500 searches/month on the free plan.
    Add SERPER_API_KEY=<key> to your .env file.
    """
    if not settings.SERPER_API_KEY:
        return []

    for attempt in range(_MAX_RETRIES + 1):
        _throttle()
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY":    settings.SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": num_results, "gl": "us", "hl": "en"},
                timeout=12,
            )

            if resp.status_code == 429:
                wait = _RETRY_BACKOFF[attempt] if attempt < len(_RETRY_BACKOFF) else _RETRY_BACKOFF[-1]
                logger.warning(
                    f"Serper 429 [{query[:50]}] — "
                    f"attempt {attempt + 1}/{_MAX_RETRIES + 1}, retrying in {wait}s"
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
                    continue
                return []  # quota NOT charged

            resp.raise_for_status()

            data    = resp.json()
            organic = data.get("organic", [])
            results = [
                {
                    "title":   r.get("title", ""),
                    "link":    r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                }
                for r in organic[:num_results]
            ]

            _quota_increment()
            return results

        except requests.exceptions.HTTPError as e:
            logger.warning(f"Serper HTTP error [{query[:50]}]: {e}")
            return []
        except Exception as e:
            logger.warning(f"Serper error [{query[:50]}]: {e}")
            return []

    return []


# ─────────────────────────────────────────────────────────────────────────────
# Public search entry point  (replaces search_serpapi — same signature)
# ─────────────────────────────────────────────────────────────────────────────

def search_web(query: str, num_results: int = 5) -> List[Dict]:
    """
    Primary web-search entry point.

    Resolution order:
      1. Memory/disk cache     — free, instant
      2. Serper.dev            — 2,500 free searches/month (Google results)
      3. DuckDuckGo fallback   — unlimited free (no key needed)
    """
    ck = _cache_key("search_v4", {"q": query.lower().strip(), "n": num_results})
    cached = _get_cached(ck)
    if cached is not None:
        return cached  # cache hit — no quota consumed

    results: List[Dict] = []

    # ── Try Serper.dev first (quota-aware) ────────────────────────────────
    if settings.SERPER_API_KEY and _quota_check():
        results = _serper_search(query, num_results)

    # ── Fallback to DuckDuckGo when Serper is unavailable or exhausted ────
    if not results:
        logger.info(f"Falling back to DuckDuckGo for: {query[:60]}")
        results = _duckduckgo_search(query, num_results)

    if results:
        _set_cache(ck, results, ttl=CACHE_TTL_MEDIUM)

    return results


# Backward-compatible wrapper for one release window.
def search_serpapi(query: str, num_results: int = 5) -> List[Dict]:
    """Deprecated wrapper. Use search_web()."""
    return search_web(query=query, num_results=num_results)


# ─────────────────────────────────────────────────────────────────────────────
# ESPN public API  (free — use aggressively before search)
# ─────────────────────────────────────────────────────────────────────────────

ESPN_SPORT_MAP = {
    "soccer":     ("soccer",     "eng.1"),
    "basketball": ("basketball", "nba"),
}
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
_SOCCER_ESPN_LEAGUES = (
    "eng.1", "eng.2", "esp.1", "esp.2", "ger.1", "ita.1", "fra.1",
    "uefa.champions", "uefa.europa", "usa.1", "por.1", "ned.1",
    "arg.1", "bra.1", "tur.1", "mex.1", "ksa.1",
)
_BASKETBALL_ESPN_LEAGUES = (
    "nba",
    "wnba",
    "mens-college-basketball",
    "womens-college-basketball",
    "euroleague",
    "eurocup",
    # Domestic leagues (best-effort; ESPN may not expose all in every region/season)
    "acb",
    "liga-acb",
    "spain.acb",
    "italy.lega.a",
    "lega-a",
    "germany.bbl",
    "easycredit-bbl",
    "greece.a1",
    "esake",
    "france.lnb",
    "betclic-elite",
    "turkey.bsl",
    "turkish-bsl",
)


def _espn_team_search(team_name: str, sport: str) -> Optional[Dict]:
    ck = _cache_key("espn_team_v2", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    espn_sport, default_league = ESPN_SPORT_MAP.get(sport, ("soccer", "eng.1"))
    if sport == "soccer":
        leagues = _SOCCER_ESPN_LEAGUES
    elif sport == "basketball":
        leagues = _BASKETBALL_ESPN_LEAGUES
    else:
        leagues = (default_league,)
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


# ─────────────────────────────────────────────────────────────────────────────
# RapidAPI sports data  (structured — zero search queries consumed)
# ─────────────────────────────────────────────────────────────────────────────

RAPIDAPI_HOST_FOOTBALL = "api-football-v1.p.rapidapi.com"
RAPIDAPI_HOST_NBA      = "api-nba-v1.p.rapidapi.com"


def _rapidapi_headers() -> Dict[str, str]:
    return {
        "X-RapidAPI-Key":  settings.RAPID_API_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST_FOOTBALL,
    }


def _fetch_rapidapi_team_stats(team_name: str, sport: str) -> Optional[Dict[str, Any]]:
    """
    Pull structured stats from RapidAPI (API-Football / API-NBA).
    Zero search queries consumed — uses your existing RAPID_API_KEY.
    Returns None if unavailable so callers fall back to search.
    """
    if not settings.RAPID_API_KEY:
        return None

    ck = _cache_key("rapidapi_stats_v1", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    try:
        if sport == "soccer":
            # Search for team ID
            resp = requests.get(
                "https://api-football-v1.p.rapidapi.com/v3/teams",
                headers=_rapidapi_headers(),
                params={"search": team_name},
                timeout=8,
            )
            if resp.status_code != 200:
                return None
            teams = resp.json().get("response", [])
            if not teams:
                return None

            team_id = teams[0]["team"]["id"]
            # Get current season stats — use current year
            season = now_wat().year
            resp2 = requests.get(
                "https://api-football-v1.p.rapidapi.com/v3/teams/statistics",
                headers=_rapidapi_headers(),
                params={"team": team_id, "season": season, "league": 39},  # EPL default
                timeout=8,
            )
            if resp2.status_code != 200:
                return None

            s = resp2.json().get("response", {})
            goals_for     = s.get("goals", {}).get("for",     {}).get("average", {}).get("total")
            goals_against = s.get("goals", {}).get("against", {}).get("average", {}).get("total")
            fixtures      = s.get("fixtures", {})
            played = fixtures.get("played", {}).get("total", 0)
            wins   = fixtures.get("wins",   {}).get("total", 0)

            result: Dict[str, Any] = {}
            if goals_for:
                result["goals_scored_avg"] = round(float(goals_for), 2)
            if goals_against:
                result["goals_conceded_avg"] = round(float(goals_against), 2)
            if played:
                result["win_rate_signal"] = round(float(wins / played), 4)
                result["espn_win_pct"]    = result["win_rate_signal"]

            _set_cache(ck, result, ttl=CACHE_TTL_MEDIUM)
            return result or None

        elif sport == "basketball":
            # API-NBA
            headers_nba = {
                "X-RapidAPI-Key":  settings.RAPID_API_KEY,
                "X-RapidAPI-Host": RAPIDAPI_HOST_NBA,
            }
            resp = requests.get(
                "https://api-nba-v1.p.rapidapi.com/teams",
                headers=headers_nba,
                params={"search": team_name},
                timeout=8,
            )
            if resp.status_code != 200:
                return None
            teams = resp.json().get("response", [])
            if not teams:
                return None

            team_id = teams[0]["id"]
            season  = now_wat().year - (1 if now_wat().month < 9 else 0)
            resp2 = requests.get(
                "https://api-nba-v1.p.rapidapi.com/teams/statistics",
                headers=headers_nba,
                params={"id": team_id, "season": season},
                timeout=8,
            )
            if resp2.status_code != 200:
                return None

            stats = resp2.json().get("response", [{}])
            if not stats:
                return None
            s = stats[0]
            result = {
                "pts_avg":         round(float(s.get("points", 110.0)), 1),
                "pts_allowed_avg": round(float(s.get("pointsAgainst", 110.0)), 1),
            }
            _set_cache(ck, result, ttl=CACHE_TTL_MEDIUM)
            return result

    except Exception as e:
        logger.debug(f"RapidAPI stats [{team_name} / {sport}]: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED search team query — 1 call covers form + injuries + sport stats
# ─────────────────────────────────────────────────────────────────────────────

_WIN_PATTERNS  = re.compile(r"\b(won|beat|defeated|victory|wins|win)\b")
_LOSS_PATTERNS = re.compile(r"\b(lost|defeat|loses|loss|beaten)\b")
_DRAW_PATTERNS = re.compile(r"\b(draw|drew|tied|nil-nil|goalless)\b")
_INJURY_KWS    = frozenset([
    "out", "injured", "injury", "suspended", "doubtful", "illness",
    "unavailable", "ruled out", "miss", "sidelined", "fitness doubt",
])
_HIGH_IMPACT   = frozenset(["star", "captain", "key player", "best scorer", "main striker"])


def _fetch_combined_team_data(team_name: str, sport: str) -> Dict[str, Any]:
    """Single search call covering form, injuries, and sport-specific stats."""
    ck = _cache_key("combined_team_v3", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    sport_terms = {
        "soccer":     "goals scored conceded clean sheets form results",
        "basketball": "points per game offensive defensive rating results",
    }.get(sport, "form results statistics")
    query = f"{team_name} {sport_terms} injuries squad availability {now_wat().year}"

    snippets = search_web(query, num_results=6)
    text = " ".join(
        (r.get("snippet") or "") + " " + (r.get("title") or "")
        for r in snippets
    ).lower()

    result = _parse_combined_text(text, team_name, sport)
    _set_cache(ck, result, ttl=CACHE_TTL_MEDIUM)
    return result


def _parse_combined_text(text: str, team_name: str, sport: str) -> Dict[str, Any]:
    tkey   = team_name.lower().split()[0]
    ctx_re = re.compile(rf"{re.escape(tkey)}.{{0,50}}")
    contexts = " ".join(ctx_re.findall(text))

    wins   = len(_WIN_PATTERNS.findall(contexts))
    losses = len(_LOSS_PATTERNS.findall(contexts))
    draws  = len(_DRAW_PATTERNS.findall(text))
    total  = wins + losses + draws
    form_rating = (wins + 0.4 * draws) / total if total > 0 else 0.5
    wl       = wins + losses
    momentum = (wins / wl * 0.7 + form_rating * 0.3) if wl > 0 else 0.5

    found_inj   = [kw for kw in _INJURY_KWS if kw in text]
    high_impact = sum(1 for ph in _HIGH_IMPACT if ph in text)
    injury_impact = min(len(found_inj) * 0.07 + high_impact * 0.05, 0.50)

    out: Dict[str, Any] = {
        "wins": wins, "losses": losses, "draws": draws,
        "form_raw":               round(float(form_rating),   4),
        "momentum_raw":           round(float(momentum),      4),
        "injury_keywords":        found_inj,
        "estimated_squad_impact": round(float(injury_impact), 4),
    }

    if sport == "soccer":
        scored   = _extract_float(text, r"(?:scores?|scored?|goals?\s+for)[:\s]+(\d+\.?\d*)")
        conceded = _extract_float(text, r"(?:conceded?|goals?\s+against|goals?\s+conceded)[:\s]+(\d+\.?\d*)")
        cs_rate  = _extract_float(text, r"clean sheets?[:\s]+(\d+\.?\d*)\s*%?")
        out["goals_scored_avg"]   = round(float(scored   or 1.40), 2)
        out["goals_conceded_avg"] = round(float(conceded or 1.20), 2)
        out["clean_sheet_rate"]   = round(float((cs_rate or 28.0) / 100.0), 3)

    elif sport == "basketball":
        pts     = _extract_float(text, r"(\d{2,3}\.?\d*)\s*points?\s+per\s+game")
        pts_all = _extract_float(text, r"allowing\s+(\d{2,3}\.?\d*)")
        out["pts_avg"]         = round(float(pts     or 110.0), 1)
        out["pts_allowed_avg"] = round(float(pts_all or 110.0), 1)
        out["pace_signal"]     = 0.5


    return out


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED search H2H + venue query — 1 call instead of 2
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_combined_h2h_venue(home_team: str, away_team: str, sport: str) -> Dict[str, Any]:
    ck = _cache_key("h2h_venue_v3", {
        "h": home_team.lower(), "a": away_team.lower(), "s": sport
    })
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    query   = f"{home_team} vs {away_team} head to head history home record {sport}"
    results = search_web(query, num_results=5)
    text    = " ".join(r.get("snippet") or "" for r in results).lower()

    hk = home_team.lower().split()[0]
    ak = away_team.lower().split()[0]

    h_wins = len(re.findall(rf"{re.escape(hk)}\s+(?:won|beat|defeated)", text))
    a_wins = len(re.findall(rf"{re.escape(ak)}\s+(?:won|beat|defeated)", text))
    draws  = len(re.findall(r"draw|drew|tied", text))
    total  = h_wins + a_wins + draws

    record      = re.findall(r"home record[:\s]+(\d+)[-\s]+(\d+)", text)
    hw = hl_rec = 0
    if record:
        hw     = int(record[0][0])
        hl_rec = int(record[0][1])
    venue_total           = hw + hl_rec
    home_advantage_signal = float(
        np.clip((hw / venue_total) if venue_total > 0 else 0.54, 0.40, 0.75)
    )

    result = {
        "h2h": {
            "home_team": home_team, "away_team": away_team,
            "home_wins": h_wins, "away_wins": a_wins,
            "draws": draws, "total_games": total,
        },
        "venue": {
            "team": home_team, "home_wins": hw, "home_losses": hl_rec,
            "home_advantage_signal": round(home_advantage_signal, 4),
        },
    }
    _set_cache(ck, result, ttl=CACHE_TTL_LONG)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API: form, stats, injuries  (ESPN → RapidAPI → search fallback)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_recent_form(team_name: str, sport: str, num_games: int = 5) -> Dict[str, Any]:
    ck = _cache_key("form_v3", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    espn            = _espn_team_record(team_name, sport)
    espn_wpct       = espn.get("espn_win_pct", 0.5)
    ranking_signal  = espn.get("ranking_signal", 0.5)
    espn_available  = espn.get("espn_data_available", False)

    if espn_available:
        form_rating     = espn_wpct
        momentum        = espn_wpct
        win_rate_signal = espn_wpct
    else:
        combined        = _fetch_combined_team_data(team_name, sport)
        form_raw        = combined.get("form_raw", 0.5)
        momentum        = combined.get("momentum_raw", 0.5)
        weight_espn     = 0.6 if espn_wpct == 0.5 else 0.35
        form_rating     = form_raw * (1 - weight_espn) + espn_wpct * weight_espn
        win_rate_signal = espn_wpct

    result = {
        "team":             team_name,
        "form_rating":      round(float(np.clip(form_rating,     0.0, 1.0)), 4),
        "momentum":         round(float(np.clip(momentum,        0.0, 1.0)), 4),
        "win_rate_signal":  round(float(np.clip(win_rate_signal, 0.0, 1.0)), 4),
        "ranking_signal":   round(float(ranking_signal), 4),
        "espn_win_pct":     round(float(espn_wpct),      4),
    }
    _set_cache(ck, result, ttl=CACHE_TTL_MEDIUM)
    return result


def fetch_injury_report(team_name: str, sport: str) -> Dict[str, Any]:
    """Piggybacks on combined team query — no extra search call."""
    ck = _cache_key("injury_v3", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    combined = _fetch_combined_team_data(team_name, sport)
    result = {
        "team":                  team_name,
        "injury_keywords_found": combined.get("injury_keywords", []),
        "estimated_squad_impact": combined.get("estimated_squad_impact", 0.0),
    }
    _set_cache(ck, result, ttl=CACHE_TTL_MEDIUM)
    return result


def fetch_head_to_head(home_team: str, away_team: str, sport: str) -> Dict[str, Any]:
    return _fetch_combined_h2h_venue(home_team, away_team, sport)["h2h"]


def fetch_venue_stats(home_team: str, sport: str) -> Dict[str, Any]:
    """Uses ESPN win% as primary signal — no extra search call."""
    ck = _cache_key("venue_v3", {"t": home_team.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    espn      = _espn_team_record(home_team, sport)
    espn_wpct = espn.get("espn_win_pct", 0.5)
    home_advantage_signal = float(np.clip(espn_wpct * 1.08, 0.40, 0.75))

    result = {
        "team":                   home_team,
        "home_wins":              0,
        "home_losses":            0,
        "home_advantage_signal":  round(home_advantage_signal, 4),
    }
    _set_cache(ck, result, ttl=CACHE_TTL_LONG)
    return result


def fetch_team_stats(team_name: str, sport: str) -> Dict[str, Any]:
    """
    Aggregate team stats.

    Priority:
      1. Cache (free)
      2. ESPN API (free, structured)
      3. RapidAPI (free tier, structured — consumes 0 search quota)
      4. Combined search query (Serper.dev → DuckDuckGo fallback)
    """
    ck = _cache_key("team_stats_v3", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    # Try RapidAPI for structured sport stats before burning search quota
    rapid_stats = _fetch_rapidapi_team_stats(team_name, sport) or {}

    combined  = _fetch_combined_team_data(team_name, sport)
    form_data = fetch_recent_form(team_name, sport)

    stats: Dict[str, Any] = {
        "team":                   team_name,
        "sport":                  sport,
        "data_freshness":         now_wat().isoformat(),
        **form_data,
        "estimated_squad_impact": combined.get("estimated_squad_impact", 0.0),
    }

    # RapidAPI structured values override scraped text where available
    if sport == "soccer":
        stats["goals_scored_avg"]   = rapid_stats.get(
            "goals_scored_avg",   combined.get("goals_scored_avg",   1.40))
        stats["goals_conceded_avg"] = rapid_stats.get(
            "goals_conceded_avg", combined.get("goals_conceded_avg",  1.20))
        stats["clean_sheet_rate"]   = combined.get("clean_sheet_rate", 0.28)

    elif sport == "basketball":
        stats["pts_avg"]            = rapid_stats.get(
            "pts_avg",            combined.get("pts_avg",         110.0))
        stats["pts_allowed_avg"]    = rapid_stats.get(
            "pts_allowed_avg",    combined.get("pts_allowed_avg", 110.0))
        stats["pace_signal"]        = combined.get("pace_signal", 0.5)


    # Override win_rate from RapidAPI if available (more accurate than scraped)
    if rapid_stats.get("win_rate_signal"):
        stats["win_rate_signal"] = rapid_stats["win_rate_signal"]
        stats["espn_win_pct"]    = rapid_stats.get("espn_win_pct", stats["espn_win_pct"])

    _set_cache(ck, stats, ttl=CACHE_TTL_MEDIUM)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Betting odds  (Odds API — no search quota impact)
# ─────────────────────────────────────────────────────────────────────────────

_ODDS_SPORT_MAP = {
    "soccer": SPORT_KEYS["soccer"],
    "basketball": SPORT_KEYS["basketball"],
}


def fetch_betting_odds(home_team: str, away_team: str, sport: str) -> Dict[str, Any]:
    ck = _cache_key("odds_v3", {"h": home_team.lower(), "a": away_team.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    result: Dict[str, Any] = {
        "implied_home_prob": None,
        "implied_away_prob": None,
        "market_confidence": 0.0,
    }

    if not settings.ODDS_API_KEY:
        return result

    sport_keys = _ODDS_SPORT_MAP.get(sport.lower(), _ODDS_SPORT_MAP["soccer"])
    try:
        hl, al = home_team.lower(), away_team.lower()
        for sport_key in sport_keys:
            resp = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
                params={
                    "apiKey":      settings.ODDS_API_KEY,
                    "regions":     "us,uk",
                    "markets":     "h2h",
                    "oddsFormat":  "decimal",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            for game in resp.json():
                gh = game.get("home_team", "").lower()
                ga = game.get("away_team", "").lower()
                if not (_word_overlap(hl, gh) and _word_overlap(al, ga)):
                    continue

                home_probs, away_probs = [], []
                for bk in game.get("bookmakers", [])[:5]:
                    for mkt in bk.get("markets", []):
                        if mkt.get("key") != "h2h":
                            continue
                        for o in mkt.get("outcomes", []):
                            price = float(o.get("price", 2.0))
                            if price <= 1.0:
                                continue
                            imp  = 1.0 / price
                            name = o.get("name", "").lower()
                            if _word_overlap(hl, name):
                                home_probs.append(imp)
                            elif _word_overlap(al, name):
                                away_probs.append(imp)

                if home_probs and away_probs:
                    raw_h = float(np.mean(home_probs))
                    raw_a = float(np.mean(away_probs))
                    total = raw_h + raw_a
                    if total > 0:
                        result["implied_home_prob"] = round(raw_h / total, 4)
                        result["implied_away_prob"] = round(raw_a / total, 4)
                        result["market_confidence"] = round(abs(raw_h / total - raw_a / total), 4)
                    break

            if result["implied_home_prob"] is not None and result["implied_away_prob"] is not None:
                break

    except Exception as e:
        logger.warning(f"Odds API [{home_team} vs {away_team}]: {e}")

    _set_cache(ck, result, ttl=CACHE_TTL_SHORT)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _word_overlap(a: str, b: str) -> bool:
    words_a = [w for w in a.split() if len(w) >= 4]
    return bool(words_a) and any(w in b for w in words_a)


def _extract_float(text: str, pattern: str) -> Optional[float]:
    m = re.search(pattern, text)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, IndexError):
            pass
    return None
