# app/services/prediction_learning.py
"""
Prediction learning & result-saving logic (extracted from prediction_service.py
in the Sprint 5.3 file-split pass).

Holds:
  - save_actual_result()              persist actual match results
  - _run_learning_in_thread()         sync entry for the daemon thread
  - _learning_with_own_client()       isolated Motor client + event loop
  - _trigger_learning_update_impl()   core ML learning logic
  - trigger_learning_update()         public manual trigger

Learning update isolation
  - trigger_learning_update() opens its own AsyncIOMotorClient in its own
    event loop running in a daemon thread — the same pattern as the daily
    scheduler.  This avoids SSL handshake timeouts that occur when Motor's
    async cursor falls back to pymongo.synchronous pool threads that don't
    share the main connection's TLS session.
"""
import asyncio
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple

from pymongo.errors import ConfigurationError

from app.config.database import get_db, override_db_context
from app.config.settings import settings
from app.ml.prediction_engine import prediction_engine
from app.utils.timezone import now_wat

logger = logging.getLogger(__name__)

# Sports the ML engine supports — soccer-only platform
_SUPPORTED_ML_SPORTS = {"soccer"}


def _is_mongo_dns_resolution_error(exc: Exception) -> bool:
    """Return True when PyMongo failed to resolve an SRV/TXT Mongo host."""
    if not isinstance(exc, ConfigurationError):
        return False

    message = str(exc).lower()
    return (
        "dns" in message
        or "resolution lifetime expired" in message
        or "operation timed out" in message
        or "srv" in message
    )


def _split_learning_records(records: List[Dict], holdout_fraction: float = 0.2, min_holdout: int = 5) -> Tuple[List[Dict], List[Dict]]:
    if len(records) < (min_holdout * 2):
        return records, []

    ordered = sorted(
        records,
        key=lambda rec: (
            str(rec.get("match_date") or ""),
            str(rec.get("match_id") or ""),
        ),
    )
    eval_size = max(min_holdout, int(round(len(ordered) * holdout_fraction)))
    eval_size = min(eval_size, len(ordered) - min_holdout)
    if eval_size < min_holdout:
        return ordered, []
    return ordered[:-eval_size], ordered[-eval_size:]


async def save_actual_result(
    match_id: str, home_score: int, away_score: int,
    actual_outcome: str, match_date: str,
    corner_stats: Optional[Dict[str, Any]] = None,
):
    """
    Persist the actual match result, then kick off learning in a fully
    isolated background thread (own event loop + own Motor client).

    Why isolated?
    Motor's async cursor internally delegates to pymongo.synchronous pool
    threads.  When those threads try to open a NEW TLS connection to Atlas
    from inside asyncio.create_task(), the SSL handshake times out because
    they don't share the main event loop's connection pool.  Running in a
    dedicated thread with a fresh Motor client avoids this entirely — the
    same approach the daily scheduler uses.
    """
    db = get_db()
    if not actual_outcome:
        actual_outcome = (
            "home_win" if home_score > away_score
            else "away_win" if away_score > home_score
            else "draw"
        )

    prediction = await db.predictions.find_one(
        {"match_id": match_id},
        {
            "_id": 0,
            "home_team": 1,
            "away_team": 1,
            "sport": 1,
            "league": 1,
            "predicted_outcome": 1,
            "confidence_score": 1,
            "prediction_group_id": 1,
        },
    )

    doc = {
        "match_id":       match_id,
        "home_score":     home_score,
        "away_score":     away_score,
        "actual_outcome": actual_outcome,
        "actual_result":  f"{home_score}-{away_score}",
        "match_date":     match_date,
        "recorded_at":    now_wat().isoformat(),
    }
    if corner_stats:
        doc.update({
            "home_corners": corner_stats.get("home_corners"),
            "away_corners": corner_stats.get("away_corners"),
            "total_corners": corner_stats.get("total_corners"),
            "corner_source": corner_stats.get("source"),
        })
    if prediction:
        doc.update({
            "home_team": prediction.get("home_team"),
            "away_team": prediction.get("away_team"),
            "sport": prediction.get("sport"),
            "league": prediction.get("league"),
            "predicted_outcome": prediction.get("predicted_outcome"),
            "confidence_score": prediction.get("confidence_score"),
        })

    await db.actual_results.replace_one({"match_id": match_id}, doc, upsert=True)

    # Group-level resolution: when all games in a group are resolved, stamp group result.
    group_id = (prediction or {}).get("prediction_group_id")
    if group_id:
        group_preds = []
        async for gp in db.predictions.find(
            {"prediction_group_id": group_id, "deleted_at": None},
            {"_id": 0, "match_id": 1, "predicted_outcome": 1},
        ):
            group_preds.append(gp)

        group_match_ids = [g["match_id"] for g in group_preds]
        resolved = []
        async for ar in db.actual_results.find(
            {"match_id": {"$in": group_match_ids}},
            {"_id": 0, "match_id": 1, "actual_outcome": 1},
        ):
            resolved.append(ar)

        if len(group_match_ids) >= 2 and len(resolved) == len(group_match_ids):
            resolved_map = {r["match_id"]: r.get("actual_outcome") for r in resolved}
            hits = sum(
                1 for g in group_preds
                if g.get("predicted_outcome") and resolved_map.get(g["match_id"]) == g.get("predicted_outcome")
            )
            hit_rate = hits / len(group_match_ids) if group_match_ids else 0.0
            group_status = "won" if hits == len(group_match_ids) else "lost"

            await db.actual_results.update_many(
                {"match_id": {"$in": group_match_ids}},
                {"$set": {
                    "group_id": group_id,
                    "group_resolved": True,
                    "group_status": group_status,
                    "group_hit_rate": round(hit_rate, 4),
                    "group_resolved_at": now_wat().isoformat(),
                }},
            )
        else:
            await db.actual_results.update_one(
                {"match_id": match_id},
                {"$set": {
                    "group_id": group_id,
                    "group_resolved": False,
                    "group_status": "pending",
                }},
            )

    # Launch learning in a daemon thread — never blocks the HTTP response
    t = threading.Thread(target=_run_learning_in_thread, daemon=True)
    t.start()

    return doc


