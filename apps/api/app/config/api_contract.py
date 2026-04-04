"""Shared API contract constants for backend validation + frontend guidance."""

TEAM_NAME_MIN_LENGTH = 1
TEAM_NAME_MAX_LENGTH = 100
CUSTOM_PROMPT_MAX_LENGTH = 500
CHAT_MESSAGE_MIN_LENGTH = 1
CHAT_MESSAGE_MAX_LENGTH = 1000
SEARCH_QUERY_MIN_LENGTH = 1
SEARCH_QUERY_MAX_LENGTH = 200
PREDICTIONS_LIMIT_DEFAULT = 50
PREDICTIONS_LIMIT_MAX = 500

SUPPORTED_SPORTS = ("soccer", "basketball")

# /metrics/summary contract:
# - performance_metrics_all_sports: weighted aggregate across all sports
#   (weighted by resolved prediction counts per sport).
# - performance_metrics_by_sport: per-sport evaluation metrics keyed by sport.
METRICS_SUMMARY_PERFORMANCE_SCOPE = {
    "aggregate_key": "performance_metrics_all_sports",
    "per_sport_key": "performance_metrics_by_sport",
    "aggregate_weight_basis": "resolved_predictions_per_sport",
}
