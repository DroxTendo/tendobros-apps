"""Parses a Baseball-Reference daily schedule-index page into BoxscoreRefs.

Completed games live inside `div.game_summaries > div.game_summary` blocks.
Each block has a `table.teams` with a `tr.loser` and a `tr.winner` row (away
team first, then home -- this matches the standard box-score convention and
is consistent with how the boxscore URL itself only encodes the home team).
Team code and full name come from the `/teams/{CODE}/{YEAR}.shtml` link in
each row; the boxscore link (with visible text "Final") lives in a
`td.gamelink` cell. A day with no games simply produces zero blocks -- not an
error.

Suspended games that finished on a later date get a third row in the same
table (`<tr><td class="desc">Completed on 5/14/2023</td></tr>`) -- filtering
to `tr.loser`/`tr.winner` specifically, rather than taking every `tr`, skips
that row instead of rejecting the whole game over it.

The All-Star Game (played on its own schedule page once a year) reuses this
same block shape but with "National League"/"American League" in place of a
real team, so the `<a>` has no `/teams/{CODE}/{YEAR}.shtml` href to resolve --
it's correctly skipped rather than parsed as a franchise matchup.

Postseason games get their own extra row too (`<tr class="date">Game N</tr>`,
before the team rows rather than after) but that's not used to detect
postseason-ness here -- see postseason.py, which resolves it far more
reliably from the season-schedule page's own explicit "Postseason Schedule"
section instead of inferring it from this annotation row.

For a date Baseball-Reference doesn't have real data for yet (e.g. requested
too close to "now"), the index.fcgi endpoint can silently return a generic
fallback page -- same URL, HTTP 200, but showing a *different* day's already-
completed games instead of an honest empty/404 response, with no visible sign
of this except a genuinely dated page's `<title>` ("...for Wednesday, August
6, 2026...") being replaced by a bare, dateless one ("MLB Scores and
Standings"). page_matches_date() catches this before its games get
mistakenly parsed as "this date's games" or its absence of real games
mistakenly parsed as "no games this date".
"""

from __future__ import annotations

import datetime
import logging
import re

from bs4 import BeautifulSoup

import config
from mlb_scraper.models import BoxscoreRef

logger = logging.getLogger(__name__)

TEAM_LINK_RE = re.compile(r"^/teams/([A-Z]{2,3})/\d{4}\.shtml$")
BOXSCORE_HREF_RE = re.compile(r"^/boxes/([A-Z]{2,3})/\1(\d{8})(\d)\.shtml$")
_TITLE_DATE_RE = re.compile(r"for \w+, ([A-Z][a-z]+ \d{1,2}, \d{4})")


def page_matches_date(html: str, queried_date: datetime.date) -> bool:
    """True only if the page's own <title> names queried_date explicitly.

    A genuine dated page's title reads "...for Wednesday, August 6, 2026...".
    Baseball-Reference's fallback page for a date it has no real data for yet
    drops that "for {weekday}, {date}" clause entirely, so a title with no
    match here is a reliable sign the page isn't really queried_date's data.
    """
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text() if soup.title else ""
    match = _TITLE_DATE_RE.search(title)
    if not match:
        return False
    try:
        page_date = datetime.datetime.strptime(match.group(1), "%B %d, %Y").date()
    except ValueError:
        return False
    return page_date == queried_date


def get_boxscore_refs(
    html: str, queried_date: datetime.date, postseason_game_ids: set[str] | None = None
) -> list[BoxscoreRef]:
    soup = BeautifulSoup(html, "lxml")
    refs: list[BoxscoreRef] = []
    postseason_game_ids = postseason_game_ids or set()

    schedule_url = f"{config.BASE_URL}/boxes/index.fcgi?year={queried_date.year}&month={queried_date.month}&day={queried_date.day}"

    for block in soup.select("div.game_summaries div.game_summary"):
        team_rows = block.select("table.teams tbody tr.loser, table.teams tbody tr.winner")
        if len(team_rows) != 2:
            logger.warning(
                "game_summary block with %d team rows, skipping (%s)",
                len(team_rows), schedule_url,
            )
            continue

        team_info = []
        unresolved_name = None
        for row in team_rows:
            link = row.find("a", href=TEAM_LINK_RE)
            if link is None:
                unresolved_name = row.find("a").get_text(strip=True) if row.find("a") else row.get_text(strip=True)
                team_info = None
                break
            code = TEAM_LINK_RE.match(link["href"]).group(1)
            name = link.get_text(strip=True)
            team_info.append((code, name))

        if not team_info:
            logger.warning(
                "could not resolve team link for %r (likely the All-Star Game, whose "
                "teams aren't real franchises), skipping (%s)",
                unresolved_name, schedule_url,
            )
            continue

        (away_code, away_name), (home_code, home_name) = team_info

        gamelink = block.select_one("td.gamelink a[href^='/boxes/']")
        if gamelink is None:
            continue  # postponed / in-progress / preview -- no "Final" link yet

        match = BOXSCORE_HREF_RE.match(gamelink["href"])
        if not match:
            logger.warning("unrecognized boxscore href format: %s", gamelink["href"])
            continue

        href_home, yyyymmdd, seq = match.groups()
        game_id = f"{href_home}{yyyymmdd}{seq}"
        game_date = f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
        if game_date != queried_date.isoformat():
            logger.warning(
                "game %s%s%s embeds date %s but was discovered on schedule page for %s "
                "(likely a suspended game completed on a later date)",
                href_home, yyyymmdd, seq, game_date, queried_date.isoformat(),
            )

        refs.append(
            BoxscoreRef(
                game_id=game_id,
                date=game_date,
                season=int(yyyymmdd[0:4]),
                game_seq=int(seq),
                home_code=home_code,
                home_name=home_name,
                away_code=away_code,
                away_name=away_name,
                url=config.BASE_URL + gamelink["href"],
                is_postseason=game_id in postseason_game_ids,
            )
        )

    return refs
