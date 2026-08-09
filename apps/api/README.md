# 1/1 — Sports Prediction System

Production-grade AI-powered sports prediction platform with live web data ingestion, calibrated probabilistic ML outputs, continuous learning from actual results, and a full React dashboard.

---

## Architecture

```
oneofone-backend/         Python / FastAPI backend
oneofone-frontend/        React / Vite frontend
```

---

## File Tree

```
oneofone-backend/
  app/
    main.py                      FastAPI application entry point
    config/
      settings.py                Pydantic settings / env config
      database.py                MongoDB motor connection + indexes
    routes/
      predictions.py             POST/GET prediction endpoints
      results.py                 Actual result retrieval
      metrics.py                 Model performance metrics
      search.py                  Live web search endpoints
      scheduler.py               Status / trigger / enable-disable / logs
      admin.py                   Admin utilities (corner enrichment, etc.)
      meta.py                    Frontend API contract / limits
    services/
      web_search_service.py      Live data fetcher (ESPN, Serper, scraping)
      prediction_service.py      Orchestration: search + ML + persistence
      prediction_learning.py     Result-saving + background learning trigger
      market_service.py          Extended market computation (O/U, BTTS, corners)
      market_accuracy_service.py Per-market accuracy tracking
      scraping_service.py        Free scrapers (Understat/FBref/SofaScore/OpenLigaDB)
      result_resolver.py         Result resolution + corner backfill
      match_validation_service.py Fixture-completion checks
      quota_service.py           Search/API quota tracking
      sport_key_catalog.py       Soccer-only league catalog
    ml/
      prediction_engine.py       Engine assembly (mixin composition)
      features.py                Feature catalog + construction
      priors.py                  Prior probabilities + ML weight
      training.py                Model lifecycle + retraining (walk-forward CV)
      calibration.py             Live predict + analytical confidence interval
      evaluation.py              Stratified holdout evaluation
    scheduler/
      daily_scheduler.py         APScheduler daily automation
    schemas/
      prediction_schema.py       Pydantic request/response models
    utils/
      logging_util.py            Async MongoDB log writer
  requirements.txt
  .env.example

oneofone-frontend/
  src/
    components/
      AppNav.jsx                 Compact rail (desktop) / bottom tabs (mobile)
      Layout.jsx                 App shell
      ErrorBoundary.jsx          Global error boundary
      ExtendedMarketsPanel.jsx   Extended market picks (O/U, BTTS, corners, cards)
      ModelStatsPanel.jsx        Brier, LogLoss, ECE, Accuracy
      PaginationControls.jsx     Paged history navigation
      PredictionCard.jsx         Rich match prediction display
      PredictionTable.jsx        Sortable tabular history
      scheduler/
        StatusCards.jsx          Scheduler job status cards
        TriggerControls.jsx      Trigger / enable / disable controls
        SchedulerLogs.jsx        Scheduler run log viewer
        schedulerUtils.js        Shared scheduler helpers
    pages/
      Dashboard.jsx              Overview + charts + recent predictions
      PredictPage.jsx            Generate prediction form + output
      HistoryPage.jsx            Full history + result submission
      MetricsPage.jsx            Full metrics + calibration history
      SchedulerPage.jsx          Scheduler status, logs, controls
    charts/
      PerformanceChart.jsx       Line chart: Brier/LogLoss/Accuracy over time
      CalibrationChart.jsx       Scatter: predicted vs actual frequency
      ProbabilityDistributionChart.jsx  Bar: probability breakdown per match
      ConfidenceHistoryChart.jsx Confidence over time
      ConfidenceThresholdChart.jsx  Accuracy by confidence threshold
      MarketAccuracyChart.jsx    Per-market accuracy + empty states
      PerformanceTrendChart.jsx  Performance trend over time
      SportPerformanceChart.jsx  Performance by sport
      TrendSparkline.jsx         Compact trend sparklines
    services/
      api.js                     Axios API client
    hooks/
      useData.js                 React hooks for all API calls
    App.jsx                      Router setup
    main.jsx                     Entry point
    index.css                    Tailwind base + custom components
  index.html
  vite.config.js
  tailwind.config.js
  postcss.config.js
  package.json
```

