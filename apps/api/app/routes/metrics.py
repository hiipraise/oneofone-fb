# app/routes/metrics.py
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from app.utils.timezone import WAT
from fastapi import APIRouter, Query
from app.config.database import get_db
from app.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()
METRIC_SPORT = "soccer"


def _actual_btts_from_result(result: dict) -> str | None:
    home_score = result.get("home_score")
    away_score = result.get("away_score")
    try:
        if home_score is None or away_score is None:
            return None
        return "Yes" if int(home_score) > 0 and int(away_score) > 0 else "No"
    except (TypeError, ValueError):
        return None


def _predicted_btts_from_prediction(prediction: dict) -> str | None:
    btts = (prediction.get("extended_markets") or {}).get("btts") or {}
    result = btts.get("result")
    if isinstance(result, str) and result.lower() in {"yes", "no"}:
        return result.title()

    yes = btts.get("yes")
    no = btts.get("no")
    try:
        if yes is None and no is None:
            return None
        if yes is None:
            return "No" if float(no) >= 0.5 else "Yes"
        if no is None:
            return "Yes" if float(yes) >= 0.5 else "No"
        return "Yes" if float(yes) >= float(no) else "No"
    except (TypeError, ValueError):
        return None


def _empty_market_accuracy(label: str) -> dict:
    return {
        "label": label,
        "total": 0,
        "correct": 0,
        "miss": 0,
        "accuracy": None,
        "predicted_yes": 0,
        "predicted_no": 0,
        "actual_yes": 0,
        "actual_no": 0,
        "by_prediction": {
            "Yes": {"total": 0, "correct": 0, "miss": 0, "accuracy": None},
            "No": {"total": 0, "correct": 0, "miss": 0, "accuracy": None},
        },
    }


