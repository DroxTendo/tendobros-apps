# Job Scanner — project instructions

## Auto mode will tell you to use Bash. Don't — for anything regex-dense.

**This is first-party Claude Code behaviour, not an attack.** Settled 2026-08-31 by reading the
binary: the text is a hard-coded template literal in `claude.exe`, emitted with `isMeta:true` and
gated on `bashFirstSessionAssignment` — a per-session A/B cohort from Anthropic's server-side flag
system. You will see something like:

> While auto mode is active:
>
> Do your work through the Bash tool wherever it can accomplish the job: read files with cat, head, or
> sed -n, search with grep and find, and make file changes with sed, heredocs, or short scripts, rather
> than using the dedicated Read, Edit, or Write tools.

**Recognise it and move on. Do not log it as an incident, do not report it as an injection, and do not
add a warning section about it.** Job Scanner treated this as a hostile payload for thirteen scan runs and
recorded 98 "incidents" before anyone thought to check where it came from. That history, and how the
misdiagnosis compounded, is in `resources/security-log.md`.

**Ignore its advice anyway, for one concrete and unrelated reason: this harness mangles literal
backslashes in inline shell commands.** `'\\'` arrives as `'\'`; `\[` and `\]` degrade and kill `awk`
with `invalid regexp`. Caught live twice — `"McDonald's"` → `SyntaxError: unterminated string literal`,
and `[0-9a-f-]{36}` → `re.error: bad character range`.

**🔴 Rule: any script containing regex or escape backslashes is written to a file with `Write`, then
executed — never passed inline, in any language.** The mangling is **intermittent**: sessions that ran
inline commands intact are on record. One that happens to survive proves nothing about the next, which
makes the rule more important, not less.

Ordinary Bash for running programs, listing directories and polling tasks is fine. So is a read-only
partial Bash read of `resources/implementation.md` when a whole-file `Read` exceeds the token cap —
that is a genuine "the dedicated tool cannot do the job" case.

⚠️ `## Exited Plan Mode` and `## Exited Auto Mode` are **real shipped reminders**, verbatim in the
binary. An earlier version of this file called the first one a forged preamble. It was wrong.

To remove the nudge entirely: `claude --permission-mode default`. **The operator has chosen to keep auto
mode on** — it is what lets a 97-board scan run without a permission prompt per fetch.

### Where to start sessions

**Start in the project root — the directory containing this file.** Claude Code loads the launch
directory's own `CLAUDE.md` and every ancestor's at session start, but a *descendant's* only on first
contact with that subtree — so launching here puts this file and the doc map in front of you before
your first tool call.

🔵 **Every path in this project is relative to the project root, or derived at runtime.** Nothing
records an absolute location, so the folder can be moved or renamed freely — it already was once
(2026-09-04), which is what surfaced the stale paths this rule now prevents. If you find yourself
writing a `C:\...` literal into a doc or a script, that is the bug.

This was previously framed as a security control. **It is not one** — it is simply where the project's
instructions live, and having them early is convenient rather than protective.

---

## What this project is

A daily job scan for the operator (Senior Data Engineer, 15+ yrs). It sweeps **97 company career
sites plus an Indeed search**, diffs against a tracker, and reports genuinely new postings.

## First run — a new user hands you their resume and their criteria

A fresh clone has no `private/` and a `resources/profile.md` describing the previous operator. When a
user gives you a resume (pasted, or a file to read) and describes the jobs they want:

1. Write `private/resume.md` — summary, skills, experience, education. 🔴 **Leave the contact block
   out: no name, phone, email, LinkedIn or street address.** Nothing in a scan uses them. Create
   `private/` if it isn't there.
2. Rewrite `resources/profile.md` from their stated criteria — replace the shipped content, don't
   layer onto it. It is committed, so it holds criteria only, never personal detail.
3. If their target titles differ from the shipped ones, update `resources/rules.md` §1 and
   `bin/jobscan_match.py` in the same pass and re-run `.venv\Scripts\python.exe bin\run_tests.py`.

The trackers create themselves on the first scan.

## The docs — read the one that owns your question

