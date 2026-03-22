# app/services/quota_service.py
import logging
from datetime import datetime, timezone
from app.utils.timezone import WAT
from app.config.settings import settings

logger = logging.getLogger(__name__)


async def record_serpapi_calls(n: int = 1) -> None:
    try:
        from app.config.database import get_db
        db = get_db()

        month_key = datetime.now(WAT).strftime("%Y-%m")
        doc_id = f"quota:{month_key}"

        await db.serpapi_quota.update_one(
            {"_id": doc_id},
            {
                "$inc": {"used": n},
                "$setOnInsert": {"month": month_key, "budget": settings.SERPAPI_MONTHLY_BUDGET},
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"quota tracking failed: {e}")


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
        from app.services.web_search_service import get_serpapi_usage
        live = get_serpapi_usage()
    except Exception as e:
        logger.warning(f"quota live read failed: {e}")

    try:
        from app.config.database import get_db
        db = get_db()

        doc = await db.serpapi_quota.find_one({"_id": f"quota:{month_key}"})
        if doc:
            used = max(int(doc.get("used", 0)), int(live.get("used", 0)))
            budget = max(int(doc.get("budget", settings.SERPAPI_MONTHLY_BUDGET)), int(live.get("budget", settings.SERPAPI_MONTHLY_BUDGET)))
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
