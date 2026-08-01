# app/services/chat_service.py
"""
Chat Service — Groq LLM + session memory + live web search.

SerpAPI conservation: the chat handler fires at most ONE SerpAPI call
per message (the context search). Prediction-specific data is fetched
inside create_prediction() which already has its own 3-call budget.
The old code duplicated fetch_recent_form() calls for both teams on top
of what create_prediction() already fetched — that's now removed.
"""
import logging
import re as _re
from datetime import datetime, timezone
from app.utils.timezone import WAT
from typing import Optional, List, Dict, Any

import httpx

from app.config.settings import settings
from app.services.web_search_service import search_serpapi, get_serpapi_usage
from app.services import memory_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the 1/1 Football Analytics AI — a quantitative football/soccer prediction system.

Core rules:
- All probability outputs must be in [0, 1] format
- Only use data provided in the context — never invent stats
- Always cite the data source when stating a probability
- State confidence intervals when available
- Acknowledge data limitations clearly

When presenting predictions:
- Home win / Draw / Away win probabilities
- Model confidence score and interval
- Relevant football markets: 1X2, double chance, draw no bet, goals O/U, BTTS, first-half 1X2, first-half BTTS, 10-minute 1X2, team totals, correct score, corners, team corners, cards, combo markets
- Provide one best pick per market when possible, based on the available data

Response style: concise, analytical, data-driven. No filler."""

FOOTBALL_TODAY_ENGINE_PROMPT = """You are a professional football prediction engine.

Your task is to generate decisive, high-confidence predictions ONLY for matches scheduled TODAY using the most recent and reliable data available.

STRICT RULES:
1. Always detect today's date from the provided runtime date and only return matches scheduled for that date.
2. Never invent matches, leagues, kickoff times, or predictions.
3. If no matches are found, return exactly: No matches found for today.
4. If real match data is unavailable, return exactly: Live match data unavailable.
5. Use clean plain text only (no markdown, bullets, emojis, or symbols).
6. Be decisive and return only one strongest outcome per market.
7. Keep reason to maximum 2 short lines.
8. Keep predictions logically consistent:
   - If BTTS = No, score cannot be 1-1, 2-2, etc.
   - If Over 2.5, score must have total goals >= 3.
   - If Under 2.5, score must have total goals <= 2.
9. If user does not specify match count, return up to 5 matches.

Output template (exact section names):
Match: [Team A vs Team B]
League: [League Name]
Kickoff: [HH:MM]

Prediction Summary:
Winner: Home / Draw / Away

Goals:
Over 2.5 / Under 2.5

BTTS:
Yes / No

Correct Score:
X-X

Corners:
Over 8.5 / Under 8.5

Confidence:
Low / Medium / High

