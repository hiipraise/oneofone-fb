# app/scheduler/daily_scheduler.py
"""
Daily sports prediction scheduler.

Runs at the configured WAT hour, discovers today's fixtures via the Odds API,
generates predictions for all supported sports, and writes structured logs to
the `system_logs` MongoDB collection so the /api/scheduler/logs endpoint can
surface them.

Log document shape (required by scheduler route):
  {
    "source":    "daily_scheduler",
    "level":     "INFO" | "WARNING" | "ERROR",
    "message":   str,
    "timestamp": datetime (WAT),
    "sport":     str | None,   # optional context
    "count":     int | None,   # optional prediction count
  }
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from app.utils.timezone import WAT
from typing import List, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler

from app.config.database import get_db
from app.config.settings import settings
import time
from app.services.web_search_service import get_serpapi_usage
from app.services.quota_service import record_serpapi_calls
from app.services.result_resolver import resolve_results
from app.services.match_validation_service import fetch_espn_today_fixtures
from app.services.sport_key_catalog import SPORT_KEYS

logger = logging.getLogger(__name__)

# ── Supported sports ──────────────────────────────────────────────────────────
# Product scope: football/soccer only.
_SUPPORTED_SPORTS: List[str] = ["soccer"]

# ── APScheduler instance (exported so scheduler_route can inspect it) ─────────
scheduler = BackgroundScheduler(timezone="Africa/Lagos")


# ── MongoDB log writer ────────────────────────────────────────────────────────

async def _log_to_db(
    level: str,
    message: str,
    sport: str | None = None,
    count: int | None = None,
    extra: Dict[str, Any] | None = None,
) -> None:
    """Write a structured log entry to db.system_logs."""
    try:
        db = get_db()
        doc: Dict[str, Any] = {
            "source":    "daily_scheduler",
            "level":     level.upper(),
            "message":   message,
            "timestamp": datetime.now(WAT),
        }
        if sport is not None:
            doc["sport"] = sport
        if count is not None:
            doc["count"] = count
        if extra:
            doc.update(extra)
        await db.system_logs.insert_one(doc)
    except Exception as e:
        logger.warning(f"[scheduler] Failed to write log to DB: {e}")


def _log_sync(level: str, message: str, **kwargs) -> None:
    """Sync wrapper that logs with an isolated loop and DB client."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.config.database import override_db_context

    async def _run() -> None:
        sched_client = AsyncIOMotorClient(settings.MONGODB_URI)
        sched_db = sched_client[settings.MONGODB_DB]
        try:
            with override_db_context(sched_db, sched_client):
                await _log_to_db(level, message, **kwargs)
        finally:
            try:
                sched_client.close()
            except Exception:
                pass

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run())
    except Exception as e:
        logger.warning(f"[scheduler] _log_sync error: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ── Odds API fixture discovery ────────────────────────────────────────────────

async def _fetch_today_fixtures(sport: str) -> List[Dict]:
    """Fetch upcoming fixtures for today from the Odds API, then fall back to ESPN."""
    import requests

    now_wat_dt = datetime.now(WAT)
    today = now_wat_dt.strftime("%Y-%m-%d")
    allowed_dates = {today}

    sport = sport.lower()
    if sport not in SPORT_KEYS:
        logger.warning(f"[scheduler] Unsupported sport for fixture fetch: {sport}")
        return []

    now_utc = datetime.now(timezone.utc)
    sport_keys = SPORT_KEYS[sport]
    should_fallback_to_espn = not bool(settings.ODDS_API_KEY)

    if settings.ODDS_API_KEY:
        for attempt in range(3):
            try:
                fixtures = []
                seen = set()
                auth_failed = False
                for sport_key in sport_keys:
                    key_fixture_count = 0
                    resp = requests.get(
                        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
                        params={
                            "apiKey": settings.ODDS_API_KEY,
                            "regions": "us,uk",
                            "markets": "h2h",
                            "oddsFormat": "decimal",
                        },
                        timeout=15,
                    )

                    if resp.status_code == 429:
                        logger.info(
                            "[scheduler] Odds API key result",
                            extra={"sport_key": sport_key, "status_code": resp.status_code, "fixture_count": key_fixture_count},
                        )
                        wait = [5.0, 15.0][min(attempt, 1)]
                        logger.warning(
                            f"[scheduler] Odds API 429 [{sport_key}] — "
                            f"attempt {attempt + 1}/3, retrying in {wait}s"
                        )
                        time.sleep(wait)
                        fixtures = []
                        break

                    if resp.status_code in (401, 403):
                        logger.info(
                            "[scheduler] Odds API key result",
                            extra={"sport_key": sport_key, "status_code": resp.status_code, "fixture_count": key_fixture_count},
                        )
                        logger.warning(f"[scheduler] Odds API {resp.status_code} for {sport_key}; falling back to ESPN")
                        auth_failed = True
                        should_fallback_to_espn = True
                        fixtures = []
                        break

                    if resp.status_code != 200:
                        logger.info(
                            "[scheduler] Odds API key result",
                            extra={"sport_key": sport_key, "status_code": resp.status_code, "fixture_count": key_fixture_count},
                        )
                        logger.warning(f"[scheduler] Odds API {resp.status_code} for {sport_key}")
                        continue

                    for game in resp.json():
                        commence_time = game.get("commence_time", "")
                        match_date = commence_time[:10]
                        if match_date not in allowed_dates:
                            continue
                        try:
                            kickoff_utc = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
                            if match_date == today and kickoff_utc <= now_utc:
                                continue
                        except Exception:
                            # Keep fixture if timestamp is malformed rather than dropping potentially valid games.
                            pass
                        game_key = (
                            game.get("home_team", "").lower(),
                            game.get("away_team", "").lower(),
                            match_date,
                        )
                        if game_key in seen:
                            continue
                        seen.add(game_key)
                        fixtures.append({
                            "fixture_id": game.get("id", ""),
                            "home_team": game.get("home_team", ""),
                            "away_team": game.get("away_team", ""),
                            "sport": sport,
                            "match_date": match_date,
                            "league": game.get("sport_title", ""),
                            "source": "odds_api",
                        })
                        key_fixture_count += 1

                    logger.info(
                        "[scheduler] Odds API key result",
                        extra={
                            "sport_key": sport_key,
                            "status_code": resp.status_code,
                            "fixture_count": key_fixture_count,
                        },
                    )

                if auth_failed:
                    break
                if fixtures:
                    return fixtures
                if attempt < 2:
                    continue
            except requests.exceptions.Timeout:
                wait = [5.0, 15.0][min(attempt, 1)]
                logger.warning(
                    f"[scheduler] Odds API timeout [{sport}] — "
                    f"attempt {attempt + 1}/3, retrying in {wait}s"
                )
                time.sleep(wait)
            except Exception as e:
                logger.error(f"[scheduler] Odds API error [{sport}]: {e}")
                should_fallback_to_espn = True
                break
    else:
        logger.warning(f"[scheduler] ODDS_API_KEY not set — using ESPN fallback for {sport}")

    if should_fallback_to_espn:
        fixtures = fetch_espn_today_fixtures(sport)
        if fixtures:
            await _log_to_db(
                "INFO",
                f"Using ESPN fixtures fallback for {sport}: {len(fixtures)} found",
                sport=sport,
                count=len(fixtures),
                extra={"fixture_source": "espn"},
            )
            return fixtures

    logger.error(f"[scheduler] Fixture discovery failed [{sport}] — no Odds API or ESPN fixtures")
    return []


# ── Core prediction runner ────────────────────────────────────────────────────

async def _run_predictions_async() -> None:
    """Main async body — runs inside a fresh event loop from run_daily_predictions()."""
    from app.services.prediction_service import generate_prediction

    run_start = datetime.now(WAT)
    await _log_to_db("INFO", f"Daily scheduler started — {run_start.strftime('%Y-%m-%d %H:%M WAT')}")

    serper_before   = get_serpapi_usage()["used"]
    total_generated = 0
    total_errors    = 0

    for sport in _SUPPORTED_SPORTS:
        await _log_to_db("INFO", f"Discovering fixtures for {sport}…", sport=sport)

        try:
            fixtures = await _fetch_today_fixtures(sport)

            if not fixtures:
                await _log_to_db(
                    "WARNING",
                    f"No {sport} fixtures found for today — skipping",
                    sport=sport, count=0,
                )
                continue

            await _log_to_db(
                "INFO",
                f"Found {len(fixtures)} {sport} fixtures — generating predictions",
                sport=sport, count=len(fixtures),
            )

            sport_generated = 0
            sport_errors    = 0

            db = get_db()
            for fixture in fixtures:
                try:
                    # Idempotency: scheduled and manual runs can overlap on Render wakeups;
                    # keep the first non-deleted prediction for a match/date/sport and skip duplicates.
                    existing = await db.predictions.find_one({
                        "match_id": fixture.get("match_id"),
                        "match_date": fixture["match_date"],
                        "sport": sport,
                        "deleted_at": None,
                    }) if db is not None and fixture.get("match_id") else None
                    if existing:
                        await _log_to_db("INFO", f"Skipping existing prediction: {fixture['home_team']} vs {fixture['away_team']}", sport=sport)
                        continue
                    await generate_prediction(
                        home_team  = fixture["home_team"],
                        away_team  = fixture["away_team"],
                        sport      = sport,
                        match_date = fixture["match_date"],
                        league     = fixture.get("league"),
                    )
                    sport_generated += 1
                    total_generated += 1
                except Exception as e:
                    sport_errors  += 1
                    total_errors  += 1
                    logger.error(
                        f"[scheduler] Prediction failed "
                        f"[{fixture['home_team']} vs {fixture['away_team']}]: {e}"
                    )
                    await _log_to_db(
                        "ERROR",
                        f"Prediction failed: {fixture['home_team']} vs {fixture['away_team']} — {e}",
                        sport=sport,
                    )

            await _log_to_db(
                "INFO",
                f"Completed {sport}: {sport_generated} generated, {sport_errors} errors",
                sport=sport, count=sport_generated,
            )

        except Exception as e:
            total_errors += 1
            logger.error(f"[scheduler] Sport loop error [{sport}]: {e}")
            await _log_to_db("ERROR", f"{sport} processing failed: {e}", sport=sport)

    # ── Persist Serper quota delta ────────────────────────────────────────────
    serper_calls_made = get_serpapi_usage()["used"] - serper_before
    if serper_calls_made > 0:
        try:
            await record_serpapi_calls(serper_calls_made)
            logger.info(f"[scheduler] Recorded {serper_calls_made} Serper calls to quota store")
        except Exception as e:
            logger.warning(f"[scheduler] Quota recording failed: {e}")

    elapsed = (datetime.now(WAT) - run_start).seconds
    await _log_to_db(
        "INFO",
        f"Daily scheduler complete — {total_generated} predictions generated, "
        f"{total_errors} errors, {elapsed}s elapsed",
        count=total_generated,
    )
    logger.info(
        f"[scheduler] Run complete: {total_generated} generated, "
        f"{total_errors} errors in {elapsed}s"
    )


def run_daily_predictions() -> None:
    logger.info("[scheduler] run_daily_predictions() called")

    async def _run():
        from motor.motor_asyncio import AsyncIOMotorClient
        from app.config.database import override_db_context

        _sched_client = AsyncIOMotorClient(settings.MONGODB_URI)
        _sched_db = _sched_client[settings.MONGODB_DB]

        try:
            with override_db_context(_sched_db, _sched_client):
                await _run_predictions_async()
        finally:
            try:
                _sched_client.close()
            except Exception:
                pass
            logger.info("[scheduler] Isolated scheduler DB client closed")

    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run())
    except Exception as e:
        logger.error(f"[scheduler] Fatal error in run_daily_predictions: {e}")
        _log_sync("ERROR", f"Fatal scheduler error: {e}")
    finally:
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass


