"""Canonical Odds API sport keys — football/soccer only.

Sprint 7.17: the multi-sport catalog shape was dead weight. OneOfOne is a
soccer-only product (see app/ml/features.py FEATURE_KEYS, scheduler
_SUPPORTED_SPORTS, settings.SUPPORTED_SPORTS), so this module exposes a
single flat list of soccer league keys instead of a generic
``Dict[sport, keys]`` abstraction nothing else uses.
"""
from typing import List

SOCCER_SPORT_KEYS: List[str] = [
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
]
