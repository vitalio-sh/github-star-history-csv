# GitHub star-history API verification

Verified **2026-09-27, 18:43 UTC**, anonymously against GitHub.com. No token was
used, displayed or saved. The endpoint is usable for the intended public export.

## Official sources

- [September 4 announcement](https://github.blog/changelog/2026-09-04-new-api-endpoint-provides-privacy-safe-star-history-data/)
- [Get repository star history](https://docs.github.com/en/rest/activity/starring?apiVersion=2026-03-10#get-repository-star-history)
- [REST pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)
- [REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

The implementation uses the documented path, not a guessed endpoint or the
current-count endpoint.

## Live requests and observations

The initial request was:

```text
GET https://api.github.com/repos/vitalio-sh/chatgpt-3.5-turbo/stargazers/history?per_page=30&page=1
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2026-03-10
```

It returned **200** and an array of weekly objects. A non-personal aggregate
object from the oldest page is reproduced unchanged:

```json
{"week": 1677369600, "total": 36, "days": [0, 0, 0, 10, 15, 4, 7]}
```

The first response's `Link` pointed to the numeric repository URL:

```text
<https://api.github.com/repositories/608376199/stargazers/history?per_page=30&page=2>; rel="next"
```

All seven history pages returned 200: six pages of 30 weeks, then eight weeks.
The final page had `prev` and `first`, and no `next`. Every observed `total`
equalled the sum of the seven `days`; buckets were newest first and contained
explicit zero weeks. There were no duplicate or missing weeks.

| Check | Observed result |
| --- | --- |
| Public access without credentials | Successful |
| Oldest bucket | `2023-02-26T00:00:00Z` |
| Repository creation (separate metadata request) | `2023-03-01T22:18:36Z`, inside that first bucket |
| Newest bucket | `2026-09-27T00:00:00Z` |
| Total buckets | 188 |
| Sum of history totals | 165 |
| Current metadata star count, comparison only | 165; never used to build the CSV |
| Anonymous rate-limit ceiling reported by headers | 60 |
| Candidate repository name lookup | Anonymous 404; does not exclude a private repository |

The [saved evidence](api-evidence.json) contains request URLs, selected response
headers and the actual aggregate history payloads. It excludes the full
repository metadata, credentials and user identities. The independent
[demo capture](demo-run.json) executed the CLI in an isolated directory and
produced [examples/stars.csv](../examples/stars.csv).

## Contract and interpretation

Official docs specify weekly buckets, Sunday-first daily counts, at most 30
buckets per page, and page numbers up to 100. Public resources can be queried
without credentials; fine-grained access uses Metadata: read. GitHub does not
guarantee UTC calendar boundaries. The code preserves each supplied week instant
in UTC notation and emits one cumulative sum per bucket, inclusive of that week.

The CSV's `stars_cumulative` is a derived running sum, **not an API-provided cumulative
field**. `week_start` is a bucket label, not the measurement time of that sum.
The creation-week example demonstrates why the distinction matters.
`stars_added` preserves the API’s `total` for each week without differencing or
inferring a net change after unstars.

## What this verification does not establish

- Private repository, organization authorization, and authenticated token access
  were not tested. Rights above come from official documentation.
- Page 100 and repositories with 3,000 weeks were not exercised live. These bounds
  are documented; stopping without partial output is covered offline.
- No controlled star/unstar experiment was performed. Equal totals in one
  snapshot do not establish historical unstar behavior. The tool makes no claim
  of reconstructing the exact historical active-star balance.
- Non-UTC boundaries, DST changes, API mutations during pagination, 403 and 429
  were not induced live. Offline tests cover defensive behavior. A public 404
  was observed in the candidate-name lookup.
- This API verification preceded publication; it does not establish remote CI
  status. See the repository’s Actions page for workflow results.

## Reproduce

```sh
python3 scripts/verify_api.py
python3 scripts/record_demo.py
python3 scripts/check_release.py
```

The verifier makes at most 10 history requests and two metadata/name requests,
without retries or authentication. It fails rather than saving incomplete
history. This example currently uses nine requests. The demo currently uses
seven more. Refresh snapshot-specific prose when regenerating evidence.