# ── Result resolution runner ──────────────────────────────────────────────────

async def _run_resolution_async() -> None:
    """Fetch completed scores and auto-submit actual results."""
    run_start = datetime.now(WAT)
    await _log_to_db("INFO", f"Result resolver started — {run_start.strftime('%Y-%m-%d %H:%M WAT')}")

    try:
        summary = await resolve_results()
        await _log_to_db(
            "INFO",
            f"Result resolver complete — {summary['resolved']} resolved, "
            f"{summary['skipped']} skipped, {summary['errors']} errors",
            count=summary["resolved"],
        )
        logger.info(f"[resolver] Complete: {summary}")
    except Exception as e:
        logger.error(f"[resolver] Fatal error: {e}")
        await _log_to_db("ERROR", f"Result resolver failed: {e}")


def run_result_resolution() -> None:
    """
    Sync entry point for APScheduler — uses the same ContextVar isolation
    as run_daily_predictions so FastAPI's Motor client is never touched.
    """
    logger.info("[resolver] run_result_resolution() called")

    async def _run():
        from motor.motor_asyncio import AsyncIOMotorClient
        from app.config.database import override_db_context

        _sched_client = AsyncIOMotorClient(settings.MONGODB_URI)
        _sched_db = _sched_client[settings.MONGODB_DB]

        try:
            with override_db_context(_sched_db, _sched_client):
                await _run_resolution_async()
        finally:
            try:
                _sched_client.close()
            except Exception:
                pass
            logger.info("[resolver] Isolated resolver DB client closed")

    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run())
    except Exception as e:
        logger.error(f"[resolver] Fatal error in run_result_resolution: {e}")
        _log_sync("ERROR", f"Fatal resolver error: {e}")
    finally:
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass


