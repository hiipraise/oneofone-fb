# app/services/web_search_service.py
"""
Web Search & Data Service — orchestration layer (Sprint 5.3 file split).

Search provider hierarchy (quota-free to quota-heavy):
  1. ESPN public API          — free, no key, no quota   (espn_service.py)
  2. Odds API                 — free tier, no quota impact
  3. Serper.dev               — 2,500 free searches/month (search_providers.py)
  4. DuckDuckGo (ddgs)        — unlimited fallback, no key required
  5. Statistical defaults     — last resort

SerpAPI has been removed entirely. Add to .env:
    SERPER_API_KEY=<your key from serper.dev — free signup>

Budget tracking now reflects Serper.dev's 2,500/month limit.
DuckDuckGo calls are NOT quota-counted (they're free).

Split responsibilities (Sprint 5.3):
  - cache_utils.py      — shared in-memory cache
  - search_providers.py — Serper/DuckDuckGo calls + monthly quota
  - espn_service.py     — ESPN public API lookups
  - THIS FILE           — orchestration: combines search + ESPN into the
                          public team/h2h/venue/odds fetchers, and
                          re-exports the split names so existing import
                          sites keep working unchanged.
"""
import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
import requests

from app.config.settings import settings
from app.services.cache_utils import (
    CACHE_TTL_LONG,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_SHORT,
    _cache_key,
    _get_cached,
    _set_cache,
)
from app.services.espn_service import (
    ESPN_BASE,
    ESPN_SPORT_MAP,
    _SOCCER_ESPN_LEAGUES,
    _espn_team_record,
    _espn_team_search,
)
from app.services.search_providers import (
    get_serper_usage,
    search_web,
)
from app.services.sport_key_catalog import SOCCER_SPORT_KEYS
from app.services.scraping_service import fetch_openligadb_matches
from app.utils.timezone import now_wat

logger = logging.getLogger(__name__)


def _coerce_sport_to_supported(sport: Optional[str]) -> str:
    """Coerce any sport input to the single supported sport (soccer).

    This keeps the codebase resilient: callers may pass other sports
    historically, but the platform is intentionally soccer-only.
    """
    try:
        s = (sport or "").lower()
    except Exception:
        s = ""
    return "soccer"


# ─────────────────────────────────────────────────────────────────────────────
# Text-analysis patterns for the search fallback path.
#
# FIXED DURING SPLIT (Sprint 5.3): these constants were referenced by
# _parse_combined_text but never defined anywhere in the file, so the
# search-fallback path would raise NameError whenever ESPN data was
# unavailable for a team. They are defined here so the fallback actually
# works; the surrounding heuristic is unchanged.
# ─────────────────────────────────────────────────────────────────────────────

_WIN_PATTERNS = re.compile(
    r"\b(?:won|wins|win|beat|beats|defeated|victory)\b", re.IGNORECASE
)
_LOSS_PATTERNS = re.compile(
    r"\b(?:lost|loses|lose|defeat|defeats|defeat by|loss)\b", re.IGNORECASE
)
_DRAW_PATTERNS = re.compile(
    r"\b(?:drew|draw|draws|tied|tie)\b", re.IGNORECASE
)
_INJURY_KWS = [
    "injured", "injury", "ruled out", "doubt", "sidelined",
    "hamstring", "knee", "strain", "muscle", "absent",
]
_HIGH_IMPACT = [
    "captain", "first-choice", "key player", "top scorer",
    "starting xi", "suspended", "star player",
]


