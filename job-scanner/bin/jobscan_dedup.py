"""URL normalization and dedup for Job Scanner.

Ruled 2026-08-30 by the operator: dedup is URL-BASED. If a company reposts a job under a
different URL, they want to see it. This RETIRES the old rules.md section 7 "match on a
stable req ID, not the raw URL" rule.

Normalization is therefore deliberately CONSERVATIVE. Every transform below exists to
absorb a documented cosmetic drift that produced false "new" positives on real runs. A
transform that might collapse two genuinely distinct postings does not belong here --
over-normalizing suppresses exactly the reposts the operator asked to see.

A dedup hit is ALWAYS a suppress, whatever the stored tag (core or borderline).

Drifts absorbed, each from a recorded incident
----------------------------------------------
  scheme      Prize Picks canonical URLs are stored as http://, served as https://
  host case   general
  www.        general
  locale      eBay stores /en-us/apply/job/... against a served /apply/job/...
  path case   Wendy's tracker holds /posting/Engineer---Data/, site serves /engineer---data/
  trail /     general
  query       Greenhouse stores identity in ?gh_jid=; Indeed in ?jk=. Tracking params
              (gh_src, utm_*, ...) drift freely and must not key.
  -N revision Pfizer and Cigna reqs resurface as {id}-1. STRIPPED ONLY for a 1-2 digit
              suffix on a req-id-shaped segment -- PetSmart's compound
              {POSTING_ID}-{LOCATION_ID} carries a 4+ digit tail that must NOT be eaten,
              or every location variant of a posting collapses onto one key.
"""

import re
try:
    from urllib.parse import urlsplit, parse_qsl, urlencode
except ImportError:  # pragma: no cover
    from urlparse import urlsplit, parse_qsl
    from urllib import urlencode

# 🔴 BLACKLIST, NOT WHITELIST, AND THE DIRECTION IS THE WHOLE POINT.
# An unknown param is KEPT. Keeping a tracking param at worst re-reports a posting as
# new -- visible, and the direction the operator asked for. DROPPING an unknown param can
# collapse distinct postings onto one key and silently suppress them.
# Measured 2026-08-30: a whitelist missing `ashby_jid` collapsed 11 distinct Shopify
# postings onto `shopify.com/careers`, and `opportunityId` collapsed 2 at UltiPro.
# Never convert this back to a whitelist.
TRACKING_PARAMS = {
    "gh_src", "src", "source", "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "utm_id", "ref", "referrer", "referer",
    "trk", "trackingid", "tracking_id", "cid", "mcid", "gclid", "fbclid",
    "lang", "locale", "sortby", "sort", "page", "from", "iis", "iisn",
}

# Only a real LANGUAGE code may be stripped as a locale. Matching any two letters ate
# meaningful path segments (a "/us/en/job/..." shape lost "us") and made normalization
# non-idempotent: 98 stored URLs changed again on a second pass.
_LOCALE_LANGS = ("en|es|fr|de|it|pt|nl|ja|zh|ko|ru|pl|sv|da|fi|nb|no|tr|ar|hi|th|vi"
                 "|id|cs|hu|ro|el|he|uk")
_LOCALE_SEG = re.compile(r"^(?:" + _LOCALE_LANGS + r")(?:[-_][a-z]{2})?$", re.IGNORECASE)
# A req-id-shaped segment: optional 0-3 letter prefix, optional separator, then digits.
_REQ_SHAPE = re.compile(r"^[A-Za-z]{0,3}[-_.]?\d[\w.]*$")
# Bounded to 1-2 digits. See the PetSmart note above -- this bound is load-bearing.
_REV_SUFFIX = re.compile(r"-\d{1,2}$")


def _strip_revision(segment):
    """Strip a Workday-style -N revision suffix, but only where it is safe."""
    m = _REV_SUFFIX.search(segment)
    if not m:
        return segment
    base = segment[: m.start()]
    # Only strip when what remains is req-id-shaped. This keeps the strip off slug-style
    # segments where a trailing -12 could be meaningful.
    # Workday carries the req id AFTER THE LAST UNDERSCORE in an otherwise wordy slug --
    # "Lead-Data-Quality-Engineer_R-426591-1" -- so test the underscore tail too, or the
    # revision suffix survives on every Workday URL and Pfizer/Cigna reqs re-report as
    # new on every scan.
    tail = base.rsplit("_", 1)[-1]
    if _REQ_SHAPE.match(base) or _REQ_SHAPE.match(tail):
        return base
    return segment


