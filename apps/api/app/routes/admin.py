"""Admin utilities for maintenance tasks.

Endpoints:
 - POST /admin/recompute-groups?match_date=YYYY-MM-DD
 - POST /admin/enrich-corners?limit=100

These are intended for operator use to repair grouping and populate
missing corner totals for existing resolved matches.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from app.config.database import get_db
from app.utils.timezone import WAT
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/recompute-groups")
async def recompute_groups(match_date: Optional[str] = Query(None, description="YYYY-MM-DD")):
    """Recompute prediction grouping for a specific date (defaults to today)."""
    db = get_db()
    from app.services.prediction_service import _assign_prediction_groups_for_date

    target_date = match_date or datetime.now(WAT).strftime("%Y-%m-%d")
    try:
        result = await _assign_prediction_groups_for_date(db, target_date)
        return {"status": "ok", "date": target_date, "result": result}
    except Exception as e:
        logger.exception("Failed to recompute groups for %s: %s", target_date, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enrich-corners")
async def enrich_corners(limit: int = Query(200, ge=1, le=2000)):
    """Attempt to fetch corner totals for recent actual_results missing corner data.

    Uses the currently configured free corner-stat fallback.
    """
    db = get_db()
    from app.services.result_resolver import _fetch_corner_stats

    updated = 0
    scanned = 0
    async for doc in db.actual_results.find({"total_corners": {"$exists": False}}).limit(limit):
        scanned += 1
        match_id = doc.get("match_id")
        home = doc.get("home_team") or doc.get("home_team")
        away = doc.get("away_team") or doc.get("away_team")
        date = doc.get("match_date")
        if not match_id or not home or not away or not date:
            continue

        try:
            stats = _fetch_corner_stats(home, away, date)
            if not stats:
                continue
            payload = {
                "home_corners": stats.get("home_corners"),
                "away_corners": stats.get("away_corners"),
                "total_corners": stats.get("total_corners"),
                "corner_source": stats.get("source") or "free_fallback",
            }
            await db.actual_results.update_one({"match_id": match_id}, {"$set": payload})
            updated += 1
        except Exception as e:
            logger.debug("enrich_corners failed for %s: %s", match_id, e)

    return {"scanned": scanned, "updated": updated}
