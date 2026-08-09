# app/routes/search.py
from fastapi import APIRouter, Query, Request

from app.config.api_contract import SEARCH_QUERY_MIN_LENGTH, SEARCH_QUERY_MAX_LENGTH
from app.utils.rate_limit import limiter
from app.services.web_search_service import (
    search_web,
    fetch_team_stats,
    fetch_recent_form,
    fetch_injury_report,
)

router = APIRouter()


@router.get("/")
@limiter.limit("30/minute")
async def web_search(request: Request, q: str = Query(..., min_length=SEARCH_QUERY_MIN_LENGTH, max_length=SEARCH_QUERY_MAX_LENGTH)):
    results = search_web(q, num_results=5)
    return {"query": q, "results": results}


@router.get("/team")
@limiter.limit("30/minute")
async def team_info(request: Request, team: str = Query(...), sport: str = Query("soccer")):
    stats = fetch_team_stats(team, sport)
    form = fetch_recent_form(team, sport)
    injuries = fetch_injury_report(team, sport)
    return {"team": team, "sport": sport, "stats": stats, "form": form, "injuries": injuries}
