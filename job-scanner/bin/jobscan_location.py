"""US / non-US resolution for Job Scanner.

rules.md: non-US is a HARD EXCLUSION, but it is CRITERIA, NOT COVERAGE. Decide it
client-side after enumerating the whole board. NEVER add a location filter to a fetch.
Ambiguous location -> report it FLAGGED, never drop it.

Return contract
---------------
    True  -> US, include
    False -> non-US, exclude outright
    None  -> ambiguous, report FLAGGED (never silently dropped)

Resolution order, which is load-bearing (implementation.md):
    "An authoritative country field, or a trailing US-state token, WINS over the hint
     list. Test the structural signal first; consult the hint list only when neither is
     present."

That ordering is what keeps the country-names-that-are-US-places family correct without
a special case for each: New Mexico, Greece NY, Lake Wales FL, Lebanon NH, Peru IN,
China TX and Cuba MO all carry a US state token, so the structural signal fires first and
the foreign hint never gets consulted.

⚠️ On the ambiguous verdict: at Home Depot a naive matcher flagged 3,806 of 3,870 records.
At that volume the flag stops carrying information, which is worse than a wrong verdict
because it silently disables the channel rules.md depends on. If a board comes back
mostly-ambiguous, the resolver is broken -- do not just report it.
"""

import re

# --- US states: names and postal abbreviations --------------------------------------
US_STATE_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
}

# --- Structured country field: every value that means "US" -------------------------
# 🔴 FOUND 2026-08-31. This set previously held only US / USA / UNITED STATES, and the
# `country_code` branch fell through to `return False` for anything else. Workday CXS
# serves the FULL NAME in jobPostingInfo.country.descriptor -- "United States of
# America" -- so any caller obeying implementation.md's "make the structured country
# field decisive" rule scored EVERY US posting on EVERY CXS tenant as non-US and dropped
# it silently. The shipped 104-case suite passed clean throughout because it had zero
# country_code cases; see test_jobscan.py.
#
# Compared after squashing to letters only, so "U.S.A." and "United States of America"
# both land here. US territories are included because the TEXT path already reads them
# as US via US_STATE_ABBR -- the two paths must not disagree on the same posting.
US_COUNTRY_VALUES = {
    "US", "USA", "UNITEDSTATES", "UNITEDSTATESOFAMERICA",
    "UNITEDSTATESOFAMERICAUSA",
    "PR", "PUERTORICO",
    "GU", "GUAM",
    "VI", "USVIRGINISLANDS", "UNITEDSTATESVIRGINISLANDS",
    "AS", "AMERICANSAMOA",
    "MP", "NORTHERNMARIANAISLANDS",
}

US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia", "puerto rico",
}

# Two-letter codes that are BOTH a US state and an ISO-2 country. These are the ones that
# cannot be resolved from the token alone.
#   MT = Montana / Malta        CA = California / Canada    DE = Delaware / Germany
#   IN = Indiana / India        ID = Idaho / Indonesia      LA = Louisiana / Laos
#   MD = Maryland / Moldova     ME = Maine / Montenegro     MS = Mississippi / Montserrat
#   NE = Nebraska / Niger       PA = Pennsylvania / Panama  SC = South Carolina/Seychelles
#   AL = Alabama / Albania      AR = Arkansas / Argentina   TN = Tennessee / Tunisia
#   MO = Missouri / Macau       IL = Illinois / Israel      GA = Georgia / Georgia(country)
#   CO = Colorado / Colombia   <-- ADDED 2026-08-31 r3, see the NON_US_ISO2 note below
AMBIGUOUS_STATE_COUNTRY = {
    "MT", "CA", "DE", "IN", "ID", "LA", "MD", "ME", "MS", "NE", "PA", "SC",
    "AL", "AR", "TN", "MO", "IL", "GA", "CO",
}

# Tokens that mean "no city given" -- the ADP shape where the 2-letter token is a COUNTRY.
# Parallels serves "Remote, MT" (Malta), "Remote, CA" (Canada), "Remote, DE" (Germany),
# alongside a separate literal "Remote, US".
PLACEHOLDER_CITY = {"remote", "virtual", "home", "homebased", "home based", "anywhere",
                    "field", "telecommute", "wfh", "n/a", "various", "multiple"}