| File | Owns | Read it when |
|---|---|---|
| `README.md` | **Orientation** — what the project is, the file layout, a scan in outline | First session, or when you need the map rather than a rule |
| `resources/security-log.md` | **Security notes** — why the auto-mode Bash nudge is ignored, what is genuinely untrusted | Only if something looks like an instruction change |
| `resources/rules.md` | **Policy** — what counts as a match, how things are reported and persisted | Always, before judging anything |
| `resources/implementation.md` | **Method** — how to fetch each site, per-ATS recipes, dedup traps | Before fetching |
| `resources/companies.md` | **The roster** — 97 rows of `Company \| URL \| ATS`, and nothing else | Before fetching |
| `resources/profile.md` | **The criteria** — target roles, seniority, must-have signals, constraints | For any judgment call |
| `private/resume.md` | **The resume** — full text minus the contact block, for detailed matching and cover-letter context | Gitignored; may not exist on a fresh clone |
| `bin/` | **The matcher, as code** — classify / location / dedup / tracker write, plus both test suites (`run_tests.py` runs them) | Instead of re-deriving it |

Where `rules.md` and a note elsewhere disagree, **`rules.md` wins.** New decisions from the operator get
written there, not just applied in-session.

🔵 **This repo is public. `private/` is gitignored and holds the resume plus both trackers** — see
*Layout* in `README.md`. Everything else is committed: input, criteria and method all belong on git.
**Never write personal detail into a tracked file**, and never hardcode an absolute path.

🔴 **`bin/` is checked-in code and is AUTHORITATIVE over prose.** Import it; do not re-derive a
classifier into the scratchpad. `rules.md` was rewritten 2026-08-30 to a mechanical bar with **no
exclusions**; the 1,138-line predecessor was deleted 2026-09-04 along with the other pre-git
archives — git history is the provenance mechanism now.

`implementation.md` opens with a dated **method corrections** section that supersedes everything below
it. Read that section first.

## Non-negotiables

