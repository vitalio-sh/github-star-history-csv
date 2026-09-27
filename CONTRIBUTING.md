# Contributing

Keep the project focused on one task: repository history in, CSV out.
The CLI and offline tests use only Python's standard library (3.9+).

Run `python3 -m unittest discover -s tests -v` and
`python3 scripts/check_release.py` before proposing a change.
Use controlled responses in tests, and label synthetic data clearly.
Do not fetch live GitHub data in CI. Document API behavior with official links
and record a separate, bounded live check when changing the integration.

Never include tokens, Authorization headers, or private repository data in
issues, fixtures, demo artifacts or commits. API error text should remain
curated and credential-free. Changes to the CSV schema need explicit release
notes because consumers may depend on its column names and order.