# ISO-2 codes that are unambiguously foreign. Every US state abbreviation MUST be absent
# from this set: a code here is treated as a country outright, so a colliding code must
# live in AMBIGUOUS_STATE_COUNTRY instead and go through the collision handling.
#
# 🔴🔴 THE INVARIANT ABOVE WAS FALSE AND IT COST REAL POSTINGS. Until 2026-08-31 r3 this
# set contained "AR" and "CO", and `_LEADING_CC` tests NON_US_ISO2 BEFORE US_STATE_ABBR --
# so a state-first location resolved non-US outright and never reached the collision
# handling. `CO - Denver` scored non-US (Colorado read as Colombia) and `AR - Little Rock`
# likewise (Arkansas as Argentina). CVS's entire board uses the state-first shape.
# **This is a SILENT DROP in the one exclusion that runs before the bar** -- strictly worse
# than the false-US positives fixed alongside it, because a dropped posting leaves no trace.
# Measured live at the time of the fix: 2 stored postings carried the shape (Comcast
# "CO - Virtual", CVS "CO - Work from home").
# `AR` was already in AMBIGUOUS_STATE_COUNTRY, so it was in BOTH sets and the wrong one won.
# `CO` was in neither collision set. Both are now in AMBIGUOUS_STATE_COUNTRY only.
# 🔵 The invariant is asserted on every run by test_jobscan.py::check_iso2_sets_are_disjoint --
# do not add a US state abbreviation here again.
NON_US_ISO2 = {
    "GB", "UK", "FR", "ES", "PT", "NL", "BE", "CH", "AT", "SE", "DK", "FI", "NO",
    "PL", "CZ", "SK", "HU", "RO", "BG", "GR", "TR", "RU", "UA", "IE", "IS", "LU",
    "HR", "RS", "LT", "LV", "EE", "CY", "JP", "CN", "KR", "SG", "MY", "TH", "VN",
    "PH", "AU", "NZ", "BR", "MX", "CL", "PE", "ZA", "EG", "AE", "PK",
    "BD", "LK", "NG", "KE", "CR", "GT", "DO", "HK", "TW", "JO", "QA", "KW",
    # Added 2026-08-31 r3, both required by live data and neither a US state abbreviation:
    #   MU  Mauritius -- absent entirely, so Overhaul's "Cybercity 72201, Ebene, MU"
    #       fell through to AMBIGUOUS.
    #   IT  Italy -- needed for the "Milan, MI, IT" shape.
    # ⚠️ RESIST bulk-adding the rest of ISO-3166. Several remaining codes COLLIDE with US
    # states and adding them here would recreate the AR/CO silent drop this fix removed:
    # MA = Massachusetts/Morocco, AZ = Arizona/Azerbaijan, IN = Indiana/India,
    # DE = Delaware/Germany. A colliding code belongs in AMBIGUOUS_STATE_COUNTRY, never
    # here. Add codes one at a time, only when real data needs them.
    "MU", "IT",
}

ISO3_COUNTRIES = {
    "USA", "CAN", "MEX", "GBR", "IRL", "FRA", "DEU", "ESP", "ITA", "PRT", "NLD", "BEL",
    "CHE", "AUT", "SWE", "NOR", "DNK", "FIN", "POL", "CZE", "HUN", "ROU", "BGR", "GRC",
    "TUR", "RUS", "UKR", "IND", "CHN", "JPN", "KOR", "SGP", "MYS", "THA", "VNM", "PHL",
    "IDN", "AUS", "NZL", "BRA", "ARG", "CHL", "COL", "PER", "ZAF", "EGY", "ISR", "ARE",
    "SAU", "PAK", "BGD", "LKA", "NGA", "KEN", "MAR", "CRI", "PAN", "GTM", "DOM", "HKG",
    "TWN", "LUX", "SVK", "SVN", "HRV", "SRB", "LTU", "LVA", "EST", "ISL", "MLT", "CYP",
}

