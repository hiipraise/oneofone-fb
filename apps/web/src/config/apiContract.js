// src/config/apiContract.js

export const FALLBACK_SUPPORTED_SPORTS = ['soccer']

export const DEFAULT_API_CONTRACT = {
  version: 'unknown',
  supported_sports: FALLBACK_SUPPORTED_SPORTS,
  field_limits: {
    team_name: { min: 1, max: 100 },
    custom_prompt: { max: 500 },
    search_query: { min: 1, max: 200 },
    predictions_page_limit: { default: 50, max: 500 },
  },
  frontend_guidance: {
    prediction_probabilities: 'All probability values are normalized in [0,1].',
    timestamp_format: 'ISO-8601 WAT datetime string.',
    recommended_polling_endpoints: ['/health', '/api/scheduler/status'],
    feature_flags: {
      supports_soft_delete: true,
      supports_prediction_restore: true,
      supports_fixture_validation: true,
    },
  },
  key_endpoints: {
    create_prediction: 'POST /api/predictions/',
    list_predictions: 'GET /api/predictions/',
    validate_fixture: 'GET /api/predictions/validate',
    search_web: 'GET /api/search/',
    health: 'GET /health',
  },
}

export const SPORT_LABELS = {
  soccer: 'Football / Soccer',
}

export const normalizeContract = (payload) => {
  if (!payload || typeof payload !== 'object') return DEFAULT_API_CONTRACT

  return {
    ...DEFAULT_API_CONTRACT,
    ...payload,
    supported_sports: Array.isArray(payload.supported_sports) && payload.supported_sports.length
      ? payload.supported_sports
      : DEFAULT_API_CONTRACT.supported_sports,
    field_limits: {
      ...DEFAULT_API_CONTRACT.field_limits,
      ...(payload.field_limits || {}),
    },
    frontend_guidance: {
      ...DEFAULT_API_CONTRACT.frontend_guidance,
      ...(payload.frontend_guidance || {}),
    },
    key_endpoints: {
      ...DEFAULT_API_CONTRACT.key_endpoints,
      ...(payload.key_endpoints || {}),
    },
  }
}
