# app/routes/scheduler.py
"""
Scheduler API — status, manual trigger, and run logs.
"""
import logging
from datetime import datetime, timezone
from app.utils.timezone import WAT
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from apscheduler.schedulers.background import BackgroundScheduler

from app.config.database import get_db
from app.scheduler.daily_scheduler import scheduler, run_daily_predictions, _SUPPORTED_SPORTS

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_db():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not connected")
    return db

def _next_run_iso(sched: BackgroundScheduler) -> Optional[str]:
    try:
        job = sched.get_job("daily_predictions")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
    except Exception:
        pass
    return None


@router.get("/status")
async def get_scheduler_status():
    db = _require_db()
    next_run = _next_run_iso(scheduler)

    # Next resolution run
    def _next_resolution_iso(sched):
        try:
            job = sched.get_job("result_resolution")
            if job and job.next_run_time:
                return job.next_run_time.isoformat()
        except Exception:
            pass
        return None

    next_resolution = _next_resolution_iso(scheduler)
    is_running = scheduler.running

    last_log = await db.system_logs.find_one(
        {"source": "daily_scheduler"},
        sort=[("timestamp", -1)],
    )
    if last_log:
        last_log.pop("_id", None)

    today = datetime.now(WAT).strftime("%Y-%m-%d")
    today_counts: dict[str, int] = {}
    for sport in _SUPPORTED_SPORTS:
        count = await db.predictions.count_documents({
            "sport": sport,
            "match_date": today,
            "deleted_at": None,
        })
        today_counts[sport] = count

    # Today's auto-resolved results count
    resolved_today = await db.actual_results.count_documents({
        "match_date": today,
        "recorded_at": {"$exists": True},
    })

    total_today = sum(today_counts.values())

    return {
        "scheduler_running": is_running,
        "next_run": next_run,
        "next_resolution": next_resolution,
        "last_run": last_log,
        "today_date": today,
        "today_predictions": {
            "total": total_today,
            "by_sport": today_counts,
        },
        "resolved_today": resolved_today,
    }


@router.post("/trigger")
async def trigger_scheduler():
    """Manually fire the daily prediction job (runs in background thread)."""
    if not scheduler.running:
        raise HTTPException(status_code=503, detail="Scheduler is not running")

    import threading
    t = threading.Thread(target=run_daily_predictions, daemon=True)
    t.start()

    return {
        "status": "triggered",
        "message": "Daily prediction job started in background",
        "triggered_at": datetime.now(WAT).isoformat(),
    }


@router.get("/logs")
async def get_scheduler_logs(limit: int = Query(50, ge=1, le=200)):
    """Recent scheduler log entries."""
    db = _require_db()
    logs: List[dict] = []
    async for doc in db.system_logs.find(
        {"source": "daily_scheduler"}
    ).sort("timestamp", -1).limit(limit):
        doc.pop("_id", None)
        logs.append(doc)
    return logs


@router.get("/fixtures/today")
async def get_today_fixtures():
    """Today's generated predictions grouped by sport."""
    db = _require_db()
    today = datetime.now(WAT).strftime("%Y-%m-%d")
    result: dict[str, list] = {s: [] for s in _SUPPORTED_SPORTS}

    async for pred in db.predictions.find(
        {"match_date": today, "deleted_at": None}
    ).sort("timestamp", -1):
        pred.pop("_id", None)
        sport = pred.get("sport", "soccer")
        if sport in result:
            result[sport].append({
                "match_id":          pred.get("match_id"),
                "home_team":         pred.get("home_team"),
                "away_team":         pred.get("away_team"),
                "league":            pred.get("league"),
                "predicted_outcome": pred.get("predicted_outcome"),
                "home_win_probability": pred.get("home_win_probability"),
                "away_win_probability": pred.get("away_win_probability"),
                "draw_probability":  pred.get("draw_probability"),
                "confidence_score":  pred.get("confidence_score"),
                "prediction_group_id": pred.get("prediction_group_id"),
                "prediction_group_index": pred.get("prediction_group_index"),
                "prediction_group_is_high_risk": pred.get("prediction_group_is_high_risk", False),
            })

    groups_doc = await db.prediction_groups.find_one({"match_date": today}, {"_id": 0})

    return {
        "date":  today,
        "total": sum(len(v) for v in result.values()),
        "by_sport": result,
        "groups": (groups_doc or {}).get("groups", []),
    }


@router.post("/trigger-resolution")
async def trigger_resolution():
    """Manually fire the result auto-resolution job."""
    if not scheduler.running:
        raise HTTPException(status_code=503, detail="Scheduler is not running")

    from app.scheduler.daily_scheduler import run_result_resolution
    import threading
    t = threading.Thread(target=run_result_resolution, daemon=True)
    t.start()

    return {
        "status": "triggered",
        "message": "Result resolution job started in background",
        "triggered_at": datetime.now(WAT).isoformat(),
    }    
