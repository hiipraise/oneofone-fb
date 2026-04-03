# app/services/quota_service.py
import logging
from datetime import datetime, timezone
from app.utils.timezone import WAT
from app.config.settings import settings

logger = logging.getLogger(__name__)


def _serper_quota_collection(db):
    """
    Preferred collection name is `serper_quota`.
    We mirror writes to `serpapi_quota` for one release window.
    """
    return db.serper_quota


async def record_serper_calls(n: int = 1) -> None:
    try:
        from app.config.database import get_db
        db = get_db()

        month_key = datetime.now(WAT).strftime("%Y-%m")
        doc_id = f"quota:{month_key}"

        payload = {
            "$inc": {"used": n},
            "$setOnInsert": {"month": month_key, "budget": settings.SERPAPI_MONTHLY_BUDGET},
        }

        await _serper_quota_collection(db).update_one({"_id": doc_id}, payload, upsert=True)
        await db.serpapi_quota.update_one({"_id": doc_id}, payload, upsert=True)
    except Exception as e:
        logger.warning(f"quota tracking failed: {e}")


# Backward-compatible wrapper (one release window)
async def record_serpapi_calls(n: int = 1) -> None:
    await record_serper_calls(n=n)


async def get_persisted_quota() -> dict:
    month_key = datetime.now(WAT).strftime("%Y-%m")
    fallback = {
        "month": month_key,
        "used": 0,
        "budget": settings.SERPAPI_MONTHLY_BUDGET,
        "remaining": settings.SERPAPI_MONTHLY_BUDGET,
    }

    live = fallback
    try:
        from app.services.web_search_service import get_serper_usage
        live = get_serper_usage()
    except Exception as e:
        logger.warning(f"quota live read failed: {e}")

    try:
        from app.config.database import get_db
        db = get_db()

        primary = await _serper_quota_collection(db).find_one({"_id": f"quota:{month_key}"})
        legacy = await db.serpapi_quota.find_one({"_id": f"quota:{month_key}"})

        docs = [d for d in [primary, legacy] if d]
        if docs:
            used = max(int(d.get("used", 0)) for d in docs)
            budget = max(
                int(d.get("budget", settings.SERPAPI_MONTHLY_BUDGET)) for d in docs
            )
            used = max(used, int(live.get("used", 0)))
            budget = max(budget, int(live.get("budget", settings.SERPAPI_MONTHLY_BUDGET)))
            return {
                "month": month_key,
                "used": used,
                "budget": budget,
                "remaining": max(budget - used, 0),
            }
    except Exception as e:
        logger.warning(f"quota read failed: {e}")

    return {
        "month": live.get("month", month_key),
        "used": int(live.get("used", 0)),
        "budget": int(live.get("budget", settings.SERPAPI_MONTHLY_BUDGET)),
        "remaining": int(live.get("remaining", settings.SERPAPI_MONTHLY_BUDGET)),
    }