---

## Quick Start

### Backend

```bash
cd oneofone-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run MongoDB (Docker)
docker run -d -p 27017:27017 --name oneofone-mongo mongo:7

# Start API server
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd oneofone-frontend

# Install dependencies
npm install

# Create environment file
echo "VITE_API_URL=/api" > .env

# Start dev server
npm run dev
```

Frontend: http://localhost:5173

---

## Environment Variables (.env)

| Variable | Description | Required |
|---|---|---|
| MONGODB_URI | MongoDB connection string | Yes |
| MONGODB_DB | Database name | Yes |
| SERPER_API_KEY | Serper.dev key for web search | Recommended |
| ODDS_API_KEY | The Odds API for betting odds | Optional |

The system functions without API keys using DuckDuckGo scraping and statistical prior-based prediction.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | /api/predictions/ | Generate prediction |
| GET | /api/predictions/ | List predictions |
| GET | /api/predictions/{match_id} | Get prediction by ID |
| POST | /api/predictions/results/submit | Submit actual result |
| POST | /api/predictions/learn/trigger | Trigger learning update |
| GET | /api/metrics/summary | Aggregated model performance |
| GET | /api/metrics/ | Metrics history |
| GET | /api/results/ | Actual results |
| GET | /api/search/ | Web search |
| GET | /api/search/team | Team statistics |
| GET | /api/meta/frontend | Frontend API contract + limits |
| GET | /health | System health + uptime + service status |

---

## Prediction Pipeline

1. User submits home_team, away_team, sport
2. Live data fetched in parallel:
   - Recent form (last 5 games)
   - Team statistics (ESPN API + web)
   - Injury reports (web search NLP)
   - Head-to-head history
   - Betting odds (The Odds API or scraped)
   - Venue/home record
   - Real expected goals (Understat scrape, best-effort)
3. Feature vector constructed (40 features: form, odds, H2H, xG, injuries, momentum)
4. HistGradientBoostingClassifier + CalibratedClassifierCV (isotonic n>=100 / Platt sigmoid)
5. Prior-based prediction when model untrained; soft-ensemble with ML weight otherwise
6. Analytical confidence interval (Beta distribution)
7. Output: home_win_prob, draw_prob, away_win_prob, confidence, CI
8. All values strictly in [0, 1]
9. Persisted to MongoDB

---

## Continuous Learning

1. Submit actual match results via POST /api/predictions/results/submit
2. System automatically cross-references predictions with results
3. Builds training dataset of (feature_vector, actual_outcome)
4. Retrains HistGradientBoostingClassifier + calibration when 30+ samples
5. Evaluates: Brier Score, Log Loss, Expected Calibration Error, Accuracy
6. Saves metrics to MongoDB (model_metrics)
7. Predictions stamped with the model version (stable per server lifetime)

---

## Daily Automation

APScheduler runs at 06:00 WAT daily:
- Fetches today's upcoming fixtures (ESPN/Odds API fixtures if configured)
- Runs prediction pipeline for each fixture
- Saves all predictions to MongoDB
- Logs execution status

---

## Color Theme

- **Black** (#0a0a0a) — base background
- **Red** (#dc2626) — primary brand, losses, alerts, CTA
- **Green** (#16a34a) — wins, positive metrics, gains
- **Gray variants** — structural elements, labels, muted content

---

## ML Notes

- Model: HistGradientBoostingClassifier wrapped in CalibratedClassifierCV
- Features: 40 features (form, odds, H2H, xG priors, injuries, momentum)
- Calibration: Isotonic regression (n>=100) or Platt sigmoid (n<100), walk-forward chronological folds
- Evaluation: Brier Score (primary), Log Loss, Expected Calibration Error, per-outcome Accuracy
- Minimum training samples: 30 (configurable)
- Prior prediction: Hand-weighted feature prior, soft-ensembled with ML weight when untrained/weak
- Real xG: Understat scrape (best-effort) overrides the heuristic xG when available
