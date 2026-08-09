# app/services/search_providers.py
"""
Search providers — Serper.dev + DuckDuckGo, with monthly quota tracking
(Sprint 5.3 file split).

Extracted from web_search_service.py: this module owns the actual
search-provider HTTP calls (Serper.dev Google API, DuckDuckGo HTML/ddgs)
and the Serper monthly budget tracker. ESPN lookups live in
espn_service.py; the orchestration layer lives in web_search_service.py.

Budget tracking reflects Serper.dev's 2,500/month limit.
DuckDuckGo calls are NOT quota-counted (they're free).
"""
import asyncio
import logging
import re
import threading
import time
from typing import Any, Dict, List

import requests

from app.config.settings import settings
from app.services.cache_utils import (
    CACHE_TTL_MEDIUM,
    _cache_key,
    _get_cached,
    _set_cache,
)
from app.utils.timezone import now_wat

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Monthly Serper.dev quota tracker  (2,500 free/month)
# ─────────────────────────────────────────────────────────────────────────────

MONTHLY_BUDGET = 2_400  # hard cap; keeps 100 buffer from the 2,500 free limit

_quota_state: Dict[str, Any] = {"month": "", "count": 0}


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
# Public search entry point
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