# ── APScheduler setup ─────────────────────────────────────────────────────────

def start_scheduler() -> None:
    if scheduler.running:
        logger.info("[scheduler] Already running — skipping start")
        return

    # Job 1 — daily predictions (morning)
    scheduler.add_job(
        run_daily_predictions,
        trigger  = "cron",
        id       = "daily_predictions",
        hour     = settings.DAILY_PREDICTION_HOUR,
        minute   = settings.DAILY_PREDICTION_MINUTE,
        replace_existing   = True,
        misfire_grace_time = 3600,
    )

    # Job 2 — result auto-resolution (evening, after games finish)
    scheduler.add_job(
        run_result_resolution,
        trigger  = "cron",
        id       = "result_resolution",
        hour     = settings.RESULT_RESOLUTION_HOUR,
        minute   = settings.RESULT_RESOLUTION_MINUTE,
        replace_existing   = True,
        misfire_grace_time = 3600,
    )

    scheduler.start()
    logger.info(
        f"[scheduler] Started — predictions at "
        f"{settings.DAILY_PREDICTION_HOUR:02d}:{settings.DAILY_PREDICTION_MINUTE:02d} WAT, "
        f"resolution at "
        f"{settings.RESULT_RESOLUTION_HOUR:02d}:{settings.RESULT_RESOLUTION_MINUTE:02d} WAT"
    )


def stop_scheduler() -> None:
    """Graceful shutdown — call from FastAPI shutdown event."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[scheduler] Stopped")
