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
        results.append(doc)

    if not results:
        return results

    # Batch-enrich with prediction data to avoid N+1 database queries.
    match_ids = [row.get("match_id") for row in results if row.get("match_id")]
    prediction_map = {}

    if match_ids:
        async for pred in db.predictions.find({"match_id": {"$in": match_ids}}):
            pred.pop("_id", None)
            match_id = pred.get("match_id")
            if match_id:
                prediction_map[match_id] = pred

    for row in results:
        pred = prediction_map.get(row.get("match_id"))
        if not pred:
            continue

        row["home_win_probability"] = pred.get("home_win_probability")
        row["away_win_probability"] = pred.get("away_win_probability")
        row["draw_probability"] = pred.get("draw_probability")
        row["predicted_outcome"] = pred.get("predicted_outcome") or row.get("predicted_outcome")
        row["confidence_score"] = pred.get("confidence_score") or row.get("confidence_score")
        row["home_team"] = pred.get("home_team") or row.get("home_team")
        row["away_team"] = pred.get("away_team") or row.get("away_team")
        row["sport"] = pred.get("sport") or row.get("sport")
        row["league"] = pred.get("league") or row.get("league")

    return results
