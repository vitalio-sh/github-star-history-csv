# v0.1.0 — GitHub star history to CSV

Export a repository's weekly GitHub star history with one Python command:

```sh
python3 star_history.py vitalio-sh/chatgpt-3.5-turbo --output stars.csv
```

- Python 3.9+ with no runtime dependencies; public repositories need no token.
- Stable `week_start,stars_cumulative,stars_added` CSV with ascending week labels, cumulative API totals, and weekly additions.
- Pagination with explicit limits, socket timeouts, clear error codes, and optional `GITHUB_TOKEN`.
- Atomic file output, overwrite protection, and explicit `--output -` for pipelines.
- Offline tests and a real 188-week example, recorded anonymously on September 27, 2026.

`week_start` labels the start of a GitHub weekly bucket; `stars_cumulative` includes that
bucket. GitHub's bucket boundaries may differ from UTC calendar weeks. The
series does not claim to reproduce historical net counts after unstars.
Private/token access and Windows were not exercised in the local release check.

MIT licensed. See README for the API contract, examples, and troubleshooting.
