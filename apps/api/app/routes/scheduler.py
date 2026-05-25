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


def _normalize_timestamp_iso(value) -> Optional[str]:
    """Return timestamps as ISO-8601 strings (or None when absent)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        # PyMongo commonly returns naive UTC datetimes unless tz-aware decoding is enabled.
        # Attach UTC explicitly so clients can correctly convert/display in WAT.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def _play_rank_from_confidence(confidence: Optional[float]) -> int:
    """Normalize confidence into an integer play rank from 0..5."""
    if confidence is None:
        return 0
    c = max(0.0, min(1.0, float(confidence)))
    if c >= 0.80:
        return 5
    if c >= 0.70:
        return 4
    if c >= 0.60:
        return 3
    if c >= 0.55:
        return 2
    if c > 0:
        return 1
    return 0


def _rank_sort_key(row: dict) -> tuple[int, int, float, str]:
    """Sort generated predictions into a stable ranked order for schedule views."""
    rank = row.get("overall_rank")
    try:
        rank_value = int(rank)
    except (TypeError, ValueError):
        rank_value = 10_000

    play_rank = row.get("play_rank")
    try:
        play_rank_value = int(play_rank)
    except (TypeError, ValueError):
        play_rank_value = 0

    confidence = row.get("confidence_score")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0

    return (
        rank_value,
        -play_rank_value,
        -confidence_value,
        str(row.get("match_id") or ""),
    )


def _group_sort_key(group: dict) -> tuple[int, int, float, str]:
    """Keep prediction groups in their assigned sequence instead of API insertion order."""
    group_index = group.get("group_index")
    try:
        group_index_value = int(group_index)
    except (TypeError, ValueError):
        group_index_value = 10_000

    play_rank = group.get("play_rank")
    try:
        play_rank_value = int(play_rank)
    except (TypeError, ValueError):
        play_rank_value = 0

    confidence = group.get("avg_confidence_score")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0

    return (
        group_index_value,
        -play_rank_value,
        -confidence_value,
        str(group.get("group_id") or ""),
    )

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
        last_log["timestamp"] = _normalize_timestamp_iso(last_log.get("timestamp"))

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
async def get_scheduler_logs(
    limit: int = Query(50, ge=1, le=200),
    sport: Optional[str] = Query(None, description="Optional sport filter, e.g. soccer"),
):
    """Recent scheduler log entries."""
    db = _require_db()
    logs: List[dict] = []
    normalized_sport = sport.lower() if sport else None
    query = {"source": "daily_scheduler"}
    if normalized_sport:
        query["$or"] = [
            {"sport": normalized_sport},
            {"sport": {"$exists": False}},
            {"sport": None},
        ]

    async for doc in db.system_logs.find(
        query
    ).sort("timestamp", -1).limit(limit):
        doc.pop("_id", None)
        doc["timestamp"] = _normalize_timestamp_iso(doc.get("timestamp"))
        logs.append(doc)
    return logs


@router.get("/fixtures/today")
async def get_today_fixtures(
    match_date: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today in WAT"),
    sport: Optional[str] = Query(None, description="Optional sport filter, e.g. soccer"),
):
    """Generated predictions grouped by sport for a given date (defaults to today)."""
    db = _require_db()
    target_date = match_date or datetime.now(WAT).strftime("%Y-%m-%d")
    normalized_sport = sport.lower() if sport else None
    result: dict[str, list] = {s: [] for s in _SUPPORTED_SPORTS}

    prediction_docs: list[dict] = []
    pred_by_match_id: dict[str, dict] = {}

    async for pred in db.predictions.find(
        {"match_date": target_date, "deleted_at": None}
    ).sort("timestamp", -1):
        pred.pop("_id", None)
        prediction_docs.append(pred)
        match_id = pred.get("match_id")
        if match_id:
            pred_by_match_id[match_id] = pred

    rank_by_match: dict[str, int] = {}
    for sport in _SUPPORTED_SPORTS:
        sport_preds = [p for p in prediction_docs if p.get("sport", "soccer") == sport]
        sport_ranked = sorted(
            sport_preds,
            key=lambda p: float(p.get("confidence_score") or 0.0),
            reverse=True,
        )
        for i, p in enumerate(sport_ranked, start=1):
            if p.get("match_id"):
                rank_by_match[p["match_id"]] = i

    for pred in prediction_docs:
        sport = pred.get("sport", "soccer")
        if sport in result:
            result[sport].append({
                "match_id": pred.get("match_id"),
                "home_team": pred.get("home_team"),
                "away_team": pred.get("away_team"),
                "league": pred.get("league"),
                "predicted_outcome": pred.get("predicted_outcome"),
                "home_win_probability": pred.get("home_win_probability"),
                "away_win_probability": pred.get("away_win_probability"),
                "draw_probability": pred.get("draw_probability"),
                "confidence_score": pred.get("confidence_score"),
                "prediction_group_id": pred.get("prediction_group_id"),
                "prediction_group_index": pred.get("prediction_group_index"),
                "prediction_group_is_high_risk": pred.get("prediction_group_is_high_risk", False),
                "overall_rank": rank_by_match.get(pred.get("match_id")),
                "play_rank": _play_rank_from_confidence(pred.get("confidence_score")),
            })

    groups_doc = await db.prediction_groups.find_one({"match_date": target_date}, {"_id": 0})
    groups = (groups_doc or {}).get("groups", [])

    if not groups:
        fallback_groups: dict[str, dict] = {}
        for pred in prediction_docs:
            group_id = pred.get("prediction_group_id")
            if not group_id:
                continue

            existing = fallback_groups.get(group_id) or {
                "group_id": group_id,
                "group_index": pred.get("prediction_group_index"),
                "is_high_risk_group": bool(pred.get("prediction_group_is_high_risk")),
                "games": [],
            }
            if existing.get("group_index") is None and pred.get("prediction_group_index") is not None:
                existing["group_index"] = pred.get("prediction_group_index")
            existing["is_high_risk_group"] = existing["is_high_risk_group"] or bool(pred.get("prediction_group_is_high_risk"))
            existing["games"].append({
                "match_id": pred.get("match_id"),
                "sport": pred.get("sport"),
                "home_team": pred.get("home_team"),
                "away_team": pred.get("away_team"),
                "risk_score": round(max(0.0, 1.0 - float(pred.get("confidence_score") or 0.0)), 6),
            })
            fallback_groups[group_id] = existing

        groups = sorted(
            fallback_groups.values(),
            key=lambda group: (
                group.get("group_index") is None,
                group.get("group_index") or 0,
                str(group.get("group_id") or ""),
            ),
        )

    enriched_groups = []
    for group in groups:
        group_games = group.get("games") or []
        group_match_ids = [g.get("match_id") for g in group_games if g.get("match_id")]
        if normalized_sport:
            group_match_ids = [
                match_id for match_id in group_match_ids
                if (pred_by_match_id.get(match_id) or {}).get("sport", "soccer") == normalized_sport
            ]
            if not group_match_ids:
                continue

        resolved_docs: list[dict] = []
        if group_match_ids:
            async for ar in db.actual_results.find(
                {"match_id": {"$in": group_match_ids}},
                {"_id": 0, "match_id": 1, "actual_outcome": 1},
            ):
                resolved_docs.append(ar)

        resolved_map = {r.get("match_id"): r.get("actual_outcome") for r in resolved_docs if r.get("match_id")}

        group_hits = 0
        fully_resolved = len(group_match_ids) > 0
        for match_id in group_match_ids:
            pred = pred_by_match_id.get(match_id) or {}
            predicted = pred.get("predicted_outcome")
            actual = resolved_map.get(match_id)
            if actual is None:
                fully_resolved = False
                continue
            if predicted and predicted == actual:
                group_hits += 1

        group_status = "pending"
        if fully_resolved:
            group_status = "won" if group_hits == len(group_match_ids) else "lost"

        confidence_values = [
            float((pred_by_match_id.get(mid) or {}).get("confidence_score") or 0.0)
            for mid in group_match_ids
        ]
        avg_confidence = (sum(confidence_values) / len(confidence_values)) if confidence_values else 0.0

        enriched_groups.append({
            **group,
            "games": [g for g in group_games if g.get("match_id") in set(group_match_ids)],
            "group_status": group_status,
            "resolved_games": len(resolved_docs),
            "total_games": len(group_match_ids),
            "group_hit_rate": round((group_hits / len(group_match_ids)), 4) if fully_resolved and group_match_ids else None,
            "avg_confidence_score": round(avg_confidence, 4),
            "play_rank": _play_rank_from_confidence(avg_confidence),
        })

    sorted_result = {
        sport_key: sorted(rows, key=_rank_sort_key)
        for sport_key, rows in result.items()
    }
    enriched_groups = sorted(enriched_groups, key=_group_sort_key)

    if normalized_sport:
        filtered_result = {normalized_sport: sorted_result.get(normalized_sport, [])}
    else:
        filtered_result = sorted_result

    for sport_key, sport_rows in filtered_result.items():
        filtered_result[sport_key] = sorted(
            sport_rows,
            key=lambda row: (
                row.get("overall_rank") is None,
                row.get("overall_rank") or 0,
                -(row.get("play_rank") or 0),
                -(float(row.get("confidence_score") or 0.0)),
                str(row.get("match_id") or ""),
            ),
        )

    return {
        "date": target_date,
        "total": sum(len(v) for v in filtered_result.values()),
        "by_sport": filtered_result,
        "groups": enriched_groups,
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