# Non-colliding foreign hint tokens. Per implementation.md these WIN outright when no
# structural US signal is present -- but they are demoted by any structural signal, which
# is what the resolution order below enforces.
FOREIGN_HINTS = {
    "bangalore", "bengaluru", "hyderabad", "chennai", "mumbai", "pune", "gurgaon",
    "gurugram", "noida", "kolkata", "delhi", "ahmedabad", "india",
    "london", "manchester", "edinburgh", "glasgow", "dublin", "ireland", "scotland",
    "wales", "england", "kingdom", "britain", "uk", "belfast", "cork", "galway",
    "leeds", "bristol", "cardiff", "sheffield", "liverpool", "nottingham",
    "aberdeen", "hertfordshire", "surrey", "essex", "middlesex", "swindon",
    "toronto", "vancouver", "montreal", "ottawa", "calgary", "canada", "ontario",
    "quebec", "alberta", "manitoba", "saskatchewan",
    # Added 2026-08-31 r3: "Dartmouth, Nova Scotia, CA" scored US because no hint fired and
    # the middle token is a full province NAME rather than a code, so the structural
    # City,SUBDIV,COUNTRY test could not confirm it either. These four have NO US namesake,
    # unlike "ontario" (Ontario, California) and "new brunswick" (New Brunswick, NJ) --
    # which is exactly why `new brunswick` is deliberately NOT added here.
    "nova scotia", "british columbia", "newfoundland", "prince edward island",
    "paris", "berlin", "munich", "frankfurt", "hamburg", "madrid", "barcelona", "lisbon",
    "rome", "milan", "amsterdam", "rotterdam", "brussels", "zurich", "geneva", "vienna",
    "stockholm", "oslo", "copenhagen", "helsinki", "warsaw", "prague", "budapest",
    "bucharest", "sofia", "athens", "istanbul", "moscow", "kyiv", "kiev",
    "tokyo", "osaka", "seoul", "singapore", "shanghai", "beijing", "shenzhen",
    "hong kong", "taipei", "bangkok", "hanoi", "jakarta", "manila", "kuala lumpur",
    "sydney", "melbourne", "brisbane", "perth", "auckland", "wellington",
    "sao paulo", "rio de janeiro", "buenos aires", "santiago", "bogota", "lima",
    "mexico city", "guadalajara", "monterrey", "san jose costa rica",
    "johannesburg", "cape town", "cairo", "nairobi", "lagos", "tel aviv", "dubai",
    "abu dhabi", "riyadh", "karachi", "lahore", "dhaka", "colombo",
    "germany", "france", "spain", "italy", "portugal", "netherlands", "belgium",
    "switzerland", "austria", "sweden", "norway", "denmark", "finland", "poland",
    "czechia", "hungary", "romania", "bulgaria", "greece", "turkey", "russia",
    "ukraine", "japan", "korea", "malaysia", "thailand", "vietnam", "philippines",
    "indonesia", "australia", "zealand", "brazil", "argentina", "chile", "colombia",
    "africa", "israel", "emirates", "arabia", "pakistan", "bangladesh",
    "kenya", "nigeria", "egypt", "morocco", "philippines", "slovenia", "slovakia",
    "belgium", "luxembourg", "croatia", "serbia", "estonia", "latvia", "lithuania",
    "taiwan", "malta", "cyprus", "iceland", "peru", "uruguay", "ecuador",
}