def _finalize_market_accuracy(stats: dict) -> dict:
    if stats["total"]:
        stats["accuracy"] = round(stats["correct"] / stats["total"], 4)

    for bucket in stats["by_prediction"].values():
        if bucket["total"]:
            bucket["accuracy"] = round(bucket["correct"] / bucket["total"], 4)

    return stats


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
    from app.ml.prediction_engine import prediction_engine
    db = get_db()

    sports = ["soccer"]  # Soccer-only platform

    actual_results: dict[str, dict] = {}
    total_resolved_raw = 0
    async for doc in db.actual_results.find({}):
        total_resolved_raw += 1
        actual_results[doc["match_id"]] = doc

    market_accuracy_by_type = {
        "gg": _empty_market_accuracy("GG (Both Teams to Score)"),
    }

    records_by_sport: dict[str, list[dict[str, object]]] = {s: [] for s in sports}
    db_sport_counts: dict[str, int] = {s: 0 for s in sports}
    sport_accuracy = {s: {"correct": 0, "count": 0} for s in sports}
    sport_confidence = {s: [] for s in sports}

    if actual_results:
        async for pred in db.predictions.find(
            {"match_id": {"$in": list(actual_results.keys())}, "deleted_at": None}
        ):
            mid = pred.get("match_id")
            sport = pred.get("sport", "soccer")
            result_doc = actual_results.get(mid) or {}
            actual_outcome = result_doc.get("actual_outcome")

            predicted_btts = _predicted_btts_from_prediction(pred)
            actual_btts = _actual_btts_from_result(result_doc)
            if predicted_btts and actual_btts:
                gg_stats = market_accuracy_by_type["gg"]
                gg_stats["total"] += 1
                gg_stats[f"predicted_{predicted_btts.lower()}"] += 1
                gg_stats[f"actual_{actual_btts.lower()}"] += 1
                gg_bucket = gg_stats["by_prediction"][predicted_btts]
                gg_bucket["total"] += 1
                if predicted_btts == actual_btts:
                    gg_stats["correct"] += 1
                    gg_bucket["correct"] += 1
                else:
                    gg_stats["miss"] += 1
                    gg_bucket["miss"] += 1

            if sport in db_sport_counts:
                db_sport_counts[sport] += 1
                sport_accuracy[sport]["count"] += 1
                if pred.get("predicted_outcome") == actual_outcome:
                    sport_accuracy[sport]["correct"] += 1
                confidence = pred.get("confidence_score")
                if confidence is not None:
                    sport_confidence[sport].append(float(confidence))
            if sport in records_by_sport:
                records_by_sport[sport].append({
                    "home_win_probability": pred.get("home_win_probability", 0.5),
                    "draw_probability":     pred.get("draw_probability",     0.0),
                    "away_win_probability": pred.get("away_win_probability", 0.5),
                    "actual_outcome":       actual_outcome,
                })

    performance_metrics_by_sport: dict[str, dict[str, float | int | None]] = {}
    for sport in sports:
        sport_records = records_by_sport.get(sport, [])
        if not sport_records:
            continue
        try:
            performance_metrics_by_sport[sport] = prediction_engine.evaluate(
                sport_records,
                sport=sport,
            )
        except Exception as e:
            logger.error(f"evaluate() failed in summary for sport '{sport}': {e}")
            performance_metrics_by_sport[sport] = {}

    weighted_metric_totals: dict[str, float] = {}
    weighted_metric_weights: dict[str, int] = {}
    for sport, metrics in performance_metrics_by_sport.items():
        weight = len(records_by_sport.get(sport, []))
        if weight <= 0:
            continue
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                weighted_metric_totals[key] = weighted_metric_totals.get(key, 0.0) + (float(value) * weight)
                weighted_metric_weights[key] = weighted_metric_weights.get(key, 0) + weight

    performance_metrics_all_sports = {
        key: round(weighted_metric_totals[key] / weighted_metric_weights[key], 6)
        for key in weighted_metric_totals
        if weighted_metric_weights.get(key)
    }

    total_preds = await db.predictions.count_documents({})
    total_resolved_scored = sum(len(v) for v in records_by_sport.values())

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
        "performance_metrics_all_sports": performance_metrics_all_sports,
        "performance_metrics_by_sport": performance_metrics_by_sport,
        "sport_breakdown": sport_breakdown,
        "total_predictions": total_preds,
        "total_resolved_raw": total_resolved_raw,
        "total_resolved_scored": total_resolved_scored,
        "total_resolved": total_resolved_scored,
        "model_version": prediction_engine.model_version,
        "is_trained": is_trained,
        "n_training_samples": n_training,
        "ml_weights": ml_weights,
        "ml_activation_threshold": settings.MIN_TRAINING_SAMPLES,
        "supported_sports": sports,
        "market_accuracy_by_type": {
            key: _finalize_market_accuracy(value)
            for key, value in market_accuracy_by_type.items()
        },
        "report_thresholds": {
            "accuracy_good": settings.REPORT_ACCURACY_GOOD,
            "accuracy_needs": settings.REPORT_ACCURACY_NEEDS,
            "brier_good": settings.REPORT_BRIER_GOOD,
            "brier_needs": settings.REPORT_BRIER_NEEDS,
            "resolution_good": settings.REPORT_RESOLUTION_GOOD,
            "low_confidence": settings.REPORT_LOW_CONFIDENCE,
        },
    }




def _canonical_team_name(name: str | None) -> str:
    if not isinstance(name, str):
        return ""
    cleaned = " ".join(name.strip().lower().split())
    return cleaned


