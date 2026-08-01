# app/main.py
"""
1/1 Sports Prediction Engine — FastAPI application entry point.
"""
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from app.utils.timezone import WAT

from fastapi import FastAPI
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config.settings import settings
from app.config.database import connect_db, disconnect_db, get_db
from app.scheduler.daily_scheduler import scheduler as daily_scheduler, start_scheduler, stop_scheduler
from app.ml.prediction_engine import get_current_model_version

# ── Routes ────────────────────────────────────────────────────────────────────
from app.routes import predictions, metrics, results, search, scheduler as scheduler_routes, meta
from app.routes import admin as admin_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
STARTED_AT_WAT = datetime.now(WAT)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting 1/1 Sports Prediction Engine…")
    await connect_db()
    start_scheduler()
    logger.info("Startup complete.")
    yield
    # Shutdown
    logger.info("Shutting down…")
    stop_scheduler()
    await disconnect_db()
    logger.info("Shutdown complete.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "1/1 Sports Prediction Engine",
    description = "Probabilistic sports prediction with ML + calibrated priors",
    version     = get_current_model_version(),
    lifespan    = lifespan,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers     = ["Authorization", "Content-Type", "X-Requested-With"],
)


@app.middleware("http")
async def add_security_headers_and_log(request: Request, call_next):
    started = time.perf_counter()
    logger.info("HTTP start %s %s from=%s", request.method, request.url.path, request.client.host if request.client else "-")
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("HTTP unhandled %s %s", request.method, request.url.path)
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Process-Time-ms"] = f"{duration_ms:.1f}"
    logger.info(
        "HTTP end %s %s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(predictions.router, prefix="/api/predictions", tags=["predictions"])
app.include_router(metrics.router,     prefix="/api/metrics",     tags=["metrics"])
app.include_router(results.router,     prefix="/api/results",     tags=["results"])
app.include_router(search.router,      prefix="/api/search",      tags=["search"])
app.include_router(scheduler_routes.router,   prefix="/api/scheduler",   tags=["scheduler"])
app.include_router(meta.router,        prefix="/api/meta",        tags=["meta"])
app.include_router(admin_routes.router, prefix="/api/admin", tags=["admin"])







# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    db_connected = get_db() is not None
    now = datetime.now(WAT)
    uptime_seconds = int((now - STARTED_AT_WAT).total_seconds())
    return {
        "status":  "ok",
        "version": get_current_model_version(),
        "timestamp": now.isoformat(),
        "uptime_seconds": uptime_seconds,
        "services": {
            "database": "up" if db_connected else "down",
            "scheduler": "running" if daily_scheduler.running else "stopped",
        },
    }


@app.get("/", tags=["system"])
async def root():
    return {
        "app":     "1/1 Sports Prediction Engine",
        "version": get_current_model_version(),
        # "docs":    "/docs",
    }
