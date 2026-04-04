# app/routes/metrics.py
import logging
from datetime import datetime, timezone, timedelta
from app.utils.timezone import WAT
from fastapi import APIRouter, Query
from app.config.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def get_metrics(limit: int = Query(30, ge=1, le=200)):
    db = get_db()
    results = []
    async for doc in db.model_metrics.find({}).sort("date", -1).limit(limit):
        doc.pop("_id", None)
        results.append(doc)
    return results


@router.get("/latest")
async def get_latest_metrics():
    db = get_db()
    doc = await db.model_metrics.find_one({}, sort=[("date", -1)])
    if doc:
        doc.pop("_id", None)
    return doc or {}


@router.get("/summary")
async def get_metrics_summary():
    from app.ml.prediction_engine import prediction_engine, FEATURE_KEYS
    db = get_db()

    sports = list(FEATURE_KEYS.keys())

    actual_results: dict[str, str] = {}
    total_resolved_raw = 0
    async for doc in db.actual_results.find({}):
        total_resolved_raw += 1
        actual_results[doc["match_id"]] = doc.get("actual_outcome")

    records = []
    db_sport_counts: dict[str, int] = {s: 0 for s in sports}
    sport_accuracy = {s: {"correct": 0, "count": 0} for s in sports}
    sport_confidence = {s: [] for s in sports}

    if actual_results:
        async for pred in db.predictions.find(
            {"match_id": {"$in": list(actual_results.keys())}, "deleted_at": None}
        ):
            mid = pred.get("match_id")
            sport = pred.get("sport", "soccer")
            actual_outcome = actual_results.get(mid)
            if sport in db_sport_counts:
                db_sport_counts[sport] += 1
                sport_accuracy[sport]["count"] += 1
                if pred.get("predicted_outcome") == actual_outcome:
                    sport_accuracy[sport]["correct"] += 1
                confidence = pred.get("confidence_score")
                if confidence is not None:
                    sport_confidence[sport].append(float(confidence))
            records.append({
                "home_win_probability": pred.get("home_win_probability", 0.5),
                "actual_outcome": actual_outcome,
            })

    try:
        metrics = prediction_engine.evaluate(records) if records else {}
    except Exception as e:
        logger.error(f"evaluate() failed in summary: {e}")
        metrics = {}

    total_preds = await db.predictions.count_documents({})
    total_resolved_scored = len(records)

    n_training = {
        s: max(
            int(prediction_engine.n_training_samples.get(s, 0)),
            db_sport_counts.get(s, 0),
        )
        for s in sports
    }

    is_trained = {s: bool(prediction_engine.is_trained.get(s, False)) for s in sports}

    try:
        ml_weights = {s: round(prediction_engine._ml_weight(s), 3) for s in sports}
    except Exception as e:
        logger.error(f"_ml_weight() failed: {e}")
        ml_weights = {s: 0.0 for s in sports}

    sport_breakdown = {
        s: {
            "resolved": db_sport_counts.get(s, 0),
            "accuracy": round(sport_accuracy[s]["correct"] / sport_accuracy[s]["count"], 4)
            if sport_accuracy[s]["count"]
            else None,
            "avg_confidence": round(
                sum(sport_confidence[s]) / len(sport_confidence[s]),
                4,
            ) if sport_confidence[s] else None,
            "ml_weight": ml_weights.get(s, 0.0),
            "trained": is_trained.get(s, False),
        }
        for s in sports
    }

    return {
        "performance_metrics": metrics,
        "sport_breakdown": sport_breakdown,
        "total_predictions": total_preds,
        "total_resolved_raw": total_resolved_raw,
        "total_resolved_scored": total_resolved_scored,
        "total_resolved": total_resolved_scored,
        "model_version": prediction_engine.model_version,
        "is_trained": is_trained,
        "n_training_samples": n_training,
        "ml_weights": ml_weights,
    }


@router.get("/confidence-history")
async def get_confidence_history(days: int = Query(30, ge=7, le=180)):
    db = get_db()
    cutoff = (datetime.now(WAT) - timedelta(days=days)).strftime("%Y-%m-%d")

    pipeline = [
        {
            "$match": {
                "deleted_at": None,
                "match_date": {"$gte": cutoff},
                "confidence_score": {"$exists": True, "$ne": None},
            }
        },
        {
            "$group": {
                "_id": {"date": "$match_date", "sport": "$sport"},
                "avg": {"$avg": "$confidence_score"},
                "min": {"$min": "$confidence_score"},
                "max": {"$max": "$confidence_score"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.date": 1}},
    ]

    rows = []
    async for doc in db.predictions.aggregate(pipeline):
        rows.append({
            "date": doc["_id"]["date"],
            "sport": doc["_id"]["sport"],
            "avg": round(doc["avg"], 4),
            "min": round(doc["min"], 4),
            "max": round(doc["max"], 4),
            "count": doc["count"],
        })
    return rows


@router.get("/quota")
async def get_serper_quota():
    from app.services.quota_service import get_persisted_quota
    return await get_persisted_quota()


@router.post("/quota/increment")
async def increment_quota(calls: int = 1):
    from app.services.web_search_service import get_serper_usage
    db = get_db()

    live = get_serper_usage()
    month_key = live.get("month", "unknown")
    doc_id = f"quota:{month_key}"
    budget = int(live.get("budget", 200))

    existing_primary = await db.serper_quota.find_one({"_id": doc_id})
    existing_legacy = await db.serpapi_quota.find_one({"_id": doc_id})
    existing = existing_primary or existing_legacy
    current_used = existing.get("used", 0) if existing else 0
    new_used = max(current_used, int(live.get("used", 0))) + calls
    remaining = max(budget - new_used, 0)

    payload = {"_id": doc_id, "month": month_key, "used": new_used,
         "budget": budget, "remaining": remaining}

    await db.serper_quota.replace_one({"_id": doc_id}, payload, upsert=True)
    await db.serpapi_quota.replace_one({"_id": doc_id}, payload, upsert=True)
    return {"used": new_used, "budget": budget, "remaining": remaining}
