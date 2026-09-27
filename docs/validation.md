# Release validation

Completed locally on **2026-09-27**, including the pre-publication README and CSV polish pass. This section records the checks performed before publication.
Remote workflow runs are tracked in [GitHub Actions](https://github.com/vitalio-sh/github-star-history-csv/actions/workflows/ci.yml).

## Automated checks

| Check | Result |
| --- | --- |
| Python 3.9.6, macOS arm64 | 50 offline tests passed |
| Python 3.10.16, macOS arm64 | 50 offline tests passed |
| Python 3.13.2, macOS arm64 | 50 offline tests passed |
| Release consistency check on all three runtimes | Passed |
| Python compilation | Passed for exporter, scripts and tests |
| Optional pandas 3.0.6 on Python 3.13.2 | Parsed all 188 example rows and timezone-aware timestamps |
| CLI help and invalid argument exit codes | Passed |
| GitHub workflow configuration | Compact offline-only matrix for Python 3.9 and 3.13; remote results are tracked in Actions |

The offline suite exercises pagination (including numeric repository URLs),
chronology, cumulative totals, direct weekly additions, explicit zeros, empty/missing/malformed data,
non-UTC timestamps, gaps, duplicate/overlapping pages, page limits, 401/403/404/
422/429/500, rate-limit hints, JSON errors, timeouts and network failures,
credential-safe diagnostics, refused redirects, stdout separation, overwrite
protection, disk failures, output races, and symlink replacement.

## New-user walkthrough

A fresh temporary copy contained only source and release files: no virtual
environment, user-site packages, tokens, or developer output. Its PATH contained
only system binary directories. With system Python 3.9.6, the following all
behaved as documented:

1. `python3 star_history.py --help` → exit 0.
2. `python3 -m unittest discover -s tests -q` → 50 passed.
3. `python3 scripts/check_release.py` → passed.
4. `python3 star_history.py vitalio-sh/chatgpt-3.5-turbo --output stars.csv` →
   exit 0; 188 rows from seven actual API pages; no stdout; bytes matched the
   saved example exactly. The header was `week_start,stars_cumulative,stars_added`;
   the sum of weekly additions matched the final cumulative value (165).
5. Repeating that command → exit 1 and original CSV unchanged.
6. Export with `--max-pages 1` → exit 1 and no output file.
7. Request for a deliberately nonexistent repository → HTTP 404, exit 1,
   and no output file.

The two failure cases used one request each. All live requests were anonymous.
The [clean-copy transcript](clean-run.json) records commands and safe outputs.
The release ZIP is also extracted into a temporary directory and checked
independently before delivery.

## Demo and documentation QA

- The [terminal SVG](demo.svg) comes from an actual CLI subprocess in an isolated
  directory; [capture provenance](demo-run.json) includes its CSV hash. The raw
  API evidence was obtained independently and reproduces every CSV row.
- `scripts/check_release.py` verifies local Markdown file links, scans publishable
  text for common GitHub token formats and machine-specific paths, compares the
  complete CSV against API buckets, and checks the transcript, README sample and
  SVG for consistency with the capture. This scan is a basic safeguard, not a
  general secret-detection guarantee.
- The README was rendered from its Markdown and visually inspected in the
  browser at its default viewport. The terminal command and CSV rows are readable,
  the smaller image loads, and the benefits line, Python requirement, and all three
  Quickstart commands (clone, cd, export) fit in the first screen. [First-screen preview](readme-preview.png) is a local render,
  not a screenshot of a published GitHub repository.
- The README's `#csv-contract` link matches its heading. Demo source, CSV,
  verification, release and license links resolve locally.
- GitHub CLI publication flags were checked against the installed command help.
  Publication commands were not executed during that local preparation pass.

## Pre-publication changes

The original local two-column draft was replaced with
`week_start,stars_cumulative,stars_added`. Tests, the pandas example, live demo,
API evidence, clean-copy transcript and release notes were refreshed together.
The schema change preceded the first public release, v0.1.0.
Detailed options and API notes now live in [usage.md](usage.md).

## Remaining boundaries

Private/token-authenticated repositories, Windows and GitHub Enterprise Server
have not been tested live. The API does not establish exact historical unstar
balances or immutable snapshots. Live quota-exhaustion errors were simulated in
unit tests rather than induced. See the Actions link above for remote CI status;
local test results alone do not establish that a remote workflow succeeded.
