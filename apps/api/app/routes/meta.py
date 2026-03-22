# app/routes/meta.py
from fastapi import APIRouter

from app.config.api_contract import (
    CHAT_MESSAGE_MAX_LENGTH,
    CHAT_MESSAGE_MIN_LENGTH,
    CUSTOM_PROMPT_MAX_LENGTH,
    PREDICTIONS_LIMIT_DEFAULT,
    PREDICTIONS_LIMIT_MAX,
    SEARCH_QUERY_MAX_LENGTH,
    SEARCH_QUERY_MIN_LENGTH,
    SUPPORTED_SPORTS,
    TEAM_NAME_MAX_LENGTH,
    TEAM_NAME_MIN_LENGTH,
)
from app.ml.prediction_engine import get_current_model_version

router = APIRouter()


@router.get('/frontend')
async def frontend_contract():
    """Machine-readable API contract for frontend validation and UX constraints."""
    return {
        "version": get_current_model_version(),
        "supported_sports": list(SUPPORTED_SPORTS),
        "field_limits": {
            "team_name": {"min": TEAM_NAME_MIN_LENGTH, "max": TEAM_NAME_MAX_LENGTH},
            "custom_prompt": {"max": CUSTOM_PROMPT_MAX_LENGTH},
            "chat_message": {"min": CHAT_MESSAGE_MIN_LENGTH, "max": CHAT_MESSAGE_MAX_LENGTH},
            "search_query": {"min": SEARCH_QUERY_MIN_LENGTH, "max": SEARCH_QUERY_MAX_LENGTH},
            "predictions_page_limit": {
                "default": PREDICTIONS_LIMIT_DEFAULT,
                "max": PREDICTIONS_LIMIT_MAX,
            },
        },
        "frontend_guidance": {
            "prediction_probabilities": "All probability values are normalized in [0,1].",
            "timestamp_format": "ISO-8601 WAT datetime string.",
            "recommended_polling_endpoints": ["/health", "/api/scheduler/status"],
            "feature_flags": {
                "supports_soft_delete": True,
                "supports_prediction_restore": True,
                "supports_fixture_validation": True,
            },
        },
        "key_endpoints": {
            "create_prediction": "POST /api/predictions/",
            "list_predictions": "GET /api/predictions/",
            "validate_fixture": "GET /api/predictions/validate",
            "search_web": "GET /api/search/",
            "chat": "POST /api/chat/",
            "health": "GET /health",
        },
    }
