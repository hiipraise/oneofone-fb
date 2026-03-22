# app/services/prediction_service.py
"""
Prediction service.

SerpAPI call budget per prediction: ~3 calls (was ~9)
  - fetch_team_stats(home)    → 1 combined SerpAPI call (form+injuries+stats)
  - fetch_team_stats(away)    → 1 combined SerpAPI call
  - _fetch_h2h_venue(h, a)    → 1 combined SerpAPI call  [H2H + venue together]
  - fetch_betting_odds        → Odds API only (no SerpAPI)
  - ESPN calls                → free, no quota

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
import uuid
from datetime import datetime, timezone
from app.utils.timezone import now_wat, WAT
from typing import Dict, Optional, List, Any

from pymongo.errors import ConfigurationError

from app.config.database import get_db
from app.config.settings import settings
from app.schemas.prediction_schema import PredictionRequest, PredictionOutput
from app.services.web_search_service import (
    fetch_team_stats,
    fetch_betting_odds,
    _fetch_combined_h2h_venue,
)
from app.services.match_validation_service import is_fixture_completed
from app.services.market_service import compute_all_markets
from app.ml.prediction_engine import prediction_engine
from app.utils.logging_util import log_system_event

_PREDICTION_TTL_HOURS = 12

logger = logging.getLogger(__name__)

# Sports the ML engine supports — others are skipped during learning
_SUPPORTED_ML_SPORTS = {"soccer", "basketball"}


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


def _generate_match_id(home: str, away: str, sport: str, date: str = "") -> str:
    raw = f"{home.lower()}-{away.lower()}-{sport.lower()}-{date}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


# ─────────────────────────────────────────────────────────────────────────────
# Prediction CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def create_prediction(request: PredictionRequest) -> PredictionOutput:
    db = get_db()
    match_date = request.match_date or now_wat().strftime("%Y-%m-%d")
    sport      = str(request.sport.value)
    match_id   = _generate_match_id(request.home_team, request.away_team, sport, match_date)

    if not request.skip_validation:
        fixture_status = is_fixture_completed(
            request.home_team,
            request.away_team,
            sport,
            match_date,
        )
        if fixture_status and fixture_status.get("completed"):
            status_text = fixture_status.get("status_text") or "Full Time"
            raise ValueError(
                f"Cannot generate a prediction for {request.home_team} vs "
                f"{request.away_team}: the match is already finished ({status_text})."
            )

    existing = await db.predictions.find_one({"match_id": match_id, "deleted_at": None})
    if existing:
        ts = existing.get("timestamp")
        is_fresh = False
        if ts:
            try:
                if isinstance(ts, str):
                    ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                else:
                    ts_dt = ts
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=WAT)
                age_hours = (datetime.now(WAT) - ts_dt).total_seconds() / 3600
                is_fresh  = age_hours < _PREDICTION_TTL_HOURS
                if not is_fresh:
                    logger.info(
                        f"Prediction {match_id} is {age_hours:.1f}h old "
                        f"(>{_PREDICTION_TTL_HOURS}h) — regenerating"
                    )
            except Exception as e:
                logger.warning(f"Could not parse prediction timestamp [{match_id}]: {e}")
                is_fresh = True

        if is_fresh:
            existing.pop("_id", None)
            logger.info(f"Returning cached prediction for {match_id}")
            return PredictionOutput(**existing)

    logger.info(f"Generating: {request.home_team} vs {request.away_team} [{sport}]")

    home_stats = fetch_team_stats(request.home_team, sport)
    away_stats = fetch_team_stats(request.away_team, sport)

    h2h_venue = _fetch_combined_h2h_venue(request.home_team, request.away_team, sport)
    h2h   = h2h_venue["h2h"]
    venue = h2h_venue["venue"]

    odds = fetch_betting_odds(request.home_team, request.away_team, sport)

    features = prediction_engine.features_from_data(
        home_stats, away_stats, h2h, odds, venue, sport=sport
    )
    result = prediction_engine.predict(features, sport=sport)

    try:
        market_features = dict(features)
        market_features["implied_home_prob"] = float(result.get("home_win_probability", features.get("implied_home_prob", 0.5)))
        market_features["implied_away_prob"] = float(result.get("away_win_probability", features.get("implied_away_prob", 0.5)))
        markets = compute_all_markets(market_features, sport)
    except Exception as e:
        logger.warning(f"Market calculation error: {e}")
        markets = None

    output = PredictionOutput(
        match_id=match_id,
        home_team=request.home_team,
        away_team=request.away_team,
        sport=sport,
        league=request.league,
        match_date=match_date,
        home_win_probability=result["home_win_probability"],
        draw_probability=result["draw_probability"],
        away_win_probability=result["away_win_probability"],
        confidence_score=result["confidence_score"],
        confidence_interval_low=result["confidence_interval_low"],
        confidence_interval_high=result["confidence_interval_high"],
        predicted_outcome=result["predicted_outcome"],
        model_version=result["model_version"],
        timestamp=datetime.now(WAT),
        features_used=features,
        data_sources=[
            "ESPN Public API", "The Odds API",
            "SerpAPI Web Search (combined)", "Venue Statistics",
        ],
        extended_markets=markets,
    )

    doc = output.model_dump()
    doc["timestamp"]  = doc["timestamp"].isoformat()
    doc["deleted_at"] = None
    doc["match_date_indexed"] = match_date
    await db.predictions.replace_one({"match_id": match_id}, doc, upsert=True)

    snapshot = {
        "match_id": match_id, "sport": sport,
        "timestamp": now_wat().isoformat(),
        "match_date": match_date,
        "home_raw": home_stats, "away_raw": away_stats,
        "h2h_raw": h2h, "odds_raw": odds, "features": features,
    }
    await db.feature_snapshots.replace_one({"match_id": match_id}, snapshot, upsert=True)

    await log_system_event("prediction_created", f"Prediction generated for {match_id}", "INFO")
    return output


async def get_predictions(
    sport: Optional[str] = None,
    limit: int = 50,
    include_deleted: bool = False,
) -> List[Dict]:
    db = get_db()
    query: Dict = {}
    if sport:
        query["sport"] = sport
    if not include_deleted:
        query["deleted_at"] = None
    results = []
    async for doc in db.predictions.find(query).sort("timestamp", -1).limit(limit):
        doc.pop("_id", None)
        results.append(doc)
    return results


async def get_prediction_by_id(match_id: str) -> Optional[Dict]:
    db = get_db()
    doc = await db.predictions.find_one({"match_id": match_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def soft_delete_prediction(match_id: str) -> bool:
    db = get_db()
    result = await db.predictions.update_one(
        {"match_id": match_id},
        {"$set": {"deleted_at": now_wat().isoformat()}},
    )
    return result.matched_count > 0


async def restore_prediction(match_id: str) -> bool:
    db = get_db()
    result = await db.predictions.update_one(
        {"match_id": match_id},
        {"$set": {"deleted_at": None}},
    )
    return result.matched_count > 0


# ─────────────────────────────────────────────────────────────────────────────
# Result submission + isolated background learning
# ─────────────────────────────────────────────────────────────────────────────

async def save_actual_result(
    match_id: str, home_score: int, away_score: int,
    actual_outcome: str, match_date: str,
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
    from app.config.database import override_db_context

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
    async for doc in db.actual_results.find({}):
        actual_results[doc["match_id"]] = doc.get("actual_outcome", "")

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
            "features":             features,
            "actual_outcome":       actual,
            "predicted_outcome":    pred.get("predicted_outcome"),
            "home_win_probability": pred.get("home_win_probability"),
            "match_date":           snap.get("match_date", "") if snap else "",
        })

    for sport, records in sport_records.items():
        try:
            retrain_result = prediction_engine.retrain(records, sport=sport)
            metrics        = prediction_engine.evaluate(records, sport=sport)
            if metrics:
                await db.model_metrics.insert_one({
                    "model_version":  prediction_engine.model_version,
                    "sport":          sport,
                    "date":           now_wat().isoformat(),
                    **{k: metrics.get(k, 0) for k in (
                        "brier_score", "log_loss", "calibration_error",
                        "accuracy", "total_predictions", "ml_weight",
                        "n_training_samples",
                    )},
                    "retrain_result": retrain_result,
                })
                logger.info(f"[{sport}] Learning complete: {metrics}")
        except Exception as e:
            logger.error(f"[{sport}] Retrain/evaluate failed: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Public endpoint trigger (POST /api/predictions/learn/trigger)
# ─────────────────────────────────────────────────────────────────────────────

async def trigger_learning_update() -> None:
    """Same isolated-thread pattern so the manual trigger also works cleanly."""
    t = threading.Thread(target=_run_learning_in_thread, daemon=True)
    t.start()


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler wrapper
# ─────────────────────────────────────────────────────────────────────────────

async def generate_prediction(
    home_team:  str,
    away_team:  str,
    sport:      str,
    match_date: str | None = None,
    league:     str | None = None,
) -> "PredictionOutput":
    """Keyword-arg wrapper called by the daily scheduler."""
    from app.schemas.prediction_schema import SportType

    try:
        sport_enum = SportType(sport.lower())
    except ValueError:
        sport_enum = SportType.SOCCER

    request = PredictionRequest(
        home_team  = home_team,
        away_team  = away_team,
        sport      = sport_enum,
        match_date = match_date,
        league     = league,
    )
    return await create_prediction(request)