def normalize_url(url):
    """Return a canonical form of `url` for exact-match dedup."""
    if not url:
        return ""
    raw = url.strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    elif not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw

    parts = urlsplit(raw)

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    segments = [s for s in parts.path.split("/") if s]
    # Drop a leading locale segment (eBay: /en-us/apply/job/...).
    if segments and _LOCALE_SEG.match(segments[0]) and len(segments) > 1:
        segments = segments[1:]
    # Drop a trailing /apply view segment (Adobe, 2026-08-31): the tracker holds both
    # the Workday externalPath and the same path + /apply for the SAME req, so three
    # tracked Adobe reqs re-reported as new. /apply identifies no posting of its own --
    # it is a view of the posting named by the preceding segment. Bounded to leave at
    # least two segments so it can never eat the only meaningful one.
    if len(segments) > 2 and segments[-1].lower() == "apply":
        segments = segments[:-1]
    if segments:
        segments[-1] = _strip_revision(segments[-1])
    path = "/" + "/".join(s.lower() for s in segments)

    # A gh_jid that merely restates the last path segment is pure duplication and must
    # not key (Scopely, 2026-08-31: the board began serving
    # /scopely/jobs/{id}?gh_jid={id} against 13 stored bare-path keys, and 7 tracked
    # reqs re-reported as new). 🔴 BOUNDED DELIBERATELY: a gh_jid that does NOT restate
    # the path is real identity and is still kept. Widening this to "drop gh_jid" would
    # be the whitelist mistake that collapsed 11 Shopify postings.
    last_seg = segments[-1].lower() if segments else ""
    kept = [
        (k.lower(), v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS and v
        and not (k.lower() == "gh_jid" and v.lower() == last_seg)
    ]
    kept.sort()
    query = urlencode(kept)

    out = host + path
    if query:
        out += "?" + query
    return out


def build_index(jobs_map):
    """Map normalized URL -> original tracker key.

    ⚠️ seen_jobs.json's `jobs` map holds two LEGACY STRING values (_comment_r4 and
    _comment_2026-08-07). Type-guard or .get() raises AttributeError.
    """
    index = {}
    for key, value in jobs_map.items():
        if not isinstance(value, dict):
            continue
        index.setdefault(normalize_url(key), key)
    return index


def is_seen(url, index):
    return normalize_url(url) in index


# =========================================================================================
# REQ-ID FOLDING -- NARROW, PER-SHAPE, AND OPT-IN. Ruled by the operator 2026-08-31 r3.
# =========================================================================================
# rules.md S3 retired req-ID keying as the GENERAL rule, and that stands: dedup is
# URL-based, because a genuine repost under a new URL is something the operator wants to see.
# What they ruled here is narrower -- "also match on job number, but only where I've proven
# it's safe" -- so this registry is a whitelist of individually evidenced drift shapes.
#
# 🔴 A SHAPE NOT IN THIS REGISTRY IS NOT FOLDED. Do not add one without running the
# evidence check: every tracker key the shape matches, grouped by extracted req id, with
# the stored titles shown. Register only if the groups are genuinely the same posting.
#
# 🔴 THIS DOES NOT SUPPRESS RETITLES. Callers must compare the served title against the
# stored titles and REPORT a difference, flagged as a retitle -- use reqid_verdict(),
# which makes that decision once so callers stop re-deriving it. ⚠️ Compare against EVERY
# stored key for the requisition, not one: a requisition legitimately holds several, and
# reading only the first manufactured a retitle for an already-tracked Ulta posting on
# 2026-09-04 r2. Measured 2026-08-31 r3: of the 7 proven drift pairs in the tracker, THREE
# carry a changed title, and one of those (Progressive 18060418) crossed a classification
# boundary -- classify() returns None on the old title and "analyst" on the new. Folding
# those silently would destroy exactly the signal URL-based dedup exists to preserve.
#
# Evidence at registration (counts are stored keys sharing an extracted req id):
#   adobe        47 req ids, 6 groups collapse. R166535/R170588 are the cross-host
#                careers.adobe.com <-> CXS pair; R166812/R169536/R170680 are the /apply
#                shape normalize_url already folds; R170861 is a same-req slug+city
#                rewrite. All stored titles within a group are identical.
#   pantheon      3 groups, identical titles, cross-host Greenhouse namespace.
#   ulta          3 groups. 517925 identical; 490486 and 500906 are RETITLES and must
#                report -- they are why the retitle rule exists.
#   progressive   1 group, 18060418, a RETITLE across a slug change.
_REQID_ADOBE = re.compile(r"(R\d{5,})")
_REQID_DIGITS6 = re.compile(r"(\d{6,})")
_REQID_ULTA = re.compile(r"/jobs/(\d{4,})")
_REQID_PROGRESSIVE = re.compile(r"/jobs/(\d{5,})")

# 🔴🔴 PetSmart's req id is a COMPOUND {POSTING_ID}-{LOCATION_ID} and MUST NOT BE REDUCED.
# One POSTING_ID is served at many LOCATION_IDs AS SEPARATE POSTINGS -- measured live
# 2026-09-01 r2: req 103680946405 appears at 5 distinct LOCATION_IDs in a 400-record
# sample, and 371 of those 400 records carry a compound id. Capturing only the leading
# digit run would collapse those into one key and silently suppress four real postings.
# So: capture the WHOLE id segment, and anchor the end so a compound id can never be
# truncated to its prefix.
_REQID_PETSMART = re.compile(r"/jobs/(\d+(?:-\d+)*)(?:/|$)")


def _adobe_reqid(url, host, path, query):
    m = _REQID_ADOBE.search(url)
    return m.group(1).upper() if m else None


def _pantheon_reqid(url, host, path, query):
    gh = query.get("gh_jid")
    if gh and gh.isdigit():
        return gh
    m = _REQID_DIGITS6.search(path)
    return m.group(1) if m else None


def _ulta_reqid(url, host, path, query):
    m = _REQID_ULTA.search(path)
    return m.group(1) if m else None


def _progressive_reqid(url, host, path, query):
    m = _REQID_PROGRESSIVE.search(path)
    return m.group(1) if m else None


def _petsmart_reqid(url, host, path, query):
    m = _REQID_PETSMART.search(path)
    return m.group(1) if m else None


# Post Holdings, registered 2026-09-08. Anchored at the END and allowing ONLY nothing or a
# trailing `/login` after the id.
#
# 🔴 Deliberately NARROWER than the Ulta/PetSmart shapes, which fold any trailing slug. The
# server evidence here covers `/login` and the path/host variants and nothing else, and
# folding more than was proven is the FALSE-NEGATIVE direction -- it silently suppresses
# distinct postings, which rules.md S3 forbids outright ("never let dedup fail toward false
# negatives"). If a slug form ever appears on this board, prove it and widen this then.
_REQID_POSTHOLDINGS = re.compile(r"(?:/careers-home)?/jobs/(\d+)(?:/login)?/?$", re.I)


def _postholdings_reqid(url, host, path, query):
    m = _REQID_POSTHOLDINGS.search(path)
    return m.group(1) if m else None


DRIFT_SHAPES = [
    {
        "key": "adobe",
        "hosts": ("adobe.wd5.myworkdayjobs.com", "careers.adobe.com"),
        "extract": _adobe_reqid,
    },
    {
        "key": "pantheon",
        "hosts": ("job-boards.greenhouse.io", "boards.greenhouse.io", "pantheon.io"),
        # 🔴 Greenhouse is MULTI-TENANT, so on those two hosts the tenant must be named in
        # the path or the fold would collapse unrelated employers who happen to share a req
        # number. `pantheon.io` needs no such guard -- the host IS the tenant. Applying the
        # path guard to it unconditionally is wrong: its path is /about/careers/detail and
        # the tenant appears nowhere in it.
        "tenant_scoped_hosts": ("job-boards.greenhouse.io", "boards.greenhouse.io"),
        "path_must_contain": ("pantheon",),
        "extract": _pantheon_reqid,
    },
    {
        "key": "ulta",
        "hosts": ("careers.ulta.com",),
        "extract": _ulta_reqid,
    },
    {
        "key": "progressive",
        "hosts": ("careers.progressive.com",),
        "extract": _progressive_reqid,
    },
    {
        # Registered 2026-09-01 r2 under the rules.md S3 evidence check.
        #
        # THE DRIFT: the scan BUILDS `careers.petsmart.com/jobs/{req}` from the Jibe API
        # (the record's `slug` == its `req_id`), while the tracker stores the served
        # `/jobs/{req}/{slug}` form. Those normalize differently, so exact-URL dedup
        # missed and any reappearing PetSmart title read as NEW while tracked.
        #
        # THE EVIDENCE (S3 requires identity, not plausibility): the server ignores the
        # slug outright -- `/jobs/7723/completely-wrong-slug-here` returns HTTP 200 with
        # the same posting and the same title as `/jobs/7723`. The slug carries no
        # identity, so folding on the id cannot merge two different postings.
        #
        # ⚠️ There were ZERO collapse groups in the tracker to inspect, because the built
        # form was never persisted -- only the slug form is stored. The evidence is
        # therefore live-board rather than tracker-derived, which is a weaker provenance
        # than the four shapes above; it is recorded that way in rules.md S3.
        #
        # 🔴 The host is pinned to the canonical board. PetSmart also serves three iCIMS
        # hosts (2careers-, 1cacareers-, crcareers-) and a Cadient host, which carry a
        # different id space and must never fold against this one.
        "key": "petsmart",
        "hosts": ("careers.petsmart.com",),
        "extract": _petsmart_reqid,
    },
    {
        # Registered 2026-09-08 under the rules.md S3 evidence check.
        #
        # THE DRIFT: THREE variants stack on one requisition -- the per-brand iCIMS host
        # (`{brand}jobs-postholdings.icims.com`) vs the aggregate board
        # (`jobs.postholdings.com`), the `/careers-home` path prefix the aggregate board
        # 302s to, and a trailing `/login` on the login-gated page. All normalize
        # differently, so exact-URL dedup missed.
        #
        # THE COST, ALREADY PAID: reqs 29572 and 31755 are each stored TWICE -- tracked
        # 2026-08-03 and 2026-08-18 on the iCIMS hosts, then re-reported as new and
        # persisted again on 2026-09-04 under the aggregate host, with BYTE-IDENTICAL
        # titles. Unlike PetSmart, the collision IS visible in stored data.
        #
        # THE EVIDENCE (S3 requires identity, not plausibility), all live-server:
        #   - `jobs.postholdings.com/jobs/31166` returns the BOB EVANS posting
        #     `Sr. Manager, Consumer Insights`, whose only stored key is on
        #     `bobevanssljobs-postholdings.icims.com`. The aggregate board resolves ids
        #     that originate on the brand subdomains, so THE ID SPACE IS PROVABLY SHARED
        #     ACROSS BRANDS -- a structural guarantee, not an inference from titles.
        #   - `/jobs/29572/login` returns the same posting and title as `/jobs/29572`, so
        #     `/login` carries no identity.
        #   - Garbage control `/jobs/99999999` returns 404, so the endpoint discriminates.
        #
        # 🔴 iCIMS IS MULTI-TENANT and req ids are per-account, so the host family is
        # pinned to the `-postholdings.icims.com` suffix. Folding across iCIMS accounts
        # would collapse unrelated employers exactly as a non-tenant-scoped Greenhouse
        # fold would -- pinned by the Cotiviti cases in REQID_UNREGISTERED.
        "key": "postholdings",
        "hosts": ("jobs.postholdings.com",),
        "host_suffixes": ("-postholdings.icims.com",),
        "extract": _postholdings_reqid,
    },
]


def _host_matches(host, shape):
    """Exact host membership, plus an optional pinned SUFFIX family.

    The suffix form exists for employers running one iCIMS account behind several branded
    subdomains. It is a whitelist like everything else here: a suffix must be specific
    enough that only one employer's tenants can match it.
    """
    if host in shape["hosts"]:
        return True
    for suffix in shape.get("host_suffixes", ()):
        if host.endswith(suffix):
            return True
    return False


def reqid_key(url):
    """(shape_key, req_id) for a URL matching a registered drift shape, else None."""
    if not url:
        return None
    raw = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path
    query = {k.lower(): v for k, v in parse_qsl(parts.query, keep_blank_values=False)}

    for shape in DRIFT_SHAPES:
        if not _host_matches(host, shape):
            continue
        need = shape.get("path_must_contain")
        scoped = shape.get("tenant_scoped_hosts", shape["hosts"])
        if need and host in scoped:
            if not any(n in (path + "?" + parts.query).lower() for n in need):
                continue
        rid = shape["extract"](raw, host, path, query)
        if rid:
            return (shape["key"], rid)
    return None


def build_reqid_index(jobs_map):
    """Map (shape_key, req_id) -> LIST of original tracker keys, registered shapes only.

    🔴 EVERY stored key is kept, not just the first. This was `index.setdefault(rk, key)`
    until 2026-09-04 r2, which discarded every key after the first and MANUFACTURED
    RETITLES -- see reqid_verdict(). One requisition legitimately holds several stored
    keys: persisting the drifted URL (ruled 2026-08-31 r3) CREATES them by design, and
    Stryker holds three non-collapsing namespaces, Adobe three, Ulta two.

    ⚠️ Same legacy-string guard as build_index().
    """
    index = {}
    for key, value in jobs_map.items():
        if not isinstance(value, dict):
            continue
        rk = reqid_key(key)
        if rk:
            index.setdefault(rk, []).append(key)
    return index


def seen_all_by_reqid(url, reqid_index):
    """EVERY stored tracker key for this requisition, oldest first. [] if none.

    Prefer reqid_verdict() -- it makes the suppress/retitle decision that callers
    otherwise re-derive, which is how the 2026-09-04 defect reached the report.
    """
    rk = reqid_key(url)
    if not rk:
        return []
    return list(reqid_index.get(rk, ()))


def seen_by_reqid(url, reqid_index):
    """One stored tracker key for the same requisition under a drifted URL, else None.

    ⚠️ Kept for "is this requisition known at all" checks. It returns an ARBITRARY key
    (the oldest) when several are stored, so it MUST NOT be used to decide suppress vs
    retitle -- that is what produced the false positives. Use reqid_verdict().
    """
    keys = seen_all_by_reqid(url, reqid_index)
    return keys[0] if keys else None


def reqid_verdict(url, reqid_index, jobs_map, served_title):
    """Decide the req-ID fold outcome. Returns (verdict, stored_url).

        ("suppress", stored)  -- pure URL drift: SOME stored key for this requisition
                                 carries a byte-identical title
        ("retitle",  stored)  -- same requisition, and NO stored title matches; must be
                                 reported, never silently suppressed (rules.md S3)
        ("new",      None)    -- requisition not known under any registered shape

    🔴 WHY THIS EXISTS, AND WHY THE COMPARISON IS OVER **ALL** STORED TITLES.
    The documented recipe used to read one stored key and compare against it. When a
    requisition has several stored keys the comparison could land on a stale one, so a
    posting whose current title was ALREADY TRACKED got reported as a retitle. Live on
    2026-09-04 r2: Ulta req 490486 is stored as "Senior Data Engineer" (2026-08-06) AND as
    "Sr Data Engineer (Remote)" (2026-08-31); the index kept the 08-06 key, so the served
    "Sr Data Engineer (Remote)" -- tracked four days -- was re-reported.

    🔵 The retitle half of the 2026-08-31 r3 ruling is UNCHANGED and still load-bearing: a
    genuine retitle is never silently suppressed, because a retitle can cross a
    classification boundary (Progressive 18060418, "A/B Testing Analyst Lead" ->
    "A/B Testing Data Analyst Lead": classify() returns None on the old title and
    "analyst" on the new). This only stops a MATCHED title being called a retitle.

    Titles are compared after stripping surrounding whitespace, and a stored entry with no
    title can never satisfy the match.
    """
    keys = seen_all_by_reqid(url, reqid_index)
    if not keys:
        return ("new", None)

    served = (served_title or "").strip()
    for key in keys:
        stored = jobs_map.get(key)
        if not isinstance(stored, dict):
            continue
        stored_title = (stored.get("title") or "").strip()
        if stored_title and stored_title == served:
            return ("suppress", key)
    return ("retitle", keys[0])


def reqid_collapse_report(jobs_map):
    """Which stored keys share a (shape, req id). Run BEFORE trusting a registry change.

    Every group here is a set of stored postings the fold would treat as one requisition.
    Verify each -- and note which carry differing titles, since those must still report.
    """
    groups = {}
    for key, value in jobs_map.items():
        if not isinstance(value, dict):
            continue
        rk = reqid_key(key)
        if rk:
            groups.setdefault(rk, []).append(key)
    return {k: v for k, v in groups.items() if len(v) > 1}


def collapse_report(jobs_map):
    """Which stored keys collapse onto the same normalized URL.

    Run this before trusting a normalization change. Any group here is a pair of stored
    postings the new rule would treat as one -- verify each is genuinely the same posting.
    """
    groups = {}
    for key, value in jobs_map.items():
        if not isinstance(value, dict):
            continue
        groups.setdefault(normalize_url(key), []).append(key)
    return {k: v for k, v in groups.items() if len(v) > 1}
