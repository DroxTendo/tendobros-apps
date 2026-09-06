"""Dataclasses shared across the scraper's parsing and storage layers.

Team full names (e.g. "Los Angeles Angels") are carried alongside team codes
on BoxscoreRef because the schedule page gives us both for free (from the
`/teams/{CODE}/{YEAR}.shtml` links), and the boxscore page's table ids use
the full name with all punctuation stripped (e.g. "LosAngelesAngelsbatting",
or "StLouisCardinalsbatting" for "St. Louis Cardinals"). Matching
against these known names lets boxscore.py resolve each table to the correct
team code without needing a separate hardcoded team-name-to-code table, which
would otherwise have to account for historical renames/relocations (e.g. the
Athletics dropping "Oakland" in 2025) that don't affect the codes we discover
directly from the schedule page.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BoxscoreRef:
    game_id: str
    date: str  # "YYYY-MM-DD"
    season: int
    game_seq: int
    home_code: str
    home_name: str
    away_code: str
    away_name: str
    url: str
    is_postseason: bool = False


@dataclass
class BattingLine:
    player_id: str
    player_name: str
    team: str
    position: str
    stats: dict = field(default_factory=dict)
    details_raw: str = ""
    unrecognized_details: list = field(default_factory=list)


@dataclass
class PitchingLine:
    player_id: str
    player_name: str
    team: str
    decision: str  # e.g. "W (3-4)", "L (3-4)", "S (12)", or "" if none
    stats: dict = field(default_factory=dict)


@dataclass
class GameRecord:
    game_id: str
    date: str
    season: int
    home_team: str
    away_team: str
    game_seq: int
    source_url: str
    scraped_at: str
    is_postseason: bool = False
    batting: list = field(default_factory=list)
    pitching: list = field(default_factory=list)
