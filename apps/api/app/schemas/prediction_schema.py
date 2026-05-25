# app/schemas/prediction_schema.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from app.config.api_contract import (
    TEAM_NAME_MIN_LENGTH,
    TEAM_NAME_MAX_LENGTH,
    CUSTOM_PROMPT_MAX_LENGTH,
    CHAT_MESSAGE_MIN_LENGTH,
    CHAT_MESSAGE_MAX_LENGTH,
)


class SportType(str, Enum):
    SOCCER = "soccer"


SPORT_DISPLAY = {
    SportType.SOCCER: "Football / Soccer",
}


class PredictionRequest(BaseModel):
    home_team: str = Field(..., min_length=TEAM_NAME_MIN_LENGTH, max_length=TEAM_NAME_MAX_LENGTH)
    away_team: str = Field(..., min_length=TEAM_NAME_MIN_LENGTH, max_length=TEAM_NAME_MAX_LENGTH)
    sport: SportType
    match_date: Optional[str] = None
    league: Optional[str] = None
    custom_prompt: Optional[str] = Field(None, max_length=CUSTOM_PROMPT_MAX_LENGTH)
    skip_validation: bool = False

    @field_validator("home_team", "away_team")
    @classmethod
    def sanitize_team_name(cls, v: str) -> str:
        return v.strip().replace("<", "").replace(">", "").replace("'", "")


class PredictionOutput(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    sport: str
    league: Optional[str] = None
    match_date: Optional[str] = None

    home_win_probability: float = Field(..., ge=0.0, le=1.0)
    draw_probability: Optional[float] = Field(None, ge=0.0, le=1.0)
    away_win_probability: float = Field(..., ge=0.0, le=1.0)

    confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_interval_low: float = Field(..., ge=0.0, le=1.0)
    confidence_interval_high: float = Field(..., ge=0.0, le=1.0)

    predicted_outcome: str
    model_version: str
    timestamp: datetime

    features_used: Dict[str, Any]
    data_sources: List[str]
    extended_markets: Optional[Dict[str, Any]] = None
    fixture_validation: Optional[Dict[str, Any]] = None


class ActualResultInput(BaseModel):
    match_id: str
    home_score: int = Field(..., ge=0)
    away_score: int = Field(..., ge=0)
    actual_outcome: str
    match_date: str
    home_corners: Optional[int] = Field(None, ge=0)
    away_corners: Optional[int] = Field(None, ge=0)
    total_corners: Optional[int] = Field(None, ge=0)


class ModelMetrics(BaseModel):
    model_version: str
    date: datetime
    brier_score: float
    log_loss: float
    calibration_error: float
    accuracy: float
    total_predictions: int
    sport_breakdown: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=CHAT_MESSAGE_MIN_LENGTH, max_length=CHAT_MESSAGE_MAX_LENGTH)
    sport: Optional[SportType] = None
    session_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        return v.strip().replace("<script>", "").replace("</script>", "")


class ChatResponse(BaseModel):
    session_id: str
    response: str
    prediction: Optional[PredictionOutput] = None
    sources: List[str] = []
    timestamp: datetime