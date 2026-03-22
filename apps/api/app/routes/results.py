# app/routes/results.py
import logging
from typing import Optional
from fastapi import APIRouter, Query
from app.config.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def list_results(limit: int = Query(50, ge=1, le=200)):
    """
    Return submitted actual results, joined with the original prediction
    so the frontend can render calibration charts and resolve match IDs.
    """
    db = get_db()
    results = []

    async for doc in db.actual_results.find({}).sort("recorded_at", -1).limit(limit):
        doc.pop("_id", None)

        # Enrich with original prediction data for calibration charts
        pred = await db.predictions.find_one({"match_id": doc.get("match_id")})
        if pred:
            pred.pop("_id", None)
            doc["home_win_probability"] = pred.get("home_win_probability")
            doc["away_win_probability"] = pred.get("away_win_probability")
            doc["draw_probability"] = pred.get("draw_probability")
            doc["predicted_outcome"] = pred.get("predicted_outcome") or doc.get("predicted_outcome")
            doc["confidence_score"] = pred.get("confidence_score") or doc.get("confidence_score")
            doc["home_team"] = pred.get("home_team") or doc.get("home_team")
            doc["away_team"] = pred.get("away_team") or doc.get("away_team")
            doc["sport"] = pred.get("sport") or doc.get("sport")
            doc["league"] = pred.get("league") or doc.get("league")

        results.append(doc)

    return results