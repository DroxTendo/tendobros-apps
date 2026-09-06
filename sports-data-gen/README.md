# sports-data-gen

Scrapes daily MLB player batting/pitching stats from
[Baseball-Reference](https://www.baseball-reference.com) as a three-stage ETL
pipeline: `extract` downloads pages to `cache/`, `transform` parses them into
local JSON — two files per game, `hitting_*.json` and `pitching_*.json` — and
`load` pushes that JSON to cloud storage.

It is rate-limited (5s + up to 2s of jitter per request), cache-first (every
fetched page is written to disk and re-read rather than re-fetched, unless you
ask otherwise — see [Flags, by command](#flags-by-command) and
[Postseason tagging](#postseason-tagging)), and resumable (each stage
checkpoints to `state/status.json` separately, so an interrupted run picks up
where it stopped and a date can sit extracted but not yet transformed).

**Contents**

- [Status and scope](#status-and-scope)
- [Data source and terms](#data-source-and-terms)
- [Requirements](#requirements)
- [Setup](#setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Pipeline](#pipeline)
- [Project layout](#project-layout)
- [Output layout](#output-layout)
- [Design notes](#design-notes)
- [Testing](#testing)
- [VS Code](#vs-code)
- [License](#license)

## Status and scope

A personal project, published for reference. It is not looking for
contributions, and there is no release cadence or support commitment.

- **MLB only.** The on-disk and cloud layouts are sport-scoped (`mlb/...`) so
  another sport could reuse the storage and load code, but none is implemented.
- **S3 only.** `--provider azure` parses and then raises `NotImplementedError`.
- **Windows-first.** Developed and run on Windows; the code itself is
  platform-neutral and the test suite passes anywhere, but the Windows paths are
  the ones that get exercised.

## Data source and terms

This scrapes Baseball-Reference, a Sports Reference LLC site. Before you run it:

- **Read their [terms of use](https://www.sports-reference.com/termsofuse.html)
  and `/robots.txt`, and satisfy yourself that your use is permitted.** They
  restrict automated access and bulk reuse. Nothing in this repo grants you any
  right to their data.
- **Don't remove the rate limiting.** `MIN_DELAY = 5` plus jitter in `config.py`
  is the whole reason this is a well-behaved client. A multi-season backfill is
  meant to take hours. The disk cache means you pay that cost only once per page.
- **The user-agent has to be yours.** There is no default: `extract` refuses to
  make a request until you set `USER_AGENT` in `.env`. Give the site an honest
  string that names your copy of this scraper and carries your own contact URL
  or email — never a browser string, and never someone else's identity. See
  [Configuration](#configuration).
- **Redistributing anything you scrape is your responsibility.** This project's
  MIT license covers the code here and nothing else.

## Requirements

- Python 3.11 or newer
- Runtime deps in `requirements.txt` (`requests`, `beautifulsoup4`, `lxml`,
  `python-dotenv`, `boto3`); test deps in `requirements-dev.txt`
- An AWS account and an S3 bucket — but **only if you use `load`**. `extract`
  needs no credentials at all.

## Setup

```
git clone <repo-url>
cd sports-data-gen
python -m venv .venv
```

Activate it. PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

cmd.exe uses `.venv\Scripts\activate.bat`; POSIX shells use
`source .venv/bin/activate`. Then:

```
pip install -r requirements.txt
```

Every command below assumes an activated venv, and all of them must be run
**from the project root** — `config.py` lives there and the modules import it
directly.

Copy `.env.example` to `.env` and fill it in — `USER_AGENT` before you run
`extract`, the AWS settings before you run `load`. `transform` needs neither.
`.env` is gitignored; never commit it.

## Configuration

All of it lives in `.env` (see `.env.example`). `USER_AGENT` is required before
`extract` will make a network request; everything else is read only by `load`.
`transform` reads no configuration and opens no socket.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `USER_AGENT` | for `extract` | — | The exact `User-Agent` header sent on every request. Make it yours. |
| `S3_BUCKET` | for `load` | — | Destination bucket. |
| `AWS_REGION` | for `load` | — | That bucket's region. |
| `UPLOAD_PROVIDER` | no | `s3` | Provider used when `--provider` is omitted. |
| `AWS_ACCESS_KEY_ID` | no | — | Only if you want credentials scoped to this project. |
| `AWS_SECRET_ACCESS_KEY` | no | — | Same. |

Leave the two AWS key variables unset if `aws configure` or an IAM role is
already set up — boto3's default credential chain finds those on its own.

## Pipeline

Each stage reads only what the one before it wrote, so each can be run, re-run
and forced on its own:

| stage | reads | writes | `--force` |
|---|---|---|---|
| `extract` | Baseball-Reference | `cache/` | re-downloads pages already cached |
| `transform` | `cache/` | `data/` | re-parses games already transformed |
| `load` | `data/` | your bucket | re-uploads games already uploaded |

`--force` means one thing everywhere: *redo this stage's work*. It stays
unambiguous because each stage owns exactly one kind of work — and those cost
wildly different amounts: `extract` is hours of rate-limited requests against
someone else's server, `transform` is minutes of local CPU, `load` is an
overwrite you can't undo. Check which stage you're forcing before you type it.

`state/status.json` tracks each stage separately, so a date can be extracted
but not transformed, or transformed but not uploaded. `status` shows what is
stuck where, and `transform` and `load` with no dates simply catch up whatever
is pending:

```
python -m mlb_scraper extract --start 2026-09-05 --end 2026-09-05
python -m mlb_scraper transform
python -m mlb_scraper load
```

## Usage

Four commands: `extract`, `transform`, `load`, and `status`. The first three
are the pipeline, in order; see [Pipeline](#pipeline) for what each owns.
**There is no `upload` command** — the cloud layer says "upload" internally, but
the CLI verb is `load`.

Start with a dry run. Both `extract` and `load` support one, and it is the
cheapest way to confirm a command does what you think it does:

```
python -m mlb_scraper extract --start 2023-04-01 --end 2023-04-07 --dry-run
```

### `extract` — download pages to `cache/`

```
# A single day. --start and --end are both required, so one day is
# --start == --end.
python -m mlb_scraper extract --start 2023-04-01 --end 2023-04-01

# A range / historical backfill. Slow by design; safe to interrupt and re-run.
python -m mlb_scraper extract --start 2023-04-01 --end 2023-09-30

# Re-download pages already cached. Hours of real traffic; see below.
python -m mlb_scraper extract --start 2023-04-01 --end 2023-04-07 --force
```

This writes HTML to `cache/` and nothing else — run `transform` afterwards to
turn it into JSON.

Dates more recent than **yesterday (UTC)** are silently capped with a warning,
because games on those dates may still be in progress. Run this once the target
dates' games are over — overnight or the next morning is fine, mid-slate is not.

### `transform` — parse cached HTML into `data/`

```
# Everything downloaded but not yet parsed.
python -m mlb_scraper transform

# A specific range. Either bound can be omitted.
python -m mlb_scraper transform --start 2023-04-01 --end 2023-09-30

# Rebuild JSON that already exists, after a parser fix.
python -m mlb_scraper transform --start 2023-04-01 --end 2023-09-30 --force
```

This never touches the network, so it needs no `USER_AGENT` and costs nothing
but CPU — re-running it is always safe. Pages that were never downloaded are
skipped with a warning, leaving their existing records alone.

### `load` — push local JSON to the cloud

```
python -m mlb_scraper load --start 2023-04-01 --end 2023-04-01 --dry-run
python -m mlb_scraper load --start 2023-04-01 --end 2023-04-01
```

Only games already extracted to `data/` are considered; `load` never touches the
source site.

### `status` — progress counts from `state/status.json`

```
$ python -m mlb_scraper status --season 2023
Days (275 total)
  extract:   done 205, empty 70
  transform: done 205, empty 70
Games (2471 total)
  extract:   done 2471
  transform: done 2471
  upload:    done 2471

Pending: 0 to transform, 0 to upload
```

`empty` days are normal — most off-days genuinely have no games. The `Pending`
line is the one to read day to day: it counts games waiting on the next stage.
Omit `--season` for totals across every season on disk. Note that this reads
the whole checkpoint file, which grows to several MB after a large backfill.

### Flags, by command

| Flag | `extract` | `transform` | `load` | `status` |
|---|:-:|:-:|:-:|:-:|
| `--start YYYY-MM-DD` | required | optional | optional | — |
| `--end YYYY-MM-DD` | required | optional | optional | — |
| `--force` | ✓ | ✓ | ✓ | — |
| `--dry-run` | ✓ | ✓ | ✓ | — |
| `-v` / `--verbose` | ✓ | ✓ | ✓ | — |
| `--provider {s3,azure}` | — | — | ✓ | — |
| `--season YYYY` | — | — | — | ✓ |

`extract` requires its dates — there is no "pending" set for a stage whose
input is the internet. `transform` and `load` default to everything pending for
their stage, and each bound is an independent filter, so `--start` alone means
"from there on". `status` takes **only** `--season`.

`--force` means the same thing everywhere — *redo this stage's work* — but the
three stages cost very different amounts:

- **`transform --force`** is cheap. It rebuilds JSON from pages already on
  disk, touches no network, and is what to run after fixing a parser. Reach for
  this one first.
- **`extract --force`** re-downloads pages the project already has, paying the
  full 5s-plus-jitter for each. A season is hours of real traffic to
  Baseball-Reference. It is for when you believe the *cached page itself* is
  wrong — which, for a completed box score, is rare.
- **`load --force`** re-uploads games already marked uploaded, overwriting
  those objects in your bucket. Without it, `load` skips anything already
  uploaded.

`--help` on any command gives the full reference, e.g.
`python -m mlb_scraper extract --help`.

## Project layout

```
sports-data-gen/
├── config.py                  # Project-wide constants, plus all of .env.
│                              #   Lives at the repo root; modules `import config`
│                              #   directly, which is why commands run from here.
├── requirements.txt           # Runtime deps: requests, beautifulsoup4, lxml,
│                              #   python-dotenv, boto3.
├── requirements-dev.txt       # The above plus pytest.
├── pytest.ini                 # Points pytest at tests/.
├── .env.example               # Committed template. Copy to .env and fill in.
├── .env                       # Your real values. Gitignored, never committed.
├── CLAUDE.md                  # Instructions for AI agents working in this repo.
├── LICENSE                    # MIT. Covers the code only, not scraped data.
├── sports-data-gen.code-workspace
│                              #   Open this, not the folder, in VS Code.
│
├── mlb_scraper/               # The application package.
│   ├── __main__.py            #   Entry point for `python -m mlb_scraper`.
│   ├── cli.py                 #   argparse: extract / transform / load /
│   │                          #     status, the SAFE_LAG_DAYS cap, and the
│   │                          #     per-stage status report.
│   ├── stages/                #   One module per pipeline stage.
│   │   ├── extract.py         #     The website -> cache/. Downloads only.
│   │   ├── transform.py       #     cache/ -> data/. Parses only, offline.
│   │   └── load.py            #     data/ -> a bucket. Uploads only.
│   ├── cache.py               #   The HTML cache: paths, reads, and the
│   │                          #     boundary between extract and transform.
│   ├── http_client.py         #   Every network request goes through here:
│   │                          #     disk cache, rate limit, retries, backoff.
│   ├── schedule.py            #   Parses a day's schedule index into refs.
│   ├── boxscore.py            #   Parses a box score page into a GameRecord.
│   ├── details_parser.py      #   Unpacks the packed "details" cell into
│   │                          #     2B/3B/HR/SB counts.
│   ├── postseason.py          #   Reads a season's postseason game IDs from the
│   │                          #     season schedule page.
│   ├── models.py              #   The dataclasses: BoxscoreRef, BattingLine,
│   │                          #     PitchingLine, GameRecord.
│   ├── storage.py             #   Writes a GameRecord as the two JSON files.
│   ├── state.py               #   Loads and saves state/status.json.
│   ├── logging_config.py      #   Console + file logging setup.
│   └── cloud/                 #   Upload backends behind one interface.
│       ├── __init__.py        #     get_uploader(); supported providers.
│       ├── base.py            #     Abstract CloudUploader.upload_file().
│       └── s3.py              #     The boto3 S3 implementation.
│
├── tests/                     # Golden-file regression suite. No network,
│                              #   no writes to data/ or cache/.
│   ├── conftest.py            #   Skip helper for the gitignored HTML fixtures.
│   ├── refresh_fixtures.py    #   Rebuilds those from cache/ or the web.
│   └── fixtures/              #   Golden JSON (committed) + captured HTML pages
│                              #     (gitignored; see Testing).
│
├── .vscode/                   # Checked-in launch, task and interpreter settings.
│                              #   Every path goes through ${workspaceFolder}.
│
├── cache/                     # extract's output: raw HTML. Gitignored.
├── data/                      # transform's output: the JSON. Gitignored.
├── state/                     # status.json, per-stage checkpoints. Gitignored.
└── logs/                      # scraper.log, truncated every run. Gitignored.
```

The four gitignored directories at the bottom are created on demand and each
keep a `.gitkeep`; see [Output layout](#output-layout) for what goes in them.

## Output layout

The layout is sport-scoped, so another sport can reuse the same storage and
load code. Each tree is one stage's output:

```
cache/mlb/{season}/{date}/schedule.html    # extract: that day's games
cache/mlb/{season}/{date}/{game_id}.html   # extract: one box score
cache/mlb/{season}/season_schedule.html    # extract: re-fetched every run,
                                           #   see Postseason tagging

data/mlb/{season}/{date}/hitting/hitting_{game_id}.json      # transform
data/mlb/{season}/{date}/pitching/pitching_{game_id}.json    # transform

state/status.json                          # all three: per-stage day and game
                                           #   status, is_postseason, paths
logs/scraper.log                           # truncated on every run
```

`cache/` is roughly ten times the size of `data/` — four seasons is about 4 GB
of HTML against 400 MB of JSON. It is the expensive thing this project owns,
which is why `transform` reads it rather than re-downloading.

`load` mirrors `data/` into the bucket 1:1, minus the local `data/` root:

```
s3://{S3_BUCKET}/mlb/{season}/{date}/hitting|pitching/...
```

A hitting file looks like this — abridged, since each batter carries about
thirty stat keys:

```json
{
  "sport": "mlb",
  "game_id": "CHN202608050",
  "date": "2026-08-05",
  "season": 2026,
  "home_team": "CHC",
  "away_team": "LAD",
  "game_seq": 0,
  "source_url": "https://www.baseball-reference.com/boxes/CHN/CHN202608050.shtml",
  "scraped_at": "2026-08-07T15:59:16Z",
  "batting": [
    {
      "player_id": "ohtansh01",
      "player_name": "Shohei Ohtani",
      "team": "LAD",
      "position": "DH",
      "stats": { "AB": 5, "R": 2, "H": 3, "RBI": 3, "BB": 0, "SO": 2, "HR": 2 }
    }
  ]
}
```

## Design notes

### Why three stages

The CLI is ETL-shaped and the commands are named for what they do to the data,
so the pipeline reads off the command line: `extract` pulls from the
**source** into `cache/`, `transform` turns that into records in `data/`, and
`load` pushes to the **destination**.

Parsing HTML is how records get out of the source in the first place, not a
reshaping of already-extracted data — so it could reasonably live inside
`extract`. It doesn't, because that is the only property the two share:

- **Cost.** A season of downloading is hours of rate-limited requests against
  someone else's server. Parsing the same season is minutes of local CPU.
- **Failure modes.** Downloads fail from timeouts, 429s and fallback pages.
  Parsing fails from a table id that changed shape. Neither retry strategy
  helps the other.
- **Reasons to redo.** You re-parse whenever you fix a parser, which is often.
  You re-download only when you believe the captured page itself is wrong,
  which is almost never for a completed box score.

Separate commands give each stage its own `--force` and its own entry in
`state/status.json`, so redoing one never implies redoing another, and a date
can sit extracted but not yet transformed.

A further transform — season aggregates, a warehouse-shaped rewrite — would
slot in after this one as a fourth command reading `data/` and writing `data/`,
touching neither the network nor the bucket.

### Postseason tagging

Every game record is tagged `is_postseason`, resolved once per season from
`/leagues/majors/{year}-schedule.shtml`'s own "Postseason Schedule" section
rather than guessed from the date. That one page is re-fetched on every
`extract` run instead of being cached forever — the only page this scraper
re-fetches without being asked to — because, unlike a completed box score, a
season's schedule keeps growing until that postseason is over. `transform` reads
whatever copy that left on disk, which is what keeps it network-free.

## Testing

```
pip install -r requirements-dev.txt
pytest
```

Tests are golden-file regressions: real cached HTML goes in, hand-reviewed JSON
comes out, and each run checks that the parsers still produce that same
known-good output. No network calls, no writes to `data/` or `cache/`.

**On a fresh clone, some tests skip** — that is expected. The large HTML
fixtures are verbatim Baseball-Reference pages, so they are gitignored rather
than redistributed here; only the golden JSON and two small hand-written
fixtures are committed. To fill in the rest:

```
python tests/refresh_fixtures.py
```

That copies from your local `cache/` when the pages are already there (instant,
no network), and otherwise fetches the four pages through the project's normal
rate-limited client — which means `USER_AGENT` must be set in `.env` before
that fallback can fetch anything. `pytest` then runs the full suite; the suite
itself makes no network calls and needs no configuration.

One consequence of rebuilding fixtures rather than pinning them: the
win-probability columns (`wpa_*`, `re24_*`, `cwpa_*`, `leverage_index_avg`,
`cli_avg`) are Baseball-Reference model outputs, not counted events, and they
get recomputed upstream — re-fetching a box score a year on returns the same
players and the same counting stats with those values nudged a unit or two in
their last decimal place. `tests/test_boxscore.py` therefore compares them
within a per-column tolerance instead of exactly. Everything else is still an
exact match.

## VS Code

Open `sports-data-gen.code-workspace` rather than the folder, to pick up the
checked-in settings automatically. `.vscode/settings.json` points the Python
extension at `.venv` and auto-activates it in new terminals;
`.vscode/launch.json` (F5) and `.vscode/tasks.json` both run
`python -m mlb_scraper` and prompt for just the arguments, defaulting to a
single-day dry run. Every path goes through `${workspaceFolder}`, so nothing is
machine-specific.

## License

MIT — see [LICENSE](LICENSE). That covers the code only, not any data you scrape
with it; see [Data source and terms](#data-source-and-terms).