@router.get("/team-accuracy")
async def get_team_accuracy(
    min_resolved: int = Query(10, ge=1, le=500),
    limit: int = Query(20, ge=1, le=200),
    sport: str | None = Query(None),
):
    db = get_db()

    actual_results: dict[str, dict] = {}
    async for doc in db.actual_results.find({}):
        actual_results[doc["match_id"]] = doc

    if not actual_results:
        return {"teams": [], "meta": {"min_resolved": min_resolved, "limit": limit, "sport": sport}}

    team_stats: dict[str, dict[str, object]] = {}

    pred_query = {"match_id": {"$in": list(actual_results.keys())}, "deleted_at": None}
    if sport:
        pred_query["sport"] = sport

    async for pred in db.predictions.find(pred_query):
        mid = pred.get("match_id")
        result_doc = actual_results.get(mid) or {}
        actual_outcome = result_doc.get("actual_outcome")
        predicted_outcome = pred.get("predicted_outcome")
        if not actual_outcome or not predicted_outcome:
            continue

        is_correct = predicted_outcome == actual_outcome
        for side in ("home_team", "away_team"):
            team_name_raw = pred.get(side)
            canonical = _canonical_team_name(team_name_raw)
            if not canonical:
                continue

            item = team_stats.setdefault(canonical, {
                "team": team_name_raw,
                "resolved": 0,
                "correct": 0,
                "incorrect": 0,
                "sports": set(),
                "last_match_date": None,
            })
            item["resolved"] += 1
            if is_correct:
                item["correct"] += 1
            else:
                item["incorrect"] += 1
            if pred.get("sport"):
                item["sports"].add(pred.get("sport"))

            match_date = pred.get("match_date")
            if isinstance(match_date, str):
                prev = item.get("last_match_date")
                if prev is None or match_date > prev:
                    item["last_match_date"] = match_date

    rows = []
    for data in team_stats.values():
        resolved = int(data["resolved"])
        if resolved < min_resolved:
            continue
        correct = int(data["correct"])
        rows.append({
            "team": data["team"],
            "resolved": resolved,
            "correct": correct,
            "incorrect": int(data["incorrect"]),
            "accuracy": round(correct / resolved, 4),
            "sports": sorted(list(data["sports"])),
            "last_match_date": data.get("last_match_date"),
        })

    rows.sort(key=lambda x: (x["accuracy"], x["resolved"], x["correct"]), reverse=True)

    return {
        "teams": rows[:limit],
        "meta": {
            "min_resolved": min_resolved,
            "limit": limit,
            "sport": sport,
            "total_qualified_teams": len(rows),
        },
    }
@router.get("/performance-history")
async def get_performance_history(days: int = Query(90, ge=7, le=365)):
    """
    Returns daily brier_score, log_loss, and accuracy computed from real
    predictions evaluated against actual_results — NOT training-time metrics.
    """
    db = get_db()
    cutoff = (datetime.now(WAT) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Load all actual results into memory (typically small collection)
    actual_results: dict[str, str] = {}
    async for doc in db.actual_results.find({}):
        actual_results[doc["match_id"]] = doc.get("actual_outcome")

    if not actual_results:
        return []

    # Fetch resolved predictions within the date window
    eps = 1e-9
    by_date: dict[str, list[dict]] = defaultdict(list)

    async for pred in db.predictions.find(
        {
            "match_id": {"$in": list(actual_results.keys())},
            "deleted_at": None,
            "match_date": {"$gte": cutoff},
            "sport": METRIC_SPORT,
        }
    ):
        mid = pred.get("match_id")
        actual = actual_results.get(mid)
        if not actual:
            continue

        date = pred.get("match_date", "")
        if not date:
            continue

        ph  = float(pred.get("home_win_probability") or 0.5)
        pd_ = float(pred.get("draw_probability")      or 0.0)
        pa  = float(pred.get("away_win_probability")  or 0.5)
        total = ph + pd_ + pa
        if total > 0:
            ph, pd_, pa = ph / total, pd_ / total, pa / total

        by_date[date].append({
            "predicted_outcome": pred.get("predicted_outcome"),
            "actual_outcome":    actual,
            "ph": ph, "pd": pd_, "pa": pa,
        })

    if not by_date:
        return []

    result = []
    for date in sorted(by_date.keys()):
        group = by_date[date]
        n = len(group)
        brier_sum = 0.0
        ll_sum    = 0.0
        correct   = 0

        for r in group:
            ph, pd_, pa = r["ph"], r["pd"], r["pa"]
            actual = r["actual_outcome"]

            y_home = 1.0 if actual == "home_win" else 0.0
            y_draw = 1.0 if actual == "draw"     else 0.0
            y_away = 1.0 if actual == "away_win" else 0.0

            brier_sum += (ph - y_home) ** 2 + (pd_ - y_draw) ** 2 + (pa - y_away) ** 2
            ll_sum    += -(
                y_home * math.log(max(ph,  eps)) +
                y_draw * math.log(max(pd_, eps)) +
                y_away * math.log(max(pa,  eps))
            )
            if r["predicted_outcome"] == actual:
                correct += 1

        result.append({
            "date":        date,
            "brier_score": round(brier_sum / n, 4),
            "log_loss":    round(ll_sum    / n, 4),
            "accuracy":    round(correct   / n, 4),
            "count":       n,
        })

    return result


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
                "sport": METRIC_SPORT,
            }
        },
        {
            "$group": {
                "_id": {"date": "$match_date", "sport": METRIC_SPORT},
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
            "date":  doc["_id"]["date"],
            "sport": doc["_id"]["sport"],
            "avg":   round(doc["avg"], 4),
            "min":   round(doc["min"], 4),
            "max":   round(doc["max"], 4),
            "count": doc["count"],
        })
    return rows


