# Usage and API details

Run these commands from the project root. Start with the [Quickstart](../README.md#quickstart).

## Examples

Export another repository (one request per 30 weeks of history):

```sh
python3 star_history.py octocat/Hello-World --output hello-world.csv
```

Write CSV to standard output explicitly; diagnostics still go to standard error:

```sh
python3 star_history.py vitalio-sh/chatgpt-3.5-turbo --output -
```

Replace an existing file only when you intend to:

```sh
python3 star_history.py vitalio-sh/chatgpt-3.5-turbo --output stars.csv --force
```

Bound the number of requests and the socket timeout:

```sh
python3 star_history.py vitalio-sh/chatgpt-3.5-turbo --output stars.csv --max-pages 10 --timeout 15
```

If more pages are needed, the command fails instead of saving a partial series. All pages are collected and validated before any CSV is emitted. File output uses a temporary sibling file and atomic publication; failure leaves an existing file untouched. `--output -` is buffered until the API succeeds, but a failed downstream pipe cannot be rolled back. Prefer `--output PATH` for file safety rather than shell redirection.

### Open in a spreadsheet or pandas

Import [examples/stars.csv](../examples/stars.csv) in Excel or Google Sheets as a comma-delimited UTF-8 file. In locales where Excel expects semicolons, use **Data → From Text/CSV** and select comma. Keep `week_start` as text if the spreadsheet does not recognize ISO 8601.

If you already use pandas (optional; it is not an exporter dependency):

```python
import pandas as pd

stars = pd.read_csv("examples/stars.csv", parse_dates=["week_start"])
print(stars.head())
```

A ready-to-run version is in [examples/read_with_pandas.py](../examples/read_with_pandas.py).

## CSV contract

| Column | Meaning |
| --- | --- |
| `week_start` | GitHub's `week` Unix timestamp rendered as ISO 8601 in UTC. It labels the **start of the API bucket**, not the moment a cumulative count was measured. |
| `stars_cumulative` | Running sum of the API's weekly `total` values, oldest first, **including that entire bucket** (or its available portion for the current week). |
| `stars_added` | GitHub’s weekly `total` for this bucket, used directly. It is not a measured net change after unstars. |

For the first example row, `36` includes all stars reported in the week labelled `2023-02-26`, even though the repository was created on March 1. It does not mean there were 36 stars at midnight on February 26.

Column order is `week_start,stars_cumulative,stars_added`. The file has one row per returned week, a header, a comma delimiter, UTF-8 encoding without a BOM, and LF newlines. Explicit zero weeks are retained. Missing weeks, malformed counts, duplicate weeks, and inconsistent daily totals cause an error. An empty API array produces a header-only CSV and a warning; it does not imply zero stars.

## Authentication and access

Public history works anonymously. If you need a higher rate allowance or access to a private repository, set `GITHUB_TOKEN` in your environment. The CLI reads only that variable; it does not discover credentials from GitHub CLI or a browser.

The [official endpoint documentation](https://docs.github.com/en/rest/activity/starring?apiVersion=2026-03-10#get-repository-star-history) specifies **Metadata: read** for fine-grained tokens. Give the token access to the selected repository and any required organization authorization. GitHub App user and installation tokens are also documented. Public access with a token was verified during publication checks; private repository access has not been tested.

To enter a token without putting its value in shell history, use this Bash/Zsh snippet:

```sh
printf 'GitHub token: '
stty -echo
read -r GITHUB_TOKEN
stty echo
printf '\n'
export GITHUB_TOKEN
python3 star_history.py owner/repo --output stars.csv
unset GITHUB_TOKEN
```

Replace `owner/repo` with the repository you can access. Restore terminal echo with `stty echo` if you interrupt the prompt. Never paste tokens into issues or commit them. The exporter does not log tokens, authorization headers, or API error bodies. Redirects are refused; use a repository's current name if it moved.

## History and API limits

This is a small GitHub star history API Python example that also works as a standalone exporter. It uses `GET /repos/{owner}/{repo}/stargazers/history` with API version `2026-03-10`, without fetching stargazer identities.

- GitHub groups stars into weeks and returns newest weeks first. The CLI fetches every linked page, reverses the chronology, and sums weekly totals. It never substitutes the current repository star count.
- The documented limits are 30 weeks per page and page numbers up to 100: at most 3,000 weekly buckets. A remaining next page at the configured limit is an error. The live example reaches its creation week; this does not prove completeness for every repository.
- Week/day boundaries are **not guaranteed to align with UTC**. UTC formatting preserves the supplied instant; it does not turn GitHub's buckets into UTC calendar weeks. No daily or per-star event times are inferred.
- The newest week is still in progress. The endpoint does not document immutable snapshots or complete unstar semantics. The cumulative series is a sum of the currently returned buckets, not a verified historical net-star balance. Repeated exports may differ.
- GitHub's published baseline rate limits are 60 unauthenticated requests per hour per IP and typically 5,000 per hour for a user token; other token classes and secondary limits differ. See [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api). There are no automatic retries.
- GitHub.com is supported. Enterprise Server, caches, resumable downloads, and daily reconstruction are outside this tool's scope.

See [docs/api-verification.md](api-verification.md) for the tested contract, preserved live responses, and the boundary between observed and unverified behavior.

## Troubleshooting

| Result | What to do |
| --- | --- |
| Output already exists | Choose another path, or pass `--force`. |
| HTTP 401 | Check `GITHUB_TOKEN`; unset an invalid token for public access. |
| HTTP 404 | Check the repository name. Private repositories may appear missing without access. |
| HTTP 403 | Check access and Metadata: read; a secondary rate limit can also return 403. |
| HTTP 429 / exhausted rate quota | Wait for the indicated retry/reset time; use a token if appropriate. |
| HTTP 422 | Check endpoint availability and page limits; retry later if GitHub is throttling. |
| Redirect | Use the repository's current owner/name. Credentials are not forwarded. |
| Network request failed | Check connectivity, certificates and proxy settings, then retry. |
| Page limit or inconsistent history | Increase `--max-pages` up to 100, or retry after the API stabilizes. No partial CSV is saved. |
| Cannot write output | Check parent directory, permissions, disk space and filesystem support for atomic file links. |

`--help` documents all options. Exit codes: **0** success (including an empty history), **1** API/network/output failure, **2** invalid command arguments, **130** interruption.

## Development and verification

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

Tests are offline and use explicitly synthetic responses. The release check verifies local Markdown links, the CSV against the saved API evidence, the demo hash, and common secret/path mistakes. A [compact CI workflow](../.github/workflows/ci.yml) runs these checks without API credentials. No CI success badge is shown before a real workflow run.

To refresh the public API evidence and record a new **live** demo (uses network quota):

```sh
python3 scripts/verify_api.py
python3 scripts/record_demo.py
```

The verification script is bounded to 10 history pages plus two metadata/name checks. The demo runs the actual CLI in an isolated temporary directory, with tokens removed, and saves the CSV, transcript, SVG and provenance. Refresh the README's displayed snapshot if the data changes. See [release validation](validation.md) and [publication instructions](../RELEASE.md).
