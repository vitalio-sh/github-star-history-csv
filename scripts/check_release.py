#!/usr/bin/env python3
"""Offline validation of release links, live-demo provenance and export fidelity."""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import star_history as sh


def release_files():
    excluded = {'.git', '.venv', '__pycache__', 'dist'}
    return sorted(path for path in ROOT.rglob('*') if path.is_file()
                  and not any(part in excluded for part in path.relative_to(ROOT).parts)
                  and path.name != '.DS_Store' and path.suffix != '.pyc')


def check():
    required = ['star_history.py', 'README.md', 'LICENSE', 'RELEASE.md', 'CONTRIBUTING.md',
                '.gitignore', '.github/workflows/ci.yml', 'examples/stars.csv',
                'docs/api-verification.md', 'docs/api-evidence.json', 'docs/demo.svg',
                'docs/demo.txt', 'docs/demo-run.json', 'docs/validation.md', 'docs/release-notes-v0.1.0.md']
    for name in required:
        if not (ROOT / name).is_file():
            raise ValueError('Required release file missing: ' + name)
    for path in release_files():
        if path.name == '.env' or path.name.startswith('.env.'):
            raise ValueError('Environment file in release: ' + str(path.relative_to(ROOT)))
        if path.suffix == '.png':
            continue
        text = path.read_text(encoding='utf-8')
        secret_pattern = r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_' + r'pat_[A-Za-z0-9_]{20,})'
        machine_pattern = '/' + r'(?:Users|home)/[A-Za-z0-9_.-]+/'
        if re.search(secret_pattern, text) or re.search(machine_pattern, text):
            raise ValueError('Possible secret or machine-specific path: ' + str(path.relative_to(ROOT)))
        if path.suffix == '.md':
            for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text):
                target = urlsplit(link)
                if not target.scheme and target.path:
                    destination = (path.parent / unquote(target.path)).resolve()
                    if ROOT not in destination.parents or not destination.exists():
                        raise ValueError('Broken local link in {}: {}'.format(path.name, link))
    csv_bytes = (ROOT / 'examples/stars.csv').read_bytes()
    evidence = json.loads((ROOT / 'docs/api-evidence.json').read_text())
    manifest = json.loads((ROOT / 'docs/demo-run.json').read_text())
    if manifest['authentication'] != 'none' or manifest['exit_code'] != 0 or manifest['stdout']:
        raise ValueError('Demo is not a successful anonymous file export')
    if hashlib.sha256(csv_bytes).hexdigest() != manifest['csv_sha256']:
        raise ValueError('Demo CSV hash differs from capture')
    csv_rows = list(csv.reader(io.StringIO(csv_bytes.decode('utf-8'))))
    if csv_rows[0] != list(sh.CSV_COLUMNS) or len(csv_rows)-1 != manifest['csv_rows']:
        raise ValueError('Demo CSV schema or row count differs from capture')
    buckets = {}
    for response in evidence['responses']:
        if response['status'] != 200:
            raise ValueError('Evidence contains an unsuccessful response')
        for bucket in response['data']:
            week, total = sh.validate_bucket(bucket)
            if week in buckets:
                raise ValueError('Evidence has duplicate weeks')
            buckets[week] = total
    expected = [[str(value) for value in row] for row in sh.cumulative_rows(buckets)]
    if csv_rows[1:] != expected:
        raise ValueError('Demo CSV differs from preserved live API evidence; refresh both captures')
    transcript = (ROOT / 'docs/demo.txt').read_text()
    preview_lines = manifest['preview_lines']
    expected_transcript = '$ ' + ' '.join(manifest['command']) + '\n' + manifest['stderr'] + '\n$ head -n {} stars.csv\n'.format(preview_lines) + '\n'.join(csv_bytes.decode().splitlines()[:preview_lines]) + '\n'
    if transcript != expected_transcript:
        raise ValueError('Demo transcript differs from capture')
    svg = ET.parse(ROOT / 'docs/demo.svg').getroot()
    svg_text = ''.join(svg.itertext())
    for line in csv_bytes.decode().splitlines()[:preview_lines]:
        if line not in svg_text:
            raise ValueError('Demo SVG omits a displayed CSV row')
    readme = (ROOT / 'README.md').read_text()
    if manifest['stderr'].strip() not in readme:
        raise ValueError('README output differs from capture')
    for line in csv_bytes.decode().splitlines()[:preview_lines]:
        if line not in readme:
            raise ValueError('README sample differs from capture')
    print('Release checks passed: local links, secret/path scan, API-to-CSV fidelity, demo provenance, README sample.')


if __name__ == '__main__':
    try:
        check()
    except (ValueError, OSError, KeyError, sh.ExportError) as error:
        print('Release check failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
