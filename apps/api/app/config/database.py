import asyncio
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Optional, Iterator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from app.config.settings import settings

logger = logging.getLogger(__name__)

client: Optional[AsyncIOMotorClient] = None
db: Optional[AsyncIOMotorDatabase] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None

_db_override: ContextVar[Optional[AsyncIOMotorDatabase]] = ContextVar("db_override", default=None)
_client_override: ContextVar[Optional[AsyncIOMotorClient]] = ContextVar("client_override", default=None)


def _ensure_client_for_current_loop() -> Optional[AsyncIOMotorDatabase]:
    global client, db, _client_loop

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is None:
        return db

    if db is not None and _client_loop is current_loop:
        return db

    if client is not None and _client_loop is not current_loop:
        logger.info("Detected event loop change for MongoDB client; rebuilding Motor client for the active loop")
        client.close()
        client = None
        db = None

    if client is None:
        logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}")
        client = AsyncIOMotorClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DB]
        _client_loop = current_loop

    return db


async def connect_db():
    active_db = _ensure_client_for_current_loop()
    if active_db is None:
        raise RuntimeError("Database connection has not been established")
    await create_indexes()
    logger.info("MongoDB connected and indexes created")


async def disconnect_db():
    global client, db, _client_loop
    if client:
        client.close()
        logger.info("MongoDB disconnected")
    client = None
    db = None
    _client_loop = None


async def create_indexes():
    active_db = get_db()
    if active_db is None:
        raise RuntimeError("Database connection has not been established")
    # predictions: frequent lookup by match_id, recency sorting, and date/sport filtering.
    await active_db.predictions.create_index([("match_id", ASCENDING)], unique=True)
    await active_db.predictions.create_index([("timestamp", DESCENDING)])
    await active_db.predictions.create_index([("match_date", ASCENDING)])
    await active_db.predictions.create_index([("sport", ASCENDING)])
    await active_db.predictions.create_index([("deleted_at", ASCENDING), ("timestamp", DESCENDING)])
    await active_db.predictions.create_index([("match_date", ASCENDING), ("deleted_at", ASCENDING)])
    await active_db.predictions.create_index([("prediction_group_id", ASCENDING), ("deleted_at", ASCENDING)])

    # actual_results: list endpoint sorts by recorded_at and writes/read by match_id/date.
    await active_db.actual_results.create_index([("match_id", ASCENDING)], unique=True)
    await active_db.actual_results.create_index([("recorded_at", DESCENDING)])
    await active_db.actual_results.create_index([("match_date", ASCENDING)])
    await active_db.actual_results.create_index([("sport", ASCENDING)])
    await active_db.predictions.create_index([("sport", ASCENDING), ("match_date", ASCENDING), ("deleted_at", ASCENDING)])

    # model_metrics: dashboard endpoints sort by date and may filter by model_version.
    await active_db.model_metrics.create_index([("date", DESCENDING)])
    await active_db.model_metrics.create_index([("model_version", ASCENDING)])

    await active_db.feature_snapshots.create_index([("match_id", ASCENDING)])
    await active_db.feature_snapshots.create_index([("timestamp", DESCENDING)])

    await active_db.system_logs.create_index([("timestamp", DESCENDING)])
    await active_db.system_logs.create_index([("level", ASCENDING)])
    await active_db.scheduler_settings.create_index([("enabled", ASCENDING)])

    await active_db.external_api_cache.create_index([("key", ASCENDING)], unique=True)
    await active_db.external_api_cache.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)


@contextmanager
def override_db_context(
    override_db: AsyncIOMotorDatabase,
    override_client: Optional[AsyncIOMotorClient] = None,
) -> Iterator[None]:
    db_token: Token = _db_override.set(override_db)
    client_token: Optional[Token] = None
    try:
        if override_client is not None:
            client_token = _client_override.set(override_client)
        yield
    finally:
        if client_token is not None:
            _client_override.reset(client_token)
        _db_override.reset(db_token)


def get_client() -> Optional[AsyncIOMotorClient]:
    override_client = _client_override.get()
    if override_client is not None:
        return override_client
    return client


def get_db() -> Optional[AsyncIOMotorDatabase]:
    override_db = _db_override.get()
    if override_db is not None:
        return override_db
    return _ensure_client_for_current_loop()
