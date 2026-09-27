# Release guide

Repository: [vitalio-sh/github-star-history-csv](https://github.com/vitalio-sh/github-star-history-csv)

[Releases](https://github.com/vitalio-sh/github-star-history-csv/releases) · [GitHub Actions](https://github.com/vitalio-sh/github-star-history-csv/actions/workflows/ci.yml) · [Validation report](docs/validation.md)

## GitHub presentation

- Name: **github-star-history-csv**
- About: **Export GitHub repository star history to CSV with one Python command. No dependencies; no token for public repos.**
- Topics (7): `github`, `star-history`, `csv`, `python`, `cli`, `data-export`, `github-api`
- License: MIT, vitalio-sh
- First tag/title: **v0.1.0 — GitHub star history to CSV**
- Release body: [docs/release-notes-v0.1.0.md](docs/release-notes-v0.1.0.md)
- Website field: empty; this is a CLI.

The name was checked while authenticated as `vitalio-sh` before repository creation.

## Demo and evidence

| File | Purpose |
| --- | --- |
| [docs/demo.svg](docs/demo.svg) | README terminal visual generated from a live run |
| [docs/demo.txt](docs/demo.txt) | Command, stderr, and CSV head as searchable text |
| [docs/demo-run.json](docs/demo-run.json) | Capture date, Python version, command and CSV SHA-256 |
| [examples/stars.csv](examples/stars.csv) | Complete real 188-week CSV |
| [examples/read_with_pandas.py](examples/read_with_pandas.py) | Optional analysis example |
| [docs/api-verification.md](docs/api-verification.md) | Observations, official docs, unverified limits |
| [docs/api-evidence.json](docs/api-evidence.json) | Actual anonymous aggregate API responses |
| [docs/validation.md](docs/validation.md) | Local and release checks |
| [docs/readme-preview.png](docs/readme-preview.png) | First screen from a local rendering of README |
| [docs/clean-run.json](docs/clean-run.json) | Fresh-copy command results |
| [docs/public-clone-run.json](docs/public-clone-run.json) | Published-repository clone and live export checks |

The terminal SVG renders a recorded command and output. No generated artwork or
third-party visual assets are included.

## Build and check release assets

From the project root:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/package_release.py
```

The last command creates `dist/github-star-history-csv-v0.1.0.zip` and
`dist/SHA256SUMS`. The ZIP uses an explicit file allowlist and excludes `.git`,
virtual environments, bytecode, generated user exports and environment files.

Extract the ZIP into a fresh directory, enter `github-star-history-csv`, then run:

```sh
python3 star_history.py --help
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 star_history.py vitalio-sh/chatgpt-3.5-turbo --output stars.csv
```

Network data can change. The source archive retains the captured example.

## Publishing procedure

The maintainer commands below publish GitHub releases. Use them for a new tag
only; inspect existing tags and releases before proceeding. For later versions,
update the code version, package name and release notes together.

1. Confirm the account, repository and clean checkout:

   ```sh
   gh auth status --active
   gh api user --jq .login
   gh repo view --json nameWithOwner,visibility
   git status --short
   ```

2. Push the reviewed commit and wait for its workflow to succeed:

   ```sh
   git push origin main
   gh run list --workflow ci.yml --limit 1
   gh run watch --exit-status
   ```

   Select the run for the intended release commit. Review README on GitHub and
   follow Quickstart from a fresh clone. Build and check the assets as above.

3. Tag that commit and create a draft release with its assets:

   ```sh
   git tag -a v0.1.0 -m "GitHub star history to CSV"
   git push origin v0.1.0
   gh release create v0.1.0 dist/github-star-history-csv-v0.1.0.zip dist/SHA256SUMS --verify-tag --draft --title "v0.1.0 — GitHub star history to CSV" --notes-file docs/release-notes-v0.1.0.md
   ```

4. Check the draft's notes and files, then publish:

   ```sh
   gh release view v0.1.0 --json isDraft,tagName,assets,url
   gh release edit v0.1.0 --draft=false
   ```

There is no PyPI package. Source archives and cloning are the supported
installation paths.
