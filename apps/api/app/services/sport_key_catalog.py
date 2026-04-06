"""Canonical Odds API sport keys used across services."""
from typing import Dict, List

SPORT_KEYS: Dict[str, List[str]] = {
    "soccer": [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
        "soccer_uefa_champs_league",
        "soccer_uefa_europa_league",
        "soccer_usa_mls",
        "soccer_portugal_primeira_liga",
        "soccer_netherlands_eredivisie",
        "soccer_brazil_campeonato",
        "soccer_argentina_primera_division",
        "soccer_turkey_super_league",
        "soccer_saudi_premier_league",
        "soccer_mexico_ligamx",
        "soccer_conmebol_copa_libertadores",
    ],
    "basketball": [
        "basketball_nba",
        "basketball_wnba",
        "basketball_euroleague",
        "basketball_ncaab",
        "basketball_nbl",
    ],
}
