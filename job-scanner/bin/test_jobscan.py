"""Tests for the Job Scanner matcher, location resolver and dedup normalizer.

Run:
  .venv\\Scripts\\python.exe bin\\test_jobscan.py        (from the project root)

Cases are seeded from real titles and real recorded incidents in rules.md,
implementation.md and matches/*.md. When a scan finds a new trap, add the case HERE
first, then fix the module -- that is the whole point of keeping this code in the repo
instead of re-deriving it into a scratchpad every run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jobscan_dedup as D
import jobscan_location as L
import jobscan_match as M

MATCH_CASES = [
    # --- core: the basic shapes -----------------------------------------------------
    ("Data Engineer", "core"),
    ("Senior Data Engineer", "core"),
    ("Data Engineer I", "core"),
    # words in any order, not necessarily adjacent -- the operator's explicit example.
    # 🔴 2026-09-02: this one now ROUTES to lead_manager on its exact `lead` token. The
    # any-order property it was written to demonstrate is unchanged and is still asserted
    # by "Engineer, Data Platform" below -- the routing happens AFTER the bar is cleared.
    ("Data Lead Engineer", "lead_manager"),
    ("Engineer, Data Platform", "core"),
    ("Sr. Engineer - Data Platform", "core"),
    # prefix matching carries the inflections
    # 🔴 "Data Engineering Manager" / "Analytics Engineering Manager" WERE core here, then
    # were excluded outright by the 2026-08-31 manager ruling. 2026-09-02 REVERSED that:
    # they are included again and ROUTED to lead_manager -- as are the Director forms, once
    # the routing was widened to the whole "lead level and up" category the same day. The
    # `engineer` -> "Engineering" inflection these demonstrate is still asserted by
    # "Engineer, Data Platform" above and "Analytics Engineer" below, neither of which routes.
    ("Data Engineering Lead", "lead_manager"),
    ("Analytics Engineering Director", "lead_manager"),
    ("Director of Data Engineering", "lead_manager"),
    ("Analytics Engineer", "core"),
    ("Database Engineer", "core"),
    ("Software Engineer, Database", "core"),
    ("BI Engineer", "core"),
    ("Business Intelligence Engineer", "core"),
    # glued form: \bdata\b used to miss this, prefix matching does not
    ("DataOps Engineer", "core"),

    # --- analyst --------------------------------------------------------------------
    ("Data Analyst", "analyst"),
    ("Data Healthcare Analyst", "analyst"),        # the operator's explicit example
    ("Senior Data Analyst - Card", "analyst"),
    ("BI Analyst", "analyst"),
    ("Business Intelligence Analyst", "analyst"),

    # --- the analytics/analyst asymmetry, which is correct --------------------------
    # 🔴 This guard USED to be ("Data Analytics Manager", "borderline_candidate"). The
    # 2026-08-31 manager exclusion would score that None and SILENTLY RETIRE the only
    # regression guard for the asymmetry documented at rules.md:35-36 -- "analytics" does
    # NOT satisfy "analyst", so this is not a Data Analyst match. Replaced with a
    # manager-free title that exercises exactly the same thing. Do not delete it.
    ("Data Analytics Lead", "borderline_candidate"),

    # --- the bar is mechanical: these are DELIBERATELY core, exclusions aside --------
    ("Data Center Facilities Engineer", "core"),
    ("Machine Learning Engineer, Data Platform", "core"),
    # bare "Summer" carries no year, so the summer-20XX exclusion must NOT fire here
    ("Data Engineering Summer Analyst", "core"),
    ("Provider Data Analyst", "analyst"),
    ("Data Entry Analyst", "analyst"),

    # --- PROMOTED TO CORE 2026-08-31 -------------------------------------------------
    # Data Modeler restored from borderline, and Developer added as a head noun across
    # all seven Engineer items. The operator: "Developer variations of all the existing ones,
    # but no data architect." See rules.md §1.
    ("Data Modeler", "core"),
    ("Senior Data Modeler - Enterprise Data Warehouse", "core"),
    ("Data Modelers", "core"),                     # "modeler" prefix reaches the plural
    # 🔴 Routes on `principal` since the 2026-09-02 widening. It is still the case that
    # ("data","modeling") is what admits it to core in the first place -- base_tier() is
    # "core" here, which is what the Modeler promotion this block tests actually asserts.
    ("Principal Data Modeling", "lead_manager"),
    ("Data Modeling Engineer", "core"),
    ("Data Modelling Consultant", "core"),         # British spelling, 0 stored today
    ("BI Developer", "core"),
    ("Business Intelligence Developer", "core"),
    ("Analytics Developer", "core"),
    ("Data Developer", "core"),
    ("Database Developer", "core"),
    ("Software Developer, Data Platform", "core"),

    # --- boundaries of the promotion: none of these may move -------------------------
    # 🟢 "development" does NOT prefix-match "developer" -- measured on 7 stored titles,
    # none of which promoted. This is what keeps Business Development out of core.
    ("Business Development Representative - Data Solutions", "borderline_candidate"),
    ("Software Developer III - Forecast Systems", None),   # no data word at all
    ("Fit Model", None),                           # bare model still must not fire
    # 🔴 bare "modeler" is NOT core -- only ("data","modeler") is. A future Financial or
    # Catastrophe Modeler must stay in judgement rather than auto-report.
    ("Financial Modeler", "borderline_candidate"),
    # ⚠️ ACCEPTED SIDE EFFECT, pinned so it is not later read as a bug. ("data","modeling")
    # matches in ANY ORDER, so a Data Science modelling title reaches core. The operator was
    # shown this and chose it; core carries no exclusions and they triage.
    ("Senior Data Scientist - Risk Modeling", "core"),
    # 🔴 REJECTED ON EVIDENCE: ("data","model") as a core item bought 1 wanted title and
    # auto-reported 4 Data-Science/actuarial/risk ones. These stay borderline.
    ("Principal Associate, Data Science - Model Risk Office", "borderline_candidate"),
    ("Actuarial and Data Science Model Validation", "borderline_candidate"),

    # --- Lead & Manager routing, ruled by the operator 2026-09-02 ------------------------
    # 🔴 THESE WERE ALL `None` (excluded outright) FROM 2026-08-31 TO 2026-09-02.
    # The operator: "instead of excluding, anything that says lead or manager we include, but
    # make it it's own section." They are INCLUDED again and routed to their own tier --
    # nothing is dropped. `base_tier()` still reports which bar each one cleared.
    ("Senior Manager, Business Intelligence Engineer", "lead_manager"),
    ("Manager, Data Engineering", "lead_manager"),
    ("Data Engineering Manager", "lead_manager"),
    ("Analytics Engineering Manager", "lead_manager"),
    ("Product Manager, Data Engineering", "lead_manager"),
    ("Data Analyst Manager - Model Risk Office", "lead_manager"),
    # ...and the `lead` half of the same ruling. The operator was shown that this moves 336
    # stored postings and that "Lead Data Engineer" is their OWN current title, and chose
    # to route it anyway. Do not "restore" these to core on that reasoning.
    ("Lead Data Engineer", "lead_manager"),
    ("Senior Data Analyst, Lead", "lead_manager"),
    ("Analytics Engineer Lead", "lead_manager"),

    # --- exclusions: the early-career family ONLY, after 2026-09-02 -----------------
    # Dropped OUTRIGHT: not core, not analyst, not borderline, not reported, not
    # persisted. These titles all qualify on their data merits and are excluded anyway.
    # 🔴 The manager family is NO LONGER HERE -- see the routing block above.
    ("Data Engineer Intern", None),
    ("Summer 2027 Internship - Data Analytics - Michigan", None),
    ("Data Operations & Analytics Fall Co-op", None),
    ("Campus Undergraduate Summer Internship Program - 2027 Data Analytics", None),
    ("Apprentice - Data Analytics", None),
    ("Graduate Data Analyst", None),
    ("New Grad Data Engineer", None),

    # --- exclusion false friends: every one of these must SURVIVE -------------------
    # 🔴 The exclusions are EXACT-token precisely so these do not die. Under the module's
    # default prefix rule a bare "intern" would kill all three of the first group -- they
    # are real stored postings, measured 2026-08-31.
    ("Internal Fraud Reporting & Insights Analyst", "borderline_candidate"),
    ("Senior Coordinator, Internal Communications - Channel & Analytics Strategy",
     "borderline_candidate"),
    ("Director, International CRM Intelligence & Insights Strategy",
     "borderline_candidate"),
    # "management" is a DOMAIN word here, not a seniority word -- 87 stored titles carry
    # it. A "manage" stem instead of exact "manager" would wrongly bin all of these.
    # 🔴 This carries `lead` but reaches only BORDERLINE (no Engineer/Analyst/Developer/
    # Modeler head noun), and borderline is deliberately NOT routed -- so it stays a
    # borderline candidate. It is STILL the proof that `management` is not caught: under a
    # `manage` stem it would have been binned entirely.
    ("Reference Data Management Lead", "borderline_candidate"),
    ("Senior Data Engineer II - Enterprise Data Platforms and Data Management", "core"),
    ("Sr. Lead Data Engineer - Enterprise Risk Management", "lead_manager"),
    # ...and a title carrying BOTH `manager` and domain-word `management` routes, on the
    # `manager` token alone. It reaches BORDERLINE, not core/analyst -- and borderline is
    # deliberately NOT routed, so it stays a borderline candidate.
    ("Manager, Data Management", "borderline_candidate"),
    # 🔴 THE ROUTING IS THE WHOLE "LEAD LEVEL AND ABOVE" CATEGORY, widened 2026-09-02:
    # "Basically any lead or manager and up level should go to the manager level."
    ("Managing Director, Data Engineering", "lead_manager"),
    ("Team Leader, Data Engineering", "lead_manager"),
    ("Director, Data Engineering", "lead_manager"),
    ("Analytics Engineering Director", "lead_manager"),
    ("Principal Data Engineer", "lead_manager"),
    ("Head of Data Engineering", "lead_manager"),
    ("VP, Data Engineering", "lead_manager"),
    # NB "Data Analytics" alone does not reach analyst -- `analytics` does not satisfy
    # `analyst` -- so the routed example has to clear a real bar first.
    ("SVP, Data Engineering", "lead_manager"),
    ("SVP, Data Analytics", "borderline_candidate"),
    ("Chief Data Engineer", "lead_manager"),
    ("Vice President, Data Engineering", "lead_manager"),
    # ⚠️ ACCEPTED FALSE FRIEND, measured and recorded rather than fixed: this is an
    # early-career rotational programme, not a leadership role, but `leadership` routes it.
    # The operator named "Leadership -> Manager" explicitly. Do not special-case it silently --
    # if it becomes a problem it needs its own ruling.
    ("Leadership Development Program - Data Analyst", "lead_manager"),
    # 🔴 EXACT-TOKEN IS WHAT KEEPS THESE OUT. A `lead` stem routes the first, a `manage`
    # stem routes the second and third (80 stored titles use "Management" as a DOMAIN
    # word), and a `director` stem routes the fourth.
    ("Data Engineer, Leading Edge Platforms", "core"),
    ("Senior Data Engineer II - Enterprise Data Platforms and Data Management", "core"),
    ("Junior Master Data Management Analyst", "analyst"),
    ("Data Engineer, Directory Services", "core"),
    # 🔴 "head of" IS A TWO-TOKEN ITEM, NOT A BARE `head`. "Head Start" is a US
    # early-childhood programme and a real stored title shape -- a bare `head` routes it.
    ("Data Engineer, Head Start Program", "core"),
    # Measured and deliberately NOT in the category -- each would cause a false route.
    # `executive` is NOT in the category -- this reaches borderline on `analytics` and is
    # judged away there, rather than being routed into the leadership section as a sales role.
    ("Sr. Solution Sales Executive, Clinical Analytics", "borderline_candidate"),
    ("Staff Software Engineer, Data and Partner Platform", "core"),
    ("Staff Data Engineer", "core"),
    ("Senior Data Engineer", "core"),
    ("Supervisor, Data Analytics Reporting", "borderline_candidate"),
    # 🔴 BORDERLINE IS NOT ROUTED -- a lead/manager title that only reaches the borderline
    # net stays a borderline candidate. Folding these into the new section would turn it
    # into a grab-bag of judgement calls rather than a clean seniority split.
    ("Manager, Data Governance", "borderline_candidate"),
    ("Lead Data Steward", "borderline_candidate"),
    # An excluded title is STILL dropped even when it carries lead/manager -- exclusions
    # are tested before routing, so the early-career family still wins.
    ("Data Engineering Manager Intern", None),
    ("Campus Graduate Masters Full-Time Manager - 2027 Data Engineering", None),
    # "internet" starts with "intern" -- exact matching is what saves this one
    ("Data Engineer, Internet of Things", "core"),
    # ("new","grad") is exact-token and any-order. If "grad" were a prefix it would reach
    # "Grade", and any-order matching would then fire on "New York" + "Grade".
    ("Data Analyst, Grade 12 - New York, NY", "analyst"),
    # "undergraduate" does not equal "graduate", so this SURVIVES. It is arguably a campus
    # programme, but campus programmes were ruled out by NAME, not by inference -- the
    # real AmEx titles are caught on `campus`/`internship`. Flagged in rules.md as a known
    # gap; if the operator rules it in, this expectation changes.
    ("Undergraduate Data Analyst Program", "analyst"),

    # --- the bi guard: none of these may match --------------------------------------
    ("Bilingual Patient Advocate", None),
    ("Biology Research Associate", None),
    ("Big Rig Driver", None),
    # "Analyst" alone is not a tier. Without a data word there is no item to satisfy,
    # and no borderline stem either -- these fall out entirely, which is correct.
    ("Billing Analyst", None),

    # --- Architect: BI IS core, DATA is not, and the split is deliberate -------------
    # 🔴 RULED 2026-09-03 r2. The operator, on Humana's `Senior Business Intelligence
    # Architect` being reported as borderline: "this one should have been in either core
    # or leadership and management, it's senior business intelligence, and then
    # architect."
    #
    # The 2026-08-31 instruction was "but no DATA architect" -- it never mentioned BI
    # Architect. rules.md recorded that correctly ("Data Architect ALONE remains
    # borderline"); profile.md had widened it to "Data Architect and BI Architect", which
    # was an inference beyond the ruling and is now corrected. BI Architect was in fact
    # borderline only because `architect` was never added to the head-noun set at all.
    ("Business Intelligence Architect", "core"),
    ("Senior Business Intelligence Architect", "core"),
    ("BI Architect", "core"),
    ("Sr BI Architect", "core"),
    # routing still applies on top of the promotion -- it is an overlay, not a filter
    ("Lead Business Intelligence Architect", "lead_manager"),
    ("Director, BI Architecture", "lead_manager"),
    # prefix matching reaches Architecture, exactly as it reaches Engineering
    ("Business Intelligence Architecture Manager", "lead_manager"),
    #
    # 🔴 DATA Architect STAYS BORDERLINE -- the operator's 2026-08-31 "but no data architect",
    # re-confirmed 2026-09-03 r2 when they were shown that promoting it would move ~50
    # stored titles and chose BI-only. profile.md qualifies it with "if hands-on with
    # pipelines/modeling", a judgement call the mechanical core bar cannot make.
    # Do NOT "fix" this asymmetry -- it is the ruling, twice over.
    ("Data Architect", "borderline_candidate"),
    ("Senior Data Architect", "borderline_candidate"),
    # ...and neither Analytics nor Database Architect were promoted either.
    ("Sr Analytics Architect", "borderline_candidate"),
    ("Database Architect", "borderline_candidate"),
    # a bare Architect with no data word is still nothing at all
    ("Enterprise Architect", None),
    ("Solutions Architect", None),

    # --- not a match at all ---------------------------------------------------------
    ("Data Scientist", "borderline_candidate"),    # net catches it; judgement rejects
    ("Registered Nurse", None),
    ("Barback", None),

    # --- borderline false-friend anchors --------------------------------------------
    ("Warehouse Associate", None),                 # bare warehouse must NOT fire
    ("Warehouse Operations Clerk", None),
    # 🔴 This line was ("Data Warehouse Developer", "borderline_candidate") and its job was
    # to prove ("data","warehouse") FIRES when both words are present -- the counterpart to
    # "Warehouse Associate -> None" above. The 2026-08-31 Developer promotion makes it core
    # via ("data","developer"), so it stops exercising the anchor at all. Kept (the new
    # expectation is correct and worth pinning) and BACKED BY A REPLACEMENT that still
    # tests the anchor. Same trap as the Data Analytics Manager asymmetry guard.
    ("Data Warehouse Developer", "core"),
    ("Data Warehouse Specialist", "borderline_candidate"),   # the actual anchor guard now
    # "data" is a SUFFIX in "Metadata", so prefix matching misses it -- listed explicitly
    ("Senior Associate, Metadata Engineering", "borderline_candidate"),
    ("Fit Model", None),                           # bare model must NOT fire
    ("Financial Modeling Manager", None),
    # No data word, so not the analyst tier -- it reaches the net on the "report" stem
    # and goes to judgement. Under the OLD rules "reporting" was hard noise.
    ("Reporting Analyst", "borderline_candidate"),
]

LOCATION_CASES = [
    # structured country field always wins
    (("London, gb", "gb"), False),
    (("Anywhere", "us"), True),
    # 🔴 FOUND 2026-08-31: Workday CXS serves the FULL NAME in
    # jobPostingInfo.country.descriptor -- "United States of America". The branch
    # accepted only US/USA/UNITED STATES, so the full name fell through to the
    # `if cc: return False` catch-all and scored non-US on EVERY CXS tenant. Any group
    # following implementation.md's "make the structured country field decisive" rule
    # would have silently dropped every US posting on Marsh, Adobe, Humana, CVS,
    # Pfizer, Stryker, Nationwide, Hartford... with nothing in the output to show it.
    # The 104-case suite passed clean because it had ZERO country_code cases.
    (("Chicago, IL", "United States of America"), True),
    ((None, "United States of America"), True),
    ((None, "United States"), True),
    ((None, "U.S.A."), True),
    ((None, "usa"), True),
    # the structured field is authoritative and OUTRANKS the display string
    (("Bengaluru", "United States of America"), True),
    # US territories: the TEXT path already reads these as US via US_STATE_ABBR
    # (line 36), so the STRUCTURED path must agree or the two disagree on the same
    # posting. Home Depot serves GU records.
    ((None, "PR"), True),
    ((None, "GU"), True),
    ((None, "VI"), True),
    ((None, "AS"), True),
    ((None, "MP"), True),
    ((None, "Puerto Rico"), True),
    # genuine non-US structured values must still exclude outright
    ((None, "GB"), False),
    ((None, "United Kingdom"), False),
    ((None, "India"), False),
    # as a structured COUNTRY field, CA is Canada -- not California
    ((None, "CA"), False),
    # explicit US markers
    (("Chicago, IL, United States", None), True),
    (("Atlanta, GA, US", None), True),             # Home Depot: 3,806 of 3,870 records
    # ZIP appended by Indeed -- must not end-anchor the state test
    (("Chicago, IL 60617", None), True),
    (("Chicago, IL", None), True),
    # Centene: state last, hyphenated and unspaced
    (("Remote-MO", None), True),
    (("Remote-IL", None), True),
    # Cigna: 3-letter ISO country prefix separated by a space
    (("IND Bengaluru", None), False),
    (("ESP Madrid - 38.75 hrs", None), False),
    (("CHN Shanghai Lujiazui Software Park (LJZ)", None), False),
    # ADP/Parallels: placeholder city + colliding code = the code is the COUNTRY
    (("Remote, MT", None), None),                  # Malta, not Montana -> ambiguous
    (("Remote, CA", None), None),                  # Canada, not California
    (("Remote, DE", None), None),                  # Germany, not Delaware
    (("Remote, US", None), True),
    # a real city before a colliding code means the code IS the subdivision
    (("Sacramento, CA", None), True),
    (("Philadelphia, PA", None), True),
    (("Indianapolis, IN", None), True),
    # country names that are US places -- structural signal fires first
    (("Albuquerque, New Mexico", None), True),
    (("Greece, NY", None), True),
    (("Lake Wales, FL", None), True),
    (("Lebanon, NH", None), True),
    (("Peru, IN", None), True),
    # non-colliding foreign hints win when no structural signal is present
    (("Bangalore", None), False),
    (("Dublin, Ireland", None), False),
    (("Tokyo", None), False),
    # leading country code -- the trailing test alone read all of these AMBIGUOUS
    (("US - Remote", None), True),
    (("US-Illinois", None), True),
    (("UK - London", None), False),
    (("Belfast, UK (2 locations)", None), False),
    (("Newcastle upon Tyne, UK", None), False),
    (("Remote (US)", None), True),
    (("TX - Work from home (49 US locations)", None), True),
    (("MO - Remote", None), True),
    (("DE - Berlin", None), False),      # same shape, resolved by the hint list
    (("IN - Bengaluru", None), False),
    (("Remote - MI", None), True),       # spaces around the dash
    (("Remote Nationwide", None), True),
    (("Nationwide Remote", None), True),
    # Capital One: semicolon-separated, no comma before the state
    (("McLean VA; Richmond VA", None), True),
    (("Plano TX; McLean VA; Richmond VA", None), True),
    (("Eden Prairie MN", None), True),
    # a bare location-count summary is structurally unresolvable, not a resolver failure
    (("2 locations", None), None),
    (("6 locations", None), None),
    # Travelers coordinate pairs are unresolvable
    (("41.7658,-72.6734", None), None),
    # nothing to go on
    (("", None), None),
    (("Remote", None), None),

    # =====================================================================================
    # 🔴 FOUR FALSE-VERDICT MECHANISMS FOUND 2026-08-31 r3, all in the _COMMA_STATE /
    # _LEADING_CC region. Root cause shared by the first three: the resolver assumed the
    # colliding token is the LAST meaningful token, so when a subdivision sits between city
    # and country, THE COUNTRY IS READ AS THE SUBDIVISION.
    # =====================================================================================

    # --- (A) City, SUBDIV, COLLIDING-ISO2 -- the country slot was read as a US state ------
    # All of these scored US. "a real city precedes it, so XX is the subdivision" is wrong
    # here: the subdivision is the MIDDLE token and the last one is the country.
    (("Toronto, ON, CA", None), False),
    (("Montreal, QC, CA", None), False),
    (("Calgary, AB, CA", None), False),
    (("Berlin, BE, DE", None), False),
    (("Hannover, NI, DE", None), False),
    (("Mumbai, MH, IN", None), False),
    (("Bengaluru, KA, IN", None), False),

    # --- (B) worse: the SUBDIVISION is itself an unguarded US state abbreviation ----------
    # NH/UT/FL/MI are US state abbrevs NOT in AMBIGUOUS_STATE_COUNTRY, so the resolver
    # returned US on the FIRST candidate and never even looked at the country slot.
    # Netherlands and Italy boards are the live exposure (Under Armour serves 30 NL records).
    (("Amsterdam, NH, NL", None), False),      # Noord-Holland, not New Hampshire
    (("Utrecht, UT, NL", None), False),        # Utrecht, not Utah
    (("Almere, FL, NL", None), False),         # Flevoland, not Florida
    (("Rotterdam, ZH, NL", None), False),
    (("Milan, MI, IT", None), False),          # Milano, not Michigan
    (("Cybercity 72201, Ebene, MU", None), False),   # MU absent from NON_US_ISO2 entirely

    # --- (C) a trailing POSTCODE hid the country, and its outward code read as a state ----
    # _COMMA_STATE is r",\s*([A-Za-z]{2})(?![A-Za-z])" -- the lookahead blocks a following
    # LETTER but not a following DIGIT, so "TN" is pulled straight out of "TN24".
    # 15 real UK outward codes collide with US state abbrevs: AL CA CO CT DE GU KY LA ME
    # NE PA PR TN WA WV. GU and PR are in that list BECAUSE of the 2026-08-31 territory
    # fix -- that fix widened this surface.
    (("England, GB, TN24 0DQ", None), False),
    (("Carlisle, GB, CA1 1AA", None), False),
    (("Derby, GB, DE1 1AA", None), False),
    (("Amsterdam, NH, NL, 1011", None), False),
    (("Toronto, ON, CA, M5V", None), False),
    # ⚠️ ACCEPTED RESIDUAL, PINNED DELIBERATELY -- "City, COLLIDING-ISO2, postcode" with NO
    # subdivision token is STRUCTURALLY UNDECIDABLE. "Wustermark, DE, 14641" (Germany) and
    # "Denver, CO, 80202" (Colorado) are the same shape character-for-character in kind, and
    # neither city is in FOREIGN_HINTS. US must remain the default here: "City, ST, ZIP" is
    # the commonest US location format on the roster, so defaulting it to AMBIGUOUS would
    # flood the flag channel and disable it -- the Home Depot 3,806-of-3,870 failure that
    # rules.md S2 explicitly warns about.
    # 🔵 THE SUPPORTED FIX IS THE CALLER PASSING country_code, which is decisive. That is
    # what implementation.md's Under Armour trailing-postcode rule is for. Both halves are
    # pinned so neither is "corrected" later without seeing the trade.
    (("Wustermark, DE, 14641", None), True),
    (("Wustermark, DE, 14641", "DE"), False),
    (("Montreal, Quebec, CA, H4N 1J8", None), False),   # middle token is a full name
    (("Central Jakarta, Jakarta, ID, 10310", None), False),

    # --- (D) 🔴 THE SILENT US DROP: AR and CO were misfiled in NON_US_ISO2 ----------------
    # _LEADING_CC tests NON_US_ISO2 BEFORE US_STATE_ABBR, so with AR/CO in that set a
    # state-first location resolved non-US outright and never reached the collision
    # handling: Colorado read as Colombia, Arkansas as Argentina. This is the WORSE
    # direction -- a silent drop in the exclusion that runs before the bar -- and CVS's
    # whole board uses the state-first shape.
    # Measured live: 2 stored postings carry it, Comcast "CO - Virtual" and CVS
    # "CO - Work from home", both Colorado, both scoring non-US.
    # The module already had the right machinery (pending_us_state, built for exactly this);
    # it was bypassed only because the two codes sat in the wrong set.
    (("CO - Denver", None), True),
    (("CO - Virtual", None), True),
    (("CO - Work from home", None), True),
    (("AR - Little Rock", None), True),
    (("CO-Denver", None), True),
    # ...and the same shape must still resolve foreign where the city says so
    (("CO - Bogota", None), False),
    (("AR - Buenos Aires", None), False),

    # --- 🔴 REGRESSION GUARDS: these must STAY US. -----------------------------------------
    # A blanket "trailing token in NON_US_ISO2 -> non-US" fix would read Denver as Colombia
    # and Cook County as Israel. Silent US drops are worse than the false positives being
    # fixed, so the colliding-slot case defers to the hint list and ends in US.
    (("Denver, CO, 80202", None), True),
    (("Baltimore, MD, 21230", None), True),
    (("Chicago, Cook County, IL", None), True),
    (("Springfield, Sangamon County, IL", None), True),
    # 🔴 REGRESSION FOUND BY THE REAL-DATA REPLAY, not by the suite. The first version of
    # the country-slot fix deferred this to FOREIGN_HINTS, which matched the bare city name
    # `nottingham` and scored it non-US -- a silent US drop, and the same family as Ross's
    # "Dublin, CA" being Dublin, CALIFORNIA. A US administrative middle token now settles it
    # before the hint list is consulted. 83 of the 90 real strings reaching that branch are
    # US, so US must win there.
    (("Nottingham, Baltimore County, MD", None), True),
    (("Brooklyn, Susquehanna County, PA", None), True),
    (("Fairfield, Adams County, PA", None), True),
    (("Arlington Heights, Cook, IL", None), True),
    (("Glendale, Los Angeles, CA", None), True),
    # multi-site US lists land in the same branch
    (("Hartford, CT; Charlotte, NC; Columbus, OH; Chicago, IL", None), True),
    (("Bethesda, MD; Palo Alto, CA", None), True),
    # ...while a full FOREIGN subdivision name in the middle must still resolve foreign.
    # "Dartmouth, Nova Scotia, CA" scored US before this run: no hint fired and the middle
    # token is a name, not a code, so the structural test could not confirm it either.
    (("Dartmouth, Nova Scotia, CA", None), False),
    (("Washington, DC", None), True),
    (("San Juan, PR", None), True),
    (("Hagatna, GU", None), True),
    (("Los Angeles, CA", None), True),
    (("Wilmington, DE, 19801", None), True),
    (("Portland, ME, 04101", None), True),
]

DEDUP_CASES = [
    # Prize Picks: stored http, served https
    ("http://prizepicks.com/position?gh_jid=7826517003",
     "https://www.prizepicks.com/position?gh_jid=7826517003"),
    # Wendy's: case-sensitive slug drift
    ("https://careers.wendys.com/posting/Engineer---Data/209972",
     "https://careers.wendys.com/posting/engineer---data/209972"),
    # eBay: leading locale segment
    ("https://ebay.wd5.myworkdayjobs.com/en-us/apply/job/R0012345",
     "https://ebay.wd5.myworkdayjobs.com/apply/job/R0012345"),
    # Cigna / Pfizer: -N revision suffix on a numeric id
    ("https://cigna.com/job/26007037", "https://cigna.com/job/26007037-1"),
    # Workday R-prefixed revision
    ("https://x.myworkdayjobs.com/job/Remote/Data-Engineer_R-426591",
     "https://x.myworkdayjobs.com/job/Remote/Data-Engineer_R-426591-1"),
    # tracking params must not key
    ("https://boards.greenhouse.io/alt/jobs/123?gh_jid=123",
     "https://boards.greenhouse.io/alt/jobs/123?gh_jid=123&gh_src=abc&utm_source=x"),
    # trailing slash
    ("https://careers.progressive.com/jobs/18060418-analyst-lead/",
     "https://careers.progressive.com/jobs/18060418-analyst-lead"),
    # 🔴 FOUND 2026-08-31 (G1, Scopely). The board now serves
    # .../scopely/jobs/{id}?gh_jid={id}; 13 of 14 stored Scopely keys are the bare path,
    # so 7 tracked reqs re-reported as new. Stripping gh_jid ONLY when its value equals
    # the last path segment is identity-preserving: the param is then pure duplication
    # of the path and carries no information the path does not already carry. A gh_jid
    # that does NOT match the path still keys -- see DEDUP_MUST_DIFFER.
    ("https://job-boards.greenhouse.io/scopely/jobs/5397611008",
     "https://job-boards.greenhouse.io/scopely/jobs/5397611008?gh_jid=5397611008"),
    # 🔴 FOUND 2026-08-31 (G3, Adobe). The tracker holds the Workday externalPath AND
    # the same path + /apply for the same req. /apply is the apply view of the posting
    # already identified by the preceding segment, never a distinct posting.
    ("https://adobe.wd5.myworkdayjobs.com/external_experienced/job/San-Jose/Data-Science-Engineer_R169523-1",
     "https://adobe.wd5.myworkdayjobs.com/external_experienced/job/San-Jose/Data-Science-Engineer_R169523-1/apply"),
    # /apply strip must compose with the revision strip, in that order
    ("https://x.myworkdayjobs.com/site/job/Remote/Data-Engineer_R-426591",
     "https://x.myworkdayjobs.com/site/job/Remote/Data-Engineer_R-426591-1/apply"),
]

DEDUP_MUST_DIFFER = [
    # PetSmart compound {POSTING_ID}-{LOCATION_ID}: the 4+ digit tail must survive, or
    # every location variant of a posting collapses onto one key.
    ("https://petsmart.com/job/12345-6789", "https://petsmart.com/job/12345-6780"),
    # genuinely different reqs, same title
    ("https://capitalone.com/job/R248928", "https://capitalone.com/job/R248849"),
    # Greenhouse identity param must key
    ("https://pinterestcareers.com/jobs/?gh_jid=111",
     "https://pinterestcareers.com/jobs/?gh_jid=222"),
    # 🔴 Ashby puts identity in ?ashby_jid=. A whitelist that missed it collapsed 11
    # distinct Shopify postings onto one key. Unknown params must be KEPT.
    ("https://www.shopify.com/careers?ashby_jid=3adac50d-f0c5-4115-88cd-f637b2be02ae",
     "https://www.shopify.com/careers?ashby_jid=86f7a932-ce76-44ac-bc4d-a72180373a88"),
    # UltiPro: ?opportunityId=, same family
    ("https://recruiting.ultipro.com/AME1070/JobBoard/b66d/OpportunityDetail?opportunityId=3fb5b7f0",
     "https://recruiting.ultipro.com/AME1070/JobBoard/b66d/OpportunityDetail?opportunityId=926d1e01"),
    # a meaningful "us" path segment must not be eaten as a locale
    ("https://careers.example.com/us/en/job/123",
     "https://careers.example.com/gb/en/job/123"),
    # 🔴 The 2026-08-31 gh_jid strip is bounded to "value == last path segment". A
    # gh_jid that does NOT restate the path is real identity and must still key --
    # this is the Shopify/ashby_jid lesson in its Greenhouse form.
    ("https://job-boards.greenhouse.io/x/jobs/123?gh_jid=999",
     "https://job-boards.greenhouse.io/x/jobs/123"),
    ("https://job-boards.greenhouse.io/x/jobs/123?gh_jid=999",
     "https://job-boards.greenhouse.io/x/jobs/123?gh_jid=998"),
    # the /apply strip must not eat the only meaningful segment
    ("https://example.com/apply", "https://example.com/"),
]


def check_core_items_are_net_anchored():
    """🔵 STRUCTURAL GUARD, added 2026-08-31 — not a title case.

    CLAUDE.md: "Criteria changes must never shrink the sweep, AND A WIDENED BAR MUST
    WIDEN THE NET." Adding a core item widens the bar. It is only safe WITHOUT touching
    implementation.md's mandated enumeration net when every word-tuple in CORE_ITEMS is
    anchored on a word that already sits in BORDERLINE_ITEMS -- because then any title
    the item can match was already being fetched and already reached the candidate net.

    A bare ("modeler",) or ("developer",) core item would fail this check, and rightly:
    `modeler` and `modeling` appear ZERO times in implementation.md, so promoting either
    unanchored would widen the bar past the net and lose postings silently.

    If this fires, do NOT delete the offending item reflexively -- either anchor it, or
    widen the enumeration net in implementation.md FIRST and then record why.
    """
    net_words = set(w for item in M.BORDERLINE_ITEMS for w in item)
    problems = []
    for item in M.CORE_ITEMS + M.ANALYST_ITEMS:
        if not any(w in net_words for w in item):
            problems.append(
                "CORE/ANALYST item {0!r} is not anchored on any BORDERLINE_ITEMS word "
                "-- the bar would outrun the enumeration net".format(item))
    return problems


# 🔴 THE EXCLUDED-AUDIT `would_be_tier` FIELD, added 2026-09-04.
#
# The audit list is the ONLY defence against a mis-scoped exclusion word silently deleting
# real core/analyst matches -- rules.md §4: "A count is a statistic; the list is a finding."
# It was empty by construction on every run before this, because callers computed it from
# base_tier(), which early-returns None for an excluded title. would_be_tier() answers the
# question base_tier() cannot.
#
# ⚠️ Each case is (title, expected would_be_tier). Every title marked EXCLUDED below is
# asserted separately to return None from base_tier() -- that pairing is the regression
# guard, since a would_be_tier() that merely delegated to base_tier() would pass the
# None cases and fail these.
WOULD_BE_TIER_CASES = [
    # -- EXCLUDED and genuinely core/analyst: these are the rows the audit list exists for.
    ("Summer 2027 Data Engineering Intern", "core"),
    ("Data Engineering Intern", "core"),
    ("Data Analyst Intern", "analyst"),
    ("Business Intelligence Analyst Apprentice", "analyst"),
    ("Campus Data Modeler - New Grad", "core"),
    # Exclusion beats routing (rules.md §1), but the audit still reports which BAR was
    # cleared -- so a seniority noun does not turn this into None or into "lead_manager".
    ("Campus Graduate Masters Full-Time Manager - 2027 Data Engineering", "core"),
    ("Lead Data Analyst Co-op", "analyst"),

    # -- EXCLUDED but never a tier candidate: must NOT pad the audit list.
    ("Retail Sales Intern", None),
    ("Pharmacy Intern", None),
    # Borderline-only. The audit is core/analyst ONLY -- rules.md §4: "borderline-only
    # withholds are counted in counts.excluded but do not enter the audit list."
    ("Data Governance Intern", None),
    ("SQL Reporting Intern", None),

    # -- NOT excluded. would_be_tier() is defined on any title, and must agree with the
    # ordinary bar so a caller cannot get two different answers for the same title.
    ("Senior Data Engineer", "core"),
    ("Data Analyst", "analyst"),
    ("Lead Data Engineer", "core"),          # routing is NOT applied here, by design
    ("Senior Business Intelligence Architect", "core"),
    ("Warehouse Associate", None),
]

# The titles above that `is_excluded()` must agree are excluded. Listed explicitly rather
# than derived, so that a change to EXCLUDE_WORDS which silently stops excluding one of
# them fails here instead of quietly shrinking the audit list.
WOULD_BE_TIER_EXCLUDED = [
    "Summer 2027 Data Engineering Intern",
    "Data Engineering Intern",
    "Data Analyst Intern",
    "Business Intelligence Analyst Apprentice",
    "Campus Data Modeler - New Grad",
    "Campus Graduate Masters Full-Time Manager - 2027 Data Engineering",
    "Lead Data Analyst Co-op",
    "Retail Sales Intern",
    "Pharmacy Intern",
    "Data Governance Intern",
    "SQL Reporting Intern",
]


def check_would_be_tier_is_not_base_tier():
    """🔵 STRUCTURAL GUARD, added 2026-09-04 — not a title case.

    Proves the defect this function was added for is actually closed, in BOTH directions:

      1. every WOULD_BE_TIER_EXCLUDED title is genuinely excluded, and
      2. base_tier() returns None for it -- so a caller using base_tier() to build the
         audit list ships an empty list, which is exactly what happened before 2026-09-04.

    If (2) ever stops holding, base_tier() has changed meaning and this module's callers
    need re-reading. If (1) stops holding, the exclusion set moved under the test.
    """
    problems = []
    for title in WOULD_BE_TIER_EXCLUDED:
        if not M.is_excluded(title):
            problems.append(
                "WOULD_BE_TIER_EXCLUDED title is no longer excluded: {0!r} -- the "
                "exclusion set moved, re-check the audit list".format(title))
        elif M.base_tier(title) is not None:
            problems.append(
                "base_tier({0!r}) = {1!r}, expected None -- base_tier has changed meaning "
                "and the would_be_tier() rationale needs re-reading".format(
                    title, M.base_tier(title)))
    # At least one excluded title must actually reach a tier, or the whole guard is
    # vacuous and would pass against a would_be_tier() that just returned None.
    if not any(M.would_be_tier(t) for t in WOULD_BE_TIER_EXCLUDED):
        problems.append(
            "no WOULD_BE_TIER_EXCLUDED title reaches core/analyst -- the audit-list "
            "guard is vacuous")
    return problems


# 🔴 REQ-ID FOLDING, ruled 2026-08-31 r3: narrow, per-shape, opt-in. Pairs that MUST share
# a (shape, req id) key -- i.e. the fold recognises them as the same requisition.
REQID_SAME = [
    # Adobe dual-scheme: cross-host AND a different path position for the req id.
    ("https://careers.adobe.com/us/en/job/R170588/Principal-Scientist-Data-Pipeline-Engineer",
     "https://adobe.wd5.myworkdayjobs.com/external_experienced/job/San-Jose/Principal-Scientist---Data-Pipeline-Engineer_R170588"),
    ("https://careers.adobe.com/us/en/job/R166535/AEP-Lead-Data-Solutions-Engineer",
     "https://adobe.wd5.myworkdayjobs.com/external_experienced/job/San-Jose/AEP-Lead-Data-Solutions-Engineer_R166535"),
    # same req, different city slug and a -1 revision (Adobe R170861, live in the tracker)
    ("https://adobe.wd5.myworkdayjobs.com/external_experienced/job/Noida/Senior-Data-Engineer_R170861",
     "https://adobe.wd5.myworkdayjobs.com/external_experienced/job/Noida/Data-Science-Engineer-3_R170861-1"),
    # Pantheon cross-host Greenhouse namespace
    ("https://job-boards.greenhouse.io/pantheon/jobs/8056205",
     "https://pantheon.io/about/careers/detail?gh_jid=8056205"),
    # Ulta iCIMS path prefix
    ("https://careers.ulta.com/jobs/517925",
     "https://careers.ulta.com/careers/jobs/517925"),
    # Ulta trailing slug (a RETITLE -- the fold recognises it, the CALLER must still report
    # it; see seen_by_reqid()'s docstring)
    ("https://careers.ulta.com/careers/jobs/490486/senior-data-engineer",
     "https://careers.ulta.com/careers/jobs/490486"),
    # Progressive slug drift (also a retitle, and it crossed a classification boundary)
    ("https://careers.progressive.com/jobs/18060418-a-slash-b-testing-analyst-lead/",
     "https://careers.progressive.com/jobs/18060418-a-slash-b-testing-data-analyst-lead/"),
    # PetSmart trailing-slug drift (registered 2026-09-01 r2). The scan BUILDS
    # /jobs/{req} from the Jibe API while the tracker stores /jobs/{req}/{slug}, so
    # exact-URL dedup missed and every reappearing PetSmart title read as new.
    # Proven identity-preserving at the server: /jobs/7723/completely-wrong-slug-here
    # returns 200 with the same posting, i.e. the slug carries no identity at all.
    ("https://careers.petsmart.com/jobs/7664",
     "https://careers.petsmart.com/jobs/7664/senior-data-engineer"),
    # the same drift on the COMPOUND {POSTING_ID}-{LOCATION_ID} form, which is 371 of
    # 400 sampled records -- the fold must key on the WHOLE id, not the prefix
    ("https://careers.petsmart.com/jobs/103680946405-1213302994",
     "https://careers.petsmart.com/jobs/103680946405-1213302994/retail-sales-associate"),
    # Post Holdings (registered 2026-09-08). THREE drifts stack on one requisition: the
    # per-brand iCIMS host vs the aggregate board, the /careers-home path prefix, and a
    # trailing /login. Both pairs below are LIVE tracker collisions that already cost a
    # duplicate persist on 2026-09-04 -- 29572 was tracked from 08-03 and 31755 from 08-18,
    # and both were re-reported as new with byte-identical titles.
    ("https://postholdingsjobs-postholdings.icims.com/jobs/29572/login",
     "https://jobs.postholdings.com/jobs/29572"),
    ("https://postconsumerbrandssljobs-postholdings.icims.com/jobs/31755/login",
     "https://jobs.postholdings.com/jobs/31755"),
    # cross-brand: a Bob Evans requisition resolves on the aggregate board under the SAME
    # bare id -- proven at the server, which is what makes the id space provably shared
    # rather than merely plausibly shared
    ("https://bobevanssljobs-postholdings.icims.com/jobs/31166/login",
     "https://jobs.postholdings.com/careers-home/jobs/31166"),
    # /login carries no identity: the server returns the same posting and title with it
    ("https://jobs.postholdings.com/jobs/29572",
     "https://jobs.postholdings.com/jobs/29572/login"),
]

# Pairs that MUST NOT share a req-id key. These are the ways a narrow fold could go wrong.
REQID_DIFFER = [
    # different reqs at the same employer
    ("https://careers.ulta.com/careers/jobs/490486",
     "https://careers.ulta.com/careers/jobs/517925"),
    ("https://careers.adobe.com/us/en/job/R170588/x",
     "https://careers.adobe.com/us/en/job/R166535/x"),
    # 🔴 Greenhouse is MULTI-TENANT. The pantheon shape must never fold another tenant's
    # board just because the host matches -- that would collapse unrelated employers.
    ("https://job-boards.greenhouse.io/pantheon/jobs/8056205",
     "https://job-boards.greenhouse.io/scopely/jobs/8056205"),
    # different Pantheon reqs
    ("https://pantheon.io/about/careers/detail?gh_jid=8056205",
     "https://pantheon.io/about/careers/detail?gh_jid=8039985"),
    # different Progressive reqs
    ("https://careers.progressive.com/jobs/18060418-x/",
     "https://careers.progressive.com/jobs/18060419-x/"),
    # 🔴🔴 THE LOAD-BEARING PETSMART CASE. Its req id is a compound
    # {POSTING_ID}-{LOCATION_ID}, and ONE POSTING_ID IS SERVED AT MANY LOCATION_IDs AS
    # SEPARATE POSTINGS -- measured live 2026-09-01 r2, req 103680946405 alone appears at
    # 5 distinct LOCATION_IDs in a 400-record sample. Reducing the compound id to its
    # POSTING_ID would collapse those into one and silently suppress four real postings.
    # `companies.md`: "THE REQ ID IS A COMPOUND ... AND MUST NOT BE REDUCED."
    ("https://careers.petsmart.com/jobs/103680946405-1213302994",
     "https://careers.petsmart.com/jobs/103680946405-1213303344"),
    # a plain id must not fold into a compound one that merely starts with it
    ("https://careers.petsmart.com/jobs/7664",
     "https://careers.petsmart.com/jobs/7664-1213302994"),
    # different plain PetSmart reqs
    ("https://careers.petsmart.com/jobs/7664/senior-data-engineer",
     "https://careers.petsmart.com/jobs/7709/data-engineer"),
    # different Post Holdings reqs, across brands and on the aggregate board alike
    ("https://bobevanssljobs-postholdings.icims.com/jobs/31166/login",
     "https://postconsumerbrandssljobs-postholdings.icims.com/jobs/31755/login"),
    ("https://jobs.postholdings.com/jobs/29572",
     "https://jobs.postholdings.com/jobs/31755"),
]

# URLs that must NOT be claimed by the registry at all -- an unregistered shape is never
# folded, which is the whole point of the whitelist.
REQID_UNREGISTERED = [
    "https://job-boards.greenhouse.io/scopely/jobs/4567890",
    "https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/x/y_R248546-2",
    "https://www.shopify.com/careers?ashby_jid=95eb987e-13ca-447b-9d19-0e42aa5ce40c",
    "https://www.indeed.com/viewjob?jk=a7da9c416a1d3625",
    "https://careers.marsh.com/global/en/job/R_355062",
    # 🔴 The petsmart shape is pinned to careers.petsmart.com. PetSmart also serves THREE
    # iCIMS hosts (2careers-, 1cacareers-, crcareers-) plus a Cadient host; those carry a
    # different id space and must never fold against the canonical board.
    "https://2careers-petsmart.icims.com/jobs/7741/login",
    # 🔴 The postholdings shape matches the `-postholdings.icims.com` SUFFIX FAMILY. It must
    # not leak to any other employer's iCIMS tenant -- iCIMS is multi-tenant and req ids are
    # per-account, so folding across accounts would collapse unrelated employers exactly the
    # way a non-tenant-scoped Greenhouse fold would.
    "https://careers-cotiviti.icims.com/jobs/12345/login",
    "https://globalcareers-cotiviti.icims.com/jobs/29572",
    "https://crcareers-petsmart.icims.com/jobs/7664/senior-data-engineer",
]


def check_retitle_survives_the_reqid_fold():
    """🔴 STRUCTURAL GUARD, added 2026-08-31 r3 — not a case-table entry.

    The req-ID fold must NOT swallow a retitle. rules.md §3 permits folding per proven shape
    only on the condition that a same-req hit whose TITLE differs is still reported, because a
    retitle can cross a classification boundary.

    The live case: Progressive 18060418 went "A/B Testing Analyst Lead" -> "A/B Testing DATA
    Analyst Lead". classify() returns None on the old title and "analyst" on the new, so
    silently suppressing it would hide a posting that only just became a match.

    This asserts the three facts the documented caller pattern depends on:
      1. the two URLs do NOT collapse under normalize_url (so plain dedup would report),
      2. seen_by_reqid DOES find the stored key (so the fold recognises the requisition),
      3. the stored title differs from the served one (so the caller reports it flagged).
    """
    problems = []
    stored_url = "https://careers.progressive.com/jobs/18060418-a-slash-b-testing-analyst-lead/"
    served_url = ("https://careers.progressive.com/jobs/"
                  "18060418-a-slash-b-testing-data-analyst-lead/")
    stored_title = "A/B Testing Analyst Lead"
    served_title = "A/B Testing Data Analyst Lead"

    jobs = {stored_url: {"company": "Progressive", "title": stored_title,
                         "location": "US | Remote", "dateFound": "2026-08-01"}}
    url_index = D.build_index(jobs)
    reqid_index = D.build_reqid_index(jobs)

    if D.is_seen(served_url, url_index):
        problems.append("normalize_url collapsed the Progressive retitle -- the two slugs "
                        "must stay distinct URLs")
    found = D.seen_by_reqid(served_url, reqid_index)
    if found != stored_url:
        problems.append("seen_by_reqid did not recognise Progressive 18060418 across the "
                        "slug change: got {0!r}".format(found))
    if found and jobs[found]["title"] == served_title:
        problems.append("fixture is wrong: the retitle case must have DIFFERING titles")

    # The decision helper must reach the same conclusion the recipe above describes.
    verdict, at = D.reqid_verdict(served_url, reqid_index, jobs, served_title)
    if verdict != "retitle":
        problems.append("reqid_verdict called Progressive 18060418 {0!r}, expected "
                        "'retitle' -- a genuine retitle must NEVER be suppressed".format(
                            verdict))

    # 🔴 THE MULTI-KEY FALSE POSITIVE, live on 2026-09-04 r2 (Ulta req 490486).
    # A requisition legitimately holds SEVERAL stored keys -- persisting the drifted URL
    # creates them by design. build_reqid_index() used to keep only the FIRST, so the
    # served title was compared against a stale one and an already-tracked posting was
    # re-reported as a retitle. The stale key is deliberately inserted FIRST here, so a
    # regression to `setdefault` fails this immediately.
    ulta_old = "https://careers.ulta.com/careers/jobs/490486/senior-data-engineer"
    ulta_new = "https://careers.ulta.com/careers/jobs/490486"
    ulta_served = "https://careers.ulta.com/jobs/490486"
    ujobs = {
        ulta_old: {"company": "Ulta Beauty", "title": "Senior Data Engineer",
                   "location": "Bolingbrook, IL", "dateFound": "2026-08-06"},
        ulta_new: {"company": "Ulta Beauty", "title": "Sr Data Engineer (Remote)",
                   "location": "Bolingbrook, Illinois", "dateFound": "2026-08-31"},
    }
    uidx = D.build_reqid_index(ujobs)

    keys = D.seen_all_by_reqid(ulta_served, uidx)
    if len(keys) != 2:
        problems.append("seen_all_by_reqid returned {0} key(s) for Ulta 490486, expected "
                        "2 -- the index is discarding stored keys again".format(len(keys)))

    verdict, at = D.reqid_verdict(ulta_served, uidx, ujobs, "Sr Data Engineer (Remote)")
    if verdict != "suppress":
        problems.append("reqid_verdict called Ulta 490486 {0!r} for a title that is stored "
                        "BYTE-IDENTICAL under the same requisition -- this is the "
                        "manufactured-retitle regression".format(verdict))
    if verdict == "suppress" and at != ulta_new:
        problems.append("reqid_verdict suppressed Ulta 490486 against {0!r}, expected the "
                        "key whose title actually matches ({1!r})".format(at, ulta_new))

    # ...and a genuinely new title under that same multi-key requisition still reports.
    verdict, _ = D.reqid_verdict(ulta_served, uidx, ujobs, "Principal Data Engineer")
    if verdict != "retitle":
        problems.append("reqid_verdict called an UNSEEN Ulta title {0!r}; a real retitle "
                        "must still surface even when other titles match".format(verdict))

    # And the classification boundary the rule exists to protect.
    if M.classify(stored_title) is not None:
        problems.append("fixture drift: old Progressive title should classify None, got "
                        "{0!r}".format(M.classify(stored_title)))
    # 🔴 2026-09-02: the served title carries `Lead`, so it now routes to lead_manager
    # rather than analyst. The property this assertion exists for is UNCHANGED and is what
    # matters -- the retitle still CROSSES A CLASSIFICATION BOUNDARY (None -> a reported
    # tier), which is exactly what a silent req-ID suppress would destroy.
    if M.classify(served_title) != "lead_manager":
        problems.append("fixture drift: new Progressive title should classify lead_manager, "
                        "got {0!r}".format(M.classify(served_title)))
    if M.base_tier(served_title) != "analyst":
        problems.append("fixture drift: new Progressive title's BASE tier should still be "
                        "analyst, got {0!r}".format(M.base_tier(served_title)))

    # An IDENTICAL title on a drifted URL is the case that MAY be suppressed.
    p_stored = "https://job-boards.greenhouse.io/pantheon/jobs/8056205"
    p_served = "https://pantheon.io/about/careers/detail?gh_jid=8056205"
    pjobs = {p_stored: {"company": "Pantheon", "title": "Senior Analytics Engineer",
                        "location": "United States (Remote)", "dateFound": "2026-08-03"}}
    if D.seen_by_reqid(p_served, D.build_reqid_index(pjobs)) != p_stored:
        problems.append("seen_by_reqid failed on the Pantheon cross-host drift")

    return problems


def check_iso2_sets_are_disjoint():
    """🔵 STRUCTURAL GUARD, added 2026-08-31 r3 — not a location case.

    NON_US_ISO2 is consulted BEFORE US_STATE_ABBR in the _LEADING_CC branch, so a code in
    that set is treated as a country outright and never reaches the collision handling. A
    US state abbreviation sitting there is therefore a SILENT US DROP in the one exclusion
    that runs before the bar.

    This is not hypothetical: `AR` and `CO` were both in NON_US_ISO2 until 2026-08-31 r3.
    `CO - Denver` scored non-US (Colorado read as Colombia) and `AR - Little Rock` likewise
    (Arkansas as Argentina), on the state-first shape CVS's entire board uses. Two stored
    postings carried it. `AR` was in BOTH sets and the wrong one won.

    A colliding code belongs in AMBIGUOUS_STATE_COUNTRY, which defers to the hint list
    rather than guessing. If this fires, MOVE the code -- do not delete the assertion.
    """
    problems = []
    overlap = sorted(L.NON_US_ISO2 & L.US_STATE_ABBR)
    if overlap:
        problems.append(
            "NON_US_ISO2 contains US state abbreviation(s) {0!r} -- a leading one of these "
            "resolves non-US outright and silently drops US postings. Move to "
            "AMBIGUOUS_STATE_COUNTRY.".format(overlap))
    not_states = sorted(L.AMBIGUOUS_STATE_COUNTRY - L.US_STATE_ABBR)
    if not_states:
        problems.append(
            "AMBIGUOUS_STATE_COUNTRY contains {0!r}, which are not US state abbreviations "
            "-- the collision handling would never fire for them.".format(not_states))
    return problems


def main():
    failures = []

    failures.extend(check_core_items_are_net_anchored())
    failures.extend(check_iso2_sets_are_disjoint())
    failures.extend(check_retitle_survives_the_reqid_fold())
    failures.extend(check_would_be_tier_is_not_base_tier())

    for title, expected in WOULD_BE_TIER_CASES:
        got = M.would_be_tier(title)
        if got != expected:
            failures.append("would_be_tier({0!r}) = {1!r}, expected {2!r}".format(
                title, got, expected))

    for title, expected in MATCH_CASES:
        got = M.classify(title)
        if got != expected:
            failures.append("classify({0!r}) = {1!r}, expected {2!r}".format(
                title, got, expected))

    for (loc, cc), expected in LOCATION_CASES:
        got = L.is_us(loc, cc)
        if got is not expected:
            failures.append("is_us({0!r}, {1!r}) = {2}, expected {3}".format(
                loc, cc, L.verdict_label(got), L.verdict_label(expected)))

    for a, b in DEDUP_CASES:
        na, nb = D.normalize_url(a), D.normalize_url(b)
        if na != nb:
            failures.append("normalize mismatch:\n    {0}\n -> {1}\n    {2}\n -> {3}".format(
                a, na, b, nb))

    for a, b in DEDUP_MUST_DIFFER:
        na, nb = D.normalize_url(a), D.normalize_url(b)
        if na == nb:
            failures.append("normalize COLLAPSED distinct postings:\n    {0}\n    {1}\n"
                            " -> both {2}".format(a, b, na))

    for a, b in REQID_SAME:
        ka, kb = D.reqid_key(a), D.reqid_key(b)
        if ka is None or kb is None or ka != kb:
            failures.append("reqid_key mismatch:\n    {0}\n -> {1}\n    {2}\n -> {3}".format(
                a, ka, b, kb))

    for a, b in REQID_DIFFER:
        ka, kb = D.reqid_key(a), D.reqid_key(b)
        if ka is not None and ka == kb:
            failures.append("reqid_key COLLAPSED distinct requisitions:\n    {0}\n    {1}\n"
                            " -> both {2}".format(a, b, ka))

    for u in REQID_UNREGISTERED:
        k = D.reqid_key(u)
        if k is not None:
            failures.append("reqid_key claimed an UNREGISTERED shape: {0!r} -> {1!r}".format(
                u, k))

    total = (len(MATCH_CASES) + len(LOCATION_CASES) + len(DEDUP_CASES)
             + len(DEDUP_MUST_DIFFER) + len(REQID_SAME) + len(REQID_DIFFER)
             + len(REQID_UNREGISTERED) + len(WOULD_BE_TIER_CASES))
    if failures:
        print("FAIL: {0} of {1} cases".format(len(failures), total))
        for f in failures:
            print("  - " + f)
        return 1
    print("OK: {0} cases passed".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