Reason:
Max 2 short lines with strongest signals only."""

_SPORT_KEYWORDS: Dict[str, List[str]] = {
    "soccer": [
        "soccer", "football", "premier league", "la liga", "champions league",
        "bundesliga", "serie a", "ligue 1", "mls", "eredivisie",
        "copa del rey", "fa cup", "goal", "striker", "goalkeeper", "penalty",
    ],
}


def _detect_sport(message: str) -> str:
    ml = message.lower()
    for sport, kws in _SPORT_KEYWORDS.items():
        if any(kw in ml for kw in kws):
            return sport
    return "soccer"


def parse_teams(message: str) -> Optional[Dict[str, str]]:
    patterns = [
        r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\s+(?:vs?\.?|versus|against)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})",
        r"predict\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\s+(?:vs?\.?|versus|against)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})",
    ]
    for pat in patterns:
        m = _re.search(pat, message)
        if m:
            sport = _detect_sport(message)
            return {
                "home_team": m.group(1).strip(),
                "away_team": m.group(2).strip(),
                "sport": sport,
            }
    return None


def _is_football_today_request(message: str) -> bool:
    ml = message.lower()
    football_terms = ["football", "soccer", "epl", "premier league", "la liga", "serie a"]
    today_terms = ["today", "scheduled today", "matches today", "fixtures today"]
    prediction_terms = ["predict", "prediction", "winner", "odds", "btss", "btts", "correct score"]
    return (
        any(t in ml for t in football_terms)
        and any(t in ml for t in today_terms)
        and any(t in ml for t in prediction_terms)
    )


def _resolve_reference_date(message: str, now_utc) -> Dict[str, str]:
    """
    Resolve common relative-date language to a concrete UTC date anchor.
    This keeps search + prompting time-aware without hardcoding years.
    """
    ml = message.lower()
    target_date = now_utc
    label = "today"

    if "yesterday" in ml:
        target_date = now_utc.fromordinal(now_utc.toordinal() - 1)
        label = "yesterday"
    elif "tomorrow" in ml:
        target_date = now_utc.fromordinal(now_utc.toordinal() + 1)
        label = "tomorrow"
    elif "next year" in ml:
        target_date = now_utc.replace(year=now_utc.year + 1)
        label = "next year"
    elif "last year" in ml or "previous year" in ml:
        target_date = now_utc.replace(year=now_utc.year - 1)
        label = "last year"
    elif "years ago" in ml:
        m = _re.search(r"(\d+)\s+years?\s+ago", ml)
        years_back = int(m.group(1)) if m else 1
        target_date = now_utc.replace(year=now_utc.year - years_back)
        label = f"{years_back} years ago"
    elif "in " in ml and " year" in ml:
        m = _re.search(r"in\s+(\d+)\s+years?", ml)
        if m:
            years_forward = int(m.group(1))
            target_date = now_utc.replace(year=now_utc.year + years_forward)
            label = f"in {years_forward} years"

    return {"label": label, "date_iso": target_date.isoformat()}


async def call_groq(messages: List[Dict], system: str) -> str:
    if not settings.GROQ_API_KEY:
        return (
            "AI language model unavailable (GROQ_API_KEY not configured). "
            "Prediction engine is operational."
        )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "system", "content": system}, *messages],
                    "temperature": 0.12,
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return f"AI response error: {e}."


async def process_chat(request) -> dict:
    from app.services.prediction_service import create_prediction
    from app.schemas.prediction_schema import PredictionRequest, SportType, ChatResponse

    session_id   = getattr(request, "session_id", None) or await memory_service.create_session()
    user_message = request.message

    # ── ONE SerpAPI call for general context ─────────────────────────────────
    # Only fire this if we have remaining budget; gracefully degrade otherwise
    usage = get_serpapi_usage()
    search_context = ""
    search_sources: List[str] = []
    today_utc = datetime.now(timezone.utc).date()
    reference_date = _resolve_reference_date(user_message, today_utc)
    date_anchor = reference_date["date_iso"]
    if usage["remaining"] > 5:
        search_results = search_serpapi(
            f"{user_message} sports fixtures {date_anchor}",
            num_results=3,
        )
        search_context = "\n".join(
            f"- {r.get('title', '')}: {r.get('snippet', '')}"
            for r in search_results if r.get("snippet")
        )
        search_sources = [r.get("link", "") for r in search_results if r.get("link")]
    else:
        logger.warning(f"Chat skipping SerpAPI context search — budget low ({usage['remaining']} remaining)")

    # ── Prediction (if this is a match request) ──────────────────────────────
    prediction_output = None
    prediction_meta: Dict[str, Any] = {}

    parsed = parse_teams(user_message)
    is_pred_request = parsed or any(
        kw in user_message.lower()
        for kw in ["predict", "who will win", "win probability", "odds", "chance", "forecast"]
    )

    if is_pred_request and parsed:
        sport_str = parsed["sport"]
        try:
            sport_enum = SportType(sport_str)
        except ValueError:
            sport_enum = SportType.SOCCER

        # NOTE: create_prediction handles its own ESPN + combined SerpAPI calls.
        # We do NOT call fetch_recent_form here — that was the old duplicate waste.
        pred_req = PredictionRequest(
            home_team=parsed["home_team"],
            away_team=parsed["away_team"],
            sport=sport_enum,
            custom_prompt=user_message,
        )
        try:
            prediction_output = await create_prediction(pred_req)
            prediction_meta = {
                "match_id": prediction_output.match_id,
                "home_team": parsed["home_team"],
                "away_team": parsed["away_team"],
                "sport": sport_str,
            }
            markets = prediction_output.extended_markets or {}
            search_context += (
                f"\n\nPrediction: {parsed['home_team']} vs {parsed['away_team']} [{sport_str}]\n"
                f"  Home={prediction_output.home_win_probability:.4f}  "
                + f"Draw={prediction_output.draw_probability:.4f}  "
                + f"Away={prediction_output.away_win_probability:.4f}\n"
                f"  Confidence: {prediction_output.confidence_score:.4f}  "
                f"CI: [{prediction_output.confidence_interval_low:.3f}, "
                f"{prediction_output.confidence_interval_high:.3f}]\n"
                f"  Predicted: {prediction_output.predicted_outcome}\n"
            )

            if sport_str == "soccer" and markets.get("goals_over_under"):
                ou = markets["goals_over_under"]
                o25 = ou.get("over_2_5", {})
                search_context += f"  xG: {ou.get('expected_goals')} | O2.5: {o25.get('over')}\n"
                if markets.get("btts"):
                    b = markets["btts"]
                    search_context += f"  BTTS: Yes={b.get('yes')} No={b.get('no')}\n"

        except Exception as e:
            logger.error(f"Chat prediction error: {e}")
            search_context += f"\nPrediction note: {e}"

    # ── Build LLM prompt ─────────────────────────────────────────────────────
    memory_ctx = await memory_service.build_memory_context(session_id)
    football_today_mode = _is_football_today_request(user_message)
    full_system = FOOTBALL_TODAY_ENGINE_PROMPT if football_today_mode else SYSTEM_PROMPT
    full_system += f"\n\nRuntime date (UTC): {today_utc.isoformat()}"
    full_system += (
        f"\nResolved time reference: '{reference_date['label']}' => {reference_date['date_iso']} (UTC)."
    )
    full_system += (
        "\nAlways interpret relative dates dynamically from runtime context "
        "(yesterday/today/tomorrow/years ago/future years)."
    )
    if memory_ctx:
        full_system += f"\n\n{memory_ctx}"
    if search_context:
        full_system += f"\n\nReal-time context:\n{search_context}"
    elif football_today_mode:
        # Deterministic fallback required by strict response contract.
        ai_response = "Live match data unavailable."
        await memory_service.append_message(session_id, "user", user_message, prediction_meta or None)
        await memory_service.append_message(session_id, "assistant", ai_response, prediction_meta or None)
        return ChatResponse(
            session_id=session_id,
            response=ai_response,
            prediction=prediction_output,
            sources=search_sources,
            timestamp=datetime.now(WAT),
        )

    # Append quota info to help LLM acknowledge data gaps
    full_system += f"\n\nSerpAPI budget: {usage['used']}/{usage['budget']} searches used this month."

    history  = await memory_service.get_context_window(session_id)
    all_msgs = [*history, {"role": "user", "content": user_message}]
    ai_response = await call_groq(all_msgs, full_system)

    await memory_service.append_message(session_id, "user", user_message, prediction_meta or None)
    await memory_service.append_message(session_id, "assistant", ai_response, prediction_meta or None)

    return ChatResponse(
        session_id=session_id,
        response=ai_response,
        prediction=prediction_output,
        sources=search_sources,
        timestamp=datetime.now(WAT),
    )
