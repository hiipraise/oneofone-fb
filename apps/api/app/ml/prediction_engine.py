# app/ml/prediction_engine.py
"""
Pro-grade prediction engine v2 (Sprint 5.3 file split).

ML improvements over v1:
  - Training-size-aware ensemble: ML weight scales with log(n_samples)
    so sparse data gracefully falls back to the calibrated prior
  - Recency-weighted training: matches from last 30 days weighted 2×,
    90 days 1.5×, older 1× — punishes stale signals less
  - Analytical confidence interval via Beta distribution (replaces slow bootstrap)
  - Soft ensemble between ML model and prior (instead of hard switch)
  - Feature importance extraction logged at retrain
  - Calibration via isotonic (n≥100) or Platt sigmoid (n<100)

Fix v2.1:
  - Raw stats (goals_scored_avg, goals_conceded_avg, pts_avg, pts_allowed_avg)
    are NOT 0–1 signals and must NOT be clipped to [0, 1] in features_from_data.

Fix v2.2:
  - Removed manual model version bumping from retrain(). Previously every
    retrain() call incremented the patch version AND wrote back to
    settings.MODEL_VERSION, causing version drift across retrains and
    filename mismatches after server restarts. Version is now stable for
    the entire server lifetime and equals settings.MODEL_VERSION.

File split (Sprint 5.3): the engine is now composed from five mixins so
each ML concern lives in its own module, with a public API that is
unchanged (PredictionEngine, prediction_engine singleton,
get_current_model_version):

  features.py      — feature catalog + construction   (FeaturesMixin)
  priors.py        — prior probabilities + ML weight  (PriorsMixin)
  training.py      — model lifecycle + retrain        (TrainingMixin)
  calibration.py   — predict + analytical CI          (CalibrationMixin)
  evaluation.py    — stratified evaluation            (EvaluationMixin)
"""
import logging
import warnings
from typing import Any, Dict, Optional

from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import RobustScaler

from app.config.settings import settings
from app.ml.calibration import CalibrationMixin
from app.ml.evaluation import EvaluationMixin
from app.ml.features import (
    FEATURE_KEYS,
    _COMMON_FEATURES,
    _DEFAULTS,
    _RAW_STAT_KEYS,
    _SOCCER_EXTRA,
    FeaturesMixin,
)
from app.ml.priors import (
    OUTCOME_MAP,
    OUTCOME_RMAP,
    _ML_WEIGHT_SCALE,
    _PRIOR,
    PriorsMixin,
)
from app.ml.training import MODEL_DIR, TrainingMixin

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PredictionEngine  (assembled from the five Sprint 5.3 mixins)
# ─────────────────────────────────────────────────────────────────────────────

class PredictionEngine(
    FeaturesMixin,
    PriorsMixin,
    TrainingMixin,
    CalibrationMixin,
    EvaluationMixin,
):

    def __init__(self):
        self.models: Dict[str, Optional[CalibratedClassifierCV]] = {s: None for s in FEATURE_KEYS}
        self.scalers: Dict[str, RobustScaler] = {s: RobustScaler() for s in FEATURE_KEYS}
        self.is_trained: Dict[str, bool] = {s: False for s in FEATURE_KEYS}
        self.n_training_samples: Dict[str, int] = {s: 0 for s in FEATURE_KEYS}
        # Outcome balance tracking for ML weight modulation
        self.outcome_balance: Dict[str, Dict[str, Any]] = {s: {} for s in FEATURE_KEYS}
        # Version is fixed for the server lifetime — never mutated after init
        self.model_version = settings.MODEL_VERSION
        self._load_all()


# Singleton
prediction_engine = PredictionEngine()


def get_current_model_version() -> str:
    return prediction_engine.model_version
