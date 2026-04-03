# app/services/memory_service.py
import logging
from datetime import datetime, timezone
from app.utils.timezone import now_wat, WAT
from typing import List, Dict, Optional
import uuid

from app.config.database import get_db
from app.config.settings import settings

logger = logging.getLogger(__name__)


async def create_session() -> str:
    session_id = str(uuid.uuid4())
    db = get_db()
    await db.chat_sessions.insert_one({
        "session_id": session_id,
        "created_at": datetime.now(WAT).isoformat(),
        "updated_at": datetime.now(WAT).isoformat(),
        "message_count": 0,
        "predictions_made": [],
        "teams_discussed": [],
        "sports_discussed": [],
        "deleted_at": None,
    })
    return session_id


async def append_message(session_id: str, role: str, content: str, metadata: Optional[Dict] = None):
    db = get_db()
    await db.chat_messages.insert_one({
        "session_id": session_id, "role": role, "content": content,
        "timestamp": datetime.now(WAT).isoformat(),
        "metadata": metadata or {},
    })

    update = {"updated_at": datetime.now(WAT).isoformat()}
    if metadata:
        teams = [team for team in [metadata.get("home_team"), metadata.get("away_team")] if team]
        if teams:
            await db.chat_sessions.update_one(
                {"session_id": session_id},
                {"$addToSet": {"teams_discussed": {"$each": teams}}},
            )
        if metadata.get("sport"):
            await db.chat_sessions.update_one(
                {"session_id": session_id},
                {"$addToSet": {"sports_discussed": metadata["sport"]}},
            )
        if metadata.get("match_id"):
            await db.chat_sessions.update_one(
                {"session_id": session_id},
                {"$addToSet": {"predictions_made": metadata["match_id"]}},
            )
    await db.chat_sessions.update_one(
        {"session_id": session_id},
        {"$set": update, "$inc": {"message_count": 1}},
    )


async def get_history(session_id: str, limit: Optional[int] = None) -> List[Dict]:
    db = get_db()
    n = limit or settings.CHAT_HISTORY_LIMIT
    messages = []
    async for doc in db.chat_messages.find(
        {"session_id": session_id}
    ).sort("timestamp", -1).limit(n):
        doc.pop("_id", None)
        messages.append(doc)
    messages.reverse()
    return messages


async def get_context_window(session_id: str) -> List[Dict]:
    history = await get_history(session_id, limit=settings.CHAT_MEMORY_WINDOW)
    return [{"role": m["role"], "content": m["content"]} for m in history]


async def get_session_summary(session_id: str) -> Dict:
    db = get_db()
    session = await db.chat_sessions.find_one({"session_id": session_id})
    if not session:
        return {}
    session.pop("_id", None)
    return session


async def build_memory_context(session_id: str) -> str:
    session = await get_session_summary(session_id)
    if not session or session.get("message_count", 0) == 0:
        return ""
    parts = []
    teams = [t for t in session.get("teams_discussed", []) if t]
    sports = [s for s in session.get("sports_discussed", []) if s]
    preds = session.get("predictions_made", [])
    if teams:
        parts.append(f"Teams discussed: {', '.join(set(teams))}")
    if sports:
        parts.append(f"Sports discussed: {', '.join(set(sports))}")
    if preds:
        parts.append(f"Predictions made: {len(preds)}")
    return "Session memory:\n" + "\n".join(f"- {p}" for p in parts) if parts else ""


async def get_all_sessions(limit: int = 50, include_deleted: bool = False) -> List[Dict]:
    db = get_db()
    query: Dict = {} if include_deleted else {"deleted_at": None}
    sessions = []
    async for doc in db.chat_sessions.find(query).sort("updated_at", -1).limit(limit):
        doc.pop("_id", None)
        sessions.append(doc)
    return sessions


async def soft_delete_session(session_id: str) -> bool:
    """Soft-delete a session — hides it from normal list but preserves data."""
    db = get_db()
    result = await db.chat_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"deleted_at": now_wat().isoformat()}},
    )
    return result.matched_count > 0


async def restore_session(session_id: str) -> bool:
    db = get_db()
    result = await db.chat_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"deleted_at": None}},
    )
    return result.matched_count > 0