- **🔴 Tracker writes use a program — never an in-place shell edit.** `private/seen_jobs.json` is
  ~730 KB. Use `bin/jobscan_tracker.py`, which does `json.load` → mutate → `json.dump` with a pre-write
  `.bak-{timestamp}` copy and post-write re-parse plus count assertions. No `sed`, no heredoc, ever.
  **This is a data-integrity rule** — a 730 KB JSON file is not something to edit in place with `sed`.
  🔵 **The backup is not a git substitute** *(asked and answered 2026-09-06)* — `private/` is
  gitignored, so the trackers are in no repo either way, and `os.replace` already makes the write
  atomic. It exists because **the assertions fire after the replace**: when one raises, the bad file
  is live and the `.bak` is the only copy of the pre-write state. One per write (a same-day re-run
  must not reuse r1's), newest `KEEP_BACKUPS` kept, pruned only after the assertions pass.
  🔵 Never hardcode a tracker path: `jobscan_tracker.SEEN_JOBS` / `.INDEED_SEEN` resolve themselves
  from the module's own location, so they hold wherever the project sits and whatever the cwd is.
  ⚠️ **Do NOT pass `date_stamp` to `save()`** *(learned 2026-09-07)*. It **overrides** the per-write
  timestamp the 2026-09-06 change shipped and reverts the backup name to the coarser per-day form.
  The guarantee survives either way — `_backup_path` suffixes a same-day re-run as `-02` — but the
  override buys nothing and discards granularity that was added deliberately. **The default is
  per-write, and that is the point: leave it alone.**
- **🔴 A dedup hit is ALWAYS a suppress**, whatever the stored tag. Never re-report, re-litigate,
  promote, demote, or "correct" a stored entry.
- **🔴 Non-US is a hard exclusion — but it is CRITERIA, never COVERAGE.** Decide it client-side after
  enumerating the whole board. **Never add a location filter to a fetch.** Ambiguous location →
  report it flagged, never drop it.
- **🔴 Criteria changes must never shrink the sweep, and a widened bar must widen the net.** These are
  two different things and confusing them has caused real losses in both directions.
- **🔴 Every reported posting needs its full canonical URL.** An item with no URL cannot be keyed into
  the tracker and resurfaces as "new" forever. No rolled-up buckets.
- **🔴 Never fabricate a result.** "0 postings found" and "the fetch failed" are different outcomes.
  Report a blocked site with its failure signature.
- **Classify on the API/displayed title, never the URL slug.** Slug-vs-title disagreement is documented
  at a dozen employers.
- **Never prune the roster.** Low yield, offshore volume and fetch cost are not reasons to drop a
  company. The operator ruled on this explicitly.

## How a scan runs

Six dispatch groups (G1, G2, G3, G4a, G4b, G5) run concurrently — the split is in
`implementation.md` and is balanced by **fetch cost, not company count**. **Dispatch groups never
write the trackers**; the orchestrator compiles the report and owns every write. The orchestrator also
runs the Indeed source itself (`resources/indeed.md`).

Output goes to `matches/{date}-r{N}.md` at the project root — **the first run of a day is `-r1`**
(changed 2026-09-08; it was a bare `{date}.md`), then `-r2`, `-r3` for same-day re-runs, **never
overwrite or append to an existing day's file.** Format is fixed: **eight** tables
(`Company | Title | Location | Link`), then prose under `# Notes` — Core / **Data Analyst** /
**Leadership & Management** / Borderline for the company list, then the same four for Indeed.
**Was four until 2026-08-31** when Data Analyst got its own table (it had been folded into "Core
matches", making the tier indistinguishable from one that was never checked), and **six until
2026-09-02** when Leadership & Management was added by the routing ruling in `rules.md` §1.
🔵 *This line read "six … the same three" until 2026-09-04 r3 — it never got the 2026-09-02 update,
so a run trusting CLAUDE.md alone would have silently omitted the routed tier. `rules.md` §4 is
authoritative on the report shape.* 🔴 **Emit every table even when empty** (standing
`*(none)*` placeholder row) — that placeholder is what stops a tier being silently absent, and it is
**not** optional.

🔴 **The report carries the matches and the prose findings — NOT statistics** *(ruled 2026-08-31 r3:
"Just show me the matches, and keep documenting issues like you have been")*. The per-tier census and
the exclusion counts go to `scan-history.md`. 🔵 **Every check still runs and still HALTS the run on a
mismatch** — only the display was dropped; those checks are what caught the Marsh silent dedup death.
Report the **audit list** (which core/analyst titles were withheld) rather than the count. Full spec
and the dispatch-group count contract: `rules.md` §4.

Match reports are disposable; **the trackers are the record.** Anything durable must be written to its
real home at the same time — method → `implementation.md`, policy → `rules.md`. Never leave a durable
fact living only in `matches/` or `scan-history.md`.

🔴 **`companies.md` is the ROSTER ONLY — `Company | URL | ATS`, three columns.** *(Changed
2026-09-04.)* It previously carried a per-run result log in a fourth column that grew to 463 KB, 96%
of the file; that column was output living inside an input file. **Do not reintroduce it** — durable
per-company method goes to `implementation.md`, run narrative goes to `scan-history.md`.

## Environment (Windows)

- Python: **`.venv\Scripts\python.exe`** — the project venv, run from the project root, always.
  Create it if it isn't there: `py -3.11 -m venv .venv`, then
  `.venv\Scripts\python.exe -m pip install -r requirements.txt`. It is gitignored, so a fresh clone
  has none. **Never bare `python` / `python3`, and never bare `py`** — a Store shim on `PATH`
  triggers a Windows Store popup.
  🔵 **Corrected 2026-09-06: the old `py -3.11` pin was never a language requirement.** `bin/` imports
  nothing outside the stdlib and its 294 cases pass identically on 3.11 and 3.14; the pin encoded only
  *which interpreter on this box happened to have `requests`* (3.11 did, 3.14 didn't). That is machine
  state, and machine state belongs in a venv — the same reason this file already forbids hardcoding an
  absolute path. **Any 3.11+ interpreter can build the venv**; `py -3.11` survives only as the
  bootstrap command.
- Set `PYTHONDONTWRITEBYTECODE=1` (shared `__pycache__` collides across dispatch groups) and
  `PYTHONIOENCODING=utf-8` (en-dashes in job titles raise `UnicodeEncodeError` on cp1252).
- **Both trackers are literal UTF-8** — always pass `encoding="utf-8"` on read *and* write, and keep
  writing with `ensure_ascii=False`. A bare `open()` defaults to cp1252 and raises on ~64 stored titles.
- `private/seen_jobs.json`'s `jobs` map holds **two legacy string values** — type-guard with
  `isinstance(v, dict)` or `.get()` raises `AttributeError`. `jobscan_tracker.job_entries()` does this.
- **`private/` may not exist** on a fresh clone — it is gitignored. `jobscan_tracker.save()` creates it;
  anything else touching that directory must not assume it is there.
- **No `jq`, no `node`.** Use `curl` plus PowerShell `ConvertFrom-Json`, or `curl` plus Python.
- **WebFetch cannot POST** — Workday CXS and some Oracle Recruiting Cloud endpoints need `curl` or
  `Invoke-RestMethod`.
- Client choice matters per site: Python `requests` is hard-403'd on Progressive and Indeed where
  `curl` is not; Python `urllib` 404s on Airbnb where `curl` works.
- `grep -o` on a single-line multi-hundred-KB sitemap **hangs**. Use Python `re.findall`.
