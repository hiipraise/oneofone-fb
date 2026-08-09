# app/services/cache_utils.py
"""
Shared in-memory cache (Sprint 5.3 file split).

Extracted from web_search_service.py so that the search providers
(Serper/DuckDuckGo), the ESPN lookup service, and the orchestration layer
all share one cache implementation. File-based caching is disabled by
default to avoid cross-pod drift on Render/serverless; state stays in
memory, with Mongo-backed quota_service providing persisted monthly
accounting for dashboards.
"""
import hashlib
import time
from typing import Any, Dict, Optional

from app.config.settings import settings

CACHE_TTL_SHORT  = 3_600   #  1 h
CACHE_TTL_MEDIUM = 21_600  #  6 h
CACHE_TTL_LONG   = 86_400  # 24 h

ENABLE_FILE_CACHE = False

_mem_cache: Dict[str, Dict] = {}


def _prune_cache() -> None:
    now = time.time()
    expired_keys = [
        key for key, entry in _mem_cache.items()
        if now - entry.get("ts", now) >= entry.get("ttl", CACHE_TTL_MEDIUM)
    ]
    for key in expired_keys:
        _mem_cache.pop(key, None)

    max_entries = max(int(getattr(settings, "SEARCH_CACHE_MAX_ENTRIES", 750)), 1)
    if len(_mem_cache) > max_entries:
        overflow = len(_mem_cache) - max_entries
        for key in list(_mem_cache.keys())[:overflow]:
            _mem_cache.pop(key, None)


def _cache_key(ns: str, params: Optional[dict] = None) -> str:
    return hashlib.md5((ns + str(sorted((params or {}).items()))).encode()).hexdigest()


def _get_cached(key: str) -> Optional[Any]:
    _prune_cache()
    entry = _mem_cache.get(key)
    if entry and time.time() - entry["ts"] < entry.get("ttl", CACHE_TTL_MEDIUM):
        return entry["data"]
    if entry is not None:
        _mem_cache.pop(key, None)
    return None


def _set_cache(key: str, data: Any, ttl: int = CACHE_TTL_MEDIUM) -> None:
    _prune_cache()
    _mem_cache[key] = {"ts": time.time(), "data": data, "ttl": ttl}
