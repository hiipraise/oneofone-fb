# app/services/prediction_service.py
"""
Prediction service — prediction CRUD + pipeline orchestration.

SerpAPI call budget per prediction: ~3 calls (was ~9)
  - fetch_team_stats(home)    → 1 combined SerpAPI call (form+injuries+stats)
  - fetch_team_stats(away)    → 1 combined SerpAPI call
  - _fetch_h2h_venue(h, a)    → 1 combined SerpAPI call  [H2H + venue together]
  - fetch_betting_odds        → Odds API only (no SerpAPI)
  - ESPN calls                → free, no quota

Result-saving / background learning logic lives in
app.services.prediction_learning (Sprint 5.3 file split) and is re-exported
here so existing import sites keep working unchanged.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from app.utils.timezone import now_wat, WAT
from typing import Dict, Optional, List, Any

from app.config.settings import settings
from app.config.database import get_db
from app.schemas.prediction_schema import PredictionRequest, PredictionOutput
from app.services.web_search_service import (
    fetch_team_stats,
    fetch_betting_odds,
    _fetch_combined_h2h_venue,
)
from app.services.match_validation_service import is_fixture_completed
from app.services.market_service import compute_all_markets
from app.ml.prediction_engine import prediction_engine
from app.services.prediction_learning import (
    save_actual_result,
    trigger_learning_update,
    _is_mongo_dns_resolution_error,
    _split_learning_records,
)
from app.utils.logging_util import log_system_event

_PREDICTION_TTL_HOURS = 12
_EXTERNAL_CACHE_TTL_SECONDS = 6 * 60 * 60

logger = logging.getLogger(__name__)


def _generate_match_id(home: str, away: str, sport: str, date: str = "") -> str:
    raw = f"{home.lower()}-{away.lower()}-{sport.lower()}-{date}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


def _build_group_sizes(total_games: int, preferred_size: int = 3) -> List[int]:
    """
    Split a slate into risk groups while keeping every group size >= 2.
    For 2-3 games, this returns a single group to respect the min-size rule.
    """
    if total_games <= 0:
        return []
    if total_games <= 3:
        return [total_games]

    group_count = max(2, round(total_games / max(preferred_size, 2)))
    while group_count > 1 and (total_games // group_count) < 2:
        group_count -= 1

    base = total_games // group_count
    rem = total_games % group_count
    return [base + (1 if i < rem else 0) for i in range(group_count)]


def _risk_score_from_prediction(doc: Dict[str, Any]) -> float:
    confidence = float(doc.get("confidence_score") or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    return 1.0 - confidence


async def _assign_prediction_groups_for_date(db, match_date: str) -> Dict[str, Any]:
    """
    Assign risk-ranked groups for all predictions on a date.
    Final group contains the highest-risk (most likely to miss) games.
    """
    preds: List[Dict[str, Any]] = []
    async for pred in db.predictions.find(
        {"match_date": match_date, "deleted_at": None},
        {"_id": 0, "match_id": 1, "confidence_score": 1, "sport": 1, "home_team": 1, "away_team": 1},
    ):
        preds.append(pred)

    if len(preds) < 2:
        return {"groups": 0, "games": len(preds)}

    ranked = sorted(preds, key=_risk_score_from_prediction)
    sizes = _build_group_sizes(len(ranked))

    cursor = 0
    group_docs: List[Dict[str, Any]] = []
    for i, size in enumerate(sizes, start=1):
        chunk = ranked[cursor: cursor + size]
        cursor += size
        group_id = f"{match_date}-G{i}"
        games = []
        for p in chunk:
            games.append({
                "match_id": p["match_id"],
                "sport": p.get("sport"),
                "home_team": p.get("home_team"),
                "away_team": p.get("away_team"),
                "risk_score": round(_risk_score_from_prediction(p), 6),
            })
            await db.predictions.update_one(
                {"match_id": p["match_id"]},
                {"$set": {
                    "prediction_group_id": group_id,
                    "prediction_group_index": i,
                    "prediction_group_size": size,
                    "prediction_group_is_high_risk": i == len(sizes),
                }},
            )
        group_docs.append({
            "group_id": group_id,
            "group_index": i,
            "is_high_risk_group": i == len(sizes),
            "games": games,
        })

    await db.prediction_groups.replace_one(
        {"match_date": match_date},
        {
            "match_date": match_date,
            "updated_at": now_wat().isoformat(),
            "total_games": len(ranked),
            "groups": group_docs,
        },
        upsert=True,
    )
    return {"groups": len(group_docs), "games": len(ranked)}


def _external_cache_key(namespace: str, payload: Dict[str, Any]) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(f"{namespace}:{canon}".encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


async def _get_external_cache(db, key: str) -> Optional[Any]:
    now = now_wat()
    doc = await db.external_api_cache.find_one({"key": key, "expires_at": {"$gt": now}}, {"_id": 0, "data": 1})
    if doc:
        return doc.get("data")
    return None


async def _set_external_cache(db, key: str, data: Any, ttl_seconds: int = _EXTERNAL_CACHE_TTL_SECONDS) -> None:
    now = now_wat()
    expires_at = now + timedelta(seconds=ttl_seconds)
    await db.external_api_cache.replace_one(
        {"key": key},
        {
            "key": key,
            "data": data,
            "created_at": now,
            "expires_at": expires_at,
        },
        upsert=True,
    )


async def _get_or_set_external_cache(db, namespace: str, payload: Dict[str, Any], fetch_fn, ttl_seconds: int = _EXTERNAL_CACHE_TTL_SECONDS) -> Any:
    key = _external_cache_key(namespace, payload)
    cached = await _get_external_cache(db, key)
    if cached is not None:
        return cached

    data = fetch_fn()
    await _set_external_cache(db, key, data, ttl_seconds=ttl_seconds)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Prediction CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def create_prediction(request: PredictionRequest, force_refresh: bool = False) -> PredictionOutput:
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
    if existing and not force_refresh:
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
                logger.warning(
                    "Could not parse prediction timestamp for match_id=%s raw_timestamp=%r: %s",
                    match_id,
                    ts,
                    e,
                )
                is_fresh = False

        if is_fresh:
            existing.pop("_id", None)
            logger.info(f"Returning cached prediction for {match_id}")
            return PredictionOutput(**existing)

    logger.info(f"Generating: {request.home_team} vs {request.away_team} [{sport}]")
    await log_system_event("prediction_pipeline", f"Started pipeline for {match_id}", "INFO")

    logger.info("Prediction pipeline [%s]: fetching home team stats", match_id)
    home_stats = await _get_or_set_external_cache(
        db,
        "team_stats",
        {"team": request.home_team.lower(), "sport": sport, "league": (request.league or "").lower()},
        lambda: fetch_team_stats(request.home_team, sport, request.league),
    )
    logger.info("Prediction pipeline [%s]: fetching away team stats", match_id)
    away_stats = await _get_or_set_external_cache(
        db,
        "team_stats",
        {"team": request.away_team.lower(), "sport": sport, "league": (request.league or "").lower()},
        lambda: fetch_team_stats(request.away_team, sport, request.league),
    )

    logger.info("Prediction pipeline [%s]: fetching h2h + venue", match_id)
    h2h_venue = await _get_or_set_external_cache(
        db,
        "h2h_venue",
        {"home": request.home_team.lower(), "away": request.away_team.lower(), "sport": sport},
        lambda: _fetch_combined_h2h_venue(request.home_team, request.away_team, sport),
        ttl_seconds=24 * 60 * 60,
    )
    h2h = h2h_venue["h2h"]
    venue = h2h_venue["venue"]

    logger.info("Prediction pipeline [%s]: fetching odds", match_id)
    odds = await _get_or_set_external_cache(
        db,
        "odds",
        {"home": request.home_team.lower(), "away": request.away_team.lower(), "sport": sport},
        lambda: fetch_betting_odds(request.home_team, request.away_team, sport),
        ttl_seconds=20 * 60,
    )

    # Real expected-goals (Understat, free) — best-effort; silently falls back
    # to the heuristic xG when the league/fixture isn't covered by the source.
    # Cached like every other external fetch so repeated lookups are free.
    scraped_xg: Optional[Dict[str, Any]] = None
    if settings.ENABLE_XG_SCRAPING:
        try:
            from app.services.scraping_service import lookup_understat_xg
            xg_lookup = await _get_or_set_external_cache(
                db,
                "understat_xg",
                {
                    "home": request.home_team.lower(),
                    "away": request.away_team.lower(),
                    "league": (request.league or "").lower(),
                },
                lambda: lookup_understat_xg(request.home_team, request.away_team, request.league or ""),
                ttl_seconds=6 * 60 * 60,
            )
            if isinstance(xg_lookup, dict) and xg_lookup.get("available"):
                scraped_xg = xg_lookup
                logger.info(
                    "Prediction pipeline [%s]: real xG from Understat "
                    "(home=%.2f away=%.2f)",
                    match_id,
                    float(xg_lookup.get("home_xg") or 0.0),
                    float(xg_lookup.get("away_xg") or 0.0),
                )
        except Exception as exc:
            logger.debug("Prediction pipeline [%s]: Understat xG lookup failed: %s", match_id, exc)

    logger.info("Prediction pipeline [%s]: building features + predicting", match_id)
    features = prediction_engine.features_from_data(
        home_stats, away_stats, h2h, odds, venue, sport=sport, scraped_xg=scraped_xg,
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

    # ── Source provenance (Sprint 7.19) ─────────────────────────────────────
    # Record which data sources actually returned usable data for this match so
    # a degraded/fallback prediction can be traced back to a missing source.
    h2h_total = int(h2h.get("total_games") or 0) if isinstance(h2h, dict) else 0
    odds_live = bool(
        isinstance(odds, dict)
        and odds.get("implied_home_prob") is not None
        and odds.get("implied_away_prob") is not None
    )
    venue_signal = bool(
        isinstance(venue, dict) and venue.get("home_advantage_signal") is not None
    )

    # OpenLigaDB (free scrape source) availability — real scored-goal/form stats
    # for German-league fixtures; missing league -> no enrichment.
    olg_home = bool(isinstance(home_stats, dict) and home_stats.get("openligadb_available"))
    olg_away = bool(isinstance(away_stats, dict) and away_stats.get("openligadb_available"))

    data_sources = ["ESPN Public API (team stats)"]
    unavailable_sources = []
    if olg_home or olg_away:
        data_sources.append("OpenLigaDB (free scraped goals/form stats)")
    if scraped_xg:
        data_sources.append("Understat xG (real expected goals)")
    else:
        unavailable_sources.append("Understat xG (heuristic xG used)")
    if h2h_total > 0:
        data_sources.append("Web search H2H + venue (Serper/DuckDuckGo)")
    else:
        unavailable_sources.append("Web search H2H + venue (priors used)")
    if odds_live:
        data_sources.append("The Odds API (live odds)")
    else:
        unavailable_sources.append("The Odds API (priors used)")

    feature_provenance = {
        "sources": data_sources,
        "unavailable_sources": unavailable_sources,
        "h2h_games_found": h2h_total,
        "odds_live": odds_live,
        "venue_signal_present": venue_signal,
        "openligadb_home": olg_home,
        "openligadb_away": olg_away,
        "recorded_at": datetime.now(WAT).isoformat(),
    }

    # ── Odds snapshot (Sprint 7.18) ──────────────────────────────────────────
    # Record the odds this prediction actually saw at generation time so any
    # ROI/value claim can later be verified against the prediction doc alone
    # (no join to feature_snapshots required). Best-effort; when the Odds API
    # was unavailable the snapshot records that fact instead of omitting it.
    odds_snapshot = {
        "captured_at": datetime.now(WAT).isoformat(),
        "source": "the-odds-api" if odds_live else "unavailable",
    }
    if isinstance(odds, dict):
        odds_snapshot["implied_home_prob"] = odds.get("implied_home_prob")
        odds_snapshot["implied_away_prob"] = odds.get("implied_away_prob")
        odds_snapshot["market_confidence"] = odds.get("market_confidence", 0.0)

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
        data_sources=data_sources,
        feature_provenance=feature_provenance,
        extended_markets=markets,
        odds_snapshot=odds_snapshot,
    )

    doc = output.model_dump()
    doc["timestamp"]  = doc["timestamp"].isoformat()
    doc["deleted_at"] = None
    doc["match_date_indexed"] = match_date
    await db.predictions.replace_one({"match_id": match_id}, doc, upsert=True)
    logger.info("Prediction pipeline [%s]: prediction persisted", match_id)

    snapshot = {
        "match_id": match_id, "sport": sport,
        "timestamp": now_wat().isoformat(),
        "match_date": match_date,
        "home_raw": home_stats, "away_raw": away_stats,
        "h2h_raw": h2h, "odds_raw": odds, "features": features,
    }
    await db.feature_snapshots.replace_one({"match_id": match_id}, snapshot, upsert=True)
    logger.info("Prediction pipeline [%s]: feature snapshot persisted", match_id)

    try:
        grouping_summary = await _assign_prediction_groups_for_date(db, match_date)
        logger.info("Prediction pipeline [%s]: regrouped %s games into %s groups for %s",
                    match_id, grouping_summary.get("games"), grouping_summary.get("groups"), match_date)
    except Exception as e:
        logger.warning(f"Could not assign prediction groups for {match_date}: {e}")

    await log_system_event("prediction_created", f"Prediction generated for {match_id}", "INFO")
    await log_system_event("prediction_pipeline", f"Completed pipeline for {match_id}", "INFO")
    return output


async def repredict_prediction(match_id: str) -> Optional[PredictionOutput]:
    db = get_db()
    existing = await db.predictions.find_one({"match_id": match_id, "deleted_at": None}, {"_id": 0})
    if not existing:
        return None

    from app.schemas.prediction_schema import SportType
    try:
        sport_enum = SportType(str(existing.get("sport", "soccer")).lower())
    except Exception:
        sport_enum = SportType.SOCCER

    request = PredictionRequest(
        home_team=existing.get("home_team", ""),
        away_team=existing.get("away_team", ""),
        sport=sport_enum,
        league=existing.get("league"),
        match_date=existing.get("match_date"),
        skip_validation=True,
    )
    return await create_prediction(request, force_refresh=True)


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
