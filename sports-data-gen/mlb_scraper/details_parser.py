"""Parses the packed `details` cell from a Baseball-Reference batting table.

Extra-base hits and other counting events (2B, 3B, HR, SB, CS, HBP, SF, SH,
IBB, GDP, E) aren't separate columns in the batting table -- they're packed
into one `details` cell as comma-separated tokens, each optionally prefixed
with a count and a middle dot (U+00B7), e.g. "2·2B,SB" means two doubles and
a stolen base, "HR" means one home run, and an empty string means none of
these events happened. The separator is a comma, confirmed live against
real 2026 box scores rather than inferred from the rendered page.
"""

from __future__ import annotations

import re

CODE_MAP = {
    "2B": "2B",
    "3B": "3B",
    "HR": "HR",
    "SB": "SB",
    "CS": "CS",
    "HBP": "HBP",
    "SF": "SF",
    "SH": "SH",
    "IBB": "IBB",
    "IW": "IBB",  # alternate code for intentional walk seen live alongside IBB
    "GDP": "GDP",
    "GIDP": "GDP",
    "E": "E",
}
COUNTED_FIELDS = sorted(set(CODE_MAP.values()))

TOKEN_RE = re.compile(r"^(?:(\d+)·)?([A-Za-z0-9]+)$")


def parse_details(details_str: str | None) -> tuple[dict[str, int], list[str]]:
    """Returns (counted_stats, unrecognized_tokens). Never raises."""
    result = {field: 0 for field in COUNTED_FIELDS}
    unrecognized: list[str] = []

    for raw_token in (details_str or "").split(","):
        token = raw_token.strip()
        if not token:
            continue
        match = TOKEN_RE.match(token)
        if not match or match.group(2) not in CODE_MAP:
            unrecognized.append(token)
            continue
        count = int(match.group(1)) if match.group(1) else 1
        field_name = CODE_MAP[match.group(2)]
        result[field_name] += count

    return result, unrecognized
