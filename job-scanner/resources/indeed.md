# Indeed Search — separate source, kept apart from the company-list scan

This is a second, independent source alongside the company career-site scan (`companies.md`/`implementation.md`). It's a single saved Indeed search rather than a list of employers, so it's tracked in its own files and reported in its own section — not mixed into `companies.md`, `implementation.md`, or `seen_jobs.json`.

## Search config

- **🔴 FIVE separate queries, run and merged client-side (changed 2026-08-25 on the operator's ruling — was two).** Each is deliberately narrow enough to land well under the 15-record page-1 ceiling:
  1. `title:(data engineer)`
  2. `title:(data analyst)`
  3. `title:(analytics engineer)`
  4. `title:(data architect)`
  5. `title:(BI engineer OR business intelligence engineer)`
  - Fetch all five against the same `l=`/`radius=`/`fromage=` params, extract each independently, then union all result sets and dedup by `jobkey` before diffing against `indeed_seen.json`.
  - **Why five.** The old two-query set had outgrown page 1: on 2026-08-25 query 1 reported a meta count of **30 against 15 extractable** and query 2 **19 against 16** — under-covering by ~18 postings per run, double the ~9 measured on 2026-08-24 r2. **The ceiling is fixed at 15 while the result counts grow, so the gap widened on its own.** The operator ruled to split rather than narrow: **the 25mi radius and the full title list both stay** — several live matches sit in Oak Brook, Naperville and Downers Grove, which a smaller radius would drop.
  - 🔴 **FLAG ON `extracted == 15`, NOT on the meta count (corrected 2026-08-25 r2 — the meta count is wrong in BOTH directions).** Measured on the first run under this five-query set: `totalJobCount` *under*-reported on all three narrow queries (q3 **5** reported vs **10** extracted, q4 **3** vs **8**, q5 **0** vs **5**) while over-reporting on the two broad ones (q1 **24** vs 15, q2 **21** vs 15). So a low meta count proves nothing and a high one is only a hint. **The page-1 ceiling is a hard 15 records, so a query that extracts exactly 15 is saturated by definition — that is the reliable signal, and it needs no meta field at all.** Report it rather than silently under-covering.
  - ⚠️ **The split helped but did NOT close the gap: q1 and q2 both still saturate.** Under-coverage went ~18 → **~15 postings per run**. Title-splitting has reached its limit.
  - **🟢 THE SATURATION RESPONSE IS NOW FACET-VARIANT UNIONING, NOT REPORTING AND MOVING ON** *(standing method, ruled 2026-08-26)*. **Any query extracting ≥15 gets the three `explvl` variants run and unioned** — see the Fetch method section below for the full recipe. It recovers ~3 records per run for ~6 requests. **Radius and title list stay fixed** per the 2026-08-25 ruling; this is the lever that replaced splitting.
  - 🔴 **CORRECTION 2026-08-26 — THE PAGE-1 CEILING IS NOT A HARD 15. q2 extracted 16.** So `extracted == 15` is a **sufficient** saturation signal, not a necessary one: a query extracting 16 may be saturated too. q1 extracted exactly 15 and was genuinely saturated, so the signal still works in the direction it was adopted for — but **do not read `extracted == 16` as "not saturated."**
  - 🔴 **`totalJobCount` WRONG IN BOTH DIRECTIONS FOR A SEVENTH CONSECUTIVE RUN (2026-08-27): q1 32 vs 15 extracted, q2 34 vs 15, q3 7 vs 7, q4 2 vs 6, q5 0 vs 5.** It stays unusable in either direction; `extracted >= 15` remains the only saturation signal worth acting on.
  - 🔴 **EIGHTH consecutive run, now under the 8-query set (2026-08-31): under-reported on
    SIX of eight and over-reported on two.** q1 26 vs 13 extracted, q2 2 vs 7, q3 3 vs 8,
    q4 **0 vs 5**, q5 **0 vs 5**, q6 27 vs 11, q7 1 vs 6, q8 4 vs 8. **Two queries reported
    a meta count of zero while returning five extractable records each** — the cleanest
    demonstration yet that a zero here is not a zero. Do not use this field for anything.
  - 🔴 **NEW 2026-08-26 — SPONSORED PLACEMENTS BYPASS `fromage=7`, and they consume page-1 capacity.** Six FBI `Special Agent` postings and a `Remote Licensed Clinical Psychologist` listing returned dated **"22 days ago"** under a 7-day filter. **This explains a previously unexplained behaviour**: why the narrow queries pad out with wholly unrelated titles (q3 returned 10 records against a meta count of 5, q4 8 against 3, q5 **5 against 0**). Those slots are **sponsored injections, not relevance-ranked near-misses.** ⚠️ **Consequence for coverage: the effective ceiling for genuine matches is 15 minus however many sponsored slots Indeed injects** — so a query can be saturated on real results while extracting fewer than 15 of them. This makes the saturation problem worse than the recorded figures suggest.
  - This split is also what the source itself forces — see the query-merge gotcha immediately below.
- **Query-merge gotcha (confirmed 2026-08-06 r4): do NOT just add "data analyst" into the same 5-term `title:(...)` OR list.** Tested directly: `title:(data engineer OR analytics engineer OR data architect OR BI engineer OR data analyst)` returned exactly 13 results, and all 13 were Data Analyst titles — byte-identical to running `title:(data analyst)` alone. The original 4 terms' results (17 meta-reported, 14 extracted) were completely absent from the merged query, even though those postings were still live (re-confirmed by running the original 4-term query separately, same day, same fetch). Indeed's `title:(...)` operator does not reliably OR-combine 5 terms — it appears to collapse toward whichever term(s) dominate relevance ranking rather than doing a literal boolean union. **Always run the queries separately and merge in code, never combine into one big OR list.** *(This is why the 2026-08-25 split to five single-title queries is the natural direction for this source, not a workaround: the operator was never doing a real union anyway. The one remaining OR — `BI engineer OR business intelligence engineer` — is two spellings of the same title, not two different titles, and should be watched for the same collapse.)*
- **All eight queries are title-scoped** using Indeed's `title:(...)` operator, not plain fuzzy keyword search. This restricts matching to the job title field itself, cutting most fuzzy-match noise (a plain `q=data engineer` pulled in "Endpoint Architect," "Senior Delivery Manager," "Cybersecurity Engineer" — anything with "data" or "engineer" anywhere in the JD). Confirmed 2026-08-06: title-scoping alone cut an unfiltered ~1,566-result query down to ~122; combined with the date filter below, into the low teens per query.
- `fromage=7` — restrict to postings from the last 7 days. This is the key that makes the page-1-only limit (see below) a non-issue: combined with title-scoping, the total result count (16, confirmed 2026-08-06) comfortably fits on a single unauthenticated page, so there's no real coverage gap day-to-day as long as this scan runs at least every few days. Run it daily anyway to keep `indeed_seen.json` current and catch things early.
- Location: `Chicago, IL`, radius `25` miles
- **🔴 QUERY SET REBUILT 2026-08-30** to mirror the rewritten `rules.md` §1 keyword list.
  Was 5 queries, now 8. The last OR pair was split per the query-merge gotcha above — two
  spellings of one title is exactly the case that gotcha says to watch. Full URLs (all
  share `&l=Chicago%2C+IL&radius=25&fromage=7`):
  1. `https://www.indeed.com/jobs?q=title%3A%28data+engineer%29&l=Chicago%2C+IL&radius=25&fromage=7`
  2. `https://www.indeed.com/jobs?q=title%3A%28database+engineer%29&l=Chicago%2C+IL&radius=25&fromage=7`
  3. `https://www.indeed.com/jobs?q=title%3A%28analytics+engineer%29&l=Chicago%2C+IL&radius=25&fromage=7`
  4. `https://www.indeed.com/jobs?q=title%3A%28BI+engineer%29&l=Chicago%2C+IL&radius=25&fromage=7`
  5. `https://www.indeed.com/jobs?q=title%3A%28business+intelligence+engineer%29&l=Chicago%2C+IL&radius=25&fromage=7`
  6. `https://www.indeed.com/jobs?q=title%3A%28data+analyst%29&l=Chicago%2C+IL&radius=25&fromage=7`
  7. `https://www.indeed.com/jobs?q=title%3A%28business+intelligence+analyst%29&l=Chicago%2C+IL&radius=25&fromage=7`
  8. `https://www.indeed.com/jobs?q=title%3A%28data+architect%29&l=Chicago%2C+IL&radius=25&fromage=7`
  - **Query 8 is a BORDERLINE FEEDER and is deliberately NOT in `rules.md`'s keyword list.**
    `Data Architect` dropped from core to borderline in the rewrite, but it is a proven
    yielder here and the new spec would otherwise stop looking for it entirely. Keep it;
    classify whatever it returns through `bin/jobscan_match.py` like everything else.
  - `bi analyst` is intentionally absent — `title:(BI analyst)` collapses into query 6's
    result set in practice. Add it if a run shows otherwise.

- **✅ ANSWERED 2026-08-31 — `title:(...)` is an UNORDERED AND, not a phrase match. The
  question is closed and no unordered variants are needed.** Measured on q1
  `title:(data engineer)`, which returned `Senior Analytics Data Engineer`,
  `Senior Lead Data Engineer`, `Data Science / Knowledge Graph Engineer` and — the
  decisive case — **`Data Center Facilities: Assess, Engineer & Design Manager`**, where
  "Data" and "Engineer" are separated by four words and a colon. A phrase-scoped operator
  could not return any of those.
  - **Consequence: Indeed's reach and `bin/jobscan_match.py`'s reach AGREE.** The matcher
    matches words in any order, and so does the source feeding it, so the two sources do
    not have different reach and nothing needs compensating for.
  - ⚠️ The operator being an unordered AND is **not** the same as it doing a real boolean
    OR across terms — the query-merge gotcha above is unaffected and still stands. AND
    within one `title:(...)` works; OR across five titles collapses. Keep running the
    eight queries separately.

- No remote/onsite filter — unlike the company list (which is pre-curated for remote roles), this search is intentionally area-based, per the operator's request to see local jobs too.
- **Matching bar is `rules.md` §1, applied client-side via `bin/jobscan_match.py`** — the same mechanical core/analyst bar and the same borderline net as the company list.
  - 🔴 **The 2026-08-31 `manager` / `intern` exclusions apply here too**, automatically — this source already routes every title through `bin/jobscan_match.py`, so there is nothing to change. **Do NOT add exclusion terms to the query strings**: the queries are the *net*, the exclusions are the *bar*, and narrowing a query would make this a coverage change rather than a criteria change. Query 8 (`data architect`) stays a deliberate borderline feeder. Title-scoping removes most noise but not all. ⚠️ **Note that under the 2026-08-30 rewrite the old worked examples here have flipped**: `Data Center Engineer` (facilities) and `Customer Engineer, Data Analytics` (pre-sales) are now **core matches**, because the exclusions were removed on the operator's instruction. That is intended — they triage them.

## Fetch method

- Plain `GET` on the search URL (`&start={n}` for pagination, increments of ~15/20 per page — increment isn't perfectly fixed, read the actual `rel="next"` link or just keep incrementing `start` by the count of results returned). No auth, no JS execution needed — HTML response (confirmed ~200-2300KB) embeds full structured job data server-side.
- **Client gotcha (confirmed 2026-08-06 r2): a plain Python `requests`-library GET was HTTP 403-blocked (even the bare `indeed.com/` homepage), while `curl` with the identical User-Agent succeeded immediately with HTTP 200.** Not a change in Indeed's blocking posture from what's documented above — just a reminder that the *client* issuing the "plain GET" matters (likely a TLS-fingerprint or default-header difference between `curl` and `requests`). Use `curl` (or an equivalent client with a realistic browser TLS fingerprint) if a `requests`-style fetch gets blocked here before concluding the source itself is down.
- Minor discrepancy noted 2026-08-06 r2: the page's own meta-description count (e.g. "15 ... jobs available") ran 1 higher than the number of complete records the regex extraction actually produced (14) — likely one record hitting a regex edge case rather than a real missing job. Not close to the 15-record flag threshold either way, no action needed.
- Find `window.mosaic.providerData["mosaic-provider-jobcards"]` in the raw HTML — this is a distinct, much larger JSON blob than the smaller `window.mosaic.initialData` config object earlier in the page; don't confuse the two. The real per-job records are under this blob's `"results":[...]` array.
- Per-job fields (confirmed field names): `"displayTitle"`, `"company"`, `"formattedLocation"`, `"formattedRelativeTime"` (e.g. "2 days ago," "30+ days ago" — **not reliably chronological even so**, see below), `"jobkey"` (16-char hex, the stable dedup ID).
- Canonical job URL: `https://www.indeed.com/viewjob?jk={jobkey}`.
- **⚠️ DO NOT zip parallel field lists by index (corrected 2026-08-20).** The previous guidance here was to regex-match each field name independently across the whole blob and zip the parallel lists together by index. **This is unsafe and silently produces wrong data.** On 2026-08-20, query 1 returned **9 `jobkey` hits but 13 `displayTitle` and 13 `formattedLocation` hits** — the extra title/location hits come from records or sub-objects outside the main job-card set, so index-zipping staples the wrong titles and cities onto the wrong job keys. The counts are not guaranteed to align, and when they don't, the mismatch is invisible in the output (you just get a plausible-looking list of wrong rows).
- **Correct extraction: split on record boundaries, then pull each record's own fields.** Split the blob on the literal `"jobkey":"` delimiter. The JSON keys within each record are alphabetically ordered, so `company`, `displayTitle`, `formattedLocation`, and `formattedRelativeTime` all appear **before** the record's own `jobkey` — i.e. they live at the end of the *preceding* chunk. For each chunk, take the **last** occurrence of each field name. A working awk implementation (used 2026-08-20, verified correct association on both queries):
  ```awk
  function lastval(s, key,   pat, val, pos, rest) {
    pat = "\"" key "\":\""; val = ""; rest = s
    while (match(rest, pat)) { pos = RSTART + RLENGTH; rest = substr(rest, pos); val = rest; sub(/".*/, "", val) }
    return val
  }
  BEGIN { RS = "\"jobkey\":\"" }
  NR > 1 { jk = substr($0, 1, 16)
    if (jk ~ /^[a-f0-9]{16}$/)
      printf "%s\t%s\t%s\t%s\t%s\n", jk, lastval(prev,"displayTitle"), lastval(prev,"company"), lastval(prev,"formattedLocation"), lastval(prev,"formattedRelativeTime") }
  { prev = $0 }
  ```
- **🔴 A `jobkey`-HIT COUNT IS NOT A RECORD COUNT — do not use it as an extraction health check** *(found 2026-08-28 r2)*. On q4 the blob carried **12 `"jobkey":"` hits but only 6 UNIQUE jobkeys**, with **zero** shape-rejects: Indeed simply served every record twice. Dedup by `jobkey` absorbs it and no data is lost, but a "hits vs extracted" comparison reads the duplication as a 50% extraction failure and will send a scan chasing a parser bug that does not exist. **Count unique jobkeys, and report shape-rejects separately from duplicates** — those are the two different ways the numbers can disagree, and only one of them is a defect.
- Sanity check either way: if the count of `jobkey` hits does not equal the count of `displayTitle` hits, index-zipping is definitely wrong. Full JSON parsing isn't practical here given the blob's size and the surrounding `window.X = {...};` JS-assignment wrapper (no clean closing boundary to slice on) — record-boundary splitting is the right middle ground.
- **`&sort=date` is NOT reliably chronological** — confirmed 2026-08-06: a `sort=date` request returned "1 day ago," "30+ days ago," "2 days ago," "30+ days ago" interleaved, not descending. Don't use it; `fromage=7` (a hard date filter, not a sort) is the reliable way to bound results by recency.
- **Pagination beyond page 1 is gated behind a sign-in wall — confirmed 2026-08-06.** `start=0` (page 1) works fine unauthenticated. Any `start>0` request (page 2+) gets an HTTP 403 with a redirect body pointing at `secure.indeed.com/auth?...branding=page-two-signin` — Indeed requires a logged-in session past page 1 for unauthenticated/automated-looking traffic. **There is no current workaround** (no login credentials are wired into this workflow, no headless-browser/session-cookie automation here) — so **only page 1 is fetchable, full stop.** This is exactly why the query is scoped with `title:(...)` + `fromage=7` — narrow enough that the whole result set fits on that one page, so the pagination wall stops being a coverage problem rather than something to work around.
- **🔴 The page-1 ceiling is 15 RECORDS. Flag when a query EXTRACTS 15 — do not rely on the meta count.** *(Corrected 2026-08-25 r2; supersedes both the stale "~20-25" and the "check the meta description" method.)* The `"X jobs available"` / `totalJobCount` figure disagreed with the extraction on **four of five queries, in both directions**, so it cannot decide saturation. Since 15 is a hard ceiling, **extracting exactly 15 IS saturation** — flag it to the operator. Per their 2026-08-25 ruling the radius and title list stay fixed; splitting was the only documented lever and has now reached its limit, so see `rules.md` §4 for the measured facet-variant alternative. Pagination is not available as a fallback.
- **🟢 FACET-VARIANT UNIONING IS STANDING METHOD (ruled 2026-08-26 by the operator: *"standing method"*).** Run it on **every query that extracts ≥15 records**, after the five base queries.
  - **The three variants:** `&sc=0kf%3Aexplvl(ENTRY_LEVEL)%3B`, `(MID_LEVEL)`, `(SENIOR_LEVEL)`, appended to the otherwise-identical query URL. **Union all variant results with the base query by `jobkey`**, then dedup against `indeed_seen.json` as normal.
  - **🔴 Trigger is `extracted >= 15`, NOT `== 15`.** This is deliberate and it absorbs the 2026-08-26 correction that the page-1 ceiling is not a hard 15 (q2 extracted 16). A `>=` trigger cannot miss a saturated query on an off-by-one.
  - **Cost:** ~1 request per variant per triggering query — **6 extra requests** on 2026-08-26 (q1 and q2 both triggered). Cheap enough that it needs no cost/benefit judgment per run.
  - **Measured yield, two runs running:** 2026-08-25 r2 recovered **3** records page 1 was hiding (one a `Senior Data Engineer`); 2026-08-26 recovered **3** again, of which **1 was a genuine new core match** ([Dev10 `Entry Level Data Engineer`](https://www.indeed.com/viewjob?jk=d9484a998568c4f6)). Consistent ~3 records per run.
  - **🔴 The facet RANKS, it does NOT filter — this is the mechanism the whole lever depends on, and it is why a facet must NEVER be used to narrow a query.** All three variants return the **same `totalJobCount` as unfiltered** (26 on 2026-08-26, 24 on 2026-08-25 r2). Proof from 2026-08-26, about as clean as it gets: **the `Entry Level Data Engineer` surfaced from the `SENIOR_LEVEL` variant, and a `Lead Data Engineer` from `ENTRY_LEVEL`.** Same behaviour family as the `title:(...)` OR-collapse below.
  - ⚠️ **PER-VARIANT CONTRIBUTION IS NOISE RUN TO RUN — the question of dropping a variant is CLOSED. Keep all three.** `MID_LEVEL` contributed **0** on 2026-08-26 r1, then **2 of 3 (including both Indeed items that reached the report)** on 2026-08-26 r2, then **0** again on 2026-08-27 (where both recoveries came from `ENTRY_LEVEL`). `SENIOR_LEVEL` contributed 2 on r2 and 0 on 2026-08-27. **A variant that looks dead one run carries the whole yield the next.** Record the per-variant split each run as a data point, but do not act on it.
  - **Yield, four runs running: 3 · 3 · 3 · 2 records recovered for 6 requests.** Consistent and cheap.
  - 🔴 **2026-08-27: the variants again did NOT return an identical `totalJobCount`** (q1 base 32, ENTRY 32, MID **25**, SENIOR 32). This re-confirms the 2026-08-26 r2 correction — **the identical-count evidence for "the facet ranks rather than filters" is dead; stop citing it.** The conclusion still holds on the recovery evidence itself.
  - ⚠️ **This does not close the coverage gap, it narrows it.** Title-splitting reached its limit at ~15 postings/run under-covered; facet unioning recovers ~3 of those. **Page 2+ remains unreachable** (sign-in wall), so a residual gap stands.
- **🔴 A TRANSIENT HTTP 403 ON A SINGLE QUERY OR FACET VARIANT CLEARS ON ONE RETRY — retry before declaring this source blocked.** Observed 2026-08-27 r2 on q2's `ENTRY_LEVEL` variant (403, 11,561 B); a single retry returned 200 / 230,643 B. A one-query 403 is not the same event as the documented site-wide block, and treating it as one throws away a whole query's coverage.
  - **🔴🔴 IT FIRED ON ALL EIGHT QUERIES AT ONCE ON 2026-09-11 r2 — A WHOLE-SET 403 THAT WAS STILL NOT A BLOCK.** Every query returned **HTTP 403 / ~28 KB / `<title>Security Check - Indeed.com</title>`** on the first pass. **One retry cleared 7 of 8; q3 cleared on the next.** Final state: 8/8 HTTP 200.
    - 🔴 **This is the case the rule above did not cover, and it is the expensive one.** "A single query" is exactly the scope a reader checks against, so a run seeing all eight fail has apparent grounds to call the source blocked — **and would have thrown away the entire source for the day**, which is the whole-of-Indeed version of the one-query cost this bullet already warns about.
    - ✅ **Rule: retry the whole set at least once before declaring Indeed blocked, however many queries failed.** A block is diagnosed on **controls**, not on a count of failing queries. This run's controls all discriminated: homepage **200**, garbage path **404 `Not Found | Indeed`**, `viewjob` on a garbage jobkey **401** (the documented link-check exemption).
    - ⚠️ **The `Security Check` title is a real signature and should be recorded when seen** — but it is a *rate-limit/challenge* shape that clears, not the site-wide block described in the etiquette note below. Do not conflate them.
- **🟢 2026-08-31 — NO QUERY SATURATED, so the lever did not fire at all.** Extractions were
  13 / 7 / 8 / 5 / 5 / 11 / 6 / 8 against the `>= 15` trigger; max 13. **This is the first
  run on record where the facet-variant stage cost zero requests**, and it is a genuine
  non-event, not a zero yield — do NOT append it to the yield history below as another `0`,
  which would misrepresent the lever as having been tried and failed. Under the 8-query
  split the two historically-saturating queries (`data engineer`, `data analyst`) came in
  at 13 and 11, so the split may finally be holding the ceiling on its own. One run.
- **🟢 2026-09-08 r3 — NO QUERY SATURATED AGAIN, so the lever did not fire at all.** Extractions
  were **14 / 5 / 7 / 6 / 6 / 7 / 6 / 9** against the `>= 15` trigger; max 14, and q1 (`data
  engineer`) came closest without reaching it. **Zero requests spent.** 🔴 **Do NOT append this to
  the yield history below as another `0`** — a lever that never fired has not been tried and
  failed, and recording it as a zero would misrepresent it. Same non-event as 2026-08-31 and
  2026-09-08 r1/r2; contrast 2026-09-07, where it did fire and recovered 0.
  - 🔵 **Five consecutive non-saturating runs now.** The 8-query split may genuinely be holding the
    page-1 ceiling on its own — the two historically-saturating queries came in at 14 and 7.
    **Do not conclude that yet**: sponsored injections consume page-1 capacity, so a query can be
    saturated on real results while extracting fewer than 15 of them.
- **🔴 `totalJobCount` WRONG IN BOTH DIRECTIONS ON 7 OF 8 QUERIES (2026-09-08 r3).** q1 17 vs 14
  extracted, **q2 0 vs 5**, q3 7 vs 7, **q4 1 vs 6**, **q5 1 vs 6**, q6 8 vs 7, **q7 1 vs 6**,
  q8 11 vs 9. **Only q3 agreed.** A query again reported a meta count of **zero while returning
  five extractable records**. The field remains unusable in either direction; `extracted >= 15` is
  still the only saturation signal worth acting on.
- **⚠️ THE SPONSORED-INJECTION FAMILY IS STILL LIVE, AND IT STILL REACHES A TIER.** The FBI
  `Special Agent: Data Science & Intelligence Expertise` posting returned on q7 dated **"7 days
  ago" under `fromage=7`**, reached **borderline** on the net, and was judged away — strip the
  domain words and it is a federal law-enforcement role. **Expect this family every run; it is not
  a parser fault and not a bar fault.**
- **🔴 2026-09-09 r2 — THE SATURATION STREAK BROKE: q1 EXTRACTED EXACTLY 15 AND THE LEVER FIRED, RECOVERING 0.** After **six** consecutive non-saturating runs, `title:(data engineer)` hit the ceiling again. All three `explvl` variants returned HTTP 200 and extracted **15 each — and every one was already in the base set.**
  - 🔴 **THIS IS A REAL ZERO FOR THE YIELD HISTORY, unlike the six runs before it.** The distinction is the whole point of the standing note: a lever that **never fired** has not been tried, while a lever that fired and recovered nothing has. History becomes **`3 · 3 · 3 · 2 · 0 · 0 · 0 · 0`**.
  - 🔵 **Worth noting against the "the 8-query split may be holding the ceiling on its own" hypothesis: it is not.** Five consecutive non-saturating runs looked like the split had solved it; run six saturated. **The split reduces the frequency, it does not remove the ceiling** — and sponsored injections still consume page-1 capacity, so a query can be saturated on real results while extracting fewer than 15.
  - ⚠️ **All three variants extracting exactly 15 is itself a data point**: the variants are subject to the same page-1 ceiling as the base query, so on a saturated query they can only ever re-rank within a full page. That is consistent with "the facet ranks, it does not filter", and it bounds what this lever can ever recover.
- **🟢 2026-09-09 r3 — NO QUERY SATURATED; THE STREAK-BREAK DID NOT PERSIST.** Extractions were
  **14 / 5 / 9 / 6 / 6 / 6 / 6 / 6** against the `>= 15` trigger; max 14, and q1 (`data engineer`)
  again came closest without reaching it — the same 14 it hit on 2026-09-08 r3. **Zero requests
  spent.** 🔴 **Do NOT append this to the yield history as another `0`** — a lever that never
  fired has not been tried and failed. History stays `3 · 3 · 3 · 2 · 0 · 0 · 0 · 0`.
  - 🔵 **Read together with r2, this is the clearest statement of the ceiling's behaviour yet:**
    six non-saturating runs, then r2 saturated at exactly 15, then r3 came in at 14. **q1 sits
    right at the boundary and crosses it intermittently.** Neither "the split has solved it" nor
    "the split has stopped working" is supportable — the split reduces the *frequency* of
    saturation on a query that is permanently marginal. Expect the lever to fire occasionally
    and indefinitely.
- **🟢 2026-09-12 r1 — NO QUERY SATURATED.** Extractions **13 / 5 / 8 / 5 / 6 / 10 / 6 / 8** against
  the `>= 15` trigger; max 13, **q1 (`data engineer`) is the largest query again** after two runs in
  which q6 was. **Zero requests spent.** 🔴 **Do NOT append this to the yield history as another
  `0`** — a lever that never fired has not been tried and failed. History stays
  `3 · 3 · 3 · 2 · 0 · 0 · 0 · 0`.
  - 🔵 **q1's drift is now eight runs long: 15 → 14 → 12 → 13 → 10 → 8 → 13.** It **reversed
    sharply** this run, from its recorded low of 8 back to 13. 🔴 **This kills any reading of the
    previous three runs as a downward trend** — the "permanently marginal, oscillating rather than
    trending" characterisation is the one that keeps fitting, and the 8 was a trough rather than a
    new level. Do not read either direction as the source easing or tightening; sponsored injections
    consume page-1 capacity, so a query can be saturated on real results while extracting well
    under 15.
  - 54 unique jobkeys, **zero shape-rejects and zero duplicate jobkeys** across all eight blobs —
    the duplicate-serving quirk has now been absent **five** runs running.
  - **36 post-bar candidates → 23 suppressed → 1 judged away → 12 new** (5 core, 2 analyst,
    3 lead_manager, 2 borderline) — **the largest Indeed yield on record for this query set.** Empty-index
    control **36 against 12**, the healthy control-≫-reported shape. Zero AMBIGUOUS, zero non-US,
    zero qualifying exclusions (the exclusion was proven live at the company list instead, 27 audit
    rows).
  - ⚠️ **The judged-away row is a pre-sales/GTM title, which is the recurring Indeed shape:** AWS
    `Principal Worldwide Specialist Solutions Architect, Agentic AI, Data & AI GTM` — "GTM" is
    go-to-market, the same family as the recorded `Sr. Solution Sales Executive, Clinical Analytics`
    judgement. Note `principal` did **not** route it: borderline is not routed.
  - ⚠️ **One posting was served twice under two different employers** — `Senior Manager Data Engineer
    (Databricks, Pyspark, Snowflake)` under both **Capital One** and the **Information Technology
    Senior Management Forum**, with distinct jobkeys. Per the known-duplicate rule both are tracked
    separately rather than de-duped on title+company+location. 🔵 **This is the first recorded instance
    where the two copies carry DIFFERENT company names** — the documented quirk describes a same-company
    repost, so a de-dupe keyed on title+location alone would have collapsed them.
  - 🔵 **A company-list employer and Indeed surfaced the same opening**, which is expected and is not a
    duplicate to collapse: United Health's `Senior Data Engineer (DBA)` (Schaumburg IL) is the
    company-list row and Indeed carries it under **Optum**, UHG's subsidiary. The two sources keep
    separate trackers by design, so each is keyed and reported independently.
- **🔴 `totalJobCount` WRONG ON 8 OF 8 FOR A SEVENTH CONSECUTIVE RUN** *(2026-09-12 r1)*. Seventeenth
  consecutive run of the field being wrong in both directions; **q2 and q4 each reported a meta count
  of ZERO while returning five extractable records.** Per the standing note, only the fact of
  disagreement is recorded, not the per-query figures.
- **🟢 2026-09-11 r2 — NO QUERY SATURATED.** Extractions **8 / 5 / 7 / 5 / 7 / 10 / 6 / 8** against
  the `>= 15` trigger; **max 10, again q6 (`data analyst`), not q1** — q1 (`data engineer`) came in at
  **8**, a new low. **Zero requests spent.** 🔴 **Do NOT append this to the yield history as another
  `0`.** History stays `3 · 3 · 3 · 2 · 0 · 0 · 0 · 0`.
  - 🔵 **q1's drift is now seven runs long: 15 → 14 → 12 → 13 → 10 → 8**, and q6 has been the largest
    query for two consecutive runs. **Read it with the standing warning, not as the source easing** —
    sponsored injections consume page-1 capacity, so a query can be saturated on real results while
    extracting well under 15. "Permanently marginal" still fits; a *falling* q1 is as consistent with
    fewer genuine Chicago-area postings as with a looser ceiling, and this source cannot tell them apart.
  - 46 unique jobkeys, **zero shape-rejects and zero duplicate jobkeys** across all eight blobs —
    the duplicate-serving quirk has now been absent **four** runs running.
  - **31 post-bar candidates → 29 suppressed → 1 judged away → 1 new** (core: Google
    `Customer Engineer II, Business Intelligence, NorthAm, Google Cloud`). Empty-index control **31
    against 1** — the healthy control-≫-reported shape. Zero AMBIGUOUS, zero non-US, zero qualifying
    exclusions (the exclusion was proven live at the company list instead, 27 audit rows).
- **🔴 `totalJobCount` WRONG ON 8 OF 8 FOR A SIXTH CONSECUTIVE RUN** *(2026-09-11 r2)*. Sixteenth
  consecutive run of the field being wrong in both directions; **q2 and q4 each reported a meta count
  of ZERO while returning five extractable records.** Per the standing note, only the fact of
  disagreement is recorded, not the per-query figures.
- **🟢 2026-09-11 r1 — NO QUERY SATURATED.** Extractions **10 / 5 / 7 / 5 / 6 / 11 / 6 / 8** against
  the `>= 15` trigger; **max 11, and it was q6 (`data analyst`), not q1** — q1 (`data engineer`) came
  in at **10**. **Zero requests spent.** 🔴 **Do NOT append this to the yield history as another
  `0`.** History stays `3 · 3 · 3 · 2 · 0 · 0 · 0 · 0`.
  - 🔵 **q1's drift around the ceiling is now six runs long: 15 → 14 → 12 → 13 → 10.** This is its
    lowest reading on record and the **first run in which q1 was not the largest query** — but read
    it with the standing warning rather than as the source easing: r2's "12, further below the
    boundary" was partly walked back one run later, and **sponsored injections consume page-1
    capacity**, so a query can be saturated on real results while extracting fewer than 15. The
    "permanently marginal" reading still fits better than either extreme.
  - 49 unique jobkeys, **zero shape-rejects and zero duplicate jobkeys** across all eight blobs —
    the duplicate-serving quirk has now been absent **three** runs running.
  - **35 post-bar candidates → 26 suppressed → 2 judged away → 7 new** (1 core, 4 analyst,
    1 lead_manager, 1 borderline). Empty-index control **35 against 7** — the healthy
    control-≫-reported shape. Zero AMBIGUOUS and zero non-US, with the exclusion proven live at the
    company list rather than here.
- **🔴 `totalJobCount` WRONG ON 8 OF 8 FOR A FIFTH CONSECUTIVE RUN** *(2026-09-11 r1)*. Fifteenth
  consecutive run of the field being wrong in both directions; **q2 and q4 each reported a meta count
  of ZERO while returning five extractable records.** Per the standing note, only the fact of
  disagreement is recorded, not the per-query figures.
- **🟢 2026-09-10 r3 — NO QUERY SATURATED.** Extractions **13 / 5 / 8 / 5 / 6 / 10 / 6 / 7** against
  the `>= 15` trigger; max 13, q1 (`data engineer`) at **13**. **Zero requests spent.** 🔴 **Do NOT
  append this to the yield history as another `0`.** History stays `3 · 3 · 3 · 2 · 0 · 0 · 0 · 0`.
  - 🔵 **q1's drift around the ceiling is now five runs long: 15 → 14 → 12 → 13.** It oscillates
    rather than trends, which is the "permanently marginal" reading holding — **and note r2's "12,
    further below the boundary" is already partly walked back one run later.** Do not read a single
    step away from the ceiling as the source easing. Queries 2–8 were **byte-identical to r2's
    extraction counts** (5/8/5/6/10/6/7), so the whole movement is in q1.
  - 47 unique jobkeys, **zero shape-rejects and zero duplicate jobkeys** across all eight blobs —
    the duplicate-serving quirk has now been absent two runs running.
  - **34 post-bar candidates → 33 suppressed → 1 new** (Molex `Data Analyst`, Lisle IL). Empty-index
    control **34 against 1 reported** — the healthy control-≫-reported shape.
- **🔴 `totalJobCount` WRONG ON 8 OF 8 FOR A FOURTH CONSECUTIVE RUN** *(2026-09-10 r3)*. Fourteenth
  consecutive run of the field being wrong in both directions; **q2 and q5 each reported a meta count
  of ZERO or ONE while returning five and six extractable records**, and q1 over-reported (15 vs 13).
  Per the standing note, only the fact of disagreement is recorded, not the per-query figures.
- **🟢 2026-09-10 r2 — NO QUERY SATURATED.** Extractions **12 / 5 / 8 / 5 / 6 / 10 / 6 / 7** against
  the `>= 15` trigger; max 12, and q1 (`data engineer`) came in at 12 — **further below the boundary
  than the 14s of 2026-09-08 r3 and 2026-09-09 r3.** **Zero requests spent.** 🔴 **Do NOT append this
  to the yield history as another `0`** — a lever that never fired has not been tried and failed.
  History stays `3 · 3 · 3 · 2 · 0 · 0 · 0 · 0`.
  - 🔵 **Consistent with the "permanently marginal" reading, not with either extreme:** q1 has now
    gone 15 (saturated) → 14 → 12 across three runs. It drifts around the ceiling rather than
    trending. Zero shape-rejects and **zero duplicate jobkeys** across all eight blobs this run —
    the duplicate-serving quirk did not appear.
- **🔴 `totalJobCount` WRONG ON 8 OF 8 FOR A THIRD CONSECUTIVE RUN** *(2026-09-10 r2)*. Thirteenth
  consecutive run of the field being wrong in both directions; **q2 and q4 each reported a meta count
  of ZERO while returning five extractable records.** Per the standing note, only the fact of
  disagreement is recorded, not the per-query figures.
- **🔴 `totalJobCount` WRONG ON 8 OF 8 FOR A SECOND CONSECUTIVE RUN** *(2026-09-09 r3)*.
  Twelfth consecutive run of the field being wrong in both directions. Per the standing note
  above, **only the fact of disagreement is now recorded — not the per-query figures.** The
  zero-while-returning-records shape recurred again.
- **🔴 `totalJobCount` WRONG ON 8 OF 8 — THE FIRST RUN ON RECORD WHERE NONE AGREED** *(2026-09-09 r2)*. q1 17 vs **15** extracted, **q2 0 vs 5**, q3 5 vs **10**, **q4 1 vs 6**, **q5 1 vs 6**, q6 5 vs **10**, **q7 1 vs 6**, q8 7 vs **6**. Under-reported on six, over-reported on two, and **a query again reported zero while returning five extractable records.** Eleventh consecutive run. **The field is unusable in either direction and should not be recorded per-query any more — record only that it disagreed.**
- **🔴 FACET-UNION YIELD HISTORY: 3 · 3 · 3 · 2 · 0 · 0 · 0** *(through 2026-08-28 r2)*. **The "consistent ~3 records per run" characterisation is DEAD — THREE consecutive runs have now recovered nothing.** The lever costs 6 requests and the operator's 2026-08-26 ruling says keep all three variants, so **no change is proposed** and the per-variant split should still be recorded each run as a data point. But do not present ~3/run as the expected yield.
- ⚠️ **Whether the variants return the same `totalJobCount` as base is a PER-RUN VARIABLE, not evidence.** They agreed on 2026-08-26 (26) and 2026-08-28 (32) and diverged on 2026-08-27 (base 32, MID 25). **The ranks-not-filters conclusion rests on the recovery evidence, not on count agreement** — cite the recoveries, not the counts.
- **Known duplicate quirk:** the same-looking posting can appear under two distinct `jobkey` values (confirmed 2026-08-06 on an earlier, wider test query: System One's "Data Architect- Wealth Management," Naperville — two different keys, same title/company/location). Likely a genuine staffing-agency repost, not a parsing bug — track both as separate entries rather than trying to de-dupe by title+company+location.

## Risk / etiquette note

Indeed actively fights automated scraping (more aggressively than most single-employer career sites) and its ToS prohibit it. This is a low-volume, personal, once-daily check — functionally the same as the operator manually loading the search page once a day, just automated — but unlike the company-list sites, there's a real chance Indeed rate-limits or blocks this specific pattern over time (CAPTCHA, 403s) if hit too frequently or from a flagged IP/UA. If that happens: don't try to bypass CAPTCHAs or rotate identities to get around a block — just report it as blocked (same as Microsoft/Cotiviti elsewhere in this system) and let the operator know so they can decide whether to keep this source or check manually instead.

## Files

- `indeed_seen.json` — jobs already reported from this search. Same shape as `seen_jobs.json` but kept separate (key = `https://www.indeed.com/viewjob?jk={jobkey}`, value = `{title, company, location, dateFound}`).
- Reported in `matches/{date}-r{N}.md` (first run of a day is `-r1`, changed 2026-09-08) under its own `## Indeed Search` heading, separate from the company-list matches sections — not merged into the same list.