def _run_learning_in_thread() -> None:
    """
    Sync entry point for the daemon thread.
    Creates a fresh event loop — mirrors run_daily_predictions() in scheduler.
    """
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_learning_with_own_client())
    except ConfigurationError as e:
        if _is_mongo_dns_resolution_error(e):
            logger.warning(
                "Learning update skipped because MongoDB DNS resolution failed "
                "for the isolated background client: %s",
                e,
            )
        else:
            logger.error(f"Learning thread fatal error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Learning thread fatal error: {e}", exc_info=True)
    finally:
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass


async def _learning_with_own_client() -> None:
    """
    Opens a dedicated AsyncIOMotorClient and scopes it to this coroutine via
    a context-local database override so other event loops never see the
    background thread's Motor client.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    try:
        learn_client = AsyncIOMotorClient(settings.MONGODB_URI)
    except ConfigurationError as e:
        if _is_mongo_dns_resolution_error(e):
            logger.warning(
                "Learning update skipped because MongoDB URI resolution failed. "
                "Verify DNS reachability for the Atlas SRV record or use a "
                "non-SRV MongoDB URI. Error: %s",
                e,
            )
            return
        raise
    learn_db = learn_client[settings.MONGODB_DB]

    try:
        with override_db_context(learn_db, learn_client):
            await _trigger_learning_update_impl(learn_db)
    except Exception as e:
        logger.error(f"Learning update failed: {e}", exc_info=True)
    finally:
        try:
            learn_client.close()
        except Exception:
            pass
        logger.info("Learning: isolated Motor client closed")


async def _trigger_learning_update_impl(db) -> None:
    """Core ML learning logic. Receives db handle directly — no get_db() call."""

    actual_results: Dict[str, str] = {}
    group_statuses: Dict[str, str] = {}
    group_hit_rates: List[float] = []
    async for doc in db.actual_results.find({}):
        actual_results[doc["match_id"]] = doc.get("actual_outcome", "")
        if doc.get("group_status"):
            group_statuses[doc["match_id"]] = doc.get("group_status")
        if isinstance(doc.get("group_hit_rate"), (int, float)):
            group_hit_rates.append(float(doc["group_hit_rate"]))

    if not actual_results:
        logger.info("Learning: no resolved results, skipping")
        return

    sport_records: Dict[str, List[Dict]] = {}
    async for pred in db.predictions.find({
        "match_id": {"$in": list(actual_results.keys())},
        "deleted_at": None,
    }):
        mid    = pred.get("match_id")
        actual = actual_results.get(mid)
        if not actual:
            continue
        sport = pred.get("sport", "soccer")

        if sport not in _SUPPORTED_ML_SPORTS:
            logger.debug(f"Learning: skipping unsupported sport '{sport}'")
            continue

        snap     = await db.feature_snapshots.find_one({"match_id": mid})
        features = (
            snap.get("features", pred.get("features_used", {}))
            if snap else pred.get("features_used", {})
        )
        sport_records.setdefault(sport, []).append({
            "match_id":             mid,
            "features":             features,
            "actual_outcome":       actual,
            "predicted_outcome":    pred.get("predicted_outcome"),
            "home_win_probability": pred.get("home_win_probability"),
            "draw_probability":     pred.get("draw_probability", 0.0),
            "away_win_probability": pred.get("away_win_probability"),
            "match_date":           snap.get("match_date", "") if snap else "",
        })

    for sport, records in sport_records.items():
        try:
            train_records, eval_records = _split_learning_records(records)
            retrain_result = prediction_engine.retrain(train_records, sport=sport)
            metrics = prediction_engine.evaluate(eval_records, sport=sport) if eval_records else {}
            if metrics:
                group_lost_count = sum(
                    1 for rec in records
                    if group_statuses.get(rec.get("match_id", "")) == "lost"
                )
                await db.model_metrics.insert_one({
                    "model_version":  prediction_engine.model_version,
                    "sport":          sport,
                    "date":           now_wat().isoformat(),
                    **{k: metrics.get(k, 0) for k in (
                        "brier_score", "log_loss", "calibration_error",
                        "accuracy", "total_predictions", "ml_weight",
                        "n_training_samples",
                    )},
                    "group_lost_samples": group_lost_count,
                    "avg_group_hit_rate": round(sum(group_hit_rates) / len(group_hit_rates), 4) if group_hit_rates else None,
                    "retrain_result": retrain_result,
                    "eval_holdout_size": len(eval_records),
                })
                logger.info(f"[{sport}] Learning complete: {metrics}")
            else:
                logger.info(
                    "[%s] Learning complete — retrained on %s records, holdout too small for evaluation",
                    sport,
                    len(train_records),
                )
        except Exception as e:
            logger.error(f"[{sport}] Retrain/evaluate failed: {e}", exc_info=True)


async def trigger_learning_update() -> None:
    """Same isolated-thread pattern so the manual trigger also works cleanly."""
    t = threading.Thread(target=_run_learning_in_thread, daemon=True)
    t.start()