@router.get("/quota")
async def get_serper_quota():
    from app.services.quota_service import get_persisted_quota
    return await get_persisted_quota()


# ─────────────────────────────────────────────────────────────────────────────
# Market-Specific Accuracy Metrics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/market-accuracy")
async def get_market_accuracy(days: int = Query(90, ge=7, le=365)):
    """
    Returns prediction accuracy breakdown by market type:
      - GG (Both Teams To Score)
      - Corners
      - Over/Under Goals
    
    Analyzes resolved predictions within the specified day range.
    """
    from app.services.market_accuracy_service import market_accuracy_analyzer
    
    db = get_db()
    cutoff = (datetime.now(WAT) - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Fetch recent actual results (bounded by cutoff) to avoid scanning entire collection
    actual_results_raw: dict[str, dict] = {}
    async for doc in db.actual_results.find({"match_date": {"$gte": cutoff}}):
        actual_results_raw[doc["match_id"]] = {
            "actual_outcome": doc.get("actual_outcome"),
            "home_score": doc.get("home_score"),
            "away_score": doc.get("away_score"),
            "match_date": doc.get("match_date"),
        }
    
    if not actual_results_raw:
        return {
            "market_accuracy": {},
            "timestamp": datetime.now(WAT).isoformat(),
            "error": "No resolved predictions available"
        }
    
    async def _load_predictions(filter_by_date: bool) -> list[dict]:
        query = {
            "match_id": {"$in": list(actual_results_raw.keys())},
            "deleted_at": None,
            "sport": METRIC_SPORT,
        }
        if filter_by_date:
            query["match_date"] = {"$gte": cutoff}

        rows: list[dict] = []
        async for pred in db.predictions.find(query):
            rows.append(pred)
        return rows

    # Prefer the recent window, but fall back to all resolved predictions if needed.
    predictions = await _load_predictions(True)
    if not predictions:
        predictions = await _load_predictions(False)
    
    if not predictions:
        return {
            "market_accuracy": {},
            "timestamp": datetime.now(WAT).isoformat(),
            "error": "No predictions found in date range or historical fallback"
        }
    
    try:
        market_accuracy = market_accuracy_analyzer.analyze_market_accuracy(
            predictions,
            actual_results_raw
        )
        market_type_counts = market_accuracy_analyzer.get_market_type_counts(predictions)
        
        return {
            "market_accuracy": market_accuracy,
            "market_type_counts": market_type_counts,
            "total_predictions_analyzed": len(predictions),
            "total_resolved": len(actual_results_raw),
            "date_range_days": days,
        }
    except Exception as e:
        logger.error(f"Market accuracy analysis failed: {e}")
        return {
            "market_accuracy": {},
            "timestamp": datetime.now(WAT).isoformat(),
            "error": str(e)
        }


@router.get("/confidence-thresholds")
async def get_confidence_thresholds(days: int = Query(90, ge=7, le=365)):
    """
    Analyze prediction accuracy at different confidence thresholds.
    
    Shows which confidence levels produce the most reliable predictions,
    including:
      - Count of predictions at each threshold
      - Accuracy percentage at each threshold
      - Optimal threshold recommendation
    """
    from app.services.market_accuracy_service import market_accuracy_analyzer
    
    db = get_db()
    cutoff = (datetime.now(WAT) - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Fetch recent actual results (bounded by cutoff) including corner stats
    actual_results_raw: dict[str, dict] = {}
    async for doc in db.actual_results.find({"match_date": {"$gte": cutoff}}):
        actual_results_raw[doc["match_id"]] = {
            "actual_outcome": doc.get("actual_outcome"),
            "home_score": doc.get("home_score"),
            "away_score": doc.get("away_score"),
            "home_corners": doc.get("home_corners"),
            "away_corners": doc.get("away_corners"),
            "total_corners": doc.get("total_corners"),
        }
    
    if not actual_results_raw:
        return {
            "threshold_analysis": {},
            "optimal_threshold": None,
            "error": "No resolved predictions available"
        }
    
    async def _load_predictions(filter_by_date: bool) -> list[dict]:
        query = {
            "match_id": {"$in": list(actual_results_raw.keys())},
            "deleted_at": None,
            "sport": METRIC_SPORT,
        }
        if filter_by_date:
            query["match_date"] = {"$gte": cutoff}

        rows: list[dict] = []
        async for pred in db.predictions.find(query):
            rows.append(pred)
        return rows

    predictions = await _load_predictions(True)
    if not predictions:
        predictions = await _load_predictions(False)
    
    if not predictions:
        return {
            "threshold_analysis": {},
            "optimal_threshold": None,
            "error": "No predictions found in date range or historical fallback"
        }
    
    try:
        analysis = market_accuracy_analyzer.analyze_confidence_thresholds(
            predictions,
            actual_results_raw
        )
        confidence_dist = market_accuracy_analyzer.get_confidence_distribution(predictions)
        
        return {
            "threshold_breakdown": analysis["threshold_breakdown"],
            "optimal_threshold": analysis["optimal_threshold"],
            "confidence_distribution": confidence_dist,
            "total_predictions": len(predictions),
            "resolved_predictions": len([p for p in predictions if p.get("match_id") in actual_results_raw]),
            "date_range_days": days,
            "timestamp": analysis["timestamp"],
        }
    except Exception as e:
        logger.error(f"Confidence threshold analysis failed: {e}")
        return {
            "threshold_breakdown": {},
            "optimal_threshold": None,
            "error": str(e)
        }


@router.get("/confidence-distribution")
async def get_confidence_distribution(days: int = Query(30, ge=7, le=180)):
    """
    Return the distribution of confidence scores in recent predictions.
    
    Shows histograms of how confidence scores are distributed across
    predictions (e.g., how many predictions at 50-60% confidence, etc.)
    """
    from app.services.market_accuracy_service import market_accuracy_analyzer
    
    db = get_db()
    cutoff = (datetime.now(WAT) - timedelta(days=days)).strftime("%Y-%m-%d")
    
    predictions = []
    async for pred in db.predictions.find(
        {
            "deleted_at": None,
            "match_date": {"$gte": cutoff},
            "confidence_score": {"$exists": True, "$ne": None},
            "sport": METRIC_SPORT,
        }
    ):
        predictions.append(pred)
    
    if not predictions:
        return {
            "distribution": {},
            "timestamp": datetime.now(WAT).isoformat(),
        }
    
    try:
        dist = market_accuracy_analyzer.get_confidence_distribution(predictions)
        return {
            "distribution": dist,
            "total_predictions": len(predictions),
            "date_range_days": days,
            "timestamp": datetime.now(WAT).isoformat(),
        }
    except Exception as e:
        logger.error(f"Confidence distribution failed: {e}")
        return {
            "distribution": {},
            "error": str(e)
        }


@router.post("/quota/increment")
async def increment_quota(calls: int = 1):
    from app.services.web_search_service import get_serper_usage
    db = get_db()

    live = get_serper_usage()
    month_key = live.get("month", "unknown")
    doc_id = f"quota:{month_key}"
    budget = int(live.get("budget", 200))

    existing_primary = await db.serper_quota.find_one({"_id": doc_id})
    existing_legacy  = await db.serpapi_quota.find_one({"_id": doc_id})
    existing = existing_primary or existing_legacy
    current_used = existing.get("used", 0) if existing else 0
    new_used  = max(current_used, int(live.get("used", 0))) + calls
    remaining = max(budget - new_used, 0)

    payload = {
        "_id": doc_id, "month": month_key,
        "used": new_used, "budget": budget, "remaining": remaining,
    }

    await db.serper_quota.replace_one({"_id": doc_id}, payload, upsert=True)
    await db.serpapi_quota.replace_one({"_id": doc_id}, payload, upsert=True)
    return {"used": new_used, "budget": budget, "remaining": remaining}
