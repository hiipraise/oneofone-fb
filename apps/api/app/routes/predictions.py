# app/routes/predictions.py
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from app.schemas.prediction_schema import PredictionRequest, PredictionOutput, ActualResultInput
from app.services.prediction_service import (
    create_prediction, get_predictions, get_prediction_by_id,
    save_actual_result, trigger_learning_update, soft_delete_prediction, restore_prediction,
)
from app.services.match_validation_service import (
    fetch_available_leagues,
    is_fixture_completed,
    search_fixtures,
)
from app.config.api_contract import PREDICTIONS_LIMIT_DEFAULT, PREDICTIONS_LIMIT_MAX

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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_predictions(
    sport: Optional[str] = Query(None),
    limit: int = Query(PREDICTIONS_LIMIT_DEFAULT, ge=1, le=PREDICTIONS_LIMIT_MAX),
    include_deleted: bool = Query(False),
):
    return await get_predictions(sport=sport, limit=limit, include_deleted=include_deleted)


@router.get("/validate")
async def validate_match(
    home_team: str = Query(...),
    away_team: str = Query(...),
    sport: str = Query("soccer"),
    date: Optional[str] = Query(None),
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
async def get_leagues(sport: str = Query("soccer")):
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/results/submit")
async def submit_result(payload: ActualResultInput):
    try:
        await save_actual_result(
            payload.match_id, payload.home_score, payload.away_score,
            payload.actual_outcome, payload.match_date,
        )
        return {"status": "recorded", "match_id": payload.match_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/trigger")
async def trigger_learning():
    try:
        await trigger_learning_update()
        return {"status": "learning_triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
