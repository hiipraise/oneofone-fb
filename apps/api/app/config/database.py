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

_db_override: ContextVar[Optional[AsyncIOMotorDatabase]] = ContextVar("db_override", default=None)
_client_override: ContextVar[Optional[AsyncIOMotorClient]] = ContextVar("client_override", default=None)


async def connect_db():
    global client, db
    logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}")
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB]
    await create_indexes()
    logger.info("MongoDB connected and indexes created")


async def disconnect_db():
    global client, db
    if client:
        client.close()
        logger.info("MongoDB disconnected")
    client = None
    db = None


async def create_indexes():
    active_db = get_db()
    if active_db is None:
        raise RuntimeError("Database connection has not been established")
    await active_db.predictions.create_index([("match_id", ASCENDING)], unique=True)
    await active_db.predictions.create_index([("date", DESCENDING)])
    await active_db.predictions.create_index([("sport", ASCENDING)])
    await active_db.predictions.create_index([("model_version", ASCENDING)])

    await active_db.actual_results.create_index([("match_id", ASCENDING)], unique=True)
    await active_db.actual_results.create_index([("date", DESCENDING)])

    await active_db.model_metrics.create_index([("date", DESCENDING)])
    await active_db.model_metrics.create_index([("model_version", ASCENDING)])

    await active_db.feature_snapshots.create_index([("match_id", ASCENDING)])
    await active_db.feature_snapshots.create_index([("timestamp", DESCENDING)])

    await active_db.system_logs.create_index([("timestamp", DESCENDING)])
    await active_db.system_logs.create_index([("level", ASCENDING)])


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
    return db
