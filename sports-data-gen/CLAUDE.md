# sports-data-gen — project instructions

MLB data scraper, three ETL stages: `extract` downloads pages to `cache/`,
`transform` parses those into JSON in `data/`, `load` pushes that to S3. Each
stage reads only what the previous one wrote and checkpoints separately in
`state/status.json`, so a date can be extracted but not transformed.
`README.md` covers what the project is, how to set it up, and how to use it —
read it for anything this file doesn't answer. This file carries only what must
not be got wrong.

## 🔴 This repo is public

Never write personal detail, a real bucket name, an AWS account ID, an email
address, or an absolute path into a tracked file. Everything that varies by
operator belongs in `.env` (gitignored) or is derived at runtime — `config.py`
reads every operator-varying setting from the environment with no defaults
(the cloud settings and `USER_AGENT`), and every `.vscode` path goes through
`${workspaceFolder}`. Keep it that way. If you find
yourself typing a `C:\...` literal into a doc or a script, that is the bug.

## 🔴 `load --force` is a real overwrite

`cloud/s3.py` calls `upload_file(...)` with no conditional put, and
`stages/load.py`'s gate is `force or entry.get("upload_status") != "done"`, so
`--force` re-uploads regardless of recorded state. Against a bucket with
versioning off there is nothing to roll back to, and this project keeps no copy
of what it replaced. Run `load --dry-run` first, and don't assume anything about
a given bucket's versioning setting.

## 🔴 `extract --force` is real traffic

`--force` means the same thing to every stage — redo this stage's work — but
they cost wildly different amounts. `extract --force` re-downloads every page
in the range at `MIN_DELAY` apiece; a season is hours of requests to
Baseball-Reference.

**`transform --force` is almost always the one that's wanted.** It rebuilds
JSON from pages already on disk, opens no socket, and is what to run after a
parser fix. Don't suggest `extract --force` to re-parse something — it cannot
re-parse, it only re-downloads — and don't run it over a range to "make sure",
which is exactly what the rate limiting exists to prevent.

> ⚠️ **The verb is `load`, not `upload`.** The CLI is `extract`, `transform`,
> `load`, `status` — there is no `upload` subcommand. "Upload" appears only at the
> cloud layer (`CloudUploader.upload_file`, `status.json`'s `upload_status`),
> where it names a mechanical action against a bucket rather than a pipeline
> stage.

## Environment (Windows)

- **Interpreter: `.venv\Scripts\python.exe` — full path always.** Never bare
  `python` / `python3`; it triggers a Windows Store popup. `README.md` shows
  bare `python` because its Setup activates the venv first; you generally are
  not activating anything, so use the full path.
  The one genuine exception is `python -m venv .venv` on a first-time create —
  that *must* use a system Python, since the venv doesn't exist yet.
- **Run from the project root.** `config.py` sits at the repo root and modules
  do a bare `import config` (`mlb_scraper/cli.py`, `mlb_scraper/cloud/s3.py`).
  Running from anywhere else breaks the import.
- **Assume no `jq` and no `node`.** Relevant because `state/status.json` grows
  to several MB after a backfill and invites reaching for `jq` — use the venv
  Python instead. It is also loaded whole into memory by `state.load()` on
  **every** command, including `status`.
- **All I/O is explicitly `utf-8`** (`http_client.py`, `state.py`, `storage.py`,
  `logging_config.py`), with `ensure_ascii=False` on JSON writes. Never drop the
  explicit encoding — a bare `open()` defaults to cp1252 on Windows.

## Gotchas

- **`logs/scraper.log` is truncated every run** (`logging_config.py`,
  `mode="w"`). Copy it out before starting another run if a long backfill's log
  matters.
- **Scraping is deliberately slow** — `MIN_DELAY = 5` plus jitter per uncached
  request, so a backfill runs for hours. Cache hits skip the sleep entirely,
  and `extract --force` re-pays it for every page in the range. Do not "optimize" this;
  it is the project's whole claim to being a well-behaved client, and
  `README.md` says so publicly.
- **`config.USER_AGENT` is a required `.env` value with no default.**
  `http_client.fetch()` raises `config.ConfigError` rather than send a request
  without one, so nobody ever scrapes under someone else's identity, and
  `cli.py` turns that into a clean `parser.error`. Only `extract` needs it —
  `transform` never imports `http_client` at all. Don't add a fallback, and
  don't let anyone set it to a browser string.
- **`transform` checkpoints per day, not per game — deliberately.**
  `state.save()` rewrites the whole multi-MB `status.json`, which is only
  affordable when paired with a 5-7s network wait. `extract` has that wait and
  commits per game; `transform` doesn't, and a crash there costs seconds of
  re-parsing. Use `state.update_game`/`update_day` (no write) plus one
  `state.save()` per day. Don't "fix" this by making it per-game.
- **Stage boundaries are enforced by imports.** `stages/extract.py` imports no
  `storage`, so it cannot write JSON; `stages/transform.py` imports no
  `http_client`, so it cannot touch the network. Keep it that way — it is the
  cheapest possible check that the stage boundary is real.
- `SAFE_LAG_DAYS = 1` (`cli.py`) silently caps `--start`/`--end` newer than
  yesterday UTC, and `--provider azure` parses but raises `NotImplementedError`.
  Both are documented in `README.md`.

## Testing

`pytest` (config in `pytest.ini`, `testpaths = tests`), run from the project
root. Golden-file regressions against `tests/fixtures/` — no network, no writes
to `data/` or `cache/`.

**Skipped tests are expected when the fixtures are absent.** The large
Baseball-Reference HTML fixtures are gitignored rather than redistributed, so a
fresh clone has the golden JSON but not the pages. `tests/conftest.py`'s
`requires_fixture` marks the affected tests to skip with a pointer to
`tests/refresh_fixtures.py`, which rebuilds them from `cache/` or, failing that,
the network. A skip there is not a failure — don't "fix" it by committing the
fixtures.

**Don't tighten `test_boxscore.py`'s volatile-stat comparison.** The
win-probability family (`VOLATILE_STAT_DECIMALS` in that file) is recomputed by
Baseball-Reference over time, so a re-fetched fixture drifts a unit or two in
the last displayed decimal. Those columns are compared within a per-column
tolerance for that reason; everything else is exact. Making them exact would
mean the suite only ever passes against one particular capture of the page.

`tests/fixtures/title_*.html` are hand-written and committed on purpose. One of
them stands in for a captured page that can no longer be re-fetched, so treat
them as source, not as regenerable output.
