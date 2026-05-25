# app/routes/reports.py
import logging
from datetime import datetime
import os
from pathlib import Path

from fastapi import APIRouter, Query

from app.config.database import get_db
from app.config.settings import settings
from app.utils.timezone import WAT
from app.routes.metrics import get_metrics_summary
REPORT_THRESHOLD = {
    "accuracy_good": settings.REPORT_ACCURACY_GOOD,
    "accuracy_needs": settings.REPORT_ACCURACY_NEEDS,
    "brier_good": settings.REPORT_BRIER_GOOD,
    "brier_needs": settings.REPORT_BRIER_NEEDS,
    "resolution_good": settings.REPORT_RESOLUTION_GOOD,
    "low_confidence": settings.REPORT_LOW_CONFIDENCE,
}


logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@router.get('/summary')
async def get_platform_report(limit: int = Query(100, ge=20, le=500)):
    """
    Backend-generated platform report combining metrics summary + recent activity.
    """
    db = get_db()
    summary = await get_metrics_summary()

    predictions = []
    async for doc in db.predictions.find({'deleted_at': None}).sort('created_at', -1).limit(limit):
        doc.pop('_id', None)
        predictions.append(doc)

    results_count = await db.actual_results.count_documents({})

    accuracy = _safe_float(summary.get('performance_metrics_all_sports', {}).get('accuracy'))
    brier = _safe_float(summary.get('performance_metrics_all_sports', {}).get('brier_score'))
    total_predictions = int(summary.get('total_predictions', 0) or 0)
    scored_resolved = int(summary.get('total_resolved_scored', summary.get('total_resolved', 0)) or 0)
    raw_resolved = int(summary.get('total_resolved_raw', 0) or 0)

    high_confidence = sum(1 for p in predictions if _safe_float(p.get('confidence_score'), 0.0) >= 0.75)
    low_confidence = sum(1 for p in predictions if _safe_float(p.get('confidence_score'), 0.0) < REPORT_THRESHOLD['low_confidence'])
    resolution_rate = (scored_resolved / total_predictions) if total_predictions else 0.0

    working = []
    if accuracy is not None and accuracy >= REPORT_THRESHOLD['accuracy_good']:
        working.append(f"Model accuracy is {accuracy * 100:.1f}%, indicating healthy baseline decision quality.")
    if brier is not None and brier <= REPORT_THRESHOLD['brier_good']:
        working.append(f"Calibration quality is acceptable (Brier {brier:.4f}).")
    if high_confidence > 0:
        working.append(f"{high_confidence} recent predictions were made with high confidence (≥ 75%).")

    needs_improvement = []
    if accuracy is None or accuracy < REPORT_THRESHOLD['accuracy_needs']:
        needs_improvement.append('Accuracy is below target and should be improved with more validated training examples.')
    if brier is None or brier > REPORT_THRESHOLD['brier_needs']:
        needs_improvement.append('Probability calibration appears weak; confidence likely needs recalibration.')
    if resolution_rate < REPORT_THRESHOLD['resolution_good']:
        needs_improvement.append(
            f"Only {resolution_rate * 100:.1f}% of predictions are scored in metrics; result submission coverage is low."
        )
    if low_confidence > high_confidence:
        needs_improvement.append('Low-confidence predictions are dominating recent output.')

    suggestions = [
        'Automate post-match result ingestion to increase resolved + scored volume.',
        'Prioritize per-sport model retraining when sample counts cross activation thresholds.',
        'Add a weekly calibration review to compare confidence buckets vs actual win rates.',
    ]

    generated_tasks = [
        {
            'id': 'task-improve-resolution',
            'title': 'Increase scored resolution coverage to 70%',
            'detail': f'Current scored coverage: {resolution_rate * 100:.1f}% ({scored_resolved}/{total_predictions}).',
        },
        {
            'id': 'task-calibration-audit',
            'title': 'Run calibration audit on latest 100 predictions',
            'detail': f'Latest Brier score is {brier:.4f}.' if brier is not None else 'Brier score unavailable; investigate metrics collection.',
        },
        {
            'id': 'task-data-quality',
            'title': 'Review unresolved submitted results',
            'detail': f'{raw_resolved} results submitted, {scored_resolved} currently scored in model metrics.',
        },
    ]

    return {
        'overview': 'This AI report analyzes platform performance using live model metrics and recent platform activity. It highlights what is working, where to improve, and the next actions for your team.',
        'working': working,
        'needsImprovement': needs_improvement,
        'suggestions': suggestions,
        'generatedTasks': generated_tasks,
        'generatedAt': datetime.now(WAT).isoformat(),
        'thresholds': REPORT_THRESHOLD,
        'facts': {
            'totalPredictions': total_predictions,
            'scoredResolved': scored_resolved,
            'rawResolved': raw_resolved,
            'accuracy': accuracy,
            'brier': brier,
            'resultsCount': int(results_count),
            'predictionsCount': len(predictions),
        },
    }


@router.get('/platform-analysis')
async def get_platform_analysis():
    """
    Serves the platform analysis report from PLATFORM_ANALYSIS_REPORT.md.
    Auto-updates by reading the latest file content.
    """
    try:
        # Navigate from this file up to the repository root (5 levels from routes.py)
        # reports.py is at apps/api/app/routes/reports.py so parents[4] -> repo root
        app_root = Path(__file__).resolve().parents[4]
        analysis_file = app_root / 'PLATFORM_ANALYSIS_REPORT.md'
        
        if not analysis_file.exists():
            return {
                'content': '',
                'exists': False,
                'message': 'Platform analysis report not found',
                'lastUpdated': None,
            }
        
        content = analysis_file.read_text(encoding='utf-8')
        stat = analysis_file.stat()
        last_updated = datetime.fromtimestamp(stat.st_mtime).isoformat()
        
        return {
            'content': content,
            'exists': True,
            'lastUpdated': last_updated,
            'message': 'Platform analysis report loaded successfully',
        }
    except Exception as e:
        logger.error(f'Error reading platform analysis: {str(e)}')
        return {
            'content': '',
            'exists': False,
            'message': f'Error reading platform analysis: {str(e)}',
            'lastUpdated': None,
        }
