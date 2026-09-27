#!/usr/bin/env python3
"""Build a local source ZIP from an explicit allowlist; never publishes anything."""
import hashlib
from pathlib import Path
import sys
import zipfile

from check_release import ROOT, check


def main():
    check()
    top_level = ['star_history.py', 'README.md', 'LICENSE', 'RELEASE.md', 'CONTRIBUTING.md', '.gitignore', '.gitattributes']
    files = [ROOT / name for name in top_level]
    for directory, suffixes in (('tests', {'.py'}), ('scripts', {'.py'}),
                               ('examples', {'.csv', '.py', '.md'}),
                               ('docs', {'.md', '.json', '.svg', '.txt', '.png'}),
                               ('.github', {'.md', '.yml'})):
        files.extend(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and path.suffix in suffixes and '__pycache__' not in path.parts)
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    archive = destination / 'github-star-history-csv-v0.1.0.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            name = 'github-star-history-csv/' + path.relative_to(ROOT).as_posix()
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 27, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, path.read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination / 'SHA256SUMS').write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
    print('Created {} ({} files) and SHA256SUMS.'.format(archive.name, len(files)))


if __name__ == '__main__':
    main()
