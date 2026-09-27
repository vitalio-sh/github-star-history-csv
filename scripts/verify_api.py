#!/usr/bin/env python3
"""Bounded, anonymous verification of public history; saves only aggregate data."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import star_history as sh

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'vitalio-sh/chatgpt-3.5-turbo'


class RecordingClient(sh.GitHubClient):
    def __init__(self):
        super().__init__(timeout=20)  # Deliberately anonymous, including when a token is set.
        self.pages = []

    def get(self, url):
        data, headers = super().get(url)
        self.pages.append({'url': url, 'status': 200,
                           'headers': {key: headers[key] for key in ('Date', 'Link', 'X-RateLimit-Limit', 'X-RateLimit-Remaining') if key in headers},
                           'data': data})
        return data, headers


def main():
    client = RecordingClient()
    rows, pages = sh.fetch_history(REPOSITORY, client, max_pages=10)
    metadata, _ = sh.GitHubClient(timeout=20).get(sh.API_ROOT + '/repos/' + REPOSITORY)
    candidate_url = sh.API_ROOT + '/repos/vitalio-sh/github-star-history-csv'
    try:
        sh.GitHubClient(timeout=20).get(candidate_url)
        candidate_status = 200
    except sh.ExportError as error:
        if not str(error).startswith('HTTP 404:'):
            raise
        candidate_status = 404
    evidence = {'verified_at': datetime.now(timezone.utc).isoformat(),
                'authentication': 'none', 'api_version': sh.API_VERSION,
                'repository': REPOSITORY, 'created_at': metadata['created_at'],
                'current_stars_observed_for_comparison_only': metadata['stargazers_count'],
                'csv_columns': list(sh.CSV_COLUMNS),
                'history_pages': pages, 'weeks': len(rows), 'first_row': rows[0] if rows else None,
                'last_row': rows[-1] if rows else None,
                'candidate_repository_check': {'url': candidate_url, 'status': candidate_status,
                                               'caveat': 'An anonymous 404 does not prove the name is available; a private repository may exist.'},
                'responses': client.pages}
    output = ROOT / 'docs' / 'api-evidence.json'
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print('Saved anonymous API evidence: {} weeks, {} history pages.'.format(len(rows), pages))


if __name__ == '__main__':
    try:
        main()
    except (sh.ExportError, OSError) as error:
        print('Verification failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
