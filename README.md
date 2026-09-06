# tendobros-apps

A monorepo holding two independent Python projects.

| Project | What it is | Docs |
|---|---|---|
| [`sports-data-gen`](sports-data-gen/) | MLB data scraper with a three-stage ETL pipeline — `extract` downloads pages, `transform` parses them to JSON, `load` pushes to S3. Each stage checkpoints separately. | [`sports-data-gen/README.md`](sports-data-gen/README.md) |
| [`job-scanner`](job-scanner/) | A daily job scan that sweeps 97 company career sites plus an Indeed search, diffs against a tracker, and reports genuinely new postings. | [`job-scanner/README.md`](job-scanner/README.md) |

## They are independent

They share a repository and nothing else. Each project has its own virtualenv, its own
`requirements.txt`, its own `.gitignore` and its own `CLAUDE.md`; neither imports the
other, and there is no shared build tooling, test runner or dependency manifest.

**Work inside a project's own directory.** Both projects resolve paths relative to their
own root and expect their own `.venv` interpreter — see that project's `README.md` for
setup and usage. Nothing here is a substitute for reading it.

The repository root carries only this file, a `.gitattributes` that normalizes line
endings, and a `.gitignore` that acts as a safety net for projects added later. Each
project's own `.gitignore` is authoritative for that project.