# ─────────────────────────────────────────────────────────────────────────────
# Structured paid sports providers removed. Free ESPN/search/scraping providers remain.
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_combined_team_data(team_name: str, sport: str) -> Dict[str, Any]:
    """Single search call covering form, injuries, and sport-specific stats."""
    ck = _cache_key("combined_team_v3", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    sport = _coerce_sport_to_supported(sport)
    sport_terms = {
        "soccer": "goals scored conceded clean sheets form results",
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

    sport = _coerce_sport_to_supported(sport)
    if sport == "soccer":
        scored   = _extract_float(text, r"(?:scores?|scored?|goals?\s+for)[:\s]+(\d+\.?\d*)")
        conceded = _extract_float(text, r"(?:conceded?|goals?\s+against|goals?\s+conceded)[:\s]+(\d+\.?\d*)")
        cs_rate  = _extract_float(text, r"clean sheets?[:\s]+(\d+\.?\d*)\s*%?")
        out["goals_scored_avg"]   = round(float(scored   or 1.40), 2)
        out["goals_conceded_avg"] = round(float(conceded or 1.20), 2)
        out["clean_sheet_rate"]   = round(float((cs_rate or 28.0) / 100.0), 3)

    # Platform is soccer-only.

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

    sport = _coerce_sport_to_supported(sport)
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
# Public API: form, stats, injuries  (ESPN → search fallback)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_recent_form(team_name: str, sport: str, num_games: int = 5) -> Dict[str, Any]:
    ck = _cache_key("form_v3", {"t": team_name.lower(), "s": sport})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    sport = _coerce_sport_to_supported(sport)
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

    sport = _coerce_sport_to_supported(sport)
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


def fetch_team_stats(team_name: str, sport: str, league: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregate team stats.

    Priority:
      1. Cache (free)
      2. ESPN API (free, structured)
      3. Free search/scraping fallbacks (OpenLigaDB for German leagues)
      4. Combined search query (Serper.dev → DuckDuckGo fallback)

    ``league`` is the optional fixture league name — used to decide whether
    OpenLigaDB (free, German competitions) can enrich goals/form stats.
    """
    ck = _cache_key("team_stats_v3", {"t": team_name.lower(), "s": sport, "l": (league or "").lower()})
    cached = _get_cached(ck)
    if cached is not None:
        return cached

    sport = _coerce_sport_to_supported(sport)
    combined  = _fetch_combined_team_data(team_name, sport)
    form_data = fetch_recent_form(team_name, sport)

    stats: Dict[str, Any] = {
        "team":                   team_name,
        "sport":                  sport,
        "data_freshness":         now_wat().isoformat(),
        **form_data,
        "estimated_squad_impact": combined.get("estimated_squad_impact", 0.0),
    }

    if sport == "soccer":
        stats["goals_scored_avg"] = combined.get("goals_scored_avg", 1.40)
        stats["goals_conceded_avg"] = combined.get("goals_conceded_avg", 1.20)
        stats["clean_sheet_rate"] = combined.get("clean_sheet_rate", 0.28)

    # OpenLigaDB enrichment (free source — German leagues): real scored-goal
    # and clean-sheet averages replace the search-derived estimates when the
    # fixture's league maps to a German competition. Best-effort; when the
    # league is unknown/unreachable the ESPN/search defaults stay and
    # `openligadb_available` is False so provenance stays honest.
    if sport == "soccer":
        olg = _openligadb_team_form(team_name, league, limit=8)
        if olg.get("openligadb_available"):
            stats["goals_scored_avg"]   = olg.get("goals_scored_avg", stats["goals_scored_avg"])
            stats["goals_conceded_avg"] = olg.get("goals_conceded_avg", stats["goals_conceded_avg"])
            stats["clean_sheet_rate"]   = olg.get("clean_sheet_rate", stats["clean_sheet_rate"])
            stats["form_rating"]        = olg.get("form_rating", stats.get("form_rating", 0.5))
            stats["recent_matches"]     = olg.get("recent_matches", 0)
        stats["openligadb_available"] = bool(olg.get("openligadb_available"))

    # Platform is soccer-only.

    _set_cache(ck, stats, ttl=CACHE_TTL_MEDIUM)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Betting odds  (Odds API — no search quota impact)
# ─────────────────────────────────────────────────────────────────────────────

_ODDS_SPORT_MAP = {
    "soccer": SOCCER_SPORT_KEYS,
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

    sport = _coerce_sport_to_supported(sport)
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
# OpenLigaDB enrichment  (free structured source — German leagues)
#
# Wired in Sprint 8: real scored-goal + form stats from OpenLigaDB (free,
# no key) enrich the team-stats dict when the fixture's league is a known
# German competition. Every lookup goes through scraping_service's in-memory
# cache/pacing so we never hammer a free source. Best-effort only — when the
# league is unknown or the API is unreachable, stats simply stay on the
# existing ESPN/search-derived defaults and `openligadb_available` is False.
# ─────────────────────────────────────────────────────────────────────────────

# OpenLigaDB league codes for the German competitions the API covers.
# Keys are normalized (lowercase, spaces removed) fragments that appear in
# request.league values from the Odds API / ESPN / frontend.
_OPENLIGADB_LEAGUES = {
    "bundesliga":        "bl1",
    "2bundesliga":       "bl2",
    "dfb":               "dfb",
    "dfbpokal":          "dfb",
    "regionalliga":      "rl",
    "oberliga":          "ol",
    "ligapokal":         "lp",
}
# League names that do NOT map to a German competition — never enrich from
# OpenLigaDB for these (avoids attributing wrong league data to foreign teams).
_NON_GERMAN_LEAGUE_MARKERS = (
    "epl", "premier", "laliga", "seriea", "ligue", "eredivisie",
    "primeira", "mls", "ligamx", "championsleague", "europaleague",
    "conference", "superlig", "seriea", "j1", "sau" ,"austra", "brazil",
    "argentina", "turkey", "scotland", "swiss", "belgian", "denmark",
    "norway", "sweden",
)


def _openligadb_league_code(league: Optional[str]) -> Optional[str]:
    """Map a free-text league name to an OpenLigaDB league code, or None."""
    if not league:
        return None
    # Normalize ("2. Bundesliga" -> "2bundesliga", "Bundesliga" -> "bundesliga")
    # and keep the leading division digit: "2. Bundesliga" is bl2, not bl1.
    norm = re.sub(r"[^a-z0-9]", "", league.lower())
    if not norm:
        return None
    division = ""
    m = re.match(r"^(\d+)", norm)
    if m:
        division = m.group(1)
        norm = norm[m.end():]
    if not norm:
        return None
    if any(marker in norm for marker in _NON_GERMAN_LEAGUE_MARKERS):
        return None
    if division == "2" and "bundesliga" in norm:
        return _OPENLIGADB_LEAGUES["2bundesliga"]
    for fragment, code in _OPENLIGADB_LEAGUES.items():
        if fragment in norm:
            return code
    # Unknown league — don't guess; a wrong league would feed wrong team stats.
    return None


_UMLAUT_MAP = {
    "\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue", "\u00df": "ss",
    "\u00c4": "ae", "\u00d6": "oe", "\u00dc": "ue",
}


def _normalize_team_name(name: str) -> tuple[str, str]:
    """
    Lowercase + transliterate umlauts (M\u00fcnchen -> muenchen) and return
    (collapsed, tokens): ``collapsed`` is the digit/letter-only string used for
    substring checks, ``tokens`` are the space-separated words for shared-token
    matching (handles "Bayern Munich" vs "FC Bayern Muenchen").
    """
    n = name
    for ch, repl in _UMLAUT_MAP.items():
        n = n.replace(ch, repl)
    spaced = re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()
    collapsed = spaced.replace(" ", "")
    return collapsed, spaced


def _team_matches(team_collapsed: str, team_tokens: str, target_collapsed: str, target_tokens: str) -> bool:
    """
    Substring OR shared-token match. Handles "Bayern Munich" vs
    "FC Bayern Muenchen" (umlauts normalized) via the shared "bayern" token.
    """
    if not target_collapsed:
        return False
    if target_collapsed in team_collapsed or team_collapsed in target_collapsed:
        return True
    t_set = {t for t in team_tokens.split() if len(t) >= 3}
    g_set = {t for t in target_tokens.split() if len(t) >= 3}
    return bool(t_set & g_set)


def _openligadb_team_form(
    team_name: str,
    league: Optional[str],
    limit: int = 8,
    season: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Best-effort recent-form/goals stats for a team from OpenLigaDB.

    Returns {} when the league doesn't map, the API fails, or the team
    cannot be matched in recent matches. ``season`` (e.g. 2023 = 2023/24)
    is passed through to the scraper; defaults to the current season.
    """
    code = _openligadb_league_code(league)
    if not code:
        return {}

    try:
        result = fetch_openligadb_matches(code, season=season)
    except Exception as exc:
        logger.debug(f"OpenLigaDB fetch failed [{code}]: {exc}")
        return {}
    if not result or not result.available:
        return {}

    matches = (result.data or {}).get("matches") or []
    if not matches:
        return {}

    tl_collapsed, tl_tokens = _normalize_team_name(team_name)
    if not tl_collapsed:
        return {}

    scored, conceded, clean, played = [], [], 0, 0
    for match in sorted(
        matches,
        key=lambda m: m.get("matchDateTime", ""),
        reverse=True,
    ):
        home_c, home_t = _normalize_team_name(str(match.get("team1", {}).get("teamName", "")))
        away_c, away_t = _normalize_team_name(str(match.get("team2", {}).get("teamName", "")))
        if not (
            _team_matches(home_c, home_t, tl_collapsed, tl_tokens)
            or _team_matches(away_c, away_t, tl_collapsed, tl_tokens)
        ):
            continue
        try:
            hs = int(match.get("matchResults") and (match.get("matchResults")[-1] or {}).get("pointsTeam1", 0))
            as_ = int(match.get("matchResults") and (match.get("matchResults")[-1] or {}).get("pointsTeam2", 0))
        except (TypeError, ValueError, IndexError):
            continue
        if _team_matches(home_c, home_t, tl_collapsed, tl_tokens):
            scored.append(hs)
            conceded.append(as_)
            if as_ == 0:
                clean += 1
        else:
            scored.append(as_)
            conceded.append(hs)
            if hs == 0:
                clean += 1
        played += 1
        if played >= limit:
            break

    if not played:
        return {}

    wins = sum(1 for s, c in zip(scored, conceded) if s > c)
    draws = sum(1 for s, c in zip(scored, conceded) if s == c)
    form_rating = round((wins + 0.4 * draws) / played, 4)
    return {
        "openligadb_available": True,
        "form_rating": form_rating,
        "goals_scored_avg": round(sum(scored) / played, 2),
        "goals_conceded_avg": round(sum(conceded) / played, 2),
        "clean_sheet_rate": round(clean / played, 3),
        "recent_matches": played,
    }


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


# ─────────────────────────────────────────────────────────────────────────────
# Re-exported public surface (Sprint 5.3 split)
#
# Existing import sites (scheduler/daily_scheduler.py, routes/metrics.py,
# services/match_validation_service.py, services/prediction_service.py,
# services/quota_service.py, routes/search.py) import the names below from
# this module; they now resolve to the split modules. Kept verbatim so no
# call site needs to change.
# ─────────────────────────────────────────────────────────────────────────────

from app.services.cache_utils import (  # noqa: E402,F401
    CACHE_TTL_SHORT,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_LONG,
    _cache_key,
    _get_cached,
    _set_cache,
)
from app.services.espn_service import (  # noqa: E402,F401
    ESPN_SPORT_MAP,
    ESPN_BASE,
    _SOCCER_ESPN_LEAGUES,
    _espn_team_search,
    _espn_team_record,
)
from app.services.search_providers import (  # noqa: E402,F401
    MONTHLY_BUDGET,
    get_serper_usage,
    search_web,
    _serper_search,
    _duckduckgo_search,
    _duckduckgo_html_search,
    _throttle,
    _quota_check,
    _quota_increment,
)
