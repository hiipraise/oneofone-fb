# app/routes/predictions.py
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from app.schemas.prediction_schema import PredictionRequest, PredictionOutput, ActualResultInput
from app.services.prediction_service import (
    create_prediction, get_predictions, get_prediction_by_id,
    save_actual_result, trigger_learning_update, soft_delete_prediction, restore_prediction,
    repredict_prediction,
)
from app.services.result_resolver import resolve_prediction_by_match_id
from app.services.match_validation_service import (
    fetch_available_leagues,
    is_fixture_completed,
    search_fixtures,
)
from app.config.api_contract import (
    PREDICTIONS_LIMIT_DEFAULT,
    PREDICTIONS_LIMIT_MAX,
    TEAM_NAME_MIN_LENGTH,
    TEAM_NAME_MAX_LENGTH,
)
from app.config.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=PredictionOutput)
async def generate_prediction(request: PredictionRequest):
    try:
        return await create_prediction(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail="Prediction generation failed")


@router.get("/")
async def list_predictions(
    sport: Optional[str] = Query(None, pattern="^soccer$"),
    limit: int = Query(PREDICTIONS_LIMIT_DEFAULT, ge=1, le=PREDICTIONS_LIMIT_MAX),
    include_deleted: bool = Query(False),
):
    return await get_predictions(sport=sport, limit=limit, include_deleted=include_deleted)


@router.get("/groups")
async def list_prediction_groups(
    match_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD; defaults to today in WAT"),
):
    from datetime import datetime
    from app.utils.timezone import WAT

    db = get_db()
    target_date = match_date or datetime.now(WAT).strftime("%Y-%m-%d")
    doc = await db.prediction_groups.find_one({"match_date": target_date}, {"_id": 0})

    if not doc:
        return {"match_date": target_date, "groups": [], "total_games": 0}
    return doc


@router.get("/validate")
async def validate_match(
    home_team: str = Query(..., min_length=TEAM_NAME_MIN_LENGTH, max_length=TEAM_NAME_MAX_LENGTH),
    away_team: str = Query(..., min_length=TEAM_NAME_MIN_LENGTH, max_length=TEAM_NAME_MAX_LENGTH),
    sport: str = Query("soccer", pattern="^soccer$"),
    date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    status = is_fixture_completed(home_team, away_team, sport, date)
    if status and status.get("completed"):
        return {
            "found": True,
            "completed": True,
            "fixture": status,
            "message": "Match already finished full time",
        }

    fixture = search_fixtures(home_team, away_team, sport, date)
    if fixture:
        return {"found": True, "completed": False, "fixture": fixture}
    return {"found": False, "message": "Match not found in upcoming fixtures"}


@router.get("/leagues")
async def get_leagues(sport: str = Query("soccer", pattern="^soccer$")):
    leagues = fetch_available_leagues(sport)
    return {"sport": sport, "leagues": leagues, "count": len(leagues)}


@router.get("/{match_id}")
async def get_prediction(match_id: str):
    pred = await get_prediction_by_id(match_id)
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return pred


@router.delete("/{match_id}")
async def delete_prediction(match_id: str):
    """Soft-delete a prediction (sets deleted_at, hides from normal queries)."""
    try:
        result = await soft_delete_prediction(match_id)
        if not result:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return {"status": "deleted", "match_id": match_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Delete prediction failed for %s", match_id)
        raise HTTPException(status_code=500, detail="Delete failed")


@router.post("/{match_id}/restore")
async def undelete_prediction(match_id: str):
    """Restore a soft-deleted prediction."""
    try:
        result = await restore_prediction(match_id)
        if not result:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return {"status": "restored", "match_id": match_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Restore prediction failed for %s", match_id)
        raise HTTPException(status_code=500, detail="Restore failed")


@router.post("/{match_id}/repredict", response_model=PredictionOutput)
async def repredict(match_id: str):
    try:
        result = await repredict_prediction(match_id)
        if not result:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Repredict error for %s: %s", match_id, e)
        raise HTTPException(status_code=500, detail="Reprediction failed")


@router.post("/results/submit")
async def submit_result(payload: ActualResultInput):
    try:
        await save_actual_result(
            payload.match_id, payload.home_score, payload.away_score,
            payload.actual_outcome, payload.match_date,
            corner_stats={
                "home_corners": payload.home_corners,
                "away_corners": payload.away_corners,
                "total_corners": payload.total_corners,
                "source": "manual",
            } if payload.total_corners is not None else None,
        )
        return {"status": "recorded", "match_id": payload.match_id}
    except Exception:
        logger.exception("Submit result failed for %s", payload.match_id)
        raise HTTPException(status_code=500, detail="Result submission failed")


@router.post("/learn/trigger")
async def trigger_learning():
    try:
        await trigger_learning_update()
        return {"status": "learning_triggered"}
    except Exception:
        logger.exception("Learning trigger failed")
        raise HTTPException(status_code=500, detail="Learning trigger failed")


@router.post("/{match_id}/resolve")
async def resolve_prediction(match_id: str):
    try:
        result = await resolve_prediction_by_match_id(match_id)
        if not result.get("resolved"):
            reason = result.get("reason", "resolution_failed")
            if reason == "prediction_not_found":
                raise HTTPException(status_code=404, detail="Prediction not found")
            if reason == "already_resolved":
                return {"status": "already_resolved", "match_id": match_id}
            if reason == "game_not_found":
                raise HTTPException(status_code=404, detail="Completed game not found yet")
            if reason == "unsupported_sport":
                raise HTTPException(status_code=400, detail="Unsupported sport for resolution")
            raise HTTPException(status_code=400, detail="Could not resolve match")

        return {"status": "resolved", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resolve prediction error for %s: %s", match_id, e)
        raise HTTPException(status_code=500, detail="Resolution failed")
