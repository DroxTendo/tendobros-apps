"""Parses a Baseball-Reference season-schedule page to find which games were
postseason.

`/leagues/majors/{year}-schedule.shtml` lists every game for the year, with
regular-season and postseason games grouped under separate labeled sections
(`<h2>Regular Season Schedule</h2>` / `<h2>Postseason Schedule</h2>`). Each
game under a section is a `<p class="game">` with a boxscore link, so
matching hrefs only within the postseason section's `div.section_content`
gives the exact set of postseason game_ids directly -- no inference needed,
unlike the day-level schedule page's ambiguous "Game N" annotation row.

Before a season's postseason has started (or for a season with none yet),
the section simply doesn't exist on the page -- that's not an error, it just
means an empty set.
"""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from mlb_scraper.schedule import BOXSCORE_HREF_RE

logger = logging.getLogger(__name__)


def get_postseason_game_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")

    heading = soup.find("h2", string="Postseason Schedule")
    if heading is None:
        return set()

    section = heading.find_parent("div", class_="section_wrapper")
    if section is None:
        return set()

    content = section.select_one("div.section_content")
    if content is None:
        return set()

    game_ids = set()
    for link in content.select("p.game a[href^='/boxes/']"):
        match = BOXSCORE_HREF_RE.match(link["href"])
        if not match:
            continue
        home, yyyymmdd, seq = match.groups()
        game_ids.add(f"{home}{yyyymmdd}{seq}")

    return game_ids
