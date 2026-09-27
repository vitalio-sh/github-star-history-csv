#!/usr/bin/env python3
"""Create the terminal SVG, CSV and transcript from an actual anonymous CLI run."""
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'vitalio-sh/chatgpt-3.5-turbo'
COMMAND = ['python3', 'star_history.py', REPOSITORY, '--output', 'stars.csv']


def terminal_svg(lines, captured_at):
    text = []
    y = 88
    for line in lines:
        color = '#75e6bf' if line.startswith('$') else '#e8edf5'
        if line.startswith('Exported'):
            color = '#9baac1'
        text.append('<text x="28" y="{}" fill="{}">{}</text>'.format(y, color, escape(line)))
        y += 26
    height = y + 10
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="{height}" viewBox="0 0 1160 {height}" role="img" aria-labelledby="title desc">
<title id="title">GitHub star history to CSV: real CLI run</title>
<desc id="desc">{description}</desc>
<rect width="1160" height="{height}" rx="14" fill="#0d1422"/>
<path d="M14 0h1132a14 14 0 0 1 14 14v38H0V14A14 14 0 0 1 14 0" fill="#182234"/>
<circle cx="28" cy="27" r="5" fill="#fa7a7a"/>
<circle cx="46" cy="27" r="5" fill="#e8bf67"/>
<circle cx="64" cy="27" r="5" fill="#6ed5a5"/>
<text x="88" y="33" font-family="system-ui, sans-serif" font-size="18" fill="#e8edf5">GitHub Star History CSV</text>
<text x="1132" y="33" text-anchor="end" font-family="system-ui, sans-serif" font-size="16" fill="#9baac1">LIVE API · {date}</text>
<g font-family="Menlo, Consolas, monospace" font-size="20">{text}</g>
</svg>
'''.format(height=height, description=escape('\n'.join(lines)), date=captured_at[:10], text='\n'.join(text))


def main():
    environment = os.environ.copy()
    environment.pop('GITHUB_TOKEN', None)
    environment.pop('GH_TOKEN', None)
    with tempfile.TemporaryDirectory(prefix='star-history-demo-') as directory:
        shutil.copy2(ROOT / 'star_history.py', directory)
        result = subprocess.run([sys.executable] + COMMAND[1:], cwd=directory,
                                env=environment, capture_output=True, text=True, timeout=240)
        if result.returncode:
            print(result.stderr, file=sys.stderr, end='')
            return result.returncode
        if result.stdout:
            raise RuntimeError('File export unexpectedly wrote to stdout')
        csv_bytes = (Path(directory) / 'stars.csv').read_bytes()
        head = subprocess.run(['head', '-n', '4', 'stars.csv'], cwd=directory,
                              capture_output=True, text=True, check=True).stdout
    captured_at = datetime.now(timezone.utc).isoformat()
    command_text = '$ ' + ' '.join(COMMAND)
    transcript = command_text + '\n' + result.stderr + '\n$ head -n 4 stars.csv\n' + head
    visual_lines = [command_text] + result.stderr.rstrip().splitlines() + ['$ head -n 4 stars.csv'] + head.rstrip().splitlines()
    (ROOT / 'examples' / 'stars.csv').write_bytes(csv_bytes)
    (ROOT / 'docs' / 'demo.txt').write_text(transcript, encoding='utf-8')
    (ROOT / 'docs' / 'demo.svg').write_text(terminal_svg(visual_lines, captured_at), encoding='utf-8')
    manifest = {'captured_at': captured_at, 'repository': REPOSITORY, 'authentication': 'none',
                'command': COMMAND, 'python_version': sys.version.split()[0],
                'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
                'csv_sha256': hashlib.sha256(csv_bytes).hexdigest(),
                'csv_rows': len(csv_bytes.decode().splitlines()) - 1, 'preview_lines': 4,
                'source': 'Actual network CLI execution from an isolated temporary directory; not test fixtures.'}
    (ROOT / 'docs' / 'demo-run.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(transcript, end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
