"""Parses a Baseball-Reference boxscore page into a GameRecord.

Each team has a batting table (`id="{FullTeamName}batting"`) and a pitching
table (`id="{FullTeamName}pitching"`), where the full team name has its
spaces stripped. Column names are read from `<thead>` dynamically rather
than hardcoded, so minor column drift across seasons doesn't break parsing.
Only `<tbody>` rows whose `<th>` has a `data-append-csv` attribute are real
player rows -- spacer rows and the `<tfoot>` "Team Totals" row don't have it.

Batting's extra-base-hit/SB/CS/etc counts are unpacked from the packed
`details` cell via details_parser. Pitching's `IP` column uses baseball
notation where the fractional part means thirds of an inning (6.1 = 6 1/3,
not 6.1 decimal) -- both the raw string and a derived `ip_outs` integer are
kept so downstream arithmetic is never silently wrong.
"""

from __future__ import annotations

import datetime
import logging
import re

from bs4 import BeautifulSoup, Comment

from mlb_scraper.details_parser import parse_details
from mlb_scraper.models import BattingLine, BoxscoreRef, GameRecord, PitchingLine

logger = logging.getLogger(__name__)

TABLE_ID_RE = re.compile(r"^(?P<team>.+)(?P<kind>batting|pitching)$")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


def _normalize_team_name(name: str) -> str:
    """Table ids strip ALL punctuation from the team name, not just spaces
    -- e.g. "St. Louis Cardinals" becomes "StLouisCardinals"."""
    return _NON_ALNUM_RE.sub("", name)


class ParseError(Exception):
    pass


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ip_to_outs(ip_str: str | None) -> int | None:
    if not ip_str:
        return None
    whole_str, _, frac_str = ip_str.partition(".")
    try:
        whole = int(whole_str)
        frac = int(frac_str) if frac_str else 0
    except ValueError:
        return None
    return whole * 3 + frac


def _coerce_value(stat_key: str, text: str):
    if stat_key in ("IP", "details"):
        return text  # kept raw; special-cased by the caller
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _extract_position(player_th) -> str:
    """Batting rows show the fielding position right after the player's name, e.g. "SS", "PH-RF"."""
    anchor = player_th.find("a")
    if anchor is None or anchor.next_sibling is None:
        return ""
    return str(anchor.next_sibling).strip()


def _extract_decision(player_th) -> str:
    """Pitching rows show a decision annotation instead of a position, e.g. ", L (3-4)" -- no
    trailing text at all if the pitcher got no decision (most relievers)."""
    anchor = player_th.find("a")
    if anchor is None or anchor.next_sibling is None:
        return ""
    return str(anchor.next_sibling).strip().lstrip(",").strip()


def _find_stat_tables(soup: BeautifulSoup) -> list:
    """Batting/pitching tables are wrapped in HTML comments on the live page
    (Baseball-Reference un-hides them client-side via JS), so a plain
    find_all misses them entirely -- comments have to be re-parsed as their
    own HTML fragment to reach the tables inside.
    """
    tables = list(soup.find_all("table", id=TABLE_ID_RE))
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if "table" not in comment:
            continue
        comment_soup = BeautifulSoup(str(comment), "lxml")
        tables.extend(comment_soup.find_all("table", id=TABLE_ID_RE))
    return tables


def parse_boxscore(html: str, ref: BoxscoreRef) -> GameRecord:
    soup = BeautifulSoup(html, "lxml")

    name_to_code = {
        _normalize_team_name(ref.home_name): ref.home_code,
        _normalize_team_name(ref.away_name): ref.away_code,
    }

    batting_lines: list[BattingLine] = []
    pitching_lines: list[PitchingLine] = []

    for table in _find_stat_tables(soup):
        match = TABLE_ID_RE.match(table["id"])
        team_name_part, kind = match.group("team"), match.group("kind")
        team_code = name_to_code.get(team_name_part)
        if team_code is None:
            logger.warning("table id %r didn't match either team (%s), skipping", table["id"], name_to_code)
            continue

        for row in table.select("tbody tr"):
            player_th = row.find("th", attrs={"data-append-csv": True})
            if player_th is None:
                continue  # spacer row, not a real player line

            player_id = player_th["data-append-csv"]
            anchor = player_th.find("a")
            player_name = anchor.get_text(strip=True) if anchor else player_th.get_text(strip=True)

            stats = {}
            for td in row.find_all("td"):
                stat_key = td.get("data-stat")
                if not stat_key:
                    continue
                stats[stat_key] = _coerce_value(stat_key, td.get_text(strip=True))

            if kind == "batting":
                position = _extract_position(player_th)
                details_raw = stats.pop("details", "") or ""
                counted, unrecognized = parse_details(details_raw)
                stats.update(counted)
                if unrecognized:
                    logger.warning(
                        "unrecognized details token(s) %s for %s in game %s",
                        unrecognized, player_id, ref.game_id,
                    )
                batting_lines.append(
                    BattingLine(player_id, player_name, team_code, position, stats, details_raw, unrecognized)
                )
            else:
                decision = _extract_decision(player_th)
                if "IP" in stats:
                    stats["ip_outs"] = _ip_to_outs(stats["IP"])
                pitching_lines.append(PitchingLine(player_id, player_name, team_code, decision, stats))

    if not batting_lines and not pitching_lines:
        raise ParseError(
            f"No batting/pitching tables found for {ref.game_id} ({ref.url}) -- "
            "page structure may differ from what's expected (postponed/suspended?)"
        )

    return GameRecord(
        game_id=ref.game_id,
        date=ref.date,
        season=ref.season,
        home_team=ref.home_code,
        away_team=ref.away_code,
        game_seq=ref.game_seq,
        source_url=ref.url,
        scraped_at=_utcnow_iso(),
        is_postseason=ref.is_postseason,
        batting=batting_lines,
        pitching=pitching_lines,
    )
