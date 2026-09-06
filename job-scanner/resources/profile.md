# Candidate Profile

Used as the matching criteria when scanning career sites for new postings.

## Target roles
- Data Engineer (Senior / Staff / Lead / Principal)
- Analytics Engineer
- BI Engineer / BI Developer / BI Architect — **`BI Developer` and `Data Modeler` are CORE as of 2026-08-31** (restored from the borderline tier), along with `Analytics Developer`, `Data Developer`, `Database Developer` and the `Business Intelligence Developer` spellings. **`BI Architect` is CORE as of 2026-09-03 r2** — both spellings, `bi architect` and `business intelligence architect`. **`Data Architect` stays borderline** by the operator's explicit instruction — the "if hands-on with pipelines/modeling" qualifier below is a judgement call, which is what the borderline tier is for. See `rules.md` §1.
  - 🔴 **CORRECTED 2026-09-03 r2 — this line previously read *"`Data Architect` and `BI Architect` stay borderline by the operator's explicit instruction."* That was WRONG, and wrong in the way that matters most: it attributed to an explicit instruction something the instruction never said.** The operator's 2026-08-31 words were *"but no **data** architect"* — BI Architect was never mentioned. `rules.md` had it right all along (*"`Data Architect` **alone** remains borderline"*); this file inferred the wider claim and then cited it as ruled. **When these two files disagree, `rules.md` wins — that is exactly the case this was.**
  - Ruled after Humana's `Senior Business Intelligence Architect` was reported as borderline: *"this one should have been in either core or leadership and management, it's senior business intelligence, and then architect."* It is **Core**, since `senior` is not a routing token. `analytics architect` and `database architect` were measured and **declined** in the same ruling. Full measurement and reasoning in `rules.md` §1.
- Data Analyst (added 2026-08-06 — the operator has years of analyst-adjacent experience from reporting/KPI work and wants these included as core matches now, not borderline, given current market conditions)
- Open to: Data Platform Engineer, Data Architect if hands-on with pipelines/modeling

**Not looking for: Data Scientist / ML modeling roles** (decided 2026-08-20). The operator: *"Data Scientist is not me, I know some ML, but I'm not looking for that right now outside of supporting it as a Data Engineer, but not me creating models as a scientist."* They have working ML knowledge and are happy to **support** ML as a data engineer — building the pipelines, platforms and feature data that models run on. They do not want roles where **building the model is the deliverable**. See `rules.md` §1 for how this is applied.

## Seniority
15+ years experience. Primarily targeting Senior, Staff, Lead, or Principal-level individual contributor or team-lead roles. Open to management if it's still hands-on with data architecture.

**Seniority level is not a filter in either direction (confirmed 2026-08-20) — but see the 2026-09-02 carve-out below, which supersedes this in part.** The operator: *"The level doesn't matter, I just want to see them and I'll determine if I want to apply or not."*
- **Don't exclude for looking too junior** (e.g. "Data Engineer I," entry/associate titles) — they don't mind applying if the pay is close to target.
- **Don't push to borderline for looking too senior** (Lead, Principal, Director, VP, Head of) — these are core when the role is a data role.
  - 🔴 **AMENDED 2026-09-02: ALL FIVE OF THESE ARE NOW ROUTED, not demoted.** Lead, Principal, Director, VP and Head of — plus Leader, Leadership, Chief, President and Supervisor — go to the **Leadership & Management** section rather than appearing under Core. They are still matches and are still reported; only the section changed. See the carve-out below.
- The only thing that decides core vs. borderline is **what the role actually is**, not what level it sits at. See `rules.md` §1.

### 🔴 CURRENT — "no intern"; lead and manager get their OWN SECTION (ruled 2026-09-02)

**One exclusion: the `intern` / early-career family** — not reported, not persisted, at any
tier.

**Nothing at lead level or above is excluded. It is reported in its own section.** The operator,
2026-09-02: *"For managers, how about instead of excluding, anything that says lead or
manager we include, but make it it's own section"* — then, widening it the same day:
*"Basically any lead or manager and up level should go to the manager level."* A title that
clears the core or analyst bar and sits at lead level or above goes to the **Leadership &
Management** table instead of Core or Data Analyst. Nothing is dropped. Full rule, token list
and measured cost in `rules.md` §1; implemented in `bin/jobscan_match.py`.

- 🔴 **`Lead` moves out of Core, and that was asked and answered explicitly.** The operator was
  shown that it affects 326 stored postings and that **`Lead Data Engineer` is their own
  current title** — the "Target roles" line above names Lead as a primary IC
  level — and chose to route it anyway. **Do not restore Lead to Core by citing this file.**
- ✅ **`Principal` STAYS ROUTED — RULED 2026-09-03, and this is no longer an open item.**
  The operator: *"Principal should stay routed - yes."* The tension is real and stays recorded:
  `principal` routes **64** stored titles including `Principal Data Engineer`, a pure IC
  role, and the "Seniority" line above names Principal as a primary target level. They were
  asked against a **live instance** — Adobe `Principal Data Analyst, Adobe Stock`, the
  2026-09-03 run's only new company-list match, an IC title reported under a seniority
  heading — and chose to keep it routed. **Do not re-open this by citing this file.**
  Nothing is dropped: routing decides the *section*, never the judgement. Full ruling and
  the reasoning are in `rules.md` §1.
- **Seniority is still not a filter in either direction.** The routing decides which
  *section* a match appears in; it never demotes, drops, or changes the judgement.

⚠️ **The position on management titles has now moved TWICE, and both moves were deliberate —
kept as history so neither reads as drift.**

1. **2026-08-20:** *"they already applied to a 'Senior Manager, Business Intelligence
   Engineer' role. Management titles are core when the role is a data role."*
2. **2026-08-31:** `manager` excluded outright. Measured cost at the time: 375 of 2,151
   stored postings carried `manager`, 66 of the excluded set were core/analyst, and
   **removing the word never changed a single title's tier — 0 of 375.**
3. **2026-09-02:** exclusion reversed; routed to its own section instead.

🔵 **That "0 of 375" measurement is why the routing design is safe**: the word was never
load-bearing on the bar, so routing on it cannot mis-tier anything. **Kohl's `Senior Manager,
Business Intelligence Engineer` — the title from step 1 — comes back** under step 3.

## Must-have match signals (any of these strongly indicate a fit)
- SQL-heavy data modeling / ETL / ELT pipeline work
- Large-scale analytics platforms (high-volume event/record processing)
- Snowflake, Hadoop ecosystem (Hive, Impala, Oozie, MapReduce), Kafka
- Python and/or C++ for data engineering/pipelines
- Tableau or other BI/dashboarding tools
- KPI/metrics definition: retention, churn, LTV, ARPU/ARPPU, cohort analysis, A/B testing
- Cloud data platform migration experience (on-prem → cloud, Hadoop → Snowflake/cloud warehouse)

## Also relevant / adjacent tech (nice-to-have, not required)
- BigQuery, Redshift, Databricks, dbt, Airflow (modern equivalents of prior stack)
- Looker, Power BI (modern equivalents of Tableau)
- Spark

## Constraints
- **🔴 US ONLY (decided 2026-08-25).** The operator: *"if it's non-us don't include it at all."* A posting outside the US is **excluded outright** — not reported, not persisted. This reversed the earlier "report non-US roles, just label them" rule. See `rules.md` §1 for how it's applied, including the ambiguous-location carve-out.
- **Remote/onsite is still NOT filtered** — the company list is pre-curated for employers that offer remote, so a US posting counts whether it's remote, hybrid or onsite.
- No other hard constraints specified yet (salary floor, industry exclusions, etc. — TBD)