_COORD_PAIR = re.compile(r"^\s*-?\d{1,3}\.\d+\s*,\s*-?\d{1,3}\.\d+\s*$")
# NOT end-anchored: Indeed appends a ZIP ("Chicago, IL 60617") alongside bare
# "Chicago, IL" on the same board. End-anchoring scores some rows US and some ambiguous.
_COMMA_STATE = re.compile(r",\s*([A-Za-z]{2})(?![A-Za-z])")
# Centene emits the state last, hyphenated and unspaced: "Remote-MO", "Remote-IL".
# Spaces around the dash are allowed too -- "Remote - MI" read AMBIGUOUS without it.
_HYPHEN_STATE = re.compile(r"-\s*([A-Za-z]{2})\s*$")
# Capital One separates multi-site postings with semicolons and NO comma before the
# state: "McLean VA; Richmond VA", "Plano TX; McLean VA; Richmond VA", "Eden Prairie MN".
# Uppercase-only, so a lowercase two-letter word cannot be read as a state.
_SPACE_STATE = re.compile(r"(?:^|[\s;,])([A-Z]{2})(?=\s*(?:[;,]|$))")
# "Remote Nationwide" / "Nationwide Remote" are US by construction.
_NATIONWIDE = re.compile(r"\bnationwide\b", re.IGNORECASE)
# Cigna uses a 3-letter ISO country PREFIX separated by a SPACE, not a dash:
# "IND Bengaluru", "ESP Madrid - 38.75 hrs", "CHN Shanghai...". Honour the space form
# ONLY for a known ISO country code so a 3-letter non-country prefix cannot collide.
_ISO3_PREFIX = re.compile(r"^\s*([A-Za-z]{3})[\s\-:]")
_TRAILING_US = re.compile(r"(?:^|[,\s])(US|USA|U\.S\.|U\.S\.A\.)\s*$", re.IGNORECASE)
# Cigna and several Workday tenants LEAD with the country: "US - Remote", "US-Illinois".
# The trailing test alone read all of these AMBIGUOUS.
_LEADING_US = re.compile(r"^\s*(US|USA|U\.S\.|U\.S\.A\.)\s*[-–,:]", re.IGNORECASE)
# Same shape, non-US: "UK - London", "IN - Bengaluru".
_LEADING_CC = re.compile(r"^\s*([A-Za-z]{2})\s*[-–,:]")
# A bare "{N} locations" summary carries no country at all. This is a FETCH problem, not
# a resolver problem -- implementation.md's rule is to scope the location resolver to
# post-bar candidates and read their real location list, never the summary string.
_N_LOCATIONS = re.compile(r"^\s*\d+\s+locations?\s*$", re.IGNORECASE)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def is_us(location, country_code=None):
    """Resolve a posting's location to True / False / None. See module docstring."""
    loc = _norm(location)

    # --- 1. Authoritative structured country field always wins -----------------------
    # SmartRecruiters serves location.country as a LOWERCASE ISO-2 code ("us", "gb").
    # Read it as structured data and uppercase it; never round-trip it through the
    # display string, which yields "London, gb" and reads ambiguous to a , XX matcher.
    if country_code:
        # Compare on letters only, so punctuation and spacing variants collapse:
        # "U.S.A." -> USA, "United States of America" -> UNITEDSTATESOFAMERICA.
        cc = re.sub(r"[^A-Z]", "", _norm(country_code).upper())
        if cc in US_COUNTRY_VALUES:
            return True
        if cc:
            return False

    if not loc:
        return None

    # Travelers serves raw coordinate pairs. Unresolvable without geocoding.
    if _COORD_PAIR.match(loc):
        return None

    low = loc.lower()

    # --- 2. Structural US signals ----------------------------------------------------
    # The trailing "a" must be OPTIONAL. Requiring it read "Remote (US)" and
    # "TX - Work from home (49 US locations)" as AMBIGUOUS.
    if "united states" in low or re.search(r"\bu\.?s\.?(a\.?)?\b", low):
        return True
    # A trailing bare US/USA token IS a US signal. Missing this flagged 3,806 of 3,870
    # Home Depot records ("Atlanta, GA, US") as ambiguous.
    if _TRAILING_US.search(loc):
        return True
    if _LEADING_US.match(loc):
        return True
    if _NATIONWIDE.search(loc):
        return True

    # "{N} locations" is structurally unresolvable -- see the note on _N_LOCATIONS.
    if _N_LOCATIONS.match(loc):
        return None

    # A leading 2-letter country code, mirroring the "US - Remote" shape.
    # Cigna-style state-first shape: "TX - Work from home", "MO - Remote".
    pending_us_state = False
    m = _LEADING_CC.match(loc)
    if m:
        code = m.group(1).upper()
        if code in NON_US_ISO2:
            return False
        if code in US_STATE_ABBR:
            if code not in AMBIGUOUS_STATE_COUNTRY:
                return True
            # A colliding code ("DE - Berlin" vs "MO - Remote"). Do not guess -- defer
            # until the hint list has had a look, and only then read it as the state.
            pending_us_state = True

    # --- 3. ISO-3 country prefix (Cigna) --------------------------------------------
    m = _ISO3_PREFIX.match(loc)
    if m:
        code = m.group(1).upper()
        if code in ISO3_COUNTRIES:
            return code == "USA"

    # --- 4. State tokens -------------------------------------------------------------
    # Full state names are unambiguous and carry the country-name-that-is-a-US-place
    # family for free (New Mexico, and via the abbrev branch Greece NY / Lake Wales FL).
    for name in US_STATE_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            return True

    # --- 4a. The COUNTRY SLOT, tested before any token is read as a US state -------------
    # 🔴 ADDED 2026-08-31 r3. The candidate loop below assumes the colliding token is the
    # LAST meaningful token in the string. In "City, SUBDIV, COUNTRY" it is not -- the
    # subdivision sits in the middle and the country is last -- so the loop read the
    # COUNTRY as a US state and returned US for Toronto/Berlin/Mumbai/Amsterdam/Milan.
    # Worse, where the subdivision is itself an unguarded US state abbreviation (NH, UT,
    # FL, MI) the loop returned US on the FIRST candidate without ever reading the country.
    #
    # Trailing tokens containing a digit are dropped first: a country slot never contains
    # one, and this is what defuses the postcode mechanism ("England, GB, TN24 0DQ" ->
    # _COMMA_STATE pulls "TN" out of "TN24" because its lookahead blocks a following LETTER
    # but not a following DIGIT). It also correctly leaves Indeed's "Chicago, IL 60617"
    # alone, since stripping that leaves one token and this block does not engage.
    slot_defer = False
    _tokens = [t.strip() for t in loc.split(",") if t.strip()]
    while _tokens and any(ch.isdigit() for ch in _tokens[-1]):
        _tokens.pop()
    if len(_tokens) >= 2:
        _slot = _tokens[-1].upper()
        _slot_letters = re.sub(r"[^A-Z]", "", _slot)
        if _slot_letters in US_COUNTRY_VALUES:
            return True
        if len(_slot) == 2 and _slot.isalpha():
            if _slot not in US_STATE_ABBR:
                # Unambiguously foreign: NL, IT, GB, MU, BR, MX. Cannot be a US state.
                return False
            if len(_tokens) >= 3 and (_slot in AMBIGUOUS_STATE_COUNTRY
                                      or _slot in NON_US_ISO2):
                _mid = _tokens[-2].upper()
                if len(_mid) == 2 and _mid.isalpha() and _mid not in US_STATE_ABBR:
                    # "Toronto, ON, CA" / "Berlin, BE, DE" / "Mumbai, MH, IN": the middle
                    # token is a foreign subdivision code, so the shape is confirmed
                    # City, SUBDIV, COUNTRY and the slot is the country.
                    return False
                # 🔴 A US ADMINISTRATIVE MIDDLE TOKEN SETTLES IT AS US, AND MUST BE TESTED
                # BEFORE THE HINT LIST. Measured over 12,557 real location strings, 90
                # reach this branch and 83 are US -- overwhelmingly "City, County, ST" and
                # multi-site US lists. Deferring those to FOREIGN_HINTS produced exactly
                # one wrong answer, and it was a silent US drop:
                # "Nottingham, Baltimore County, MD" scored non-US because `nottingham` is
                # a bare CITY name in FOREIGN_HINTS. implementation.md is explicit that a
                # bare city name is never a non-US signal -- same family as Ross's
                # "Dublin, CA" being Dublin, CALIFORNIA.
                _midl = _mid.lower()
                if (_midl.endswith((" county", " parish", " borough"))
                        or _midl in US_STATE_NAMES):
                    return True
                # Genuinely undecidable from structure alone -- "Chicago, Cook County, IL"
                # (Illinois) and "Montreal, Quebec, CA" (Canada) are the same shape. Defer
                # to the hint list exactly as the _LEADING_CC collision case does, rather
                # than guessing. 🔴 A blanket "slot in NON_US_ISO2 -> non-US" here would
                # read Cook County as Israel and Denver as Colombia: silent US drops, the
                # worse direction than the false positives this block fixes.
                # 🔵 And AMBIGUOUS is NOT the safe answer here either: it would flag all 90,
                # including the 83 clearly-US ones -- the Home Depot 3,806-of-3,870 flood
                # that rules.md S2 says is worse than a wrong verdict.
                slot_defer = True

    candidates = [g.upper() for g in _COMMA_STATE.findall(loc)]
    hyph = _HYPHEN_STATE.search(loc)
    if hyph:
        candidates.append(hyph.group(1).upper())
    candidates.extend(_SPACE_STATE.findall(loc))

    # When the country slot is undecidable, the slot code is the ONLY US-looking signal in
    # the string, so consulting the candidate loop would just re-derive the wrong answer.
    # Skip straight to the hint list, then fall through to US.
    if slot_defer:
        pending_us_state = True
        candidates = []

    for code in candidates:
        if code not in US_STATE_ABBR:
            continue
        if code not in AMBIGUOUS_STATE_COUNTRY:
            return True
        # Colliding code. The ADP shape is "{placeholder}, XX" with NO subdivision token,
        # where XX is the COUNTRY: "Remote, MT" is Malta, not Montana.
        head = _norm(loc.split(",")[0]).lower()
        if head in PLACEHOLDER_CITY:
            return None  # genuinely ambiguous -> report flagged, never drop
        return True  # a real city precedes it, so XX is the subdivision

    # --- 5. Hint list, consulted ONLY when no structural signal fired -----------------
    for hint in FOREIGN_HINTS:
        if re.search(r"\b" + re.escape(hint) + r"\b", low):
            return False

    if pending_us_state:
        return True
    return None


def verdict_label(v):
    return {True: "US", False: "non-US", None: "AMBIGUOUS"}[v]